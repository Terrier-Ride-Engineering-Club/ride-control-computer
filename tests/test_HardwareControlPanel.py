import pytest
pytest.importorskip("gpiozero")
from gpiozero import Device
from gpiozero.pins.mock import MockFactory

from ride_control_computer.control_panel.ControlPanel import (
    MomentaryButtonState,
    SustainedSwitchState,
    MomentarySwitchState,
)
from ride_control_computer.control_panel.HardwareControlPanel import (
    HardwareControlPanel,
    MomentaryInput,
    ThreePositionSwitch,
)


@pytest.fixture(autouse=True)
def mockGpioFactory():
    """Install a mock GPIO pin factory for every test, then tear it down."""
    factory = MockFactory()
    Device.pin_factory = factory
    yield factory
    factory.reset()


# ---------------------------------------------------------------------------
# MomentaryInput unit tests
# ---------------------------------------------------------------------------
class TestMomentaryInput:

    def testPressEnqueuesPressed(self):
        received = []
        inp = MomentaryInput(17, received.append)
        inp.btn.pin.drive_high()
        inp.poll()
        assert received == [MomentaryButtonState.PRESSED]

    def testReleaseEnqueuesReleased(self):
        received = []
        inp = MomentaryInput(17, received.append)
        inp.btn.pin.drive_high()
        inp.poll()
        received.clear()
        inp.btn.pin.drive_low()
        inp.poll()
        assert received == [MomentaryButtonState.RELEASED]

    def testNoDuplicateOnSameState(self):
        received = []
        inp = MomentaryInput(17, received.append)
        inp.btn.pin.drive_high()
        inp.poll()
        received.clear()
        inp.poll()
        assert received == []

    def testMultiplePressReleaseCycles(self):
        received = []
        inp = MomentaryInput(17, received.append)
        inp.btn.pin.drive_high()
        inp.poll()
        inp.btn.pin.drive_low()
        inp.poll()
        inp.btn.pin.drive_high()
        inp.poll()
        assert received == [
            MomentaryButtonState.PRESSED,
            MomentaryButtonState.RELEASED,
            MomentaryButtonState.PRESSED,
        ]


# ---------------------------------------------------------------------------
# ThreePositionSwitch unit tests
# ---------------------------------------------------------------------------
class TestThreePositionSwitch:

    def _makeSwitch(self, enqueue):
        return ThreePositionSwitch(
            24, 25,
            SustainedSwitchState.ON,
            SustainedSwitchState.MAINTENANCE,
            SustainedSwitchState.OFF,
            enqueue,
        )

    def testSwitchToPositionA(self):
        received = []
        sw = self._makeSwitch(received.append)
        sw.btnA.pin.drive_high()
        sw.poll()
        assert received == [SustainedSwitchState.ON]

    def testSwitchToPositionB(self):
        received = []
        sw = self._makeSwitch(received.append)
        sw.btnB.pin.drive_high()
        sw.poll()
        assert received == [SustainedSwitchState.MAINTENANCE]

    def testReturnToNeutral(self):
        received = []
        sw = self._makeSwitch(received.append)
        sw.btnA.pin.drive_high()
        sw.poll()
        received.clear()
        sw.btnA.pin.drive_low()
        sw.poll()
        assert received == [SustainedSwitchState.OFF]

    def testNoDuplicateOnSameState(self):
        received = []
        sw = self._makeSwitch(received.append)
        sw.btnA.pin.drive_high()
        sw.poll()
        received.clear()
        sw.poll()
        assert received == []

    def testReadReturnsCurrentState(self):
        sw = self._makeSwitch(lambda _: None)
        assert sw.read() == SustainedSwitchState.OFF
        sw.btnA.pin.drive_high()
        assert sw.read() == SustainedSwitchState.ON
        sw.btnA.pin.drive_low()
        sw.btnB.pin.drive_high()
        assert sw.read() == SustainedSwitchState.MAINTENANCE


