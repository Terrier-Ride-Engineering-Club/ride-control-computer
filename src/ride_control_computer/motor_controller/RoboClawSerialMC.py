# RoboClaw motorcontroller for TREC's REC Ride Control Computer
    # Made by Jackson Justus (jackjust@bu.edu)

import time
import logging
from threading import Thread, Event, Lock

from ride_control_computer.loop_timer import LoopTimer
from ride_control_computer.motor_controller.MotorController import MotorController, MotorControllerState, MotorTelemetry, ControllerTelemetry
from ride_control_computer.motor_controller.RoboClaw import RoboClaw

logger = logging.getLogger(__name__)

class RoboClawSerialMotorController(MotorController):
    """
    Implementation of MotorController using a RoboClaw motor controller over serial.

    Runs a background serial thread that is the sole owner of all RoboClaw I/O.
    Public API methods set state and parameters; the serial thread picks them up
    on its next tick and sends the appropriate commands.
    """

    # --- Configuration ---
    POLL_RATE_HZ = 50
    JOG_SPEED = 500
    JOG_ACCELERATION = 200
    STOP_DECELERATION = 300
    HALT_DECELERATION = 10000
    STOPPED_THRESHOLD = 5  # QPPS — below this, motors are considered stopped

    def __init__(self, roboClaw: RoboClaw):
        super().__init__()

        self._roboClaw = roboClaw

        # State (written by main thread, read by serial thread)
        self._state = MotorControllerState.DISABLED

        # Jog parameters (set by main thread, read by serial thread)
        self._jog_motor: int = 0
        self._jog_direction: int = 0

        # Active deceleration (STOP vs HALT)
        self._active_deceleration: int = self.STOP_DECELERATION

        # Telemetry cache
        self._telemetry = ControllerTelemetry()
        self._telemetry_lock = Lock()

        # Background thread control
        self._stop_event = Event()
        self._control_thread: Thread | None = None


        # Loop timer
        self._loop_timer = LoopTimer()

    # =========================================================================
    #                           LIFECYCLE
    # =========================================================================

    def start(self):
        """Initialize hardware and start the serial communication thread."""
        logger.info("Starting RoboClawSerialMotorController")

        version = self._roboClaw.read_version()
        logger.info(f"Connected to RoboClaw: {version}")

        # Start serial thread
        self._stop_event.clear()
        self._control_thread = Thread(
            target=self._control_loop,
            daemon=True,
            name="RoboClaw-Control"
        )
        self._control_thread.start()
        self._attempt_reset()

    def shutdown(self):
        """Stop all motion and clean up."""
        logger.info("Shutting down RoboClawSerialMotorController")

        self.haltMotion()

        self._stop_event.set()
        if self._control_thread:
            self._control_thread.join(timeout=1.0)

        if self._control_thread is not None and self._control_thread.is_alive():
            logger.error("Control thread failed to shutdown.")

        self._set_state(MotorControllerState.DISABLED)

    # =========================================================================
    #                           COMMANDS
    # =========================================================================

    def startRideSequence(self):
        if self._state != MotorControllerState.IDLE:
            logger.warning(f"Cannot start sequence from state {self._state}")
            return
        self._set_state(MotorControllerState.SEQUENCING)

    def home(self):
        self._set_state(MotorControllerState.HOMING)

    def jogMotor(self, motorNumber: int, direction: int):
        if motorNumber not in (1, 2):
            logger.error(f"Invalid motor number: {motorNumber}")
            return False

        if self._state not in (MotorControllerState.IDLE, MotorControllerState.JOGGING):
            logger.debug(f"Cannot jog from state {self._state}")
            return False

        self._jog_motor = motorNumber
        self._jog_direction = direction
        self._set_state(MotorControllerState.JOGGING)
        return True

    def stopMotion(self):
        self._active_deceleration = self.STOP_DECELERATION
        self._set_state(MotorControllerState.STOPPING)

    def haltMotion(self):
        self._active_deceleration = self.HALT_DECELERATION
        self._set_state(MotorControllerState.STOPPING)

    # =========================================================================
    #                           MOTOR TELEMETRY
    # =========================================================================

    def getMotorSpeed(self, motor: int):
        with self._telemetry_lock:
            return self._telemetry.motors[motor].speed

    def getMotorSpeeds(self) -> tuple[float, float]:
        with self._telemetry_lock:
            return (
                self._telemetry.motors[1].speed,
                self._telemetry.motors[2].speed
            )

    def getMotorPosition(self, motor: int):
        with self._telemetry_lock:
            return self._telemetry.motors[motor].encoder

    def getMotorPositions(self) -> tuple[int, int]:
        with self._telemetry_lock:
            return (
                self._telemetry.motors[1].encoder,
                self._telemetry.motors[2].encoder
            )

    def getMotorCurrent(self, motor: int):
        with self._telemetry_lock:
            return self._telemetry.motors[motor].current

    def getMotorCurrents(self) -> tuple[float, float]:
        with self._telemetry_lock:
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
        with self._telemetry_lock:
            return self._telemetry.voltage

    def getTemperature(self, sensor: int):
        with self._telemetry_lock:
            return self._telemetry.temp1 if sensor == 1 else self._telemetry.temp2

    def getControllerStatus(self):
        with self._telemetry_lock:
            return self._telemetry.status

    def isEstopActive(self):
        with self._telemetry_lock:
            return self._telemetry.status == "E-Stop"

    # =========================================================================
    #                           TELEMETRY HEALTH
    # =========================================================================

    STALE_THRESHOLD_MULTIPLIER = 3

    def getTelemetryAge(self):
        with self._telemetry_lock:
            lastUpdate = self._telemetry.last_update
        if lastUpdate == 0.0:
            return float('inf')
        return time.time() - lastUpdate

    def isTelemetryStale(self, maxAgeSeconds: float | None = None):
        if maxAgeSeconds is None:
            maxAgeSeconds = self.STALE_THRESHOLD_MULTIPLIER / self.POLL_RATE_HZ
        return self.getTelemetryAge() > maxAgeSeconds

    # =========================================================================
    #                           STATE
    # =========================================================================

    def getState(self) -> MotorControllerState:
        return self._state

    def _set_state(self, new_state: MotorControllerState):
        if self._state != new_state:
            logger.info(f"State: {self._state.name} -> {new_state.name}")
            self._state = new_state

    def _attempt_reset(self):
        if self.getState() is not MotorControllerState.DISABLED:    return
        if self.isTelemetryStale():                                 return
        if self.getControllerStatus() is not "Normal":              return
        self._set_state(MotorControllerState.IDLE)

    # =========================================================================
    #                           CONTROL LOOP
    # =========================================================================

    def _control_loop(self):
        poll_interval = 1.0 / self.POLL_RATE_HZ

        while not self._stop_event.is_set():
            self._loop_timer.tick()
            try:
                self._execute_state_action()
                self._poll_telemetry()
                self._check_state_transitions()
            except Exception as e:
                logger.error(f"Control loop error: {e}")

            self._stop_event.wait(poll_interval)

    def _execute_state_action(self):
        """Send the appropriate serial command for the current state."""
        if self._state == MotorControllerState.JOGGING:
            speed = self.JOG_SPEED if self._jog_direction > 0 else -self.JOG_SPEED
            self._roboClaw.set_speed_with_acceleration(self._jog_motor, speed, self.JOG_ACCELERATION)
        elif self._state == MotorControllerState.STOPPING:
            for motor in [1, 2]:
                self._roboClaw.set_speed_with_acceleration(motor, 0, self._active_deceleration)

    def _check_state_transitions(self):
        """Check if the current state should transition."""
        if self._state == MotorControllerState.STOPPING:
            s1, s2 = self.getMotorSpeeds()
            if abs(s1) < self.STOPPED_THRESHOLD and abs(s2) < self.STOPPED_THRESHOLD:
                self._set_state(MotorControllerState.IDLE)

    def _poll_telemetry(self):
        pollingStartTime = time.time()

        # Read from hardware
        status = self._roboClaw.read_status()
        voltage = self._roboClaw.read_batt_voltage()
        currents = self._roboClaw.read_currents()
        temp1 = self._roboClaw.read_temp_sensor(1)
        temp2 = self._roboClaw.read_temp_sensor(2)

        motor_data: dict[int, MotorTelemetry] = {}

        for motor in [1, 2]:
            enc_data = self._roboClaw.read_encoder_pos(motor)
            speed_data = self._roboClaw.read_encoder_speed(motor)

            motor_data[motor] = MotorTelemetry(
                speed=speed_data["speed"],
                encoder=enc_data["encoder"],
                current=currents[motor - 1],
                direction=speed_data["direction"],
                timestamp=pollingStartTime
            )

        pollingEndTime = time.time()
        polling_dt = pollingEndTime-pollingStartTime
        logging.debug(f"Polling took {polling_dt} ms")
        # Update cache atomically
        with self._telemetry_lock:
            self._telemetry.motors = motor_data
            self._telemetry.voltage = voltage
            self._telemetry.status = status
            self._telemetry.temp1 = temp1
            self._telemetry.temp2 = temp2
            self._telemetry.last_update = pollingStartTime
