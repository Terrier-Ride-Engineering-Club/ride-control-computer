# PLC ↔ RCC UART Watchdog and Status Link for TREC's REC Ride Control Computer
# Made by Jackson Justus (jackjust@bu.edu)

import logging
import struct
import threading
import time
from typing import TYPE_CHECKING, Callable

import serial

if TYPE_CHECKING:
    from ride_control_computer.motor_controller.MotorController import MotorController

logger = logging.getLogger(__name__)


# ── Packet format constants ────────────────────────────────────────────────────
#
# RCC → PLC  (69 bytes = 67 payload + 2 CRC)
#   myCounter(H) yourCounter(H) statusBits(B)
#   m1Speed(i) m1Encoder(i) m1Current(h)
#   m2Speed(i) m2Encoder(i) m2Current(h)
#   voltage(H) mcStatus(I) mcTimeSinceUpdate(H)
#   m1CmdPos(i) m1CmdSpeed(i) m1CmdAccel(I) m1CmdDecel(I)
#   m2CmdPos(i) m2CmdSpeed(i) m2CmdAccel(I) m2CmdDecel(I)
#   rideState(B) limitSwitches(B) crc(H)
_TX_PAYLOAD_FMT = '<HHBiihiihHIHiiIIiiIIBB'
_TX_FMT         = _TX_PAYLOAD_FMT + 'H'   # with CRC appended
_TX_PAYLOAD_SIZE = struct.calcsize(_TX_PAYLOAD_FMT)   # 67
_TX_SIZE         = struct.calcsize(_TX_FMT)            # 69

# PLC → RCC  (10 bytes = 8 payload + 2 CRC)
#   myCounter(H) yourCounter(H) statusBits(B) reserved(B) reserved(H) crc(H)
_RX_PAYLOAD_FMT = '<HHBBH'
_RX_FMT         = _RX_PAYLOAD_FMT + 'H'
_RX_PAYLOAD_SIZE = struct.calcsize(_RX_PAYLOAD_FMT)   # 8
_RX_SIZE         = struct.calcsize(_RX_FMT)            # 10

assert _TX_SIZE == 69, f"TX packet size mismatch: {_TX_SIZE}"
assert _RX_SIZE == 10, f"RX packet size mismatch: {_RX_SIZE}"

# RCC status byte bit masks
_BIT_ESTOP  = 0x01   # bit 0: E-Stop active
_BIT_IM_OK  = 0x02   # bit 1: RCC is healthy
_BIT_ESTOP2 = 0x80   # bit 7: E-Stop duplicate

# PLC status byte bit masks (Rev 2026-03-26)
_PLC_BIT_ESTOP_RELEASED   = 0x01   # bit 0: PLC E-stop gate open (not asserting)
_PLC_BIT_OK               = 0x02   # bit 1: all safety checks passing
_PLC_BIT_WATCHDOG_FAULT   = 0x04   # bit 2: RCC packets stopped
_PLC_BIT_LIMIT_MISMATCH   = 0x08   # bit 3: PLC/RCC limit switch readings disagree
_PLC_BIT_BAD_CRC          = 0x10   # bit 4: packet received but CRC failed (live, clears on good packet)
_PLC_BIT_LEVEL0_FAULT     = 0x20   # bit 5: relay cut — terminal, requires key cycle to OFF
_PLC_BIT_ECHO_FAULT       = 0x40   # bit 6: RCC not echoing PLC counter within allowed lag
_PLC_BIT_MOTION_FAULT     = 0x80   # bit 7: motion envelope violation (motor speed > 9500 QPPS)

# RCCState values — used to set status bits without importing RCC.py
_RCC_ESTOP_VALUE = 5
_RCC_FAULT_VALUE = 6


