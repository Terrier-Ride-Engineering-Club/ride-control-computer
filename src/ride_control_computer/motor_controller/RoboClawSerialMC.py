# RoboClaw motorcontroller TREC's REC Ride Control Computer
    # Made by Jackson Justus (jackjust@bu.edu)

from ride_control_computer.motor_controller.MotorController import MotorController, MotorControllerState

class RoboClawSerialMotorController(MotorController):
    """
    Implementation of MotorController using a RoboClaw Motor Controller over a serial port.
    """

    def __init__(self):
        super().__init__()

    def startRideSequence(self):
        """Starts the ride sequence"""
        ...

    @abstractmethod
    def home(self):
        """Stops the ride sequence and brings the motors to the home position"""
        ...

    @abstractmethod
    def jogMotor(self, motorNumber: int, direction: int) -> bool:
        """
        Jogs the motor continuously in a direction for 10ms.
        Must be called again to keep the motor moving.
        MotorController must be in idle for this to work.

        Returns:
            bool - whether the motor is being jogged.
        """
        ...

    @abstractmethod
    def stopMotion(self):
        """Decelerates gently to a stop"""
        ...

    @abstractmethod
    def haltMotion(self):
        """Immediately stops motion"""
        ...

    @abstractmethod
    def getMotorSpeed(self) -> tuple[float, float]:
        """Gets the motor speed for both towers."""
        ...

    @abstractmethod
    def haltMotion(self):
        """Immediately stops motion"""
        ...

    def getState(self):
        return self._state