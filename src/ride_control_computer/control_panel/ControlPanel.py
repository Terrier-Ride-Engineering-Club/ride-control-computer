from abc import ABC, abstractmethod
from typing import List, Callable
from enum import Enum
from functools import partial
from queue import Queue, Empty
from threading import Thread

from ride_control_computer.loop_timer import LoopTimer

class MomentaryButtonState(Enum):
    PRESSED = 1,
    RELEASED = 2
    
class SustainedSwitchState(Enum):
    ON = 1,
    OFF = 2,
    MAINTENANCE = 3

class MomentarySwitchState(Enum):
    UP = 1,
    NEUTRAL = 2,
    DOWN = 3


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
    - Power switch: ON/OFF/MAINTENANCE sustained rotary switch
    - Maintenance Jog switch: UP/N/DOWN momentary rotary switch
    """

    def __init__(self):
        self._loop_timer = LoopTimer()
        self.__callbackQueue: Queue = Queue()
        
        self.__dispatchCallbacks: List[Callable[[], None]] = []
        self.__resetCallbacks: List[Callable[[], None]] = []
        self.__stopCallbacks: List[Callable[[], None]] = []
        self.__estopCallbacks: List[Callable[[], None]] = []
        self.__powerSwitchCallbacks: List[Callable[[], None]] = []
        self.__maintenanceJogSwitchCallbacks: List[Callable[[], None]] = []

    @abstractmethod
    def run(self) -> None:
        """Blocking call which guarantees ControlPanel will keep callbackQueue up to date based on the implementation inputs."""
        ...

    def start(self) -> None:
        """Non-blocking call which calls run() in a seperate daemon thread."""
        Thread(
            target=self.run,
            daemon=True
            ).start()

    def triggerCallbacks(self) -> None:
        """When called by the main thread, this will execute all callbacks in the callback queue."""
        while not self.__callbackQueue.empty():
            try:
                callback = self.__callbackQueue.get_nowait()
                callback()
            except Empty:
                break
            
    # Callback adders
    def addDispatchCallback(self, callback: Callable[[MomentaryButtonState], None]) -> None:
        self.__dispatchCallbacks.append(callback)
    def addResetCallback(self, callback: Callable[[MomentaryButtonState], None]) -> None:
        self.__resetCallbacks.append(callback)
    def addStopCallback(self, callback: Callable[[MomentaryButtonState], None]) -> None:
        self.__stopCallbacks.append(callback)
    def addEstopCallback(self, callback: Callable[[MomentaryButtonState], None]) -> None:
        self.__estopCallbacks.append(callback)
    def addPowerSwitchCallback(self, callback: Callable[[SustainedSwitchState], None]) -> None:
        self.__powerSwitchCallbacks.append(callback)
    def addMaintenanceJogSwitchCallback(self, callback: Callable[[MomentarySwitchState], None]) -> None:
        self.__maintenanceJogSwitchCallbacks.append(callback)
    
    
    def updateIndicators(self, state, hasActiveFaults: bool) -> None:
        """
        Update indicator LEDs based on the current RCC state and fault status.
        Hardware implementations should override this.  The default is a no-op
        so software-only panels (e.g. web UI) need not implement it.
        """
        pass

    @property
    def loopTimer(self) -> LoopTimer:
        return self._loop_timer

    def _addListToCallbackQueue(self, callbackList: List[Callable[[], None]]) -> None:
        for callback in callbackList:
            self.__callbackQueue.put(callback)

    # Protected enqueue helpers for subclasses
    def _enqueueDispatch(self, state: MomentaryButtonState) -> None:
        self._addListToCallbackQueue([partial(cb, state) for cb in self.__dispatchCallbacks])

    def _enqueueReset(self, state: MomentaryButtonState) -> None:
        self._addListToCallbackQueue([partial(cb, state) for cb in self.__resetCallbacks])

    def _enqueueStop(self, state: MomentaryButtonState) -> None:
        self._addListToCallbackQueue([partial(cb, state) for cb in self.__stopCallbacks])

    def _enqueueEstop(self, state: MomentaryButtonState) -> None:
        self._addListToCallbackQueue([partial(cb, state) for cb in self.__estopCallbacks])

    def _enqueueMaintenanceSwitch(self, state: SustainedSwitchState) -> None:
        self._addListToCallbackQueue([partial(cb, state) for cb in self.__powerSwitchCallbacks])

    def _enqueueMaintenanceJogSwitch(self, state: MomentarySwitchState) -> None:
        self._addListToCallbackQueue([partial(cb, state) for cb in self.__maintenanceJogSwitchCallbacks])