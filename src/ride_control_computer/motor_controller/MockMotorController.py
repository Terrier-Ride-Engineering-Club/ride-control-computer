from ride_control_computer.motor_controller.MotorController import MotorControllerState, MotorController
import random

class MockMotorController(MotorController):

    def __init__(self):
        super().__init__()

    # =========================================================================
    #                           LIFECYCLE
    # =========================================================================

    def start(self):
        self._state = MotorControllerState.ACTIVE

    def shutdown(self):
        pass

    # =========================================================================
    #                           HEARTBEAT
    # =========================================================================

    def heartbeat(self) -> None:
        pass  # No serial thread to authorize

    # =========================================================================
    #                           COMMANDS
    # =========================================================================

    def driveToPosition(self, motor: int, position: int, speed: int, accel: int, decel: int) -> None:
        pass  # No-op: mock reports isMotorNearTarget=True immediately

    def homeMotors(self, motors: list[int]) -> None:
        pass  # Mock is always at home

    def isAtBottomLimit(self, motor: int) -> bool:
        return True

    def isAtTopLimit(self, motor: int) -> bool:
        return False

    def isMotorNearTarget(self, motor: int, tolerance: int = 50) -> bool:
        return True

    def jogMotor(self, motorNumber: int, direction: int):
        return True

    def stopMotion(self):
        pass

    def haltMotion(self):
        pass

    # =========================================================================
    #                           MOTION STATUS
    # =========================================================================

    def areMotorsStopped(self) -> bool:
        return True

    def isHomingComplete(self) -> bool:
        return True

    # =========================================================================
    #                              TELEMETRY
    # =========================================================================

    def getMotorSpeed(self, motor: int):
        return random.random() * 100, random.random() * 100

    def getMotorSpeeds(self) -> tuple[float, float]:
        return (0.0, 0.0)

    def getMotorPosition(self, motor: int) -> int:
        return 0

    def getMotorPositions(self) -> tuple[int, int]:
        return (0, 0)

    def getMotorCurrent(self, motor: int) -> float:
        return 0.0

    def getMotorCurrents(self) -> tuple[float, float]:
        return (0.0, 0.0)

    def getVoltage(self) -> float:
        return 0.0

    def getTemperature(self, sensor: int) -> float:
        return 0.0

    def getControllerStatus(self) -> str:
        return "Normal"

    def getRawControllerStatus(self) -> int:
        return 0

    def getLastMotorCommand(self, motor: int) -> tuple[int, int, int, int] | None:
        return None

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
