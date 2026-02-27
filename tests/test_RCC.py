import json
import time
import pytest

from ride_control_computer.RCC import RCC, RCCState
from ride_control_computer.control_panel.MockControlPanel import MockControlPanel
from ride_control_computer.control_panel.ControlPanel import MomentaryButtonState, SustainedSwitchState
from ride_control_computer.motor_controller.MockMotorController import MockMotorController
from ride_control_computer.theming_controller.MockThemeingController import MockThemingController


# ── Controllable MC ───────────────────────────────────────────────────────────

class ControllableMC(MockMotorController):
    """MockMotorController with individually overridable safety signals."""
    def __init__(self):
        super().__init__()
        self.telemetryStale   = False
        self.estopActive      = False
        self.homingComplete   = True
        self.controllerStatus = "Normal"
        self.speeds           = (0.0, 0.0)

    def isTelemetryStale(self, maxAgeSeconds=None): return self.telemetryStale
    def isEstopActive(self):                        return self.estopActive
    def isHomingComplete(self):                     return self.homingComplete
    def getControllerStatus(self):                  return self.controllerStatus
    def getMotorSpeeds(self):                       return self.speeds


# ── Minimal webserver stub ────────────────────────────────────────────────────

class _NullWebserver:
    """Webserver stub that does nothing; avoids Flask/Waitress import side-effects."""
    def start(self): pass


# ── Minimal ride profile ──────────────────────────────────────────────────────

_PROFILE = {
    "name": "Test",
    "rideDurationS": 30.0,
    "segments": [
        {
            "name": "Lift",
            "completionMode": "waitForBoth",
            "timeoutS": 10.0,
            "motor1": {"type": "driveToPosition", "position": 1000,
                       "speed": 500, "accel": 200, "decel": 200},
            "motor2": {"type": "driveToPosition", "position": 1000,
                       "speed": 500, "accel": 200, "decel": 200},
        }
    ],
}


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mc():
    ctrl = ControllableMC()
    ctrl.start()  # → ACTIVE state
    return ctrl

@pytest.fixture
def panel():
    return MockControlPanel()

@pytest.fixture
def rcc(mc, panel, tmp_path, monkeypatch):
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps(_PROFILE))
    monkeypatch.setattr(RCC, "PROFILE_PATH", str(profile_path))
    tc = MockThemingController()
    return RCC(mc, panel, tc, _NullWebserver())


# ── Helpers ───────────────────────────────────────────────────────────────────

def _tick(rcc):
    """Single main-loop iteration: process inputs → update state → monitor safety."""
    rcc._RCC__processInputs()
    rcc._RCC__updateState()
    rcc._RCC__monitorSafety()

def _press(rcc, handler: str):
    """Call a button-press handler directly, bypassing the callback queue."""
    getattr(rcc, f"_RCC__{handler}")(MomentaryButtonState.PRESSED)

def _release(rcc, handler: str):
    getattr(rcc, f"_RCC__{handler}")(MomentaryButtonState.RELEASED)

def _switch(rcc, state: SustainedSwitchState):
    rcc._RCC__onPowerSwitch(state)

def _rewindEntryTime(rcc, extraSeconds=1.0):
    """Move __stateEntryTime into the past so timed transitions fire immediately."""
    rcc._RCC__stateEntryTime = time.monotonic() - extraSeconds


# ── Initial state ─────────────────────────────────────────────────────────────

class TestInitialState:

    def testStartsInIdle(self, rcc):
        assert rcc.getState() == RCCState.IDLE


# ── Dispatch ──────────────────────────────────────────────────────────────────

class TestDispatch:

    def testDispatchFromIdleGoesToRunning(self, rcc):
        _press(rcc, "onDispatch")
        assert rcc.getState() == RCCState.RUNNING

    def testDispatchFromEstopIgnored(self, rcc):
        rcc._RCC__setState(RCCState.ESTOP)
        _press(rcc, "onDispatch")
        assert rcc.getState() == RCCState.ESTOP

    def testDispatchFromRunningIgnored(self, rcc):
        rcc._RCC__setState(RCCState.RUNNING)
        _press(rcc, "onDispatch")
        assert rcc.getState() == RCCState.RUNNING

    def testDispatchFromMaintenanceIgnored(self, rcc):
        rcc._RCC__setState(RCCState.MAINTENANCE)
        _press(rcc, "onDispatch")
        assert rcc.getState() == RCCState.MAINTENANCE

    def testDispatchReleaseIsNoop(self, rcc):
        _release(rcc, "onDispatch")
        assert rcc.getState() == RCCState.IDLE


# ── Stop ──────────────────────────────────────────────────────────────────────

