from ride_control_computer.theming_controller.ThemingController import ThemingController

class MockThemingController(ThemingController):

    def __init__(self):
        super().__init__()

    def startShow(self):
        ...

    def stopShow(self):
        ...
    