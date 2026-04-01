import time
import pytest
from unittest.mock import MagicMock

from ride_control_computer.ride_sequencer import RideSequencer
from ride_control_computer.ride_profile import RideProfile, ProfileSegment, MotorCommand
from ride_control_computer.motor_controller.MockMotorController import MockMotorController


# ── Test helpers ──────────────────────────────────────────────────────────────

def _cmd(position=1000):
    return MotorCommand(type="driveToPosition", position=position,
                        speed=500, accel=200, decel=200)

def _seg(name="seg", mode="waitForBoth", timeoutS=10.0, durationS=0.0,
         withMotor1=True, withMotor2=True, homeMotors=False):
    return ProfileSegment(
        name=name,
        completionMode=mode,
        timeoutS=timeoutS,
        motor1=_cmd() if withMotor1 else None,
        motor2=_cmd() if withMotor2 else None,
        durationS=durationS,
        homeMotors=homeMotors,
    )

def _profile(*segments):
    return RideProfile(name="Test", rideDurationS=30.0, segments=list(segments))


class ControllableMC(MockMotorController):
    """MockMotorController with per-motor near-target control."""
    def __init__(self):
        super().__init__()
        self._nearTarget = {1: True, 2: True}

    def isMotorNearTarget(self, motor, tolerance=50):
        return self._nearTarget[motor]


# ── start() ───────────────────────────────────────────────────────────────────

class TestStart:

    def testStartIssuesCommandsForBothMotors(self):
        mc = MagicMock(spec=ControllableMC())
        mc.isMotorNearTarget.return_value = False
        seq = RideSequencer(mc, _profile(_seg()))
        seq.start()
        assert mc.driveToPosition.call_count == 2

    def testStartIssuesCommandOnlyForPresentMotors(self):
        mc = MagicMock(spec=ControllableMC())
        mc.isMotorNearTarget.return_value = False
        seq = RideSequencer(mc, _profile(_seg(withMotor2=False)))
        seq.start()
        assert mc.driveToPosition.call_count == 1

    def testStartResetsToFirstSegment(self):
        mc = ControllableMC()
        mc._nearTarget = {1: True, 2: True}
        seq = RideSequencer(mc, _profile(_seg("a"), _seg("b")))
        seq.start()
        seq.tick()  # completes segment 0, advances to 1
        seq.tick()  # completes segment 1, sets complete
        assert seq.isComplete()
        seq.start()  # restart
        assert not seq.isComplete()


# ── Completion modes ──────────────────────────────────────────────────────────

class TestCompletionModes:

    def testWaitForBothCompletesWhenBothNear(self):
        mc = ControllableMC()
        mc._nearTarget = {1: True, 2: True}
        seq = RideSequencer(mc, _profile(_seg(mode="waitForBoth")))
        seq.start()
        seq.tick()
        assert seq.isComplete()

    def testWaitForBothStaysActiveWhenOnlyOneNear(self):
        mc = ControllableMC()
        mc._nearTarget = {1: True, 2: False}
        seq = RideSequencer(mc, _profile(_seg(mode="waitForBoth")))
        seq.start()
        seq.tick()
        assert not seq.isComplete()

    def testWaitForBothStaysActiveWhenNeitherNear(self):
        mc = ControllableMC()
        mc._nearTarget = {1: False, 2: False}
        seq = RideSequencer(mc, _profile(_seg(mode="waitForBoth")))
        seq.start()
        seq.tick()
        assert not seq.isComplete()

    def testWaitForEitherCompletesWhenOneNear(self):
        mc = ControllableMC()
        mc._nearTarget = {1: True, 2: False}
        seq = RideSequencer(mc, _profile(_seg(mode="waitForEither")))
        seq.start()
        seq.tick()
        assert seq.isComplete()

    def testWaitForEitherStaysActiveWhenNeitherNear(self):
        mc = ControllableMC()
        mc._nearTarget = {1: False, 2: False}
        seq = RideSequencer(mc, _profile(_seg(mode="waitForEither")))
        seq.start()
        seq.tick()
        assert not seq.isComplete()

    def testDurationCompletesAfterElapsed(self):
        mc = ControllableMC()
        seq = RideSequencer(mc, _profile(_seg(mode="duration", durationS=0.0)))
        seq.start()
        seq.tick()
        assert seq.isComplete()

    def testDurationStaysActiveBeforeElapsed(self):
        mc = ControllableMC()
        seq = RideSequencer(mc, _profile(_seg(mode="duration", durationS=9999.0)))
        seq.start()
        seq.tick()
        assert not seq.isComplete()

    def testUnknownModeTreatedAsComplete(self):
        mc = ControllableMC()
        seq = RideSequencer(mc, _profile(_seg(mode="unrecognized")))
        seq.start()
        seq.tick()
        assert seq.isComplete()


# ── Multi-segment advancement ─────────────────────────────────────────────────

