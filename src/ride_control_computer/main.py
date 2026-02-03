# Entry Point for TREC's REC Ride Control Computer
    # Made by Jackson Justus (jackjust@bu.edu)

import logging
import time
import datetime

from ride_control_computer.RCC import RCC
from ride_control_computer.motor_controller.MockMotorController import MockMotorController
from ride_control_computer.control_panel.MockControlPanel import MockControlPanel
from ride_control_computer.theming_controller.MockThemeingController import MockThemingController
from ride_control_computer.webserver.MockWebserverController import MockWebserverController


"""
HOW TO RUN THIS PROJECT:

1. Activate venv w/ requirements.txt installed
2. Do `pip install -e .` 
3. python -m ride_control_computer.main

"""
# SETUP LOGGING
LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s]: %(message)s"
LOG_FILE = f"./logs/RCC_Log [{datetime.datetime.now()}]"
logging.basicConfig(
    level=logging.DEBUG,
    format=LOG_FORMAT,
    handlers=[logging.FileHandler(LOG_FILE)])  # Log to a file
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter(LOG_FORMAT))
console_handler.setLevel(logging.INFO)
logging.getLogger().addHandler(console_handler)  # Log to the console (INFO or higher)

def main(): 
    mc = MockMotorController()
    cp = MockControlPanel()
    tc = MockThemingController()
    wc = MockWebserverController(getSpeeds=mc.getMotorSpeeds, getState=mc.getState, startTheming=tc.startShow, stopTheming=tc.stopShow, themeStatus=tc.status)
    rideControlComputer = RCC(
        mc,
        cp,
        tc,
        wc
    )

    rideControlComputer.run()

if __name__ == '__main__':
    main()