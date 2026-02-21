"""
Ride Telemetry Logger
Records position, velocity, and elapsed ride time snapshots
so data can be compared across multiple rides.
"""

from dataclasses import dataclass, field
import time
from typing import List, Tuple


# ============================================================
# Snapshot Data Structure
# ============================================================

@dataclass
class TelemetrySample:
    """
    Single telemetry sample at a given time.
    """
    rideElapsed: float
    motor1Position: int
    motor2Position: int
    motor1Velocity: float
    motor2Velocity: float


# ============================================================
# Ride Telemetry Container
# ============================================================

@dataclass
class RideTelemetryData:
    """
    Holds telemetry samples for a single ride.
    """
    rideIndex: int
    startTime: float = field(default_factory=time.monotonic)
    samples: List[TelemetrySample] = field(default_factory=list)

    def addSample(
        self,
        rideElapsed: float,
        positions: Tuple[int, int],
        velocities: Tuple[float, float],
    ) -> None:
        """
        Add a telemetry snapshot.
        """
        sample = TelemetrySample(
            rideElapsed=rideElapsed,
            motor1Position=positions[0],
            motor2Position=positions[1],
            motor1Velocity=velocities[0],
            motor2Velocity=velocities[1],
        )
        self.samples.append(sample)


# ============================================================
# Telemetry Logger (Manages Multiple Rides)
# ============================================================

class RideTelemetryLogger:
    """
    Owns and manages telemetry across multiple ride cycles.
    """

    def __init__(self):
        self._rides: List[RideTelemetryData] = []
        self._currentRide: RideTelemetryData | None = None

    # --------------------------------------------------------

    def startRide(self) -> None:
        """
        Call when RCC enters RUNNING state.
        """
        rideIndex = len(self._rides) + 1
        self._currentRide = RideTelemetryData(rideIndex=rideIndex)

    # --------------------------------------------------------

    def logSample(
        self,
        rideElapsed: float,
        positions: Tuple[int, int],
        velocities: Tuple[float, float],
    ) -> None:
        """
        Log a telemetry snapshot for the active ride.
        """
        if self._currentRide is None:
            return

        self._currentRide.addSample(rideElapsed, positions, velocities)

    # --------------------------------------------------------

    def endRide(self) -> None:
        """
        Call when RCC leaves RUNNING state.
        """
        if self._currentRide is None:
            return

        self._rides.append(self._currentRide)
        self._currentRide = None

    # --------------------------------------------------------

    def getAllRides(self) -> List[RideTelemetryData]:
        """
        Returns telemetry for all completed rides.
        """
        return self._rides

    # --------------------------------------------------------

    def getCurrentRide(self) -> RideTelemetryData | None:
        """
        Returns current active ride telemetry.
        """
        return self._currentRide