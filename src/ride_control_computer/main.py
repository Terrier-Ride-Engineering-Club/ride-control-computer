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

def main(): 
    mc = MockMotorController()
    cp = MockControlPanel()
    tc = MockThemingController()
    wc = MockWebserverController(getSpeed=mc.getMotorSpeed)
    rideControlComputer = RCC(
        mc,
        cp,
        tc,
        wc
    )

    rideControlComputer.run()

if __name__ == '__main__':
    main()