import logging
from enum import Enum, auto
from time import sleep
from typing import Callable

from gpiozero import Button, LED

from ride_control_computer.RCC import RCCState
from ride_control_computer.control_panel.ControlPanel import (
    ControlPanel,
    MomentaryButtonState,
    SustainedSwitchState,
    MomentarySwitchState,
)

logger = logging.getLogger(__name__)

# BCM GPIO pin numbers (active-high with internal pull-downs)
PIN_DISPATCH = 10
PIN_RESET = 9
PIN_STOP = 11
PIN_ESTOP = 5
PIN_MAINT_ON = 4           # Maintenance switch "ON" position
PIN_MAINT_MAINTENANCE = 17  # Maintenance switch "MAINTENANCE" position
PIN_JOG_UP = 27              # Jog switch "UP" position
PIN_JOG_DOWN = 22            # Jog switch "DOWN" position

# BCM GPIO pin numbers for button indicator LEDs (active-high, 120VAC control board)
PIN_DISPATCH_LED = 6
PIN_RESET_LED    = 19
PIN_STOP_LED     = 26

DEBOUNCE_TIME       = 0.05  # 50ms debounce
BLINK_PERIOD_S      = 0.5   # on_time and off_time for standard blinking LEDs
BLINK_FAST_PERIOD_S = 0.1   # on_time and off_time for fast blinking LEDs


class _LEDMode(Enum):
    OFF        = auto()
    ON         = auto()
    BLINK      = auto()
    BLINK_FAST = auto()


class _ButtonLED:
    """
    Manages one indicator LED paired with its button.

    Base mode (OFF / ON / BLINK) is set by updateIndicators() each RCC tick.
    While the physical button is held down the LED is unconditionally solid ON;
    on release it returns to whatever the current base mode is.

    setMode() is guarded — it only re-applies gpiozero if the mode actually
    changed, so calling it at 1 kHz will not restart the blink cycle each tick.
    """

    def __init__(self, button: Button, ledPin: int):
        self._led    = LED(ledPin)
        self._button = button
        self._mode   = _LEDMode.OFF
        button.when_pressed  = self._onPress
        button.when_released = self._onRelease

    def setMode(self, mode: _LEDMode) -> None:
        if mode == self._mode:
            return
        self._mode = mode
        if not self._button.is_pressed:
            self._applyMode()

    def _onPress(self) -> None:
        self._led.on()

    def _onRelease(self) -> None:
        self._applyMode()

    def _applyMode(self) -> None:
        if self._mode == _LEDMode.OFF:
            self._led.off()
        elif self._mode == _LEDMode.ON:
            self._led.on()
        elif self._mode == _LEDMode.BLINK:
            self._led.blink(on_time=BLINK_PERIOD_S, off_time=BLINK_PERIOD_S)
        elif self._mode == _LEDMode.BLINK_FAST:
            self._led.blink(on_time=BLINK_FAST_PERIOD_S, off_time=BLINK_FAST_PERIOD_S)


class MomentaryInput:
    """Tracks a single momentary push button with edge detection."""

    def __init__(self, pin: int, enqueue: Callable):
        self.btn = Button(pin, pull_up=False, bounce_time=DEBOUNCE_TIME)
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
        self.btnA = Button(pinA, pull_up=False, bounce_time=DEBOUNCE_TIME)
        self.btnB = Button(pinB, pull_up=False, bounce_time=DEBOUNCE_TIME)
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

        # Indicator LEDs — paired to their respective buttons for press-override
        self._dispatchLED = _ButtonLED(self._buttons[0].btn, PIN_DISPATCH_LED)
        self._resetLED    = _ButtonLED(self._buttons[1].btn, PIN_RESET_LED)
        self._stopLED     = _ButtonLED(self._buttons[2].btn, PIN_STOP_LED)

        logger.info("HardwareControlPanel initialized (pins: dispatch=%d, reset=%d, stop=%d, estop=%d, "
                     "maint_on=%d, maint_maint=%d, jog_up=%d, jog_down=%d)",
                     PIN_DISPATCH, PIN_RESET, PIN_STOP, PIN_ESTOP,
                     PIN_MAINT_ON, PIN_MAINT_MAINTENANCE, PIN_JOG_UP, PIN_JOG_DOWN)

    def updateIndicators(self, state, hasActiveFaults: bool) -> None:
        """
        Update the three button indicator LEDs based on RCC state.

        Dispatch — blinks at 500ms when IDLE (ready to dispatch); off otherwise.
        Reset    — blinks at 500ms when in E-Stop with no active software faults
                   (hardware E-Stop cleared; safe to reset); off otherwise.
        Stop     — no autonomous blink behavior; press-override still lights it
                   solid while held.
        """
        # Dispatch: blink when ready for the operator to dispatch
        self._dispatchLED.setMode(
            _LEDMode.BLINK if state == RCCState.IDLE else _LEDMode.OFF
        )

        # Reset: blink to invite reset when E-Stop can actually be cleared
        self._resetLED.setMode(
            _LEDMode.BLINK if (state == RCCState.ESTOP and not hasActiveFaults)
            else _LEDMode.OFF
        )

        # Stop: fast blink while the ride is actively stopping
        self._stopLED.setMode(
            _LEDMode.BLINK_FAST if state == RCCState.STOPPING else _LEDMode.OFF
        )

    def run(self) -> None:
        # Read initial switch states so we don't fire spurious callbacks on startup
        self._maintSwitch.prevState = self._maintSwitch.read()
        self._jogSwitch.prevState = self._jogSwitch.read()

        logger.info("HardwareControlPanel running (initial maint=%s, jog=%s)",
                     self._maintSwitch.prevState.name, self._jogSwitch.prevState.name)

        while not self._stopEvent.is_set():
            self._loop_timer.tick()

            for button in self._buttons:
                button.poll()
            self._maintSwitch.poll()
            self._jogSwitch.poll()

            sleep(0.1)
