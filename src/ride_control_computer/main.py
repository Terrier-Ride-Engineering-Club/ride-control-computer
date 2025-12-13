from ride_control_computer.RCC import RCC

from ride_control_computer.motor_controller.MockMotorController import MockMotorController
from ride_control_computer.control_panel.MockControlPanel import MockControlPanel
from ride_control_computer.theming_controller.MockThemeingController import MockThemingController



def main():
    rideControlComputer = RCC(
        MockMotorController(),
        MockControlPanel(),
        MockThemingController()
    )

    rideControlComputer.run()