from abc import ABC, abstractmethod
from enum import Enum
from typing import Tuple

class MotorControllerState(Enum):
    IDLE =          0, 
    JOGGING =       1, 
    HOMING =        2, 
    SEQUENCING =    3, 
    STOPPING =      4, 
    DISABLED =      5

class MotorController(ABC):
    """
    Interface for a MotorController.
    """

    _state: MotorControllerState

    def __init__(self):
        ...

    @abstractmethod
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