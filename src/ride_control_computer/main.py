from ride_control_computer.RCC import RCC

from ride_control_computer.motor_controller.MockMotorController import MockMotorController
from ride_control_computer.control_panel.MockControlPanel import MockControlPanel
from ride_control_computer.theming_controller.MockThemeingController import MockThemingController
from ride_control_computer.webserver.MockWebserverController import MockWebserverController


def main():
    rideControlComputer = RCC(
        MockMotorController(),
        MockControlPanel(),
        MockThemingController(),
        MockWebserverController
    )

    rideControlComputer.run()