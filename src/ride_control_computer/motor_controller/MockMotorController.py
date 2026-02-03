from ride_control_computer.motor_controller.MotorController import MotorControllerState, MotorController
import random
import time

class MockMotorController(MotorController):

    def startRideSequence(self):
        self._state = MotorControllerState.SEQUENCING

    def home(self):
        self._state = MotorControllerState.HOMING
    
    def jogMotor(self, motorNumber: int, direction: int) -> bool:
        self._state = MotorControllerState.JOGGING
        
    def stopMotion(self):
        self._state = MotorControllerState.STOPPING

    def haltMotion(self):
        self._state = MotorControllerState.STOPPING

    def getMotorSpeed(self) -> tuple[float, float]:
        return random.random()*100, random.random()*100

    def getState(self) -> MotorControllerState:
        return 1
        
        
        