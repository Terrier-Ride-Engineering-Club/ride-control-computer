from time import sleep
from ride_control_computer.control_panel.ControlPanel import ControlPanel

class MockControlPanel(ControlPanel):

    def __init__(self):
        super().__init__()

    def run(self) -> None:
        while not self._stopEvent.is_set():
            self._loop_timer.tick()
            sleep(0.1)


class PassiveControlPanel(ControlPanel):
    """ControlPanel with no hardware or auto-behavior. Events are enqueued via the web panel."""

    def __init__(self):
        super().__init__()

    def run(self) -> None:
        self._stopEvent.wait()
