# Ride Timer for TREC's REC Ride Control Computer
    # Made by Jackson Justus (jackjust@bu.edu)

import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class RideTimingData:
    """Snapshot of all ride-cycle timing statistics for the current session."""

    # Ride cycle tracking
    rideActive: bool = False
    rideStartTime: float = 0.0
    lastRideDuration: float = 0.0
    totalRideCycles: int = 0
    totalRideTime: float = 0.0

    # E-Stop tracking
    estopActive: bool = False
    estopStartTime: float = 0.0
    totalEstopTime: float = 0.0
    totalEstopCount: int = 0

    # Session tracking
    sessionStartTime: float = field(default_factory=time.monotonic)

    def getUptime(self) -> float:
        """Returns session uptime in seconds."""
        return time.monotonic() - self.sessionStartTime

    def getCurrentRideElapsed(self) -> float:
        """Returns elapsed time of current ride, or 0.0 if no ride active."""
        if not self.rideActive:
            return 0.0
        return time.monotonic() - self.rideStartTime

    def getCurrentEstopElapsed(self) -> float:
        """Returns elapsed time of current e-stop, or 0.0 if not in e-stop."""
        if not self.estopActive:
            return 0.0
        return time.monotonic() - self.estopStartTime

    def getAverageRideDuration(self) -> float:
        """Returns average ride duration, or 0.0 if no rides completed."""
        if self.totalRideCycles == 0:
            return 0.0
        return self.totalRideTime / self.totalRideCycles


class RideTimer:
    """
    Encapsulates ride-cycle timing logic.

    Owned by RCC. Exposes a RideTimingData instance that can be
    shared (by reference or via a getter callable) with the webserver.
    """

    def __init__(self):
        self._data = RideTimingData()

    @property
    def data(self) -> RideTimingData:
        """Returns the mutable timing data object."""
        return self._data

    def startRide(self) -> None:
        """Called when a ride cycle begins (dispatch -> startRideSequence)."""
        self._data.rideActive = True
        self._data.rideStartTime = time.monotonic()

    def endRide(self) -> None:
        """Called when a ride cycle ends (MC leaves SEQUENCING). Idempotent."""
        if not self._data.rideActive:
            return
        duration = time.monotonic() - self._data.rideStartTime
        self._data.lastRideDuration = duration
        self._data.totalRideCycles += 1
        self._data.totalRideTime += duration
        self._data.rideActive = False
        logger.info(f"Ride cycle completed: {duration:.2f}s (total: {self._data.totalRideCycles})")

    def startEstop(self) -> None:
        """Called when e-stop is latched."""
        if self._data.estopActive:
            return
        self._data.estopActive = True
        self._data.estopStartTime = time.monotonic()
        self._data.totalEstopCount += 1
        # If a ride was active when e-stop hit, end it
        self.endRide()

    def endEstop(self) -> None:
        """Called when e-stop latch is cleared."""
        if not self._data.estopActive:
            return
        duration = time.monotonic() - self._data.estopStartTime
        self._data.totalEstopTime += duration
        self._data.estopActive = False
