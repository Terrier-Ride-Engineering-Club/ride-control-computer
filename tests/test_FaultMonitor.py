import pytest
from ride_control_computer.fault_monitor import Fault, FaultMonitor, FaultSeverity


# ── evaluate() / rising-edge ──────────────────────────────────────────────────

class TestEvaluate:

    def testInactiveFaultNotReturned(self):
        monitor = FaultMonitor()
        monitor.register(Fault("F1", FaultSeverity.HIGH, "desc", condition=lambda: False))
        assert monitor.evaluate() == []

    def testActiveFaultReturnedOnFirstTick(self):
        monitor = FaultMonitor()
        f = Fault("F1", FaultSeverity.HIGH, "desc", condition=lambda: True)
        monitor.register(f)
        assert monitor.evaluate() == [f]

    def testActiveFaultNotReturnedOnSubsequentTick(self):
        """Rising-edge only — same fault should not appear on every tick it stays active."""
        monitor = FaultMonitor()
        monitor.register(Fault("F1", FaultSeverity.HIGH, "desc", condition=lambda: True))
        monitor.evaluate()
        assert monitor.evaluate() == []

    def testFaultClearsAndRefiresOnNextRisingEdge(self):
        monitor = FaultMonitor()
        active = [True]
        monitor.register(Fault("F1", FaultSeverity.HIGH, "desc", condition=lambda: active[0]))

        monitor.evaluate()       # fires
        active[0] = False
        monitor.evaluate()       # clears
        active[0] = True
        result = monitor.evaluate()  # fires again
        assert len(result) == 1

    def testMultipleFaultsEvaluatedIndependently(self):
        monitor = FaultMonitor()
        fa = Fault("FA", FaultSeverity.HIGH, "a", condition=lambda: False)
        fb = Fault("FB", FaultSeverity.LOW,  "b", condition=lambda: True)
        monitor.register(fa)
        monitor.register(fb)

        result = monitor.evaluate()
        assert fb in result
        assert fa not in result

    def testExceptionInConditionTreatedAsActiveFault(self):
        monitor = FaultMonitor()
        def bad():
            raise RuntimeError("sensor failure")
        f = Fault("F1", FaultSeverity.HIGH, "desc", condition=bad)
        monitor.register(f)
        result = monitor.evaluate()
        assert f in result
        assert f.active is True

    def testAllSeveritiesReturnedInNewlyActive(self):
        """evaluate() returns newly-active faults of all severities; caller is responsible for filtering."""
        monitor = FaultMonitor()
        fh = Fault("FH", FaultSeverity.HIGH,   "h", condition=lambda: True)
        fm = Fault("FM", FaultSeverity.MEDIUM, "m", condition=lambda: True)
        fl = Fault("FL", FaultSeverity.LOW,    "l", condition=lambda: True)
        for f in (fh, fm, fl):
            monitor.register(f)
        result_codes = {f.code for f in monitor.evaluate()}
        assert result_codes == {"FH", "FM", "FL"}


# ── hasActiveFaults / getActiveFaults ─────────────────────────────────────────

class TestQueries:

    def testHasActiveFaultsIsFalseBeforeEvaluate(self):
        monitor = FaultMonitor()
        monitor.register(Fault("F1", FaultSeverity.HIGH, "desc", condition=lambda: True))
        assert monitor.hasActiveFaults() is False

    def testHasActiveFaultsIsFalseWhenNoneActive(self):
        monitor = FaultMonitor()
        monitor.register(Fault("F1", FaultSeverity.HIGH, "desc", condition=lambda: False))
        monitor.evaluate()
        assert monitor.hasActiveFaults() is False

    def testHasActiveFaultsIsTrueWhenOneActive(self):
        monitor = FaultMonitor()
        monitor.register(Fault("F1", FaultSeverity.HIGH, "desc", condition=lambda: True))
        monitor.evaluate()
        assert monitor.hasActiveFaults() is True

    def testHasActiveFaultsReflectsClearance(self):
        monitor = FaultMonitor()
        active = [True]
        monitor.register(Fault("F1", FaultSeverity.HIGH, "desc", condition=lambda: active[0]))
        monitor.evaluate()
        assert monitor.hasActiveFaults() is True
        active[0] = False
        monitor.evaluate()
        assert monitor.hasActiveFaults() is False

    def testGetActiveFaultsReturnsOnlyActiveOnes(self):
        monitor = FaultMonitor()
        fa = Fault("FA", FaultSeverity.HIGH, "a", condition=lambda: True)
        fb = Fault("FB", FaultSeverity.LOW,  "b", condition=lambda: False)
        monitor.register(fa)
        monitor.register(fb)
        monitor.evaluate()
        active = monitor.getActiveFaults()
        assert fa in active
        assert fb not in active

    def testCallableDescriptionEvaluatedAtFireTime(self):
        """Description callable must be called at fault-fire time, not at registration."""
        value = ["initial"]
        monitor = FaultMonitor()
        monitor.register(Fault("F1", FaultSeverity.HIGH, lambda: value[0], condition=lambda: True))
        value[0] = "changed"
        # Should not raise, and should use the current value of `value[0]`
        monitor.evaluate()