class TestStop:

    def testStopFromRunningGoesToStopping(self, rcc):
        rcc._RCC__setState(RCCState.RUNNING)
        _press(rcc, "onStop")
        assert rcc.getState() == RCCState.STOPPING

    def testStopFromIdleIgnored(self, rcc):
        _press(rcc, "onStop")
        assert rcc.getState() == RCCState.IDLE

    def testStopFromEstopIgnored(self, rcc):
        rcc._RCC__setState(RCCState.ESTOP)
        _press(rcc, "onStop")
        assert rcc.getState() == RCCState.ESTOP


# ── E-Stop ────────────────────────────────────────────────────────────────────

class TestEstop:

    def testEstopFromIdleLatches(self, rcc):
        _press(rcc, "onEstop")
        assert rcc.getState() == RCCState.ESTOP

    def testEstopFromRunningLatches(self, rcc):
        rcc._RCC__setState(RCCState.RUNNING)
        _press(rcc, "onEstop")
        assert rcc.getState() == RCCState.ESTOP

    def testEstopFromMaintenanceLatches(self, rcc):
        rcc._RCC__setState(RCCState.MAINTENANCE)
        _press(rcc, "onEstop")
        assert rcc.getState() == RCCState.ESTOP

    def testEstopFromEstopIsNoop(self, rcc):
        rcc._RCC__setState(RCCState.ESTOP)
        _press(rcc, "onEstop")
        assert rcc.getState() == RCCState.ESTOP


# ── Reset ─────────────────────────────────────────────────────────────────────

class TestReset:

    def testResetFromEstopGoesToResetting(self, rcc, mc):
        rcc._RCC__setState(RCCState.ESTOP)
        mc.estopActive = False
        _press(rcc, "onReset")
        assert rcc.getState() == RCCState.RESETTING

    def testResetBlockedWhileHardwareEstopActive(self, rcc, mc):
        rcc._RCC__setState(RCCState.ESTOP)
        mc.estopActive = True
        _press(rcc, "onReset")
        assert rcc.getState() == RCCState.ESTOP

    def testResetFromIdleIgnored(self, rcc):
        _press(rcc, "onReset")
        assert rcc.getState() == RCCState.IDLE

    def testResetFromRunningIgnored(self, rcc):
        rcc._RCC__setState(RCCState.RUNNING)
        _press(rcc, "onReset")
        assert rcc.getState() == RCCState.RUNNING


# ── Key switch ────────────────────────────────────────────────────────────────

class TestPowerSwitch:

    def testKeyOffFromIdleGoesToOff(self, rcc):
        _switch(rcc, SustainedSwitchState.OFF)
        assert rcc.getState() == RCCState.OFF

    def testKeyOnFromOffGoesToIdle(self, rcc):
        rcc._RCC__setState(RCCState.OFF)
        _switch(rcc, SustainedSwitchState.ON)
        assert rcc.getState() == RCCState.IDLE

    def testKeyMaintenanceFromIdleGoesToMaintenance(self, rcc):
        _switch(rcc, SustainedSwitchState.MAINTENANCE)
        assert rcc.getState() == RCCState.MAINTENANCE

    def testKeyOnFromMaintenanceGoesToIdle(self, rcc):
        rcc._RCC__setState(RCCState.MAINTENANCE)
        _switch(rcc, SustainedSwitchState.ON)
        assert rcc.getState() == RCCState.IDLE

    def testKeyMaintenanceDuringRunningGoesToEstop(self, rcc):
        rcc._RCC__setState(RCCState.RUNNING)
        _switch(rcc, SustainedSwitchState.MAINTENANCE)
        assert rcc.getState() == RCCState.ESTOP

    def testKeyOffDuringRunningIgnored(self, rcc):
        rcc._RCC__setState(RCCState.RUNNING)
        _switch(rcc, SustainedSwitchState.OFF)
        assert rcc.getState() == RCCState.RUNNING

    def testKeyOffDuringEstopIgnored(self, rcc):
        rcc._RCC__setState(RCCState.ESTOP)
        _switch(rcc, SustainedSwitchState.OFF)
        assert rcc.getState() == RCCState.ESTOP


# ── Timed state transitions ───────────────────────────────────────────────────

