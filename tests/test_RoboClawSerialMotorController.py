import time
import threading
from unittest.mock import patch, MagicMock
from ride_control_computer.motor_controller.MotorController import MotorControllerState
from ride_control_computer.motor_controller.RoboClaw import RoboClaw
from ride_control_computer.motor_controller.RoboClawSerialMC import RoboClawSerialMotorController


def _configureDefaultMock(mockCls: MagicMock) -> MagicMock:
    """Configure a RoboClaw mock with fast default return values."""
    roboClaw = mockCls.return_value

    roboClaw.read_version.return_value = "MockClaw v1.0"
    roboClaw.read_status.return_value = "Normal"
    roboClaw.read_batt_voltage.return_value = 12.0
    roboClaw.read_currents.return_value = (0.5, 0.6)
    roboClaw.read_temp_sensor.side_effect = lambda s: 25.0
    roboClaw.read_encoder_pos.side_effect = lambda m: {
        "encoder": 1000, "underflow": False,
        "direction": "Forward", "overflow": False,
    }
    roboClaw.read_encoder_speed.side_effect = lambda m: {
        "speed": 100, "direction": "Forward",
    }

    return roboClaw

class TestRoboClawSerialMotorController():
    def testReportsStaleTelemetry(self):
        with patch(
            "ride_control_computer.motor_controller.RoboClawSerialMC.RoboClaw"
        ) as mockCls:
            roboClaw = _configureDefaultMock(mockCls)
            controller = RoboClawSerialMotorController(roboClaw)
            controller.start()
            time.sleep(0.05)  # let cache populate with fast values
            assert not controller.isTelemetryStale()

            # --- Now make polling slow ---
            pollBarrier = threading.Event()
            def slowReadStatus():
                pollBarrier.wait(timeout=5.0)  # block until test releases it
                return "Normal"
            roboClaw.read_status.side_effect = slowReadStatus

            # Give time for the telemetry thread to enter the slow call
            time.sleep(1)

            # --- Main thread getter should return instantly from cache ---
            startTime = time.monotonic()
            voltage = controller.getVoltage()
            elapsedTime = time.monotonic() - startTime

            assert voltage == 12.0  # got the cached value
            assert elapsedTime < 0.01  # didn't block (well under 10ms)
            assert controller.isTelemetryStale() # telem is marked as stale

            # Release the blocked poll thread so shutdown doesn't hang
            pollBarrier.set()
            controller.shutdown()

    def testStartupHappyPath(self):
        with patch(
                "ride_control_computer.motor_controller.RoboClawSerialMC.RoboClaw"
        ) as mockCls:
            roboClaw = _configureDefaultMock(mockCls)
            controller = RoboClawSerialMotorController(roboClaw)
            controller.start()
            time.sleep(0.05)
            assert controller.getState() is MotorControllerState.IDLE

    def testStartupEStop(self):
        with patch(
                "ride_control_computer.motor_controller.RoboClawSerialMC.RoboClaw"
        ) as mockCls:
            roboClaw = _configureDefaultMock(mockCls)
            roboClaw.read_status.return_value = "E-Stop"
            controller = RoboClawSerialMotorController(roboClaw)
            controller.start()
            assert controller.getState() is MotorControllerState.DISABLED
            time.sleep(0.05)
            assert controller.getState() is MotorControllerState.DISABLED
            time.sleep(1)
            assert controller.getState() is MotorControllerState.DISABLED\

    def testRideSequenceLifecycle(self):
        with patch(
                "ride_control_computer.motor_controller.RoboClawSerialMC.RoboClaw"
        ) as mockCls:
            roboClaw = _configureDefaultMock(mockCls)
            controller = RoboClawSerialMotorController(roboClaw)
            controller.start()
            controller.startRideSequence()
            assert controller.getState() is MotorControllerState.SEQUENCING

            # Test triggering E-Stop mid sequence
            controller.stopMotion()
            assert controller.getState() is MotorControllerState.STOPPING

            # Mock motor stopping, make sure MC -> idle.
            roboClaw.read_encoder_speed.side_effect = lambda m: {
                "speed": 100, "direction": "Forward",
            }
            time.sleep(0.5)
            assert controller.getState() is MotorControllerState.STOPPING
            roboClaw.read_encoder_speed.side_effect = lambda m: {
                "speed": 0.5, "direction": "Forward",
            }
            time.sleep(0.5)
            assert controller.getState() is MotorControllerState.IDLE
