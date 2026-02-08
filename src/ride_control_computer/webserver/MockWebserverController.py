from pydoc import html
from ride_control_computer.webserver.WebserverController import WebserverController
from flask import *
from waitress import serve
from ride_control_computer.motor_controller.MotorData import getAverageSpeed # this should be done somewhere else

class MockWebserverController(WebserverController):

    def __init__(self, getSpeeds, getState, startTheming, stopTheming, themeStatus, getPositions):
        super().__init__(getSpeeds,getState, startTheming, stopTheming, themeStatus, getPositions)

    def start(self):
        #Motor information:
        self.getSpeed()
        self.getState()

        @self.app.route('/')
        def index():
            return one()

        @self.app.route('/one')
        def one():
            speed = self.getSpeed()
            state = self.getState()
            positions = self.getPositions()  # e.g. (5, 8)

            # convert 0–10 → percentage height
            line1 = positions[0] * 10
            line2 = positions[1] * 10

            return render_template(
                "one.html",
                speed=speed,
                state=state,
                positions=positions,
                line1=line1,
                line2=line2
            )
        @self.app.route('/two')
        def two():
            speeds = self.getSpeed()
            positions = self.getPositions()
            averageSpeed = getAverageSpeed()

            c1_list = ["Motor one", "Motor two", "Average", "Difference 1", "Difference 2"]
            time_list = [1, 2, 3, 4, 5]
            speed_list = [speeds[0], speeds[1], averageSpeed, averageSpeed-speeds[0],averageSpeed-speeds[1]]
            position_list = [positions[0], positions[1], 31, 41, 51]
            data_lists = [c1_list, time_list, speed_list, position_list]

            # Convert into a list of dicts for Jinja
            data = [
                {"data": d,"time": t, "speed": s, "position": p}
                for d, t, s, p in zip(data_lists[0], data_lists[1], data_lists[2], data_lists[3])
            ]
            return render_template("two.html", data=data)

        @self.app.route("/start-theming", methods=["POST"])
        def start_theming():
            self.startTheming()
            return redirect(url_for("three"))

        @self.app.route("/stop-theming", methods=["POST"])
        def stop_theming():
            self.stopTheming()
            return redirect(url_for("three"))

        @self.app.route('/three')
        def three():
            status = self.themeStatus()
            return render_template("three.html", status=status)
        serve(self.app, host="127.0.0.1")