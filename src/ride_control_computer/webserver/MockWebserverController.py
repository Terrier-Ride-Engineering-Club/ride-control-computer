from pydoc import html
from ride_control_computer.webserver.WebserverController import WebserverController
from flask import *
from math import inf
from waitress import serve
from ride_control_computer.motor_controller.MotorData import getAverageSpeed # this should be done somewhere else

class MockWebserverController(WebserverController):

    def __init__(self, getSpeeds, getState, startTheming, stopTheming, themeStatus, getPositions, getAverageSpeed, getCurrents, getVoltage, getTemperatures):
        super().__init__(getSpeeds,getState, startTheming, stopTheming, themeStatus, getPositions, getAverageSpeed, getCurrents, getVoltage, getTemperatures)

    def _compute_four_data(self):
        if self.rcc is None:
            return None

        from math import inf

        # ----------------------------
        # Current Live Data
        # ----------------------------
        elapsed = self.getRideElapsed()
        positions = self.getPositions() or (0, 0)
        velocities = self.getSpeed() or (0, 0)
        currents = self.getCurrents() or (0, 0)
        voltage = self.getVoltage() or 0
        temps = self.getTemperatures() or (0, 0)

        m1_pos, m2_pos = positions
        m1_vel, m2_vel = velocities
        m1_current, m2_current = currents
        m1_temp, m2_temp = temps

        # ----------------------------
        # Historical Telemetry
        # ----------------------------
        telemetry = self.rcc.getTelemetryLogger()
        rides = telemetry.getAllRides()

        avg_m1_pos = avg_m2_pos = 0
        avg_m1_vel = avg_m2_vel = 0
        avg_m1_cur = avg_m2_cur = 0
        avg_vol = 0
        avg_m1_temp = avg_m2_temp = 0
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
                avg_m1_cur += closest.motor1Current
                avg_m2_cur += closest.motor2Current
                avg_vol += closest.busVoltage
                avg_m1_temp += closest.motor1Temperature
                avg_m2_temp += closest.motor2Temperature
                count += 1

        if count > 0:
            avg_m1_pos /= count
            avg_m2_pos /= count
            avg_m1_vel /= count
            avg_m2_vel /= count
            avg_m1_cur /= count
            avg_m2_cur /= count
            avg_vol /= count
            avg_m1_temp /= count
            avg_m2_temp /= count

        return {
            "elapsed": elapsed,
            "count": count,

            "m1_pos": m1_pos,
            "m2_pos": m2_pos,
            "avg_m1_pos": avg_m1_pos,
            "avg_m2_pos": avg_m2_pos,
            "diff_m1_pos": m1_pos - avg_m1_pos,
            "diff_m2_pos": m2_pos - avg_m2_pos,

            "m1_vel": m1_vel,
            "m2_vel": m2_vel,
            "avg_m1_vel": avg_m1_vel,
            "avg_m2_vel": avg_m2_vel,
            "diff_m1_vel": m1_vel - avg_m1_vel,
            "diff_m2_vel": m2_vel - avg_m2_vel,

            "m1_current": m1_current,
            "m2_current": m2_current,
            "avg_m1_cur": avg_m1_cur,
            "avg_m2_cur": avg_m2_cur,
            "diff_m1_cur": m1_current - avg_m1_cur,
            "diff_m2_cur": m2_current - avg_m2_cur,

            "voltage": voltage,
            "avg_vol": avg_vol,
            "diff_vol": voltage - avg_vol,

            "m1_temp": m1_temp,
            "m2_temp": m2_temp,
            "avg_m1_temp": avg_m1_temp,
            "avg_m2_temp": avg_m2_temp,
            "diff_m1_temp": m1_temp - avg_m1_temp,
            "diff_m2_temp": m2_temp - avg_m2_temp,
        }

    def start(self):
        @self.app.route('/')
        def index():
            return one()

        @self.app.route('/one')
        def one():
            speed = self.getSpeed() or (0, 0)
            raw_state_obj = self.getState()
            positions = self.getPositions() or (0, 0)
            temps = self.getTemperatures() or (0, 0)
            ride_time = self.getElapsedTime() or 0


            # Only show text after period
            raw_state = str(raw_state_obj) if raw_state_obj is not None else ""

            state = raw_state.split(".", 1)[1] if "." in raw_state else raw_state
            # convert position to percent height
            line1 = positions[0] / 2.56
            line2 = positions[1] / 2.56

            # Get comparison data from page four logic
            four_data = self._compute_four_data() or {}

            # Console output (replace with your real getter if different)
            console_output = ""
            if self.rcc:
                console_output = self.rcc.getConsoleOutput() if hasattr(self.rcc, "getConsoleOutput") else ""

            return render_template(
                "one.html",
                speed=speed,
                state=state,
                positions=positions,
                temps=temps,
                rideTime=ride_time,
                line1=line1,
                line2=line2,
                four=four_data,
                console=console_output
            )

        @self.app.route('/one-data')
        def one_data():
            speed = self.getSpeed() or (0, 0)
            raw_state_obj = self.getState()
            positions = self.getPositions() or (0, 0)
            temps = self.getTemperatures() or (0, 0)
            ride_time = self.getElapsedTime() or 0

            # Clean state
            raw_state = str(raw_state_obj) if raw_state_obj else ""
            state = raw_state.split(".", 1)[1] if "." in raw_state else raw_state

            return jsonify({
                "state": state,
                "rideTime": ride_time,
                "m1_speed": speed[0],
                "m2_speed": speed[1],
                "m1_pos": positions[0],
                "m2_pos": positions[1],
                "m1_temp": temps[0],
                "m2_temp": temps[1],
                "line1": positions[0] / 2.56,
                "line2": positions[1] / 2.56,
            })


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
            data = self._compute_four_data()
            if data is None:
                return "RCC not connected"

            return render_template("four.html", **data)

        @self.app.route('/four-data')
        def four_data():
            data = self._compute_four_data()
            if data is None:
                return {}

            return jsonify(data)

        serve(self.app, host="127.0.0.1")