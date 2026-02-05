from abc import ABC, abstractmethod
from flask import Flask, render_template_string
from typing import Callable

from ride_control_computer.motor_controller.MotorController import MotorControllerState

class WebserverController(ABC):
    """Webserver Controller and methods"""

    def __init__(self,
                 getSpeeds: Callable[[], tuple[float, float]],
                 getState: Callable[[], MotorControllerState],
                 startTheming: Callable[[], None],
                 stopTheming: Callable[[], None],
                 themeStatus: Callable[[], str]
                 ):
        self.app = Flask(__name__)
        self.getSpeed = getSpeeds
        self.getState = getState
        self.startTheming = startTheming
        self.stopTheming = stopTheming
        self.themeStatus = themeStatus

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

        self.app.run(debug=False)

