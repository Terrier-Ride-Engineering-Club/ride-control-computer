from ride_control_computer.webserver.WebserverController import WebserverController
from ride_control_computer.control_panel.ControlPanel import MomentaryButtonState, MomentarySwitchState, SustainedSwitchState
from flask import *
from math import inf
from waitress import serve

class MockWebserverController(WebserverController):

    def __init__(self, getSpeeds, getState, startTheming, stopTheming, themeStatus, getPositions, getCurrents, getVoltage, getTemperatures, isTelemetryStale=lambda: True, getLimitSwitches=lambda: {"m1_top": False, "m1_bottom": False, "m2_top": False, "m2_bottom": False}, getMCStatusString=lambda: "Unknown"):
        super().__init__(getSpeeds, getState, startTheming, stopTheming, themeStatus, getPositions, getCurrents, getVoltage, getTemperatures, isTelemetryStale, getLimitSwitches, getMCStatusString)

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
                avg_vol += closest.voltage
                avg_m1_temp += closest.motor1temp
                avg_m2_temp += closest.motor2temp
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

        ride_durations = []
        for ride in rides:
            if ride.samples:
                duration = ride.samples[-1].rideElapsed
            else:
                duration = 0.0

            ride_durations.append({
                "index": ride.rideIndex,
                "duration": duration
            })

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

            "ride_durations": ride_durations,
        }

    def start(self):
        @self.app.route('/')
        def index():
            return one()

        @self.app.route('/one')
        def one():
            positions = self.getPositions() or (0, 0)
            ride_time = self.getElapsedTime() or 0

            raw_state = str(self.rcc.getState()) if self.rcc else ""
            rcc_state = raw_state.split(".", 1)[1] if "." in raw_state else raw_state
            faults = self.rcc.getActiveFaults() if self.rcc else []
            mc_connected = not self.isTelemetryStale()
            watchdog = self.rcc.getWatchdogStatus() if self.rcc else "DISABLED"


            line1 = positions[0] / 14.0
            line2 = positions[1] / 14.0

            return render_template(
                "one.html",
                state = rcc_state,
                rcc_state=rcc_state,
                positions=positions,
                rideTime=ride_time,
                faults = faults,
                mc_connected = mc_connected,
                line1=line1,
                line2=line2,
                watchdog=watchdog,
            )

        @self.app.route('/one-data')
        def one_data():
            positions = self.getPositions() or (0, 0)
            ride_time = self.getElapsedTime() or 0

            raw_state = str(self.rcc.getState()) if self.rcc else ""
            rcc_state = raw_state.split(".", 1)[1] if "." in raw_state else raw_state
            faults = self.rcc.getActiveFaults() if self.rcc else []
            mc_connected = not self.isTelemetryStale()
            watchdog = self.rcc.getWatchdogStatus() if self.rcc else "DISABLED"



            return jsonify({
                "state": rcc_state,
                "rcc_state": rcc_state,
                "rideTime": ride_time,
                "m1_pos": positions[0],
                "m2_pos": positions[1],
                "faults": faults,
                "mc_connected": mc_connected,
                "line1": positions[0] / 14.0,
                "line2": positions[1] / 14.0,
                "watchdog": watchdog,
            })


        @self.app.route('/two')
        def two():
            speeds = self.getSpeed() or (0, 0)
            positions = self.getPositions() or (0, 0)
            temps = self.getTemperatures() or (0, 0)
            currents = self.getCurrents() or (0, 0)
            voltage = self.getVoltage() or 0

            raw_rcc = str(self.rcc.getState()) if self.rcc else ""
            rcc_state = raw_rcc.split(".", 1)[1] if "." in raw_rcc else raw_rcc

            mc_connected = not self.isTelemetryStale()

            avg_time = self.getAverageTime() or 0
            elapsed = self.getElapsedTime() or 0

            console_output = self.rcc.getConsoleOutput() if self.rcc and hasattr(self.rcc, "getConsoleOutput") else ""
            faults = self.rcc.getActiveFaults() if self.rcc else []
            last_estop_faults = self.rcc.getLastEstopFaults() if self.rcc else []
            watchdog = self.rcc.getWatchdogStatus() if self.rcc else "DISABLED"
            watchdog_details = self.rcc.getWatchdogDetails() if self.rcc else {"status": "DISABLED"}

            limits = self.getLimitSwitches()
            mc_status_string = self.getMCStatusString()
            return render_template("two.html",
                rcc_state=rcc_state,
                mc_connected=mc_connected,
                watchdog=watchdog,
                watchdog_details=watchdog_details,
                speeds=speeds,
                positions=positions,
                temps=temps,
                currents=currents,
                voltage=voltage,
                avg_time=avg_time,
                elapsed=elapsed,
                console=console_output,
                faults=faults,
                last_estop_faults=last_estop_faults,
                limits=limits,
                mc_status_string=mc_status_string,
            )

        @self.app.route('/two-data')
        def two_data():
            speeds = self.getSpeed() or (0, 0)
            positions = self.getPositions() or (0, 0)
            temps = self.getTemperatures() or (0, 0)
            currents = self.getCurrents() or (0, 0)
            voltage = self.getVoltage() or 0

            raw_rcc = str(self.rcc.getState()) if self.rcc else ""
            rcc_state = raw_rcc.split(".", 1)[1] if "." in raw_rcc else raw_rcc

            mc_connected = not self.isTelemetryStale()

            avg_time = self.getAverageTime() or 0
            elapsed = self.getElapsedTime() or 0

            faults = self.rcc.getActiveFaults() if self.rcc else []
            last_estop_faults = self.rcc.getLastEstopFaults() if self.rcc else []
            watchdog = self.rcc.getWatchdogStatus() if self.rcc else "DISABLED"
            watchdog_details = self.rcc.getWatchdogDetails() if self.rcc else {"status": "DISABLED"}
            limits = self.getLimitSwitches()
            mc_status_string = self.getMCStatusString()
            return jsonify({
                "rcc_state": rcc_state,
                "mc_connected": mc_connected,
                "watchdog": watchdog,
                "watchdog_details": watchdog_details,
                "m1_speed": speeds[0],
                "m2_speed": speeds[1],
                "m1_pos": positions[0],
                "m2_pos": positions[1],
                "m1_temp": temps[0],
                "m2_temp": temps[1],
                "m1_current": currents[0],
                "m2_current": currents[1],
                "voltage": voltage,
                "avg_time": avg_time,
                "elapsed": elapsed,
                "faults": faults,
                "last_estop_faults": last_estop_faults,
                "limits": limits,
                "mc_status_string": mc_status_string,
            })

        @self.app.route("/shutdown", methods=["POST"])
        def shutdown():
            if self.rcc:
                self.rcc.shutdown()
            return ("", 204)

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

        # ── Web Control Panel ──────────────────────────────────────────────────

        @self.app.route('/panel')
        def panel():
            return render_template("panel.html", panel_enabled=(self._panel is not None))

        @self.app.route('/api/panel/state')
        def panelState():
            if not self._panel:
                return jsonify({"error": "Panel not enabled"}), 503
            from ride_control_computer.RCC import RCCState
            rcc_state_obj = self.rcc.getState() if self.rcc else None
            name = rcc_state_obj.name if rcc_state_obj else "UNKNOWN"
            return jsonify({
                "rcc_state": name,
                "has_active_faults": bool(self.rcc and self.rcc.getActiveFaults()),
                "indicators": {
                    "dispatch": "blink"      if rcc_state_obj == RCCState.IDLE     else "off",
                    "reset":    "blink"      if rcc_state_obj == RCCState.ESTOP    else "off",
                    "stop":     "blink_fast" if rcc_state_obj == RCCState.STOPPING else "off",
                },
            })

        @self.app.route('/api/panel/button/<name>', methods=['POST'])
        def panelButton(name):
            if not self._panel:
                return jsonify({"error": "Panel not enabled"}), 503
            data = request.get_json(silent=True) or {}
            pressed = data.get("pressed", True)
            btnState = MomentaryButtonState.PRESSED if pressed else MomentaryButtonState.RELEASED
            dispatchers = {
                "dispatch": self._panel._enqueueDispatch,
                "reset":    self._panel._enqueueReset,
                "stop":     self._panel._enqueueStop,
                "estop":    self._panel._enqueueEstop,
            }
            if name not in dispatchers:
                return jsonify({"error": f"Unknown button: {name}"}), 400
            dispatchers[name](btnState)
            return jsonify({"ok": True})

        @self.app.route('/api/panel/power', methods=['POST'])
        def panelPower():
            if not self._panel:
                return jsonify({"error": "Panel not enabled"}), 503
            data = request.get_json(silent=True) or {}
            position = data.get("position", "")
            mapping = {
                "on":          SustainedSwitchState.ON,
                "off":         SustainedSwitchState.OFF,
                "maintenance": SustainedSwitchState.MAINTENANCE,
            }
            if position not in mapping:
                return jsonify({"error": f"Unknown position: {position}"}), 400
            self._panel._enqueueMaintenanceSwitch(mapping[position])
            return jsonify({"ok": True})

        @self.app.route('/api/panel/jog', methods=['POST'])
        def panelJog():
            if not self._panel:
                return jsonify({"error": "Panel not enabled"}), 503
            data = request.get_json(silent=True) or {}
            direction = data.get("direction", "neutral")
            mapping = {
                "up":      MomentarySwitchState.UP,
                "neutral": MomentarySwitchState.NEUTRAL,
                "down":    MomentarySwitchState.DOWN,
            }
            if direction not in mapping:
                return jsonify({"error": f"Unknown direction: {direction}"}), 400
            self._panel._enqueueMaintenanceJogSwitch(mapping[direction])
            return jsonify({"ok": True})

        serve(self.app, host="127.0.0.1")