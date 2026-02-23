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

    def driveToPosition(self, motor: int, position: int, speed: int, accel: int, decel: int) -> None:
        pass  # No-op: mock reports isMotorNearTarget=True immediately

    def homeMotors(self, motors: list[int]) -> None:
        # All mock motors are always at home; transition directly to IDLE
        self._state = MotorControllerState.IDLE

    def isAtBottomLimit(self, motor: int) -> bool:
        return True

    def isAtTopLimit(self, motor: int) -> bool:
        return False

    def isMotorNearTarget(self, motor: int, tolerance: int = 50) -> bool:
        return True

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
        pass

    def getMotorPosition(self, motor: int) -> int:
        pass

    def getMotorPositions(self) -> tuple[int, int]:
        pass

    def getMotorCurrent(self, motor: int) -> float:
        pass

    def getMotorCurrents(self) -> tuple[float, float]:
        pass

    def getVoltage(self) -> float:
        pass

    def getTemperature(self, sensor: int) -> float:
        pass

    def getControllerStatus(self) -> str:
        return "Normal"

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
