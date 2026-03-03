# Entry Point for TREC's REC Ride Control Computer
    # Made by Jackson Justus (jackjust@bu.edu)

import argparse
import logging
import signal
import time
from datetime import datetime
from pathlib import Path

from ride_control_computer.RCC import RCC
from ride_control_computer.control_panel.MockControlPanel import MockControlPanel
from ride_control_computer.motor_controller.MockMotorController import MockMotorController
from ride_control_computer.motor_controller.MotorData import getAverageSpeed
from ride_control_computer.motor_controller.RoboClawSerialMC import RoboClawSerialMotorController
from ride_control_computer.motor_controller.RoboClaw import RoboClaw
from ride_control_computer.theming_controller.MockThemeingController import MockThemingController
from ride_control_computer.webserver.MockWebserverController import MockWebserverController
from ride_control_computer.RideTimer import RideTimingData
from ride_control_computer.motor_controller.MotorData import getAverageSpeed

# SETUP LOGGING
LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s]: %(message)s"
ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
# make logs folder if it doesn't exist
log_dir = Path(__file__).resolve().parent.parent.parent / "logs"
log_dir.mkdir(parents=True, exist_ok=True)
LOG_FILE = f"./logs/RCC_Log_{ts}.log"
logging.basicConfig(
    level=logging.DEBUG,
    format=LOG_FORMAT,
    handlers=[logging.FileHandler(LOG_FILE)])  # Log to a file
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter(LOG_FORMAT))
console_handler.setLevel(logging.DEBUG)
logging.getLogger().addHandler(console_handler)  # Log to the console (INFO or higher)

def main():
    parser = argparse.ArgumentParser(description="Ride Control Computer")
    parser.add_argument(
        "--hardware",
        action="store_true",
        help="Use hardware implementations instead of mocks (for Pi deployment)"
    )
    parser.add_argument(
        "--web-panel",
        action="store_true",
        help="Use WebControlPanel (browser UI) instead of the physical RCP control hardware"
    )
    args = parser.parse_args()

    if args.hardware:
        logger = logging.getLogger(__name__)
        logger.info("Starting with HARDWARE implementations")

        from ride_control_computer.motor_controller.RoboClawSerialMC import RoboClawSerialMotorController

        ROBOCLAW_PORTS = [
            '/dev/ttyAMA1',   # Pi GPIO serial
            '/dev/ttyACM0',   # USB (Pi)
            '/dev/ttyACM1',   # USB (Pi fallback)
        ]
        WATCHDOG_PORT = '/dev/ttyUSB0'  # Arduino Nano (PLC) via USB CDC

        mc = RoboClawSerialMotorController(ROBOCLAW_PORTS)
        # TODO: Add hardware ThemingController when implemented
        tc = MockThemingController()
    else:
        logger = logging.getLogger(__name__)
        logger.info("Starting with MOCK implementations")

        WATCHDOG_PORT = None

        mc = MockMotorController()
        tc = MockThemingController()

    if args.web_panel:
        logger = logging.getLogger(__name__)
        logger.info("Control panel: WEB (http://0.0.0.0:5001)")
        from ride_control_computer.control_panel.WebControlPanel import WebControlPanel
        cp = WebControlPanel()
    elif args.hardware:
        from ride_control_computer.control_panel.HardwareControlPanel import HardwareControlPanel
        cp = HardwareControlPanel()
    else:
        cp = MockControlPanel()

    wc = MockWebserverController(
        getSpeeds=mc.getMotorSpeeds,
        getState=mc.getState,
        startTheming=tc.startShow,
        stopTheming=tc.stopShow,
        themeStatus=tc.getStatus,
        getPositions=mc.getMotorPositions,
        getAverageSpeed=getAverageSpeed,
        getVoltage=mc.getVoltage,
        getTemperatures=mc.getTemperatures,
        getCurrents=mc.getMotorCurrents
        )

    rideControlComputer = RCC(mc, cp, tc, wc, watchdogPort=WATCHDOG_PORT)
    wc.set_rcc(rideControlComputer)

    def _shutdown(sig, frame):
        rideControlComputer.shutdown()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    rideControlComputer.run()

if __name__ == '__main__':
    main()