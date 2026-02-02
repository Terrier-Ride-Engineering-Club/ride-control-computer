# RoboClaw motorcontroller for TREC's REC Ride Control Computer
    # Made by Jackson Justus (jackjust@bu.edu)

import time
import logging
from threading import Thread, Event, Lock
from dataclasses import dataclass, field

from ride_control_computer.motor_controller.MotorController import MotorController, MotorControllerState
from ride_control_computer.motor_controller.RoboClaw import RoboClaw

logger = logging.getLogger(__name__)


@dataclass
class MotorTelemetry:
    """Cached telemetry for a single motor."""
    speed: float = 0.0
    encoder: int = 0
    current: float = 0.0
    direction: str = "Forward"
    timestamp: float = 0.0


@dataclass
class ControllerTelemetry:
    """Cached telemetry for the entire controller."""
    motors: dict[int, MotorTelemetry] = field(default_factory=lambda: {1: MotorTelemetry(), 2: MotorTelemetry()})
    voltage: float = 0.0
    status: str = "Unknown"
    temp1: float = 0.0
    temp2: float = 0.0
    last_update: float = 0.0


class RoboClawSerialMotorController(MotorController):
    """
    Implementation of MotorController using a RoboClaw motor controller over serial.

    Runs a background telemetry thread to keep motor state updated without blocking
    the main control loop.
    """

    # --- Configuration ---
    POLL_RATE_HZ = 50
    JOG_SPEED = 500
    JOG_ACCELERATION = 200
    STOP_DECELERATION = 300
    HALT_DECELERATION = 10000

    def __init__(self, port: str = '/dev/ttyAMA1', address: int = 0x80):
        super().__init__()

        self._port = port
        self._address = address
        self._roboclaw: RoboClaw | None = None

        # State
        self._state = MotorControllerState.DISABLED
        self._state_lock = Lock()

        # Telemetry cache
        self._telemetry = ControllerTelemetry()
        self._telemetry_lock = Lock()

        # Background thread control
        self._stop_event = Event()
        self._telem_thread: Thread | None = None

    # =========================================================================
    #                           LIFECYCLE
    # =========================================================================

    def start(self):
        """Initialize hardware and start telemetry polling."""
        logger.info("Starting RoboClawSerialMotorController")

        self._roboclaw = RoboClaw(port=self._port, address=self._address, auto_recover=True)

        version = self._roboclaw.read_version()
        logger.info(f"Connected to RoboClaw: {version}")

        # Start telemetry thread
        self._stop_event.clear()
        self._telem_thread = Thread(
            target=self._telemetry_loop,
            daemon=True,
            name="RoboClaw-Telemetry"
        )
        self._telem_thread.start()

        self._set_state(MotorControllerState.IDLE)

    def shutdown(self):
        """Stop all motion and clean up."""
        logger.info("Shutting down RoboClawSerialMotorController")

        self.haltMotion()

        self._stop_event.set()
        if self._telem_thread:
            self._telem_thread.join(timeout=1.0)

        self._set_state(MotorControllerState.DISABLED)

    # =========================================================================
    #                           COMMANDS
    # =========================================================================

    def startRideSequence(self):
        if self._state != MotorControllerState.IDLE:
            logger.warning(f"Cannot start sequence from state {self._state}")
            return

        self._set_state(MotorControllerState.SEQUENCING)
        # TODO: Implement ride sequence

    def home(self):
        self._set_state(MotorControllerState.HOMING)
        # TODO: Implement homing

    def jogMotor(self, motorNumber: int, direction: int) -> bool:
        if self._state not in (MotorControllerState.IDLE, MotorControllerState.JOGGING):
            logger.debug(f"Cannot jog from state {self._state}")
            return False

        if motorNumber not in (1, 2):
            logger.error(f"Invalid motor number: {motorNumber}")
            return False

        self._set_state(MotorControllerState.JOGGING)

        speed = self.JOG_SPEED if direction > 0 else -self.JOG_SPEED
        self._roboclaw.set_speed_with_acceleration(motorNumber, speed, self.JOG_ACCELERATION)

        return True

    def stopMotion(self):
        self._set_state(MotorControllerState.STOPPING)

        for motor in [1, 2]:
            self._roboclaw.set_speed_with_acceleration(motor, 0, self.STOP_DECELERATION)

        # TODO: Monitor until stopped, then transition to IDLE
        self._set_state(MotorControllerState.IDLE)

    def haltMotion(self):
        for motor in [1, 2]:
            self._roboclaw.set_speed_with_acceleration(motor, 0, self.HALT_DECELERATION)

        self._set_state(MotorControllerState.IDLE)

    # =========================================================================
    #                           MOTOR TELEMETRY
    # =========================================================================

    def getMotorSpeed(self, motor: int) -> float:
        with self._telemetry_lock:
            return self._telemetry.motors[motor].speed

    def getMotorSpeeds(self) -> tuple[float, float]:
        with self._telemetry_lock:
            return (
                self._telemetry.motors[1].speed,
                self._telemetry.motors[2].speed
            )

    def getMotorPosition(self, motor: int) -> int:
        with self._telemetry_lock:
            return self._telemetry.motors[motor].encoder

    def getMotorPositions(self) -> tuple[int, int]:
        with self._telemetry_lock:
            return (
                self._telemetry.motors[1].encoder,
                self._telemetry.motors[2].encoder
            )

    def getMotorCurrent(self, motor: int) -> float:
        with self._telemetry_lock:
            return self._telemetry.motors[motor].current

    def getMotorCurrents(self) -> tuple[float, float]:
        with self._telemetry_lock:
            return (
                self._telemetry.motors[1].current,
                self._telemetry.motors[2].current
            )

    # =========================================================================
    #                           CONTROLLER TELEMETRY
    # =========================================================================

    def getVoltage(self) -> float:
        with self._telemetry_lock:
            return self._telemetry.voltage

    def getTemperature(self, sensor: int) -> float:
        with self._telemetry_lock:
            return self._telemetry.temp1 if sensor == 1 else self._telemetry.temp2

    def getControllerStatus(self) -> str:
        with self._telemetry_lock:
            return self._telemetry.status

    def isEstopActive(self) -> bool:
        with self._telemetry_lock:
            return self._telemetry.status == "E-Stop"

    # =========================================================================
    #                           STATE
    # =========================================================================

    def getState(self) -> MotorControllerState:
        with self._state_lock:
            return self._state

    def _set_state(self, new_state: MotorControllerState):
        with self._state_lock:
            if self._state != new_state:
                logger.info(f"State: {self._state.name} -> {new_state.name}")
                self._state = new_state

    # =========================================================================
    #                           BACKGROUND TELEMETRY
    # =========================================================================

    def _telemetry_loop(self):
        poll_interval = 1.0 / self.POLL_RATE_HZ

        while not self._stop_event.is_set():
            try:
                self._poll_telemetry()
            except Exception as e:
                logger.error(f"Telemetry poll failed: {e}")

            self._stop_event.wait(poll_interval)

    def _poll_telemetry(self):
        now = time.time()

        # Read from hardware
        status = self._roboclaw.read_status()
        voltage = self._roboclaw.read_batt_voltage()
        currents = self._roboclaw.read_currents()
        temp1 = self._roboclaw.read_temp_sensor(1)
        temp2 = self._roboclaw.read_temp_sensor(2)

        motor_data: dict[int, MotorTelemetry] = {}

        for motor in [1, 2]:
            enc_data = self._roboclaw.read_encoder_pos(motor)
            speed_data = self._roboclaw.read_encoder_speed(motor)

            motor_data[motor] = MotorTelemetry(
                speed=speed_data["speed"],
                encoder=enc_data["encoder"],
                current=currents[motor - 1],
                direction=speed_data["direction"],
                timestamp=now
            )

        # Update cache atomically
        with self._telemetry_lock:
            self._telemetry.motors = motor_data
            self._telemetry.voltage = voltage
            self._telemetry.status = status
            self._telemetry.temp1 = temp1
            self._telemetry.temp2 = temp2
            self._telemetry.last_update = now