class TestTimedTransitions:

    def testStoppingToIdleWhenHomingComplete(self, rcc, mc):
        rcc._RCC__setState(RCCState.STOPPING)
        mc.homingComplete = True
        _tick(rcc)
        assert rcc.getState() == RCCState.IDLE

    def testStoppingToEstopOnTimeout(self, rcc, mc):
        rcc._RCC__setState(RCCState.STOPPING)
        mc.homingComplete = False
        _rewindEntryTime(rcc, rcc.STOPPING_TIMEOUT_S + 1)
        _tick(rcc)
        assert rcc.getState() == RCCState.ESTOP

    def testStoppingTimeoutTakesPriorityOverHoming(self, rcc, mc):
        """If timeout and homing both happen simultaneously, timeout wins."""
        rcc._RCC__setState(RCCState.STOPPING)
        mc.homingComplete = True
        _rewindEntryTime(rcc, rcc.STOPPING_TIMEOUT_S + 1)
        _tick(rcc)
        assert rcc.getState() == RCCState.ESTOP

    def testResettingToIdleAfterWindowWithNoFaults(self, rcc):
        rcc._RCC__setState(RCCState.RESETTING)
        _rewindEntryTime(rcc, rcc.RESETTING_DURATION_S + 1)
        _tick(rcc)
        assert rcc.getState() == RCCState.IDLE

    def testResettingToEstopWhenFaultsRemainAfterWindow(self, rcc, mc):
        rcc._RCC__setState(RCCState.RESETTING)
        mc.telemetryStale = True  # will activate MC_COMM_FAILURE
        _rewindEntryTime(rcc, rcc.RESETTING_DURATION_S + 1)
        _tick(rcc)
        assert rcc.getState() == RCCState.ESTOP

    def testResettingToMaintenanceWhenPreEstopWasMaintenance(self, rcc):
        rcc._RCC__setState(RCCState.MAINTENANCE)
        rcc._RCC__setState(RCCState.ESTOP)      # records preEstopState = MAINTENANCE
        rcc._RCC__setState(RCCState.RESETTING)
        _rewindEntryTime(rcc, rcc.RESETTING_DURATION_S + 1)
        _tick(rcc)
        assert rcc.getState() == RCCState.MAINTENANCE

    def testResettingWindowNotElapsedStaysInResetting(self, rcc):
        rcc._RCC__setState(RCCState.RESETTING)
        # stateEntryTime is already set to now by __setState; do not rewind
        _tick(rcc)
        assert rcc.getState() == RCCState.RESETTING


# ── Fault monitor integration ─────────────────────────────────────────────────

class TestFaultIntegration:

    def testCommFailureFromIdleGoesToEstop(self, rcc, mc):
        mc.telemetryStale = True
        _tick(rcc)
        assert rcc.getState() == RCCState.ESTOP

    def testCommFailureFromRunningGoesToEstop(self, rcc, mc):
        rcc._RCC__setState(RCCState.RUNNING)
        mc.telemetryStale = True
        _tick(rcc)
        assert rcc.getState() == RCCState.ESTOP

    def testHardwareEstopFaultTriggersEstop(self, rcc, mc):
        mc.estopActive = True
        _tick(rcc)
        assert rcc.getState() == RCCState.ESTOP

    def testAbnormalMCStatusTriggersEstop(self, rcc, mc):
        mc.controllerStatus = "M1 Over Current Warning"
        _tick(rcc)
        assert rcc.getState() == RCCState.ESTOP

    def testNormalConditionsNoFault(self, rcc, mc):
        mc.telemetryStale   = False
        mc.estopActive      = False
        mc.controllerStatus = "Normal"
        _tick(rcc)
        assert rcc.getState() == RCCState.IDLE

    def testFaultSkippedWhenAlreadyInEstop(self, rcc, mc):
        """Safety monitor must not cascade or raise when already in ESTOP."""
        rcc._RCC__setState(RCCState.ESTOP)
        mc.telemetryStale = True
        _tick(rcc)
        assert rcc.getState() == RCCState.ESTOP

    def testFaultSkippedInOffState(self, rcc, mc):
        rcc._RCC__setState(RCCState.OFF)
        mc.telemetryStale = True
        _tick(rcc)
        assert rcc.getState() == RCCState.OFF

    def testFaultSkippedInFaultState(self, rcc, mc):
        rcc._RCC__setState(RCCState.FAULT)
        mc.telemetryStale = True
        _tick(rcc)
        assert rcc.getState() == RCCState.FAULT

    def testHighFaultOnlyTriggersOnce(self, rcc, mc):
        """A fault that stays active should not repeatedly re-trigger ESTOP → ESTOP."""
        mc.telemetryStale = True
        _tick(rcc)
        assert rcc.getState() == RCCState.ESTOP
        # Second tick: still in ESTOP, monitoring is suppressed
        _tick(rcc)
        assert rcc.getState() == RCCState.ESTOP


# ── Callback queue integration ────────────────────────────────────────────────

class TestCallbackQueue:

    def testButtonPressViaQueueTriggersTransition(self, rcc, panel):
        """Verify the full path: panel enqueues → processInputs drains → state changes."""
        panel._enqueueDispatch(MomentaryButtonState.PRESSED)
        _tick(rcc)
        assert rcc.getState() == RCCState.RUNNING

    def testCallbackNotFiredUntilProcessInputs(self, rcc, panel):
        panel._enqueueDispatch(MomentaryButtonState.PRESSED)
        # State should not change before processInputs is called
        assert rcc.getState() == RCCState.IDLE
        rcc._RCC__processInputs()
        assert rcc.getState() == RCCState.RUNNING