def _crc16(data: bytes) -> int:
    """ANSI CRC-16, polynomial 0x8005. Per Microchip AN730."""
    crc = 0x0000
    for byte in data:
        crc ^= (byte << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x8005
            else:
                crc <<= 1
        crc &= 0xFFFF
    return crc


class PLCWatchdog:
    """
    PLC ↔ RCC UART watchdog and status link.

    Runs a dedicated daemon thread that:
      - Sends a 69-byte status packet to the PLC every `intervalS` (default 10 ms)
      - Receives and validates 10-byte packets from the PLC
      - Exposes `isTimedOut()` which returns True when no valid packet has arrived
        within `timeoutS` — intended as a HIGH-severity fault condition

    All serial I/O is contained in this thread; there is no lock contention with
    the RoboClaw serial thread (which uses a separate port).
    """

    DEFAULT_BAUD        = 115200
    DEFAULT_TIMEOUT     = 0.5    # seconds before watchdog fires
    DEFAULT_INTERVAL    = 0.01   # 10 ms transmit interval
    RECONNECT_INTERVAL  = 2.0    # seconds between reconnection attempts

    def __init__(
        self,
        port: str,
        getRccState: Callable,           # Callable[[], RCCState]
        mc: 'MotorController',
        baud: int = DEFAULT_BAUD,
        timeoutS: float = DEFAULT_TIMEOUT,
        intervalS: float = DEFAULT_INTERVAL,
    ):
        """
        Args:
            port:        Serial device path (e.g. '/dev/ttyUSB0').
            getRccState: Callable returning the current RCCState enum value.
            mc:          MotorController instance for telemetry and limit switch data.
            baud:        Baud rate (must match Arduino firmware; default 115200).
            timeoutS:    Seconds without a valid PLC packet before `isTimedOut()` → True.
            intervalS:   Target transmit interval in seconds (default 10 ms).
        """
        self._port = port
        self._baud = baud
        self._getRccState = getRccState
        self._mc = mc
        self._timeoutS = timeoutS
        self._intervalS = intervalS

        self._serial: serial.Serial | None = None
        self._stopEvent = threading.Event()
        self._thread: threading.Thread | None = None

        # Own transmit counter (wraps 0 → 65535 → 0)
        self._myCounter: int = 0
        # Last PLC counter received (for echo-back and advance validation)
        self._plcCounter: int = 0
        # True on first packet — skip counter-advance check since we have no baseline
        self._firstPacket: bool = True

        # Decoded status fields from the most recent valid PLC packet
        self._plcEstopReleased:    bool = False   # bit 0: E-stop gate open
        self._plcOk:               bool = False   # bit 1: PLC healthy
        self._plcWatchdogFault:    bool = False   # bit 2: RCC comms lost
        self._plcLimitMismatch:    bool = False   # bit 3: limit switch disagreement
        self._plcBadCrc:           bool = False   # bit 4: received packet had bad CRC (live)
        self._plcLevel0Fault:      bool = False   # bit 5: relay cut — terminal
        self._plcEchoFault:        bool = False   # bit 6: RCC counter echo lag
        self._plcMotionFault:      bool = False   # bit 7: motion envelope violation
        self._plcStatusBits:       int  = 0       # raw status byte

        # Watchdog timing
        self._startTime: float = 0.0
        self._lastValidPacketTime: float = 0.0   # 0.0 = thread not started yet

        # Reconnection tracking
        self._lastConnectAttempt: float = 0.0

        # Receive accumulation buffer (handles partial / fragmented reads)
        self._rxBuffer: bytes = b''

    # =========================================================================
    #                           LIFECYCLE
    # =========================================================================

    def start(self) -> None:
        """Open serial port and start the watchdog background thread."""
        self._startTime = time.monotonic()
        # Grace period: give the system `timeoutS` from start before first timeout check
        self._lastValidPacketTime = self._startTime

        self._tryConnect()

        self._stopEvent.clear()
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="PLCWatchdog",
        )
        self._thread.start()

    def _tryConnect(self) -> None:
        """Attempt to open the serial port. Resets communication state on success."""
        self._lastConnectAttempt = time.monotonic()
        try:
            self._serial = serial.Serial(
                port=self._port,
                baudrate=self._baud,
                timeout=0.001,   # 1 ms read timeout — effectively non-blocking
            )
            logger.info(f"PLCWatchdog opened on {self._port} @ {self._baud} baud")
            # Reset communication state so the grace period and counter checks restart cleanly
            self._lastValidPacketTime = time.monotonic()
            self._firstPacket = True
            self._rxBuffer = b''
        except serial.SerialException as e:
            logger.warning(f"PLCWatchdog failed to open {self._port}: {e} — will retry in {self.RECONNECT_INTERVAL}s")
            self._serial = None

    def shutdown(self) -> None:
        """Stop the watchdog thread and close the serial port."""
        self._stopEvent.set()
        if self._thread:
            self._thread.join(timeout=1.0)
        if self._serial and self._serial.is_open:
            self._serial.close()
        logger.info("PLCWatchdog shut down")

    # =========================================================================
    #                           FAULT CONDITION
    # =========================================================================

    def isTimedOut(self) -> bool:
        """
        Returns True when no valid PLC packet has been received within `timeoutS`.

        Use as a HIGH-severity fault condition in the FaultMonitor.
        Returns False until `start()` has been called (prevents spurious fault on init).
        """
        if self._lastValidPacketTime == 0.0:
            return False
        return (time.monotonic() - self._lastValidPacketTime) > self._timeoutS

    def isPlcOk(self) -> bool:
        """True if the PLC reported all safety checks passing (bit 1)."""
        return self._plcOk

    def isEstopReleased(self) -> bool:
        """True if the PLC E-stop gate is open (not asserting) — bit 0."""
        return self._plcEstopReleased

    def isWatchdogFault(self) -> bool:
        """True if the PLC latched a watchdog fault (RCC comms dropped) — bit 2."""
        return self._plcWatchdogFault

    def isLimitSwitchMismatch(self) -> bool:
        """True if the PLC latched a limit switch mismatch against the RCC — bit 3."""
        return self._plcLimitMismatch

    def isBadCrcFault(self) -> bool:
        """True if the PLC received a packet with a bad CRC (live, clears on next good packet) — bit 4."""
        return self._plcBadCrc

    def isLevel0Fault(self) -> bool:
        """True if the PLC has cut the 24 V relay — terminal, requires power cycle — bit 5."""
        return self._plcLevel0Fault

    def isEchoFault(self) -> bool:
        """True if the PLC latched an echo-counter fault (RCC not mirroring counter) — bit 6."""
        return self._plcEchoFault

    def isMotionFault(self) -> bool:
        """True if the PLC detected a motion envelope violation (motor speed > 9500 QPPS) — bit 7."""
        return self._plcMotionFault

    def getDetails(self) -> dict:
        """Returns a snapshot of watchdog communication state for display."""
        now = time.monotonic()
        if self._lastValidPacketTime == 0.0:
            ageSec = None
        else:
            ageSec = round(now - self._lastValidPacketTime, 3)
        return {
            "port":                self._port,
            "portOpen":            self._serial is not None and self._serial.is_open,
            "rccCounter":          self._myCounter,
            "plcCounter":          self._plcCounter,
            "timeSinceLastPacket": ageSec,
            "timedOut":            self.isTimedOut(),
            "plcStatusBits":       f"{self._plcStatusBits:#04x}",
            "plcOk":               self._plcOk,
            "estopReleased":       self._plcEstopReleased,
            "watchdogFault":       self._plcWatchdogFault,
            "limitMismatch":       self._plcLimitMismatch,
            "badCrcFault":         self._plcBadCrc,
            "level0Fault":         self._plcLevel0Fault,
            "echoFault":           self._plcEchoFault,
            "motionFault":         self._plcMotionFault,
        }

    # =========================================================================
    #                           WATCHDOG THREAD
    # =========================================================================

    def _run(self) -> None:
        while not self._stopEvent.is_set():
            loopStart = time.monotonic()

            if self._serial is None or not self._serial.is_open:
                if loopStart - self._lastConnectAttempt >= self.RECONNECT_INTERVAL:
                    logger.info("PLCWatchdog attempting reconnect...")
                    self._tryConnect()
                self._stopEvent.wait(0.1)
                continue

            try:
                self._sendPacket()
            except serial.SerialException as e:
                logger.error(f"PLCWatchdog serial error (send): {e} — will retry in {self.RECONNECT_INTERVAL}s")
                if self._serial and self._serial.is_open:
                    self._serial.close()
                self._serial = None
            except struct.error as e:
                mc = self._mc
                speeds    = mc.getMotorSpeeds()
                positions = mc.getMotorPositions()
                currents  = mc.getMotorCurrents()
                m1Cmd     = mc.getLastMotorCommand(1)
                m2Cmd     = mc.getLastMotorCommand(2)
                logger.error(
                    f"PLCWatchdog pack error: {e} | "
                    f"speeds={speeds} positions={positions} currents={currents} "
                    f"m1Cmd={m1Cmd} m2Cmd={m2Cmd}"
                )
            except Exception as e:
                logger.error(f"PLCWatchdog send error: {e}")

            try:
                self._receivePackets()
            except serial.SerialException as e:
                logger.error(f"PLCWatchdog serial error (recv): {e} — will retry in {self.RECONNECT_INTERVAL}s")
                if self._serial and self._serial.is_open:
                    self._serial.close()
                self._serial = None
            except Exception as e:
                logger.error(f"PLCWatchdog recv error: {e}")

            elapsed = time.monotonic() - loopStart
            remaining = self._intervalS - elapsed
            if remaining > 0:
                self._stopEvent.wait(remaining)

    # =========================================================================
    #                           TX
    # =========================================================================

    def _sendPacket(self) -> None:
        if self._serial is None or not self._serial.is_open:
            return

        payload = self._buildPayload()
        crc = _crc16(payload)
        self._serial.write(payload + struct.pack('<H', crc))

        self._myCounter = (self._myCounter + 1) & 0xFFFF

    def _buildPayload(self) -> bytes:
        mc  = self._mc
        rccState = self._getRccState()

        # Status bits
        # E-Stop is active if the MC hardware reports it OR the RCC is in a software ESTOP/FAULT state
        estopActive = mc.isEstopActive() or rccState.value in (_RCC_ESTOP_VALUE, _RCC_FAULT_VALUE)
        imOk = rccState.value not in (_RCC_ESTOP_VALUE, _RCC_FAULT_VALUE)
        statusBits = 0
        if estopActive:
            statusBits |= _BIT_ESTOP | _BIT_ESTOP2
        if imOk:
            statusBits |= _BIT_IM_OK

        # Motor telemetry — default to 0 if not available
        speeds    = mc.getMotorSpeeds()
        positions = mc.getMotorPositions()
        currents  = mc.getMotorCurrents()

        m1Speed = int(speeds[0])    if speeds    is not None else 0
        m2Speed = int(speeds[1])    if speeds    is not None else 0
        m1Enc   = positions[0]      if positions is not None else 0
        m2Enc   = positions[1]      if positions is not None else 0

        # Currents: int16 centamps (spec); getMotorCurrents() returns amps → × 100
        m1Cur = int(round(currents[0] * 100)) if currents is not None else 0
        m2Cur = int(round(currents[1] * 100)) if currents is not None else 0

        # Voltage: uint16 in 0.1 V units
        voltage    = mc.getVoltage() or 0.0
        voltageRaw = int(round(voltage * 10))

        # Raw MC status register (uint32)
        mcRawStatus = mc.getRawControllerStatus()

        # MC time since last valid read: milliseconds, capped at 0xFFFF
        ageS = mc.getTelemetryAge()
        if ageS == float('inf'):
            mcTimeSinceUpdate = 0xFFFF
        else:
            mcTimeSinceUpdate = min(int(ageS * 1000), 0xFFFF)

        # Last commanded position/speed/accel/decel per motor
        m1Cmd = mc.getLastMotorCommand(1)
        m2Cmd = mc.getLastMotorCommand(2)
        m1CmdPos, m1CmdSpd, m1CmdAcc, m1CmdDec = m1Cmd if m1Cmd is not None else (0, 0, 0, 0)
        m2CmdPos, m2CmdSpd, m2CmdAcc, m2CmdDec = m2Cmd if m2Cmd is not None else (0, 0, 0, 0)

        # Ride state enum integer value (matches PLC spec table)
        rideStateVal = rccState.value

        # Limit switch byte: bits 0-3 map to T1-bot, T1-top, T2-bot, T2-top
        limitByte = 0
        if mc.isAtBottomLimit(1): limitByte |= 0x01
        if mc.isAtTopLimit(1):    limitByte |= 0x02
        if mc.isAtBottomLimit(2): limitByte |= 0x04
        if mc.isAtTopLimit(2):    limitByte |= 0x08

        return struct.pack(
            _TX_PAYLOAD_FMT,
            self._myCounter,
            self._plcCounter,
            statusBits,
            m1Speed, m1Enc, m1Cur,
            m2Speed, m2Enc, m2Cur,
            voltageRaw,
            mcRawStatus,
            mcTimeSinceUpdate,
            m1CmdPos, m1CmdSpd, m1CmdAcc, m1CmdDec,
            m2CmdPos, m2CmdSpd, m2CmdAcc, m2CmdDec,
            rideStateVal,
            limitByte,
        )

    # =========================================================================
    #                           RX
    # =========================================================================

    def _receivePackets(self) -> None:
        if self._serial is None or not self._serial.is_open:
            return

        # Drain whatever the OS has buffered into our accumulation buffer
        waiting = self._serial.in_waiting
        if waiting > 0:
            self._rxBuffer += self._serial.read(waiting)

        # Parse as many complete 10-byte packets as are available
        while len(self._rxBuffer) >= _RX_SIZE:
            raw     = self._rxBuffer[:_RX_SIZE]
            payload = raw[:-2]
            receivedCrc, = struct.unpack('<H', raw[-2:])

            if _crc16(payload) == receivedCrc:
                self._processPacket(payload)
                self._rxBuffer = self._rxBuffer[_RX_SIZE:]
            else:
                # CRC mismatch: shift one byte to re-find packet boundary
                logger.warning(
                    f"PLCWatchdog: CRC mismatch — re-syncing RX buffer "
                    f"(raw={raw.hex()}, expected={_crc16(payload):#06x}, got={receivedCrc:#06x})"
                )
                self._rxBuffer = self._rxBuffer[1:]

    def _processPacket(self, payload: bytes) -> None:
        plcCounter, echoCounter, statusBits, _reserved1, _reserved2 = struct.unpack(
            _RX_PAYLOAD_FMT, payload
        )

        # Counter advance check (mod-65536 forward window)
        if not self._firstPacket:
            delta = (plcCounter - self._plcCounter) & 0xFFFF
            if delta == 0:
                logger.warning(f"PLCWatchdog: duplicate PLC counter ({plcCounter}) — ignoring packet")
                return
            if delta >= 0x8000:
                logger.warning(
                    f"PLCWatchdog: PLC counter did not advance (delta={delta:#06x}) — ignoring"
                )
                return

        self._firstPacket        = False
        self._plcCounter         = plcCounter
        self._plcStatusBits      = statusBits
        self._plcEstopReleased   = bool(statusBits & _PLC_BIT_ESTOP_RELEASED)
        self._plcOk              = bool(statusBits & _PLC_BIT_OK)
        self._plcWatchdogFault   = bool(statusBits & _PLC_BIT_WATCHDOG_FAULT)
        self._plcLimitMismatch   = bool(statusBits & _PLC_BIT_LIMIT_MISMATCH)
        self._plcBadCrc          = bool(statusBits & _PLC_BIT_BAD_CRC)
        self._plcLevel0Fault     = bool(statusBits & _PLC_BIT_LEVEL0_FAULT)
        self._plcEchoFault       = bool(statusBits & _PLC_BIT_ECHO_FAULT)
        self._plcMotionFault     = bool(statusBits & _PLC_BIT_MOTION_FAULT)
        self._lastValidPacketTime = time.monotonic()

        if self._plcLevel0Fault:
            logger.critical("PLCWatchdog: FAULT_LEVEL0 — relay cut, key must be cycled to OFF to recover")
        if self._plcMotionFault:
            logger.critical("PLCWatchdog: FAULT_MOTION — motion envelope violation (motor speed > 9500 QPPS)")
        if self._plcWatchdogFault:
            logger.error("PLCWatchdog: FAULT_WATCHDOG — RCC packets stopped")
        if self._plcEchoFault:
            logger.error("PLCWatchdog: FAULT_ECHO_COUNTER — RCC not echoing PLC counter within allowed lag")
        if self._plcBadCrc:
            logger.error("PLCWatchdog: FAULT_BAD_CRC — PLC received a packet with invalid CRC")
        if self._plcLimitMismatch:
            logger.warning("PLCWatchdog: FAULT_LIMIT_MISMATCH — PLC and RCC limit switch readings disagree")
