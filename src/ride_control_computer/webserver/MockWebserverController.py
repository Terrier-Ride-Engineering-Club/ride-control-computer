from ride_control_computer.webserver.WebserverController import WebserverController
from flask import Flask, render_template_string

class MockWebserverController(WebserverController):

    def __init__(self, getSpeed, getState, startTheming, stopTheming, themeStatus):
        super().__init__(getSpeed,getState, startTheming, stopTheming, themeStatus)

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
            html = """
                <h1 style='text-align:center;'>speed = {{ speed }}, state = {{ state }}</h2>
                <div style="text-align:center; margin-top:20px;">
                    <a href="/one"><button style="padding: 12px 24px; font-size:18px;"}><b>One</b></button></a>
                    <a href="/two"><button style="padding: 12px 24px; font-size:18px;"}>Two</button></a>
                    <a href="/three"><button style="padding: 12px 24px; font-size:18px;"}>Three</button></a>
                </div>"""
            return render_template_string(html, speed=speed, state=state)

        @self.app.route('/two')
        def two():
            time_list = [1, 2, 3, 4, 5]
            speed_list = [10, 20, 30, 40, 50]
            position_list = [11, 21, 31, 41, 51]
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

        @self.app.route('/three')
        def three():
            status = self.themeStatus
            html = """
            <body style=\"text-align:center;\">
                <h1> Theming controls </h1>
                <h2> Status: {{ status }} </h2>
                <button style="padding: 12px 24px; font-size:18px;" name="Start" onclick="self.startTheming()">Start</button>
                <button style="padding: 12px 24px; font-size:18px;" name="Stop" onclick="self.stopTheming()">Stop</button>
            </body>
            <div style="text-align:center; margin-top:20px;">
                    <a href="/one"><button style="padding: 12px 24px; font-size:18px;"}>One</button></a>
                    <a href="/two"><button style="padding: 12px 24px; font-size:18px;"}>Two</button></a>
                    <a href="/three"><button style="padding: 12px 24px; font-size:18px;"}><b>Three</b></button></a>
            </div>
            """
            return render_template_string(html, status=status)
        self.app.run(debug=False)