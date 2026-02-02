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
        # TODO
        ...

    def home(self):
        # TODO
        ...

    def jogMotor(self, motorNumber: int, direction: int) -> bool:
        # TODO

        ...

    def stopMotion(self):
        # TODO
        ...

    def haltMotion(self):
        # TODO
        ...

    def getMotorSpeed(self) -> tuple[float, float]:
        # TODO
        ...

