# Motor Controller Abstract Interface for TREC's REC Ride Control Computer
    # Made by Jackson Justus (jackjust@bu.edu)

from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional

from ride_control_computer.loop_timer import LoopTimer

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
    rawStatus: int = 0
    temp1: float = 0.0
    temp2: float = 0.0
    lastUpdate: float = 0.0

class MotorControllerState(Enum):
    DISABLED = 0
    IDLE     = 1
    JOGGING  = 2
    HOMING   = 3   # Driving toward bottom limit switch
    STOPPING = 4

class MotorController(ABC):
    """
    Interface for a MotorController.

    This motor controller is responsible for the following:
        1. Talking to an implementation-specific motor controller.
        2. Executing motor commands (position, jog, stop, home).
        3. Providing feedback on the state of the motor controller, including motor speed, temp, etc.
            a. This information is available via get() functions in this interface.
    """

    _state: MotorControllerState

    def __init__(self):
        self._state = MotorControllerState.DISABLED

    # =========================================================================
    #                           LIFECYCLE
    # =========================================================================

    @abstractmethod
    def start(self):
        """Initialize hardware and begin background operations."""
        ...

    @abstractmethod
    def shutdown(self):
        """Stop all motion and release resources."""
        ...

    # =========================================================================
    #                           COMMANDS
    # =========================================================================

    @abstractmethod
    def driveToPosition(self, motor: int, position: int, speed: int, accel: int, decel: int) -> None:
        """
        Drive motor to an absolute encoder position (fire-and-forget; hardware manages motion).

        Args:
            motor: Motor number (1 or 2)
            position: Target encoder count
            speed: Max speed in QPPS
            accel: Acceleration in QPPS/s
            decel: Deceleration in QPPS/s
        """
        ...

    @abstractmethod
    def homeMotors(self, motors: list[int]) -> None:
        """
        Drive specified motors toward the bottom limit switch at homing speed.
        Stops each motor when its bottom limit switch is triggered.
        Sets MC state to HOMING; transitions to IDLE when all motors reach home.

        Args:
            motors: List of motor numbers to home (e.g. [1, 2])
        """
        ...

    @abstractmethod
    def isAtBottomLimit(self, motor: int) -> bool:
        """True if the bottom limit switch for this motor is currently active."""
        ...

    @abstractmethod
    def isAtTopLimit(self, motor: int) -> bool:
        """True if the top limit switch for this motor is currently active."""
        ...

    @abstractmethod
    def isMotorNearTarget(self, motor: int, tolerance: int = 50) -> bool:
        """
        True if the motor encoder is within tolerance counts of the last commanded position.

        Args:
            motor: Motor number (1 or 2)
            tolerance: Acceptable error in encoder counts
        """
        ...

    @abstractmethod
    def jogMotor(self, motorNumber: int, direction: int) -> bool:
        """
        Jogs the motor continuously in a direction for 10ms.
        Must be called again to keep the motor moving.
        MotorController must be in IDLE for this to work.

        Args:
            motorNumber: Motor identifier (1 or 2)
            direction: Positive for forward, negative for backward

        Returns:
            True if jog command was accepted, False otherwise.
        """
        ...

    @abstractmethod
    def stopMotion(self):
        """Decelerates gently to a stop."""
        ...

    @abstractmethod
    def haltMotion(self):
        """Immediately stops motion"""
        ...

    # =========================================================================
    #                               TELEMETRY
    # =========================================================================

    @abstractmethod
    def getMotorSpeed(self, motor: int) -> float:
        """
        Gets the speed for a single motor.

        Args:
            motor: Motor number (1 or 2)

        Returns:
            Speed in QPPS (quad pulses per second). Sign indicates direction.
        """
        ...

    @abstractmethod
    def getMotorSpeeds(self) -> tuple[float, float]:
        """
        Gets the motor speeds for both motors.

        Returns:
            Tuple of (motor1_speed, motor2_speed) in QPPS.
        """
        ...

    @abstractmethod
    def getMotorPosition(self, motor: int) -> int:
        """
        Gets the encoder position for a single motor.

        Args:
            motor: Motor number (1 or 2)

        Returns:
            Encoder count (signed).
        """
        ...

    @abstractmethod
    def getMotorPositions(self) -> tuple[int, int]:
        """
        Gets the encoder positions for both motors.

        Returns:
            Tuple of (motor1_position, motor2_position) in encoder counts.
        """
        ...

    @abstractmethod
    def getMotorCurrent(self, motor: int) -> float:
        """
        Gets the current draw for a single motor.

        Args:
            motor: Motor number (1 or 2)

        Returns:
            Current in amps.
        """
        ...

    @abstractmethod
    def getMotorCurrents(self) -> tuple[float, float]:
        """
        Gets the current draw for both motors.

        Returns:
            Tuple of (motor1_current, motor2_current) in amps.
        """
        ...

    @abstractmethod
    def getVoltage(self) -> float:
        """
        Gets the main battery voltage.

        Returns:
            Voltage in volts.
        """
        ...

    @abstractmethod
    def getTemperature(self, sensor: int) -> float:
        """
        Gets temperature from a sensor.

        Args:
            sensor: Sensor number (1 or 2)

        Returns:
            Temperature in degrees Celsius.
        """
        ...

    @abstractmethod
    def getControllerStatus(self) -> str:
        """
        Gets the current error/status state of the hardware controller.

        Returns:
            Human-readable status string (e.g., "Normal", "E-Stop", "M1 Over Current Warning")
        """
        ...

    @abstractmethod
    def getRawControllerStatus(self) -> int:
        """
        Gets the raw hardware status register value.

        Returns:
            Raw uint32 status register (0 = Normal).
        """
        ...

    @abstractmethod
    def getLastMotorCommand(self, motor: int) -> tuple[int, int, int, int] | None:
        """
        Gets the last position command issued to a motor.

        Args:
            motor: Motor number (1 or 2)

        Returns:
            (position, speed, accel, decel) tuple, or None if no command has been issued.
        """
        ...

    @property
    def loopTimer(self) -> Optional[LoopTimer]:
        """Returns the telemetry loop timer, or None if not implemented by child."""
        return None

    # =========================================================================
    #                           STATE
    # =========================================================================


    def getState(self) -> MotorControllerState:
        """Gets the current state of the motor controller."""
        return self._state

    @abstractmethod
    def isEstopActive(self) -> bool:
        """
        Checks if the emergency stop is currently active.

        Returns:
            True if E-Stop is active.
        """
        ...

    # =========================================================================
    #                           TELEMETRY HEALTH
    # =========================================================================

    @abstractmethod
    def getTelemetryAge(self) -> float:
        """
        Gets the time in seconds since telemetry was last successfully updated.

        Returns:
            Seconds since last telemetry update. Returns float('inf') if
            telemetry has never been updated.
        """
        ...

    @abstractmethod
    def isTelemetryStale(self, maxAgeSeconds: float | None = None) -> bool:
        """
        Checks if telemetry data is stale (i.e., not being updated in time).

        Args:
            maxAgeSeconds: Maximum acceptable age in seconds. If None, defaults
                to 3x the implementation's expected poll interval.

        Returns:
            True if telemetry data is older than the threshold.
        """
        ...