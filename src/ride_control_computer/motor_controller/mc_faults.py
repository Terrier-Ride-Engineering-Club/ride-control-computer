from typing import Callable

from ride_control_computer.fault_monitor import Fault, FaultMonitor, FaultSeverity
from ride_control_computer.motor_controller.MotorController import MotorController


def registerMotorControllerFaults(
    monitor: FaultMonitor,
    mc: MotorController,
    isMotionForbidden: Callable[[], bool],
) -> None:
    """Register all motor-controller-related fault conditions.

    Args:
        isMotionForbidden: Returns True when the system is in a state where
                           motor motion should not occur (e.g. IDLE or OFF).
                           Supplied by the orchestrator to avoid a circular import.
    """
    monitor.register(Fault(
        code="MC_COMM_FAILURE",
        severity=FaultSeverity.HIGH,
        description="Motor controller telemetry is stale — communication lost",
        condition=mc.isTelemetryStale,
    ))
    monitor.register(Fault(
        code="MC_ESTOP_ACTIVE",
        severity=FaultSeverity.HIGH,
        description="Hardware E-Stop is active on motor controller",
        condition=mc.isEstopActive,
    ))
    monitor.register(Fault(
        code="MC_STATUS_ABNORMAL",
        severity=FaultSeverity.HIGH,
        description=lambda: f"Motor controller reported abnormal status: {mc.getControllerStatus()}",
        condition=lambda: mc.getControllerStatus() not in ("Normal", "E-Stop"),
    ))
    monitor.register(Fault(
        code="MC_UNEXPECTED_MOTION",
        severity=FaultSeverity.MEDIUM,
        description="Motor motion detected while system is idle",
        condition=lambda: isMotionForbidden() and any(abs(s) > 10 for s in mc.getMotorSpeeds()),
    ))
