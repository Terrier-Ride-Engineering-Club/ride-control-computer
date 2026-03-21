from abc import ABC,abstractmethod

class ThemingController(ABC):
    """
    Interface for a Theming Controller
    """

    def __init__(self):
        ...

    @abstractmethod
    def startShow(self):
        """Called by the Theming Controller owner to signal that the ride sequence has started."""
        ...

    @abstractmethod
    def stopShow(self):
        """Called by the Theming Controller owner to signal that the ride sequence has stopped."""
        ...

    @abstractmethod
    def getStatus(self) -> str:
        """called by the Theming Controller owner to get the current status of the theming sequence"""
        ...