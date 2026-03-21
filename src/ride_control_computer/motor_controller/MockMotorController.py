from ride_control_computer.motor_controller.MotorController import MotorControllerState, MotorController
from ride_control_computer.motor_controller.MotorData import addSpeed,getSpeeds
import random
import time
import logging
import json


logger = logging.getLogger(__name__)

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

    def homeMotors(self) -> None:
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
        speeds = random.random()*100, random.random()*100
        self.recordSpeed(speeds[0])
        self.recordSpeed(speeds[1])
        return speeds

    def getMotorPosition(self, motor: int) -> int:
        return 0

    def getMotorPositions(self) -> tuple[int, int]:
        return random.randint(0,256), random.randint(0,256)

    def getMotorCurrent(self, motor: int) -> float:
        return 0.0

    def getMotorCurrents(self) -> tuple[float, float]:
        return random.randint(0,10), random.randint(0,10)

    def getVoltage(self) -> float:
        return random.randint(0,100)

    def getTemperature(self, sensor: int) -> float:
        return random.randint(0,100)

    def getTemperatures(self) -> tuple[float, float]:
        return random.randint(0,100), random.randint(0,100)

    def getControllerStatus(self) -> str:
        return "Normal"

    def getRawControllerStatus(self) -> int:
        return 0

    def getLastMotorCommand(self, motor: int) -> tuple[int, int, int, int] | None:
        return None

    def recordSpeed(self,speed):
        addSpeed(speed)


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
