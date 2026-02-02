from abc import ABC, abstractmethod
from flask import Flask, render_template_string
from typing import Callable


class WebserverController(ABC):
    """Webserver Controller and methods"""

    def __init__(self,
                 getSpeed: Callable[None, float],
                 getState: Callable[None, int]):
        self.app = Flask(__name__)
        self.getSpeed = getSpeed
        self.getState = getState

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
        self.app.run(debug=False)

