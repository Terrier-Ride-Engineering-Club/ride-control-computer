# Entry Point for TREC's REC Ride Control Computer
    # Made by Jackson Justus (jackjust@bu.edu)

import argparse
import logging
import time
from datetime import datetime
from pathlib import Path

import serial.serialutil

from ride_control_computer.RCC import RCC
from ride_control_computer.control_panel.MockControlPanel import MockControlPanel
from ride_control_computer.motor_controller.MockMotorController import MockMotorController
from ride_control_computer.motor_controller.RoboClawSerialMC import RoboClawSerialMotorController
from ride_control_computer.motor_controller.RoboClaw import RoboClaw
from ride_control_computer.theming_controller.MockThemeingController import MockThemingController
from ride_control_computer.webserver.MockWebserverController import MockWebserverController
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
    args = parser.parse_args()

    if args.hardware:
        logger = logging.getLogger(__name__)
        logger.info("Starting with HARDWARE implementations")

        from ride_control_computer.motor_controller.RoboClaw import RoboClaw
        from ride_control_computer.motor_controller.RoboClawSerialMC import RoboClawSerialMotorController

        # Try ports in order until one works
        ROBOCLAW_PORTS = [
            '/dev/ttyAMA1',   # Pi GPIO serial
            '/dev/ttyACM0',   # USB (Pi)
            '/dev/ttyACM1',   # USB (Pi fallback)
        ]

        roboclaw = None
        for port in ROBOCLAW_PORTS:
            try:
                roboclaw = RoboClaw(port=port)
                logger.info(f"RoboClaw connected on {port}")
                break
            except serial.serialutil.SerialException:
                logger.debug(f"RoboClaw not found on {port}")

        if roboclaw is None:
            raise RuntimeError(f"RoboClaw not found on any port: {ROBOCLAW_PORTS}")

        mc = RoboClawSerialMotorController(roboclaw)
        # TODO: Add hardware ControlPanel when implemented
        cp = MockControlPanel()
        # TODO: Add hardware ThemingController when implemented
        tc = MockThemingController()
    else:
        logger = logging.getLogger(__name__)
        logger.info("Starting with MOCK implementations")

        mc = MockMotorController()
        cp = MockControlPanel()
        tc = MockThemingController()

    wc = MockWebserverController(
        getSpeeds=mc.getMotorSpeeds,
        getState=mc.getState,
        startTheming=tc.startShow,
        stopTheming=tc.stopShow,
        themeStatus=tc.getStatus,
        getPositions=mc.getMotorPositions)

    rideControlComputer = RCC(mc, cp, tc, wc)
    rideControlComputer.run()

if __name__ == '__main__':
    main()