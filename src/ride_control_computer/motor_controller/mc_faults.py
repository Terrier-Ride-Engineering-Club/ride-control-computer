from typing import Callable

from ride_control_computer.fault_monitor import Fault, FaultMonitor, FaultSeverity
from ride_control_computer.motor_controller.MotorController import MotorController



# RoboClaw error bits (raw status register, command 90).
# Only these bits represent true hardware errors worth triggering an E-Stop.
# Warning bits (0xFFFF0000) such as Reset Warning (0x20000000) are intentionally
# excluded — they are transient and expected at startup or after a reset.
_MC_ERROR_BITS = (
    0x00000002  # Temperature Error
    | 0x00000004  # Temperature 2 Error
    | 0x00000010  # Logic Voltage High Error
    | 0x00000020  # Logic Voltage Low Error
    | 0x00000040  # Motor 1 Fault Error
    | 0x00000080  # Motor 2 Fault Error
    | 0x00000100  # Motor 1 Speed Error
    | 0x00000200  # Motor 2 Speed Error
    | 0x00000400  # Motor 1 Position Error
    | 0x00000800  # Motor 2 Position Error
    | 0x00001000  # Motor Current 1 Error
    | 0x00002000  # Motor Current 2 Error
)


def registerMotorControllerFaults(
    monitor: FaultMonitor,
    mc: MotorController,
    isMotionForbidden: Callable[[], bool],
    isMotor1AtTopLimit: Callable[[], bool],
    isMotor2AtTopLimit: Callable[[], bool],
    isMotor1AtBottomLimit: Callable[[], bool],
    isMotor2AtBottomLimit: Callable[[], bool],

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
        condition=lambda: bool(mc.getRawControllerStatus() & _MC_ERROR_BITS),
    ))
    monitor.register(Fault(
        code="MC_UNEXPECTED_MOTION",
        severity=FaultSeverity.MEDIUM,
        description="Motor motion detected while system is idle",
        condition=lambda: isMotionForbidden() and any(abs(s) > 10 for s in mc.getMotorSpeeds()),
    ))
    monitor.register(Fault(
        code="MC_MOTOR1_LIMIT_SWITCH_VIOLATION",
        severity=FaultSeverity.HIGH,
        description= "Limit switches both active on tower 1",
        condition=lambda: isMotor1AtTopLimit() and isMotor1AtBottomLimit()
    ))
    monitor.register(Fault(
        code="MC_MOTOR2_LIMIT_SWITCH_VIOLATION",
        severity=FaultSeverity.HIGH,
        description="Limit switches both active on tower 2",
        condition=lambda: isMotor2AtTopLimit() and isMotor2AtBottomLimit()
    ))
