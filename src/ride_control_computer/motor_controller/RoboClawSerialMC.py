# RoboClaw motorcontroller for TREC's REC Ride Control Computer
    # Made by Jackson Justus (jackjust@bu.edu)

import time
import logging
import serial.serialutil
from enum import Enum
from threading import Thread, Event, Lock

from gpiozero import Button

from ride_control_computer.loop_timer import LoopTimer
from ride_control_computer.motor_controller.MotorController import MotorController, MotorControllerState, MotorTelemetry, ControllerTelemetry
from ride_control_computer.motor_controller.RoboClaw import RoboClaw

# --- Limit switch GPIO pins (BCM numbering) ---
PIN_M1_TOP_LIMIT    = 20
PIN_M1_BOTTOM_LIMIT = 21
PIN_M2_TOP_LIMIT    = 8
PIN_M2_BOTTOM_LIMIT = 7

# --- Homing parameters ---
HOMING_SPEED        = 300   # QPPS — slow creep toward limit switch
HOMING_ACCELERATION = 100

# --- Position tolerance ---
POSITION_TOLERANCE  = 50    # Encoder counts — "near enough" to target

logger = logging.getLogger(__name__)


class _CommandType(Enum):
    """Active command the serial thread should re-send each write tick."""
    NONE  = -1  # No command — serial thread does not send anything
    STOP  = 0   # Decelerate both motors to 0
    JOG   = 1   # Continuous speed on one motor
    DRIVE = 2   # Position command on one or both motors
    HOME  = 3   # Drive toward bottom limit at homing speed


