from ride_control_computer.theming_controller.ThemingController import ThemingController

class MockThemingController(ThemingController):

    def __init__(self):
        super().__init__()
        self.status = "off"

    def startShow(self):
        self.status = "on"

    def stopShow(self):
        self.status = "off"
