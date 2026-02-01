from abc import ABC
from flask import Flask, render_template_string


class WebserverController(ABC):
    """Webserver Controller and methods"""

    def __init__(self):
        self.app = Flask(__name__)

    def start(self):
        self.app.run(debug=True)

    def add_page(self, route, handler, methods=["GET"]):
        self.app.add_url_rule(route, route, handler, methods=methods)