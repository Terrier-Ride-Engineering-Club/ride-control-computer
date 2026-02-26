import logging
from time import sleep
from typing import Callable

from gpiozero import Button

from ride_control_computer.control_panel.ControlPanel import (
    ControlPanel,
    MomentaryButtonState,
    SustainedSwitchState,
    MomentarySwitchState,
)

logger = logging.getLogger(__name__)

# BCM GPIO pin numbers (active-low with internal pull-ups)
PIN_DISPATCH = 17
PIN_RESET = 27
PIN_STOP = 22
PIN_ESTOP = 23
PIN_MAINT_ON = 24           # Maintenance switch "ON" position
PIN_MAINT_MAINTENANCE = 25  # Maintenance switch "MAINTENANCE" position
PIN_JOG_UP = 5              # Jog switch "UP" position
PIN_JOG_DOWN = 6            # Jog switch "DOWN" position

DEBOUNCE_TIME = 0.05  # 50ms debounce


class MomentaryInput:
    """Tracks a single momentary push button with edge detection."""

    def __init__(self, pin: int, enqueue: Callable):
        self.btn = Button(pin, pull_up=True, bounce_time=DEBOUNCE_TIME)
        self.enqueue = enqueue
        self.wasPressed = False

    def poll(self) -> None:
        pressed = self.btn.is_pressed
        if pressed and not self.wasPressed:
            self.enqueue(MomentaryButtonState.PRESSED)
        elif not pressed and self.wasPressed:
            self.enqueue(MomentaryButtonState.RELEASED)
        self.wasPressed = pressed


class ThreePositionSwitch:
    """Tracks a 3-position switch (2 GPIO pins) with change detection."""

    def __init__(self, pinA: int, pinB: int, stateA, stateB, stateNeutral, enqueue: Callable):
        self.btnA = Button(pinA, pull_up=True, bounce_time=DEBOUNCE_TIME)
        self.btnB = Button(pinB, pull_up=True, bounce_time=DEBOUNCE_TIME)
        self.stateA = stateA
        self.stateB = stateB
        self.stateNeutral = stateNeutral
        self.enqueue = enqueue
        self.prevState = stateNeutral

    def read(self):
        if self.btnA.is_pressed:
            return self.stateA
        elif self.btnB.is_pressed:
            return self.stateB
        return self.stateNeutral

    def poll(self) -> None:
        state = self.read()
        if state != self.prevState:
            self.enqueue(state)
            self.prevState = state


class HardwareControlPanel(ControlPanel):

    def __init__(self):
        super().__init__()

        self._buttons = [
            MomentaryInput(PIN_DISPATCH, self._enqueueDispatch),
            MomentaryInput(PIN_RESET, self._enqueueReset),
            MomentaryInput(PIN_STOP, self._enqueueStop),
            MomentaryInput(PIN_ESTOP, self._enqueueEstop),
        ]

        self._maintSwitch = ThreePositionSwitch(
            PIN_MAINT_ON, PIN_MAINT_MAINTENANCE,
            SustainedSwitchState.ON, SustainedSwitchState.MAINTENANCE, SustainedSwitchState.OFF,
            self._enqueueMaintenanceSwitch,
        )

        self._jogSwitch = ThreePositionSwitch(
            PIN_JOG_UP, PIN_JOG_DOWN,
            MomentarySwitchState.UP, MomentarySwitchState.DOWN, MomentarySwitchState.NEUTRAL,
            self._enqueueMaintenanceJogSwitch,
        )

        logger.info("HardwareControlPanel initialized (pins: dispatch=%d, reset=%d, stop=%d, estop=%d, "
                     "maint_on=%d, maint_maint=%d, jog_up=%d, jog_down=%d)",
                     PIN_DISPATCH, PIN_RESET, PIN_STOP, PIN_ESTOP,
                     PIN_MAINT_ON, PIN_MAINT_MAINTENANCE, PIN_JOG_UP, PIN_JOG_DOWN)

    def run(self) -> None:
        # Read initial switch states so we don't fire spurious callbacks on startup
        self._maintSwitch.prevState = self._maintSwitch.read()
        self._jogSwitch.prevState = self._jogSwitch.read()

        logger.info("HardwareControlPanel running (initial maint=%s, jog=%s)",
                     self._maintSwitch.prevState.name, self._jogSwitch.prevState.name)

        while True:
            self._loop_timer.tick()

            for button in self._buttons:
                button.poll()
            self._maintSwitch.poll()
            self._jogSwitch.poll()

            sleep(0.1)