class RoboClawSerialMotorController(MotorController):
    """
    Implementation of MotorController using a RoboClaw motor controller over serial.

    All RoboClaw I/O is owned exclusively by the background serial thread.
    Public API methods store a pending command; the serial thread re-sends it
    each write tick as long as the RCC heartbeat is fresh.

    If the RCC stops calling heartbeat() (e.g. it hangs), the serial thread
    stops sending within HEARTBEAT_TTL seconds and the RoboClaw's own packet
    serial watchdog becomes the last line of defence.
    """

    # --- Timing ---
    WRITE_RATE_HZ      = 200    # command write frequency
    READ_RATE_HZ       = 20     # telemetry read frequency
    RECONNECT_INTERVAL_S = 5.0  # seconds between reconnection attempts
    HEARTBEAT_TTL      = 0.025  # seconds — must stay above RoboClaw's 20ms timeout

    # --- Motion parameters ---
    JOG_SPEED          = 300
    JOG_ACCELERATION   = 2000
    STOP_DECELERATION  = 2000
    HALT_DECELERATION  = 10000
    STOPPED_THRESHOLD              = 5    # QPPS — below this, motors are considered stopped
    VELOCITY_TO_POSITION_LOCKOUT_S = 0.4  # seconds to wait after last velocity command before allowing DRIVE

    def __init__(self, ports: list[str], address: int = 0x80):
        """
        Args:
            ports:   Serial port paths to try in order (e.g. ['/dev/ttyAMA1', '/dev/ttyACM0']).
                     The MC will try each port on startup and retry every RECONNECT_INTERVAL_S.
            address: RoboClaw packet serial address (default 0x80).
        """
        super().__init__()

        self._ports = ports
        self._address = address
        self._roboClaw: RoboClaw | None = None
        self._lastConnectAttempt: float = 0.0

        # --- Heartbeat (written by RCC main thread, read by serial thread) ---
        self._heartbeatExpiry: float = 0.0

        # --- Pending command (main thread writes, serial thread reads) ---
        self._commandLock = Lock()
        self._commandType: _CommandType   = _CommandType.NONE
        self._commandDecel: int           = self.STOP_DECELERATION
        self._commandJogDir: int          = 0
        # Per-motor drive params: motor → (position, speed, accel, decel)
        self._commandDrive: dict[int, tuple[int, int, int, int]] = {}
        # Set to True by homeMotors(); cleared implicitly when command switches away from HOME
        self._homingActive: bool = False
        # Per-motor flag: True once the encoder has been zeroed for the current bottom-limit arrival.
        # Reset by homeMotors() at the start of each homing sequence.
        # Reset per-motor in the JOG branch when the motor leaves the bottom limit.
        self._bottomResetDone: dict[int, bool] = {1: False, 2: False}
        # Tracks the last time a velocity command was executed; DRIVE is blocked
        # for VELOCITY_TO_POSITION_LOCKOUT_S after any velocity command to prevent
        # the position PID from seeing accumulated velocity-mode encoder error.
        self._lastVelocityCmdTime: float = time.monotonic()

        # --- Telemetry cache (serial thread writes, any thread reads) ---
        self._telemetry = ControllerTelemetry()
        self._telemetryLock = Lock()

        # --- Limit switches (NC, 3.3 V) ---
        # Switches are normally-closed with 3.3 V: pin HIGH = switch closed = NOT at limit.
        # When a limit is hit the switch opens, the internal pull-down takes the pin LOW,
        # and the cache entry is set True (at limit).
        # pull_up=False → internal pull-down; when_pressed fires on HIGH (switch closes),
        # when_released fires on LOW (switch opens = limit hit).
        self._limitSwitches = {
            1: {"top": Button(PIN_M1_TOP_LIMIT,    pull_up=False),
                "bottom": Button(PIN_M1_BOTTOM_LIMIT, pull_up=False)},
            2: {"top": Button(PIN_M2_TOP_LIMIT,    pull_up=False),
                "bottom": Button(PIN_M2_BOTTOM_LIMIT, pull_up=False)},
        }
        # Limit switch cache — seeded from GPIO at startup and kept current via
        # gpiozero when_pressed/when_released callbacks (no serial-thread polling).
        self._limitCache: dict[int, dict[str, bool]] = {
            1: {"top": False, "bottom": False},
            2: {"top": False, "bottom": False},
        }
        def _makeLimitCallback(motor: int, pos: str, value: bool):
            def cb(): self._limitCache[motor][pos] = value
            return cb
        for motor, switches in self._limitSwitches.items():
            for pos, btn in switches.items():
                # is_pressed=True means 3.3 V (switch closed) = NOT at limit → invert seed
                self._limitCache[motor][pos] = not btn.is_pressed
                btn.when_pressed  = _makeLimitCallback(motor, pos, False)  # 3.3 V → not at limit
                btn.when_released = _makeLimitCallback(motor, pos, True)   # pin LOW → at limit

        # --- Background thread control ---
        self._stopEvent = Event()
        self._controlThread: Thread | None = None

        # --- Loop timer ---
        self._loop_timer = LoopTimer()

    # =========================================================================
    #                           LIFECYCLE
    # =========================================================================

    def start(self):
        """Attempt initial connection and start the background serial thread.

        If no port is reachable on startup the thread still starts and will
        retry every RECONNECT_INTERVAL_S seconds until a device is found.
        """
        logger.info("Starting RoboClawSerialMotorController")
        self._tryConnect()   # Best-effort; background thread retries on failure

        self._stopEvent.clear()
        self._controlThread = Thread(
            target=self._controlLoop,
            daemon=True,
            name="RoboClawSerial"
        )
        self._controlThread.start()

    def _tryConnect(self) -> bool:
        """Try each configured port in order. Returns True if a device was found."""
        for port in self._ports:
            try:
                rc = RoboClaw(port=port, address=self._address)
                version = rc.read_version()
                logger.info(f"RoboClaw connected on {port}: {version}")
                self._roboClaw = rc
                self._attemptActivation()
                return True
            except Exception as e:
                logger.debug(f"RoboClaw not available on {port}: {e}")
        logger.warning(f"RoboClaw not found on any port: {self._ports}")
        return False

    def shutdown(self):
        """Stop all motion and clean up."""
        logger.info("Shutting down RoboClawSerialMotorController")

        self.haltMotion()

        self._stopEvent.set()
        if self._controlThread:
            self._controlThread.join(timeout=1.0)

        if self._controlThread is not None and self._controlThread.is_alive():
            logger.error("Control thread failed to shutdown.")

        self._setState(MotorControllerState.DISABLED)

    # =========================================================================
    #                           HEARTBEAT
    # =========================================================================

    def heartbeat(self) -> None:
        """
        Called by the RCC main thread every loop tick.
        Authorises the serial thread to keep re-sending the active command
        for the next HEARTBEAT_TTL seconds.  If heartbeat() is not called
        within that window (e.g. RCC hangs), the serial thread stops sending
        and the RoboClaw's own packet-serial watchdog takes over.
        """
        self._heartbeatExpiry = time.monotonic() + self.HEARTBEAT_TTL

    # =========================================================================
    #                           COMMANDS
    # =========================================================================

    def driveToPosition(self, motor: int, position: int, speed: int, accel: int, decel: int) -> None:
        with self._commandLock:
            self._commandType = _CommandType.DRIVE
            self._commandDrive[motor] = (position, speed, accel, decel)

    def homeMotors(self) -> None:
        with self._commandLock:
            self._commandType = _CommandType.HOME
            self._homingActive = True
            self._bottomResetDone = {1: False, 2: False}

    def isAtBottomLimit(self, motor: int) -> bool:
        return self._limitCache[motor]["bottom"]

    def isAtTopLimit(self, motor: int) -> bool:
        return self._limitCache[motor]["top"]

    def isMotorNearTarget(self, motor: int, tolerance: int = POSITION_TOLERANCE) -> bool:
        with self._commandLock:
            cmd = self._commandDrive.get(motor)
        if cmd is None:
            return False
        return abs(self.getMotorPosition(motor) - cmd[0]) <= tolerance

    def jogMotor(self, motorNumber: int, direction: int) -> bool:
        if motorNumber not in (1, 2):
            logger.error(f"Invalid motor number: {motorNumber}")
            return False
        with self._commandLock:
            self._commandType   = _CommandType.JOG
            self._commandJogDir = direction
        return True

    def clearCommand(self) -> None:
        with self._commandLock:
            self._commandType = _CommandType.NONE

    def stopMotion(self) -> None:
        with self._commandLock:
            self._commandType  = _CommandType.STOP
            self._commandDecel = self.STOP_DECELERATION

    def haltMotion(self) -> None:
        with self._commandLock:
            self._commandType  = _CommandType.STOP
            self._commandDecel = self.HALT_DECELERATION

    # =========================================================================
    #                           MOTION STATUS
    # =========================================================================

    def areMotorsStopped(self) -> bool:
        """True when both motors are below the stopped speed threshold."""
        s1, s2 = self.getMotorSpeeds()
        return abs(s1) < self.STOPPED_THRESHOLD and abs(s2) < self.STOPPED_THRESHOLD

    def isHomingComplete(self) -> bool:
        """True when both motors are at the bottom limit since the last homeMotors() call."""
        with self._commandLock:
            homingActive = self._homingActive
        if not homingActive:
            return False
        return self._limitCache[1]["bottom"] and self._limitCache[2]["bottom"]

    # =========================================================================
    #                           MOTOR TELEMETRY
    # =========================================================================

    def getMotorSpeed(self, motor: int) -> float:
        with self._telemetryLock:
            return self._telemetry.motors[motor].speed

    def getMotorSpeeds(self) -> tuple[float, float]:
        with self._telemetryLock:
            return (
                self._telemetry.motors[1].speed,
                self._telemetry.motors[2].speed
            )

    def getMotorPosition(self, motor: int) -> int:
        with self._telemetryLock:
            return self._telemetry.motors[motor].encoder

    def getMotorPositions(self) -> tuple[int, int]:
        with self._telemetryLock:
            return (
                self._telemetry.motors[1].encoder,
                self._telemetry.motors[2].encoder
            )

    def getMotorCurrent(self, motor: int) -> float:
        with self._telemetryLock:
            return self._telemetry.motors[motor].current

    def getMotorCurrents(self) -> tuple[float, float]:
        with self._telemetryLock:
            return (
                self._telemetry.motors[1].current,
                self._telemetry.motors[2].current
            )

    @property
    def loopTimer(self):
        return self._loop_timer

    # =========================================================================
    #                           CONTROLLER TELEMETRY
    # =========================================================================

    def getVoltage(self) -> float:
        with self._telemetryLock:
            return self._telemetry.voltage

    def getTemperature(self, sensor: int) -> float:
        with self._telemetryLock:
            return self._telemetry.temp1 if sensor == 1 else self._telemetry.temp2

    def getTemperatures(self) -> tuple[float, float]:
        return self.getTemperature(1), self.getTemperature(2)

    def getControllerStatus(self) -> str:
        with self._telemetryLock:
            return self._telemetry.status

    def getRawControllerStatus(self) -> int:
        with self._telemetryLock:
            return self._telemetry.rawStatus

    def getLastMotorCommand(self, motor: int) -> tuple[int, int, int, int] | None:
        with self._commandLock:
            return self._commandDrive.get(motor)

    def isEstopActive(self) -> bool:
        with self._telemetryLock:
            return "E-Stop" in self._telemetry.status

    # =========================================================================
    #                           TELEMETRY HEALTH
    # =========================================================================

    STALE_THRESHOLD_MULTIPLIER = 3

    def getTelemetryAge(self) -> float:
        with self._telemetryLock:
            lastUpdate = self._telemetry.lastUpdate
        if lastUpdate == 0.0:
            return float('inf')
        return time.monotonic() - lastUpdate

    def isTelemetryStale(self, maxAgeSeconds: float | None = None) -> bool:
        if maxAgeSeconds is None:
            maxAgeSeconds = self.STALE_THRESHOLD_MULTIPLIER / self.READ_RATE_HZ
        return self.getTelemetryAge() > maxAgeSeconds

    # =========================================================================
    #                           STATE
    # =========================================================================

    def getState(self) -> MotorControllerState:
        return self._state

    def _setState(self, newState: MotorControllerState) -> None:
        if self._state != newState:
            logger.info(f"MC State: {self._state.name} -> {newState.name}")
            self._state = newState

    def _attemptActivation(self) -> None:
        """Transition DISABLED → ACTIVE when telemetry is healthy and status is Normal."""
        if self._state != MotorControllerState.DISABLED:  return
        if self.isTelemetryStale():                        return
        if self.getControllerStatus() != "Normal":         return
        self._setState(MotorControllerState.ACTIVE)

    def getCurrentCommand(self) -> dict:
        with self._commandLock:
            t = self._commandType
            cmd = {"type": t.name}

            if t == _CommandType.STOP:
                for m in [1, 2]:
                    cmd[f"m{m}"] = {"speed": 0, "accel": self._commandDecel}

            elif t == _CommandType.JOG:
                speed = self.JOG_SPEED if self._commandJogDir > 0 else (
                        -self.JOG_SPEED if self._commandJogDir < 0 else 0)
                for m in [1, 2]:
                    cmd[f"m{m}"] = {"speed": speed, "accel": self.JOG_ACCELERATION}

            elif t == _CommandType.DRIVE:
                for m, (pos, spd, acc, dec) in self._commandDrive.items():
                    cmd[f"m{m}"] = {"position": pos, "speed": spd, "accel": acc, "decel": dec}

            elif t == _CommandType.HOME:
                for m in [1, 2]:
                    cmd[f"m{m}"] = {"speed": -HOMING_SPEED, "accel": HOMING_ACCELERATION}

            return cmd

    # =========================================================================
    #                           CONTROL LOOP
    # =========================================================================

    def _controlLoop(self):
        writeInterval = 1.0 / self.WRITE_RATE_HZ
        readInterval  = 1.0 / self.READ_RATE_HZ
        loopInterval  = min(writeInterval, readInterval)

        lastWrite = 0.0
        lastRead  = 0.0

        while not self._stopEvent.is_set():
            self._loop_timer.tick()
            now = time.monotonic()

            if self._roboClaw is None:
                if now - self._lastConnectAttempt >= self.RECONNECT_INTERVAL_S:
                    self._lastConnectAttempt = now
                    logger.info("Attempting to reconnect to RoboClaw...")
                    self._tryConnect()
                self._stopEvent.wait(0.1)
                continue

            try:
                if now - lastWrite >= writeInterval:
                    lastWrite = now
                    self._executeCommand()

                if now - lastRead >= readInterval:
                    lastRead = now
                    self._pollTelemetry()
                    self._checkStateTransitions()

            except serial.serialutil.SerialException as e:
                logger.error(f"Serial communication lost: {e} — will retry in {self.RECONNECT_INTERVAL_S}s")
                self._roboClaw = None
                self._setState(MotorControllerState.DISABLED)
                with self._telemetryLock:
                    self._telemetry.lastUpdate = 0.0   # Force isTelemetryStale() → True immediately
                # Reset command state to STOP so stale drive commands don't
                # re-execute when the connection is re-established.
                with self._commandLock:
                    self._commandType  = _CommandType.STOP
                    self._commandDecel = self.HALT_DECELERATION
                    self._commandDrive.clear()

            except Exception as e:
                logger.error(f"Unexpected control loop error: {e}", exc_info=True)
                # Defensively reset to STOP — we don't know what state the command left things in.
                with self._commandLock:
                    self._commandType  = _CommandType.STOP
                    self._commandDecel = self.HALT_DECELERATION
                    self._commandDrive.clear()

            elapsed = time.monotonic() - now
            sleepTime = loopInterval - elapsed
            if sleepTime > 0:
                self._stopEvent.wait(sleepTime)

    def _executeCommand(self) -> None:
        """
        Re-send the active command to the RoboClaw — but only while the RCC
        heartbeat is fresh.  If the heartbeat has expired the method returns
        immediately so the RoboClaw's own packet-serial watchdog can fire.
        """
        if time.monotonic() > self._heartbeatExpiry:
            return

        with self._commandLock:
            if self._commandType == _CommandType.NONE:
                return
            cmdType         = self._commandType
            cmdDecel        = self._commandDecel
            cmdJogDir       = self._commandJogDir
            cmdDrive        = dict(self._commandDrive)
            bottomResetDone = dict(self._bottomResetDone)

        if cmdType == _CommandType.STOP:
            self._lastVelocityCmdTime = time.monotonic()
            for motor in [1, 2]:
                self._roboClaw.set_speed_with_acceleration(motor, 0, cmdDecel)

        elif cmdType == _CommandType.JOG:
            for motor in [1, 2]:
                atTop    = self._limitCache[motor]["top"]
                atBottom = self._limitCache[motor]["bottom"]
                atLimit  = (cmdJogDir > 0 and atTop) or (cmdJogDir < 0 and atBottom)
                speed    = 0 if atLimit else (self.JOG_SPEED if cmdJogDir > 0 else -self.JOG_SPEED)
                self._lastVelocityCmdTime = time.monotonic()
                self._roboClaw.set_speed_with_acceleration(motor, speed, self.JOG_ACCELERATION)

                # Encoder reset: fires once per bottom-limit arrival when jogging down.
                # Flag is cleared when the motor leaves the bottom so re-arrivals reset again.
                if cmdJogDir < 0:
                    if atBottom and not bottomResetDone[motor]:
                        self._roboClaw.reset_quad_encoders([motor])
                        with self._commandLock:
                            self._bottomResetDone[motor] = True
                        bottomResetDone[motor] = True
                        logger.info(f"Motor {motor} encoder zeroed at bottom limit (jog)")
                    elif not atBottom:
                        with self._commandLock:
                            self._bottomResetDone[motor] = False
                        bottomResetDone[motor] = False

        elif cmdType == _CommandType.DRIVE:
            age = time.monotonic() - self._lastVelocityCmdTime
            if age < self.VELOCITY_TO_POSITION_LOCKOUT_S:
                logger.error(
                    "DRIVE blocked: only %.3fs since last velocity command (lockout=%.1fs) — "
                    "unsafe velocity→position transition",
                    age, self.VELOCITY_TO_POSITION_LOCKOUT_S,
                )
                return
            for motor, (pos, spd, acc, dec) in cmdDrive.items():
                self._roboClaw.drive_to_position_with_speed_acceleration_deceleration(
                    motor, pos, spd, acc, dec
                )

        elif cmdType == _CommandType.HOME:
            m1Home = self._limitCache[1]["bottom"]
            m2Home = self._limitCache[2]["bottom"]
            spd1 = 0 if m1Home else -HOMING_SPEED
            spd2 = 0 if m2Home else -HOMING_SPEED
            self._lastVelocityCmdTime = time.monotonic()
            self._roboClaw.set_speed_with_acceleration(1, spd1, HOMING_ACCELERATION)
            self._roboClaw.set_speed_with_acceleration(2, spd2, HOMING_ACCELERATION)

            # Reset each motor's encoder the first time it reaches the bottom limit this sequence
            for motor, atHome in [(1, m1Home), (2, m2Home)]:
                if atHome and not bottomResetDone[motor]:
                    self._roboClaw.reset_quad_encoders([motor])
                    with self._commandLock:
                        self._bottomResetDone[motor] = True
                    logger.info(f"Motor {motor} encoder zeroed at bottom limit (homing)")

            # Auto-switch to STOP once both motors have reached the home limit
            if m1Home and m2Home:
                with self._commandLock:
                    self._commandType  = _CommandType.STOP
                    self._commandDecel = self.STOP_DECELERATION

    def _checkStateTransitions(self) -> None:
        """Promote DISABLED → ACTIVE when hardware becomes healthy."""
        if self._state == MotorControllerState.DISABLED:
            self._attemptActivation()

    def _pollTelemetry(self) -> None:
        pollingStartTime = time.monotonic()

        status, rawStatus = self._roboClaw.read_status()
        voltage  = self._roboClaw.read_batt_voltage()
        currents = self._roboClaw.read_currents()
        temp1    = self._roboClaw.read_temp_sensor(1)
        temp2    = self._roboClaw.read_temp_sensor(2)

        motorData: dict[int, MotorTelemetry] = {}
        for motor in [1, 2]:
            encData   = self._roboClaw.read_encoder_pos(motor)
            speedData = self._roboClaw.read_encoder_speed(motor)
            motorData[motor] = MotorTelemetry(
                speed     = speedData["speed"],
                encoder   = encData["encoder"],
                current   = currents[motor - 1],
                direction = speedData["direction"],
                timestamp = pollingStartTime,
            )

        with self._telemetryLock:
            self._telemetry.motors    = motorData
            self._telemetry.voltage   = voltage
            self._telemetry.status    = status
            self._telemetry.rawStatus = rawStatus
            self._telemetry.temp1     = temp1
            self._telemetry.temp2     = temp2
            self._telemetry.lastUpdate = pollingStartTime
