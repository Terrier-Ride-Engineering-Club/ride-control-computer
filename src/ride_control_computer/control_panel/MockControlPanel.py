from time import sleep
from ride_control_computer.control_panel.ControlPanel import ControlPanel

class MockControlPanel(ControlPanel):

    def __init__(self):
        super().__init__()

    def run(self) -> None:
        while (True):
            sleep(0.1)