class TestMultiSegment:

    def testAdvancesToNextSegmentOnCompletion(self):
        mc = MagicMock(spec=ControllableMC())
        mc.isMotorNearTarget.return_value = True
        seq = RideSequencer(mc, _profile(_seg("a"), _seg("b")))
        seq.start()
        seq.tick()  # segment 0 completes → segment 1 starts
        assert not seq.isComplete()

    def testIsCompleteAfterLastSegment(self):
        mc = ControllableMC()
        mc._nearTarget = {1: True, 2: True}
        seq = RideSequencer(mc, _profile(_seg("a"), _seg("b")))
        seq.start()
        seq.tick()  # segment 0 → 1
        seq.tick()  # segment 1 → complete
        assert seq.isComplete()

    def testTickAfterCompleteIsNoop(self):
        mc = ControllableMC()
        mc._nearTarget = {1: True, 2: True}
        seq = RideSequencer(mc, _profile(_seg()))
        seq.start()
        seq.tick()  # completes
        seq.tick()  # should be a no-op
        assert seq.isComplete()

    def testEachSegmentIssuesItsOwnCommands(self):
        mc = MagicMock(spec=ControllableMC())
        mc.isMotorNearTarget.return_value = True
        seq = RideSequencer(mc, _profile(_seg("a"), _seg("b")))
        seq.start()
        seq.tick()  # segment 0 completes, segment 1 starts
        # start() for segment 0 + _startSegment for segment 1 = 4 driveToPosition calls
        assert mc.driveToPosition.call_count == 4


# ── abort() and timeout ───────────────────────────────────────────────────────

class TestAbortAndTimeout:

    def testAbortPreventsAdvancement(self):
        mc = ControllableMC()
        mc._nearTarget = {1: True, 2: True}
        seq = RideSequencer(mc, _profile(_seg("a"), _seg("b")))
        seq.start()
        seq.abort()
        seq.tick()
        assert not seq.isComplete()
        assert not seq._active

    def testTimeoutFiresOnTimeoutCallback(self):
        mc = ControllableMC()
        mc._nearTarget = {1: False, 2: False}
        fired = []
        seq = RideSequencer(mc, _profile(_seg(timeoutS=0.0)),
                            onTimeout=lambda: fired.append(True))
        seq.start()
        seq.tick()
        assert fired == [True]

    def testTimeoutSetsInactive(self):
        mc = ControllableMC()
        mc._nearTarget = {1: False, 2: False}
        seq = RideSequencer(mc, _profile(_seg(timeoutS=0.0)))
        seq.start()
        seq.tick()
        assert not seq._active

    def testTimeoutTakesPriorityOverCompletion(self):
        """Timeout fires even when motors happen to be near target."""
        mc = ControllableMC()
        mc._nearTarget = {1: True, 2: True}
        fired = []
        seq = RideSequencer(mc, _profile(_seg(mode="waitForBoth", timeoutS=0.0)),
                            onTimeout=lambda: fired.append(True))
        seq.start()
        seq.tick()
        assert fired == [True]
        assert not seq.isComplete()

    def testNoTimeoutCallbackIfNoneRegistered(self):
        mc = ControllableMC()
        mc._nearTarget = {1: False, 2: False}
        seq = RideSequencer(mc, _profile(_seg(timeoutS=0.0)))
        seq.start()
        seq.tick()  # should not raise


# ── waitForHome and homeMotors ────────────────────────────────────────────────

class ControllableMCWithHoming(ControllableMC):
    """Adds controllable isHomingComplete() for homing tests."""
    def __init__(self):
        super().__init__()
        self._homingComplete = False

    def isHomingComplete(self):
        return self._homingComplete


class TestHoming:

    def testWaitForHomeCompletesWhenHomingComplete(self):
        mc = ControllableMCWithHoming()
        mc._homingComplete = True
        seq = RideSequencer(mc, _profile(_seg(mode="waitForHome", homeMotors=True,
                                              withMotor1=False, withMotor2=False)))
        seq.start()
        seq.tick()
        assert seq.isComplete()

    def testWaitForHomeStaysActiveWhenNotComplete(self):
        mc = ControllableMCWithHoming()
        mc._homingComplete = False
        seq = RideSequencer(mc, _profile(_seg(mode="waitForHome", homeMotors=True,
                                              withMotor1=False, withMotor2=False)))
        seq.start()
        seq.tick()
        assert not seq.isComplete()

    def testHomeMotorsFlagCallsHomeMotors(self):
        mc = MagicMock(spec=ControllableMCWithHoming())
        mc.isHomingComplete.return_value = False
        seq = RideSequencer(mc, _profile(_seg(mode="waitForHome", homeMotors=True,
                                              withMotor1=False, withMotor2=False)))
        seq.start()
        mc.homeMotors.assert_called_once()

    def testHomeMotorsFlagSkipsDriveToPosition(self):
        mc = MagicMock(spec=ControllableMCWithHoming())
        mc.isHomingComplete.return_value = False
        seq = RideSequencer(mc, _profile(_seg(mode="waitForHome", homeMotors=True,
                                              withMotor1=True, withMotor2=True)))
        seq.start()
        mc.homeMotors.assert_called_once()
        mc.driveToPosition.assert_not_called()
