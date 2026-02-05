from ride_control_computer.motor_controller.MotorController import MotorControllerState, MotorController
import random
import time

class MockMotorController(MotorController):

    def __init__(self):
        super().__init__()

    # =========================================================================
    #                           LIFECYCLE
    # =========================================================================

    def start(self):
        pass

    def shutdown(self):
        pass

    # =========================================================================
    #                           COMMANDS
    # =========================================================================

    def startRideSequence(self):
        self._state = MotorControllerState.SEQUENCING

    def home(self):
        self._state = MotorControllerState.HOMING

    def jogMotor(self, motorNumber: int, direction: int):
        self._state = MotorControllerState.JOGGING

    def stopMotion(self):
        self._state = MotorControllerState.STOPPING

    def haltMotion(self):
        self._state = MotorControllerState.STOPPING

    # =========================================================================
    #                              TELEMETRY
    # =========================================================================

    def getMotorSpeed(self, motor: int):
        return random.random()*100, random.random()*100

    def getMotorSpeeds(self) -> tuple[float, float]:
        return random.random()*100, random.random()*100

    def getMotorPosition(self, motor: int) -> int:
        pass

    def getMotorPositions(self) -> tuple[int, int]:
        return random.randint(0,10), random.randint(0,10)

    def getMotorCurrent(self, motor: int) -> float:
        pass

    def getMotorCurrents(self) -> tuple[float, float]:
        pass

    def getVoltage(self) -> float:
        pass

    def getTemperature(self, sensor: int) -> float:
        pass

    def getControllerStatus(self) -> str:
        pass

    # =========================================================================
    #                           STATE
    # =========================================================================

    def getState(self) -> MotorControllerState:
        return self._state

    def isEstopActive(self) -> bool:
        return False

    # =========================================================================
    #                           TELEMETRY HEALTH
    # =========================================================================

    def getTelemetryAge(self) -> float:
        return 0.01

    def isTelemetryStale(self, maxAgeSeconds: float | None = None) -> bool:
        return False




        
        