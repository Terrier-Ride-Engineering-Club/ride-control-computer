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

            html = """
            <html>
            <head>
                <style>
                    .bars-container {
                        display: flex;
                        justify-content: center;
                        gap: 50px;
                        margin-top: 30px;
                    }

                    .bar-wrapper {
                        position: relative;
                        width: 50px;
                        height: 200px;
                        border: 2px solid #333;
                        background: #f5f5f5;
                    }

                    .marker-line {
                        position: absolute;
                        left: 0;
                        width: 100%;
                        height: 3px;
                        background: red;
                        transform: translateY(50%);
                    }

                    .bar-label {
                        text-align: center;
                        margin-top: 10px;
                        font-size: 16px;
                    }
                </style>
            </head>
            <body>

                <div style="text-align:center">
                    <h1>speed = {{ speed }}</h1>
                    <h1>state = {{ state }}</h1>
                    <h1>positions = {{ positions }}</h1>

                    <div class="bars-container">
                        <div>
                            <div class="bar-wrapper">
                                <div class="marker-line" style="bottom: {{ line1 }}%;"></div>
                            </div>
                            <div class="bar-label">Car 1</div>
                        </div>

                        <div>
                            <div class="bar-wrapper">
                                <div class="marker-line" style="bottom: {{ line2 }}%;"></div>
                            </div>
                            <div class="bar-label">Car 2</div>
                        </div>
                    </div>

                    <div style="text-align:center; margin-top:30px;">
                        <a href="/one"><button style="padding: 12px 24px; font-size:18px;"><b>One</b></button></a>
                        <a href="/two"><button style="padding: 12px 24px; font-size:18px;">Two</button></a>
                        <a href="/three"><button style="padding: 12px 24px; font-size:18px;">Three</button></a>
                    </div>
                </div>

            </body>
            </html>
            """

            return render_template_string(
                html,
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
            time_list = [1, 2, 3, 4, 5]
            speed_list = [speeds[0], speeds[1], getAverageSpeed(), 40, 50]
            position_list = [positions[0], positions[1], 31, 41, 51]
            data_lists = [time_list, speed_list, position_list]

            # Convert into a list of dicts for Jinja
            data = [
                {"time": t, "speed": s, "position": p}
                for t, s, p in zip(data_lists[0], data_lists[1], data_lists[2])
            ]
            html = """
            <html>
            <head>
                <title>Data Viewer</title>
                <style>
                    table { border-collapse: collapse; width: 60%; margin: 20px auto; }
                    th, td { border: 1px solid #444; padding: 8px; text-align: center; }
                    th { background-color: #eee; }
                </style>
            </head>
            <body>
                <h2 style=\"text-align:center;\">Time, Speed, and Position Data</h2>
                <table>
                    <tr>
                        <th>Time</th>
                        <th>Speed</th>
                        <th>Position</th>
                    </tr>
                    {% for row in data %}
                    <tr>
                        <td>{{ row.time }}</td>
                        <td>{{ row.speed }}</td>
                        <td>{{ row.position }}</td>
                    </tr>
                    {% endfor %}
                </table>
                <div style="text-align:center; margin-top:20px;">
                    <a href="/one"><button style="padding: 12px 24px; font-size:18px;"}>One</button></a>
                    <a href="/two"><button style="padding: 12px 24px; font-size:18px;"}><b>Two</b></button></a>
                    <a href="/three"><button style="padding: 12px 24px; font-size:18px;"}>Three</button></a>
                </div>
            </body>
            </html>
            """
            return render_template_string(html, data=data)


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
            html = """
            <body style=\"text-align:center;\">
                <h1> Theming controls </h1>
                <h2> Status: {{ status }} </h2>
                <div style= "display: flex; justify-content: center; gap: 12px; margin-top: 20px;">
                    <form action="/start-theming" method="post">
                        <button style="padding: 12px 24px; font-size:18px;">Start</button>
                    </form>
                    <form action="/stop-theming" method="post">
                        <button style="padding: 12px 24px; font-size:18px;">Stop</button>
                    </form>
                </div>
            </body>
            <div style="text-align:center; margin-top:20px;">
                    <a href="/one"><button style="padding: 12px 24px; font-size:18px;"}>One</button></a>
                    <a href="/two"><button style="padding: 12px 24px; font-size:18px;"}>Two</button></a>
                    <a href="/three"><button style="padding: 12px 24px; font-size:18px;"}><b>Three</b></button></a>
            </div>
            """
            return render_template_string(html, status=status)
        serve(self.app, host="127.0.0.1")