# ---------------------------------------------------------------------------
# HardwareControlPanel integration tests
# ---------------------------------------------------------------------------
class TestHardwareControlPanel:

    def _pollOnce(self, panel):
        """Simulate one iteration of the polling loop."""
        for button in panel._buttons:
            button.poll()
        panel._maintSwitch.poll()
        panel._jogSwitch.poll()

    def testDispatchPressAndRelease(self):
        panel = HardwareControlPanel()
        received = []
        panel.addDispatchCallback(received.append)

        panel._buttons[0].btn.pin.drive_high()
        self._pollOnce(panel)
        panel.triggerCallbacks()
        assert received == [MomentaryButtonState.PRESSED]

        received.clear()
        panel._buttons[0].btn.pin.drive_low()
        self._pollOnce(panel)
        panel.triggerCallbacks()
        assert received == [MomentaryButtonState.RELEASED]

    def testResetCallback(self):
        panel = HardwareControlPanel()
        received = []
        panel.addResetCallback(received.append)

        panel._buttons[1].btn.pin.drive_high()
        self._pollOnce(panel)
        panel.triggerCallbacks()
        assert received == [MomentaryButtonState.PRESSED]

    def testStopCallback(self):
        panel = HardwareControlPanel()
        received = []
        panel.addStopCallback(received.append)

        panel._buttons[2].btn.pin.drive_high()
        self._pollOnce(panel)
        panel.triggerCallbacks()
        assert received == [MomentaryButtonState.PRESSED]

    def testEstopCallback(self):
        panel = HardwareControlPanel()
        received = []
        panel.addEstopCallback(received.append)

        panel._buttons[3].btn.pin.drive_high()
        self._pollOnce(panel)
        panel.triggerCallbacks()
        assert received == [MomentaryButtonState.PRESSED]

    def testMaintenanceSwitchAllPositions(self):
        panel = HardwareControlPanel()
        received = []
        panel.addPowerSwitchCallback(received.append)

        # OFF -> ON
        panel._maintSwitch.btnA.pin.drive_high()
        self._pollOnce(panel)
        panel.triggerCallbacks()
        assert received[-1] == SustainedSwitchState.ON

        # ON -> MAINTENANCE
        panel._maintSwitch.btnA.pin.drive_low()
        panel._maintSwitch.btnB.pin.drive_high()
        self._pollOnce(panel)
        panel.triggerCallbacks()
        assert received[-1] == SustainedSwitchState.MAINTENANCE

        # MAINTENANCE -> OFF
        panel._maintSwitch.btnB.pin.drive_low()
        self._pollOnce(panel)
        panel.triggerCallbacks()
        assert received[-1] == SustainedSwitchState.OFF

        assert len(received) == 3

    def testJogSwitchAllPositions(self):
        panel = HardwareControlPanel()
        received = []
        panel.addMaintenanceJogSwitchCallback(received.append)

        # NEUTRAL -> UP
        panel._jogSwitch.btnA.pin.drive_high()
        self._pollOnce(panel)
        panel.triggerCallbacks()
        assert received[-1] == MomentarySwitchState.UP

        # UP -> NEUTRAL
        panel._jogSwitch.btnA.pin.drive_low()
        self._pollOnce(panel)
        panel.triggerCallbacks()
        assert received[-1] == MomentarySwitchState.NEUTRAL

        # NEUTRAL -> DOWN
        panel._jogSwitch.btnB.pin.drive_high()
        self._pollOnce(panel)
        panel.triggerCallbacks()
        assert received[-1] == MomentarySwitchState.DOWN

        assert len(received) == 3

    def testMultipleCallbacksAllFire(self):
        panel = HardwareControlPanel()
        receivedA = []
        receivedB = []
        panel.addDispatchCallback(receivedA.append)
        panel.addDispatchCallback(receivedB.append)

        panel._buttons[0].btn.pin.drive_high()
        self._pollOnce(panel)
        panel.triggerCallbacks()

        assert receivedA == [MomentaryButtonState.PRESSED]
        assert receivedB == [MomentaryButtonState.PRESSED]

    def testNoSpuriousCallbacksOnIdlePoll(self):
        panel = HardwareControlPanel()
        received = []
        panel.addDispatchCallback(received.append)
        panel.addResetCallback(received.append)
        panel.addStopCallback(received.append)
        panel.addEstopCallback(received.append)
        panel.addPowerSwitchCallback(received.append)
        panel.addMaintenanceJogSwitchCallback(received.append)

        for _ in range(5):
            self._pollOnce(panel)
        panel.triggerCallbacks()
        assert received == []

    def testCallbacksOnlyFireOnTrigger(self):
        """Callbacks enqueued by poll are not executed until triggerCallbacks."""
        panel = HardwareControlPanel()
        received = []
        panel.addDispatchCallback(received.append)

        panel._buttons[0].btn.pin.drive_high()
        self._pollOnce(panel)
        assert received == []

        panel.triggerCallbacks()
        assert received == [MomentaryButtonState.PRESSED]