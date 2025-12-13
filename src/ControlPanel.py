from abc import ABC, abstractmethod
from typing import List, Callable
from queue import Queue, Empty

"""
Interface for a control panel.

"""
class ControlPanel(ABC):
    """
    Interface for ride control panel implementations.
    
    Defines the standard interface for control panels that manage ride operations.
    Implementations include hardware control panels and web-based control panels.
    
    The control panel includes:
    - Dispatch button
    - Reset button
    - Stop button
    - E-Stop button
    - Maintenance mode switch: ON/OFF/MAINTENANCE sustained rotary switch
    - Maintenance Jog switch: FWD/N/BWD momentary rotary switch
    """

    def __init__(self):
        self.__callbackQueue: Queue = Queue()
        
        self.__dispatchCallbacks: List[Callable[[], None]] = []
        self.__resetCallbacks: List[Callable[[], None]] = []
        self.__stopCallbacks: List[Callable[[], None]] = []
        self.__estopCallbacks: List[Callable[[], None]] = []
        self.__maintenanceSwitchCallbacks: List[Callable[[], None]] = []
        self.__maintenanceJogSwitchCallbacks: List[Callable[[], None]] = []

    @abstractmethod
    def run(self) -> None:
        """Blocking call which guarantees ControlPanel will keep callbackQueue up to date based on the implementation inputs."""
        ...

    def triggerCallbacks(self) -> None:
        """When called by the main thread, this will execute all callbacks in the callback queue."""
        while not self.__callbackQueue.empty():
            try:
                callback = self.__callbackQueue.get_nowait()
                callback()
            except Empty:
                break
            
    # Callback adders
    def addDispatchCallback(self, callback: Callable[[],None]) -> None:
        self.__dispatchCallbacks.append(callback)
    def addResetCallback(self, callback: Callable[[],None]) -> None:
        self.__resetCallbacks.append(callback)
    def addStopCallback(self, callback: Callable[[],None]) -> None:
        self.__stopCallbacks.append(callback)
    def addEstopCallback(self, callback: Callable[[],None]) -> None:
        self.__estopCallbacks.append(callback)
    def addMaintenanceSwitchCallback(self, callback: Callable[[],None]) -> None:
        self.__maintenanceSwitchCallbacks.append(callback)
    def addMaintenanceJogSwitchCallback(self, callback: Callable[[],None]) -> None:
        self.__maintenanceJogSwitchCallbacks.append(callback)
    
    
    def _addListToCallbackQueue(self, callbackList: List[Callable[[], None]]) -> None:
        for callback in callbackList:
            self.callbackList.append(callback)