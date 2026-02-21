from pydoc import html
from ride_control_computer.webserver.WebserverController import WebserverController
from flask import *
from waitress import serve
from ride_control_computer.motor_controller.MotorData import getAverageSpeed # this should be done somewhere else

class MockWebserverController(WebserverController):

    def __init__(self, getSpeeds, getState, startTheming, stopTheming, themeStatus, getPositions, getAverageSpeed):
        super().__init__(getSpeeds,getState, startTheming, stopTheming, themeStatus, getPositions, getAverageSpeed)

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
            positions = self.getPositions()
            ride_time = self.getElapsedTime()

            # convert 0–10 → percentage height
            line1 = positions[0] * 10
            line2 = positions[1] * 10

            return render_template(
                "one.html",
                speed=speed,
                state=state,
                positions=positions,
                line1=line1,
                line2=line2,
                rideTime = ride_time
            )
        @self.app.route('/two')
        def two():
            speeds = self.getSpeed()
            positions = self.getPositions()
            averageSpeed = getAverageSpeed()
            averageTime = self.getAverageTime()
            currentTime = self.getElapsedTime()

            c1_list = ["Motor one", "Motor two", "Average", "Difference 1", "Difference 2"]
            time_list = [currentTime, "-", averageTime, averageTime-currentTime, "-"]
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

        @self.app.route('/four')
        def four():
            from math import inf

            if self.rcc is None:
                return "RCC not connected"

            # ----------------------------
            # Current Live Data
            # ----------------------------
            elapsed = self.getRideElapsed()
            positions = self.getPositions()
            velocities = self.getSpeed()

            m1_pos, m2_pos = positions
            m1_vel, m2_vel = velocities

            # ----------------------------
            # Historical Telemetry
            # ----------------------------
            telemetry = self.rcc.getTelemetryLogger()
            rides = telemetry.getAllRides()

            avg_m1_pos = 0
            avg_m2_pos = 0
            avg_m1_vel = 0
            avg_m2_vel = 0
            count = 0

            for ride in rides:
                closest = None
                min_diff = inf

                for sample in ride.samples:
                    diff = abs(sample.rideElapsed - elapsed)
                    if diff < min_diff:
                        min_diff = diff
                        closest = sample

                if closest:
                    avg_m1_pos += closest.motor1Position
                    avg_m2_pos += closest.motor2Position
                    avg_m1_vel += closest.motor1Velocity
                    avg_m2_vel += closest.motor2Velocity
                    count += 1

            if count > 0:
                avg_m1_pos /= count
                avg_m2_pos /= count
                avg_m1_vel /= count
                avg_m2_vel /= count

            diff_m1_pos = m1_pos - avg_m1_pos
            diff_m2_pos = m2_pos - avg_m2_pos
            diff_m1_vel = m1_vel - avg_m1_vel
            diff_m2_vel = m2_vel - avg_m2_vel

            return render_template(
                "four.html",
                elapsed=elapsed,
                count=count,

                m1_pos=m1_pos,
                m2_pos=m2_pos,
                avg_m1_pos=avg_m1_pos,
                avg_m2_pos=avg_m2_pos,
                diff_m1_pos=diff_m1_pos,
                diff_m2_pos=diff_m2_pos,

                m1_vel=m1_vel,
                m2_vel=m2_vel,
                avg_m1_vel=avg_m1_vel,
                avg_m2_vel=avg_m2_vel,
                diff_m1_vel=diff_m1_vel,
                diff_m2_vel=diff_m2_vel,
            )

        serve(self.app, host="127.0.0.1")
