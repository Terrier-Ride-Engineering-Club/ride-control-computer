# Motor Controller Abstract Interface for TREC's REC Ride Control Computer
    # Made by Jackson Justus (jackjust@bu.edu)

from abc import ABC, abstractmethod
from enum import Enum

class MotorControllerState(Enum):
    IDLE =          0
    JOGGING =       1
    HOMING =        2
    SEQUENCING =    3
    STOPPING =      4
    DISABLED =      5

class MotorController(ABC):
    """
    Interface for a MotorController.

    This motor controller is responsible for the following:
        1. Talking to an implementation-specific motor controller.
        2. Taking motor start/stop commands.
            a. When given the start command, the motor controller should follow a pre-defined ride sequence.
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
    def startRideSequence(self):
        """Starts the ride sequence."""
        ...

    @abstractmethod
    def home(self):
        """Stops the ride sequence and brings the motors to the home position."""
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
        """Immediately stops motion (emergency stop)."""
        ...

    # =========================================================================
    #                           MOTOR TELEMETRY
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

    # =========================================================================
    #                           CONTROLLER TELEMETRY
    # =========================================================================

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