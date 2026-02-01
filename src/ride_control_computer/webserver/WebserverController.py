from abc import ABC, abstractmethod
from flask import Flask, render_template_string
from typing import Callable


class WebserverController(ABC):
    """Webserver Controller and methods"""

    def __init__(self,
                 getSpeed: Callable[None, float]):
        self.app = Flask(__name__)
        self.getSpeed = getSpeed

    def start(self):
        self.app.run(debug=True)

    def add_page(self, route, handler, methods=["GET"]):
        self.app.add_url_rule(route, route, handler, methods=methods)