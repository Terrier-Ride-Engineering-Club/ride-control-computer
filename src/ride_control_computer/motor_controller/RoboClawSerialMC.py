# RoboClaw motorcontroller for TREC's REC Ride Control Computer
    # Made by Jackson Justus (jackjust@bu.edu)

import time
import logging
import serial.serialutil
from threading import Thread, Event, Lock

from gpiozero import Button

from ride_control_computer.loop_timer import LoopTimer
from ride_control_computer.motor_controller.MotorController import MotorController, MotorControllerState, MotorTelemetry, ControllerTelemetry
from ride_control_computer.motor_controller.RoboClaw import RoboClaw

# --- Limit switch GPIO pins (BCM numbering) ---
PIN_M1_TOP_LIMIT    = 12
PIN_M1_BOTTOM_LIMIT = 16
PIN_M2_TOP_LIMIT    = 20
PIN_M2_BOTTOM_LIMIT = 21

# --- Homing parameters ---
HOMING_SPEED        = 300   # QPPS — slow creep toward limit switch
HOMING_ACCELERATION = 100

# --- Position tolerance ---
POSITION_TOLERANCE  = 50    # Encoder counts — "near enough" to target

logger = logging.getLogger(__name__)

class RoboClawSerialMotorController(MotorController):
    """
    Implementation of MotorController using a RoboClaw motor controller over serial.

    Runs a background serial thread that is the sole owner of all RoboClaw I/O.
    Public API methods set state and parameters; the serial thread picks them up
    on its next tick and sends the appropriate commands.
    """

    # --- Configuration ---
    WRITE_RATE_HZ = 200      # command writes (jog, stop, etc.)
    READ_RATE_HZ = 20        # telemetry reads (status, voltage, encoders, etc.)
    JOG_SPEED = 500
    JOG_ACCELERATION = 200
    STOP_DECELERATION = 300
    HALT_DECELERATION = 10000
    STOPPED_THRESHOLD = 5    # QPPS — below this, motors are considered stopped
    RECONNECT_INTERVAL_S = 5.0  # seconds between reconnection attempts

    def __init__(self, ports: list[str], address: int = 0x80):
        """
        Args:
            ports: Serial port paths to try in order (e.g. ['/dev/ttyAMA1', '/dev/ttyACM0']).
                   The MC will try each port on startup and on every reconnection attempt.
            address: RoboClaw packet serial address (default 0x80).
        """
        super().__init__()

        self._ports = ports
        self._address = address
        self._roboClaw: RoboClaw | None = None   # Managed internally; None when disconnected
        self._lastConnectAttempt: float = 0.0

        # State (written by main thread, read by serial thread)
        self._state = MotorControllerState.DISABLED

        # Jog parameters (set by main thread, read by serial thread)
        self._jogMotor: int = 0
        self._jogDirection: int = 0

        # Active deceleration (STOP vs HALT)
        self._activeDeceleration: int = self.STOP_DECELERATION

        # Telemetry cache
        self._telemetry = ControllerTelemetry()
        self._telemetryLock = Lock()

        # Limit switches (active-high, no internal pull-up)
        self._limitSwitches = {
            1: {"top": Button(PIN_M1_TOP_LIMIT, pull_up=False), "bottom": Button(PIN_M1_BOTTOM_LIMIT, pull_up=False)},
            2: {"top": Button(PIN_M2_TOP_LIMIT, pull_up=False), "bottom": Button(PIN_M2_BOTTOM_LIMIT, pull_up=False)},
        }
        # Cached limit switch state (updated in _pollTelemetry, read from serial thread only)
        self._limitCache: dict[int, dict[str, bool]] = {
            1: {"top": False, "bottom": False},
            2: {"top": False, "bottom": False},
        }
        # Last commanded position per motor (for isMotorNearTarget)
        self._targetPositions: dict[int, int | None] = {1: None, 2: None}
        # Motors currently being homed
        self._homingMotors: list[int] = []

        # Background thread control
        self._stopEvent = Event()
        self._controlThread: Thread | None = None

        # Loop timer
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
                self._attemptReset()
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
    #                           COMMANDS
    # =========================================================================

    def driveToPosition(self, motor: int, position: int, speed: int, accel: int, decel: int) -> None:
        if self._roboClaw is None:
            return
        self._targetPositions[motor] = position
        self._roboClaw.drive_to_position_with_speed_acceleration_deceleration(
            motor, position, speed, accel, decel
        )

    def homeMotors(self, motors: list[int]) -> None:
        self._homingMotors = [m for m in motors if not self._limitCache[m]["bottom"]]
        if self._homingMotors:
            self._setState(MotorControllerState.HOMING)
        # Motors already at home are skipped; if all are already home, state stays IDLE

    def isAtBottomLimit(self, motor: int) -> bool:
        return self._limitCache[motor]["bottom"]

    def isAtTopLimit(self, motor: int) -> bool:
        return self._limitCache[motor]["top"]

    def isMotorNearTarget(self, motor: int, tolerance: int = POSITION_TOLERANCE) -> bool:
        target = self._targetPositions[motor]
        if target is None:
            return False
        return abs(self.getMotorPosition(motor) - target) <= tolerance

    def jogMotor(self, motorNumber: int, direction: int):
        if motorNumber not in (1, 2):
            logger.error(f"Invalid motor number: {motorNumber}")
            return False

        if self._state not in (MotorControllerState.IDLE, MotorControllerState.JOGGING):
            logger.debug(f"Cannot jog from state {self._state}")
            return False

        self._jogMotor = motorNumber
        self._jogDirection = direction
        self._setState(MotorControllerState.JOGGING)
        return True

    def stopMotion(self):
        self._activeDeceleration = self.STOP_DECELERATION
        self._setState(MotorControllerState.STOPPING)

    def haltMotion(self):
        self._activeDeceleration = self.HALT_DECELERATION
        self._setState(MotorControllerState.STOPPING)

    # =========================================================================
    #                           MOTOR TELEMETRY
    # =========================================================================

    def getMotorSpeed(self, motor: int):
        with self._telemetryLock:
            return self._telemetry.motors[motor].speed

    def getMotorSpeeds(self) -> tuple[float, float]:
        with self._telemetryLock:
            return (
                self._telemetry.motors[1].speed,
                self._telemetry.motors[2].speed
            )

    def getMotorPosition(self, motor: int):
        with self._telemetryLock:
            return self._telemetry.motors[motor].encoder

    def getMotorPositions(self) -> tuple[int, int]:
        with self._telemetryLock:
            return (
                self._telemetry.motors[1].encoder,
                self._telemetry.motors[2].encoder
            )

    def getMotorCurrent(self, motor: int):
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

    def getVoltage(self):
        with self._telemetryLock:
            return self._telemetry.voltage

    def getTemperature(self, sensor: int):
        with self._telemetryLock:
            return self._telemetry.temp1 if sensor == 1 else self._telemetry.temp2

    def getControllerStatus(self):
        with self._telemetryLock:
            return self._telemetry.status

    def isEstopActive(self):
        with self._telemetryLock:
            return "E-Stop" in self._telemetry.status

    # =========================================================================
    #                           TELEMETRY HEALTH
    # =========================================================================

    STALE_THRESHOLD_MULTIPLIER = 3

    def getTelemetryAge(self):
        with self._telemetryLock:
            lastUpdate = self._telemetry.lastUpdate
        if lastUpdate == 0.0:
            return float('inf')
        return time.time() - lastUpdate

    def isTelemetryStale(self, maxAgeSeconds: float | None = None):
        if maxAgeSeconds is None:
            maxAgeSeconds = self.STALE_THRESHOLD_MULTIPLIER / self.READ_RATE_HZ
        return self.getTelemetryAge() > maxAgeSeconds

    # =========================================================================
    #                           STATE
    # =========================================================================

    def getState(self) -> MotorControllerState:
        return self._state

    def _setState(self, newState: MotorControllerState):
        if self._state != newState:
            logger.info(f"State: {self._state.name} -> {newState.name}")
            self._state = newState

    def _attemptReset(self):
        if self.getState() is not MotorControllerState.DISABLED:    return
        if self.isTelemetryStale():                                  return
        if self.getControllerStatus() != "Normal":                   return
        self._setState(MotorControllerState.IDLE)

    # =========================================================================
    #                           CONTROL LOOP
    # =========================================================================

    def _controlLoop(self):
        writeInterval = 1.0 / self.WRITE_RATE_HZ
        readInterval = 1.0 / self.READ_RATE_HZ
        loopInterval = min(writeInterval, readInterval)

        lastWrite = 0.0
        lastRead = 0.0

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
                    self._executeStateAction()

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

            except Exception as e:
                logger.error(f"Control loop error: {e}")

            elapsed = time.monotonic() - now
            sleepTime = loopInterval - elapsed
            if sleepTime > 0:
                self._stopEvent.wait(sleepTime)

    def _executeStateAction(self):
        """Send the appropriate serial command for the current state."""
        if self._state == MotorControllerState.JOGGING:
            speed = self.JOG_SPEED if self._jogDirection > 0 else -self.JOG_SPEED
            self._roboClaw.set_speed_with_acceleration(self._jogMotor, speed, self.JOG_ACCELERATION)
        elif self._state == MotorControllerState.STOPPING:
            for motor in [1, 2]:
                self._roboClaw.set_speed_with_acceleration(motor, 0, self._activeDeceleration)
        elif self._state == MotorControllerState.HOMING:
            for motor in self._homingMotors:
                if not self._limitCache[motor]["bottom"]:
                    self._roboClaw.set_speed_with_acceleration(motor, -HOMING_SPEED, HOMING_ACCELERATION)
                else:
                    self._roboClaw.set_speed_with_acceleration(motor, 0, HOMING_ACCELERATION)

    def _checkStateTransitions(self):
        """Check if the current state should transition."""
        if self._state == MotorControllerState.DISABLED:
            self._attemptReset()
        elif self._state == MotorControllerState.STOPPING:
            s1, s2 = self.getMotorSpeeds()
            if abs(s1) < self.STOPPED_THRESHOLD and abs(s2) < self.STOPPED_THRESHOLD:
                self._setState(MotorControllerState.IDLE)
        elif self._state == MotorControllerState.HOMING:
            if all(self._limitCache[m]["bottom"] for m in self._homingMotors):
                self._setState(MotorControllerState.IDLE)

    def _pollTelemetry(self):
        pollingStartTime = time.time()

        # Read from hardware
        status = self._roboClaw.read_status()
        voltage = self._roboClaw.read_batt_voltage()
        currents = self._roboClaw.read_currents()
        temp1 = self._roboClaw.read_temp_sensor(1)
        temp2 = self._roboClaw.read_temp_sensor(2)

        motorData: dict[int, MotorTelemetry] = {}

        for motor in [1, 2]:
            encData = self._roboClaw.read_encoder_pos(motor)
            speedData = self._roboClaw.read_encoder_speed(motor)

            motorData[motor] = MotorTelemetry(
                speed=speedData["speed"],
                encoder=encData["encoder"],
                current=currents[motor - 1],
                direction=speedData["direction"],
                timestamp=pollingStartTime
            )

        # Read limit switches
        for motor in [1, 2]:
            self._limitCache[motor]["top"]    = self._limitSwitches[motor]["top"].is_pressed
            self._limitCache[motor]["bottom"] = self._limitSwitches[motor]["bottom"].is_pressed

        # Update cache atomically
        with self._telemetryLock:
            self._telemetry.motors = motorData
            self._telemetry.voltage = voltage
            self._telemetry.status = status
            self._telemetry.temp1 = temp1
            self._telemetry.temp2 = temp2
            self._telemetry.lastUpdate = pollingStartTime
