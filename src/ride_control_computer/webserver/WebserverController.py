from abc import ABC, abstractmethod
from flask import Flask, render_template_string
from typing import Callable

from ride_control_computer.RideTimer import RideTimingData
from ride_control_computer.motor_controller.MotorController import MotorControllerState

class WebserverController(ABC):
    """Webserver Controller and methods"""

    def __init__(self,
                 getSpeeds: Callable[[], tuple[float, float]],
                 getState: Callable[[], MotorControllerState],
                 startTheming: Callable[[], None],
                 stopTheming: Callable[[], None],
                 themeStatus: Callable[[], str],
                 getPositions: Callable[[], tuple[int, int]],
                 getAverageSpeed: Callable[[], float],
                 getCurrents: Callable[[], tuple[float, float]],
                 getVoltage: Callable[[], float],
                 getTemperatures: Callable[[], tuple[float, float]],
                 isTelemetryStale: Callable[[], bool] = lambda: True,
                 ):
        self.app = Flask(__name__)
        self.getSpeed = getSpeeds
        self.getState = getState
        self.isTelemetryStale = isTelemetryStale
        self.startTheming = startTheming
        self.stopTheming = stopTheming
        self.themeStatus = themeStatus
        self.getPositions = getPositions
        self.getAverageSpeed = getAverageSpeed
        self.getCurrents = getCurrents
        self.getVoltage = getVoltage
        self.getTemperatures = getTemperatures
        self.rcc = None
        self._panel = None

    def set_rcc(self, rcc):
        self.rcc = rcc

    def set_panel(self, cp) -> None:
        self._panel = cp

    def getElapsedTime(self):
        return self.rcc.getCurrentRideElapsed()

    def getAverageTime(self):
        return self.rcc.getAverageRideDuration()

    def getRideData(self):
        return self.rcc.getCurrentRideData()

    def getRideElapsed(self):
        return self.rcc.getCurrentRideElapsed()


    def start(self):
        @self.app.route('/')
        def index():
            """code for start page - links to page n"""
            ...

        @self.app.route('/one')
        def one():
            """code for page one that shows standard run info"""
            ...

        @self.app.route('/two')
        def two():
            """code for page two that shows debug info"""
            ...

        @self.app.route('/three')
        def three():
            """code for page three that shows design info"""
            ...
        @self.app.route("/start-theming", methods=["POST"])
        def start_theming():
            """code to start theming - redirect to page three"""
            ...

        @self.app.route("/stop-theming", methods=["POST"])
        def stop_theming():
            """code to stop theming - redirect to page three"""
            ...

        @self.app.route('/four')
        def four():
            ...

        @self.app.route('/four-data')
        def four_data():
            ...

        self.app.run(debug=False)

