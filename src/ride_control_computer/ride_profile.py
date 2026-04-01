# Ride profile dataclasses and JSON loader for TREC's REC Ride Control Computer
    # Made by Jackson Justus (jackjust@bu.edu)

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

VALID_COMPLETION_MODES = {"waitForBoth", "waitForEither", "duration", "waitForHome"}


@dataclass
class MotorCommand:
    """Command parameters for a single motor within a profile segment."""
    type: str       # Currently only "driveToPosition"
    position: int   # Target encoder count
    speed: int      # Max speed in QPPS
    accel: int      # Acceleration in QPPS/s
    decel: int      # Deceleration in QPPS/s

    @classmethod
    def fromDict(cls, d: dict) -> MotorCommand:
        return cls(
            type=d["type"],
            position=int(d["position"]),
            speed=int(d["speed"]),
            accel=int(d["accel"]),
            decel=int(d["decel"]),
        )


@dataclass
class ProfileSegment:
    """A single phase of a ride profile."""
    name: str
    completionMode: str         # "waitForBoth" | "waitForEither" | "duration" | "waitForHome"
    timeoutS: float             # Max seconds before the segment is force-aborted (→ ESTOP)
    motor1: MotorCommand | None = None   # None for duration-only or home segments
    motor2: MotorCommand | None = None
    durationS: float = 0.0      # Used only when completionMode == "duration"
    homeMotors: bool = False    # If True, triggers mc.homeMotors() instead of position commands
    endsCycle: bool = False     # If True, fires onCycleEnd callback when this segment starts

    @classmethod
    def fromDict(cls, d: dict) -> ProfileSegment:
        motor1 = MotorCommand.fromDict(d["motor1"]) if "motor1" in d else None
        motor2 = MotorCommand.fromDict(d["motor2"]) if "motor2" in d else None
        completionMode = d["completionMode"]
        if completionMode not in VALID_COMPLETION_MODES:
            raise ValueError(
                f"Invalid completionMode '{completionMode}' in segment '{d.get('name', '?')}'. "
                f"Must be one of: {sorted(VALID_COMPLETION_MODES)}"
            )
        return cls(
            name=d["name"],
            completionMode=completionMode,
            timeoutS=float(d.get("timeoutS", 30.0)),
            motor1=motor1,
            motor2=motor2,
            durationS=float(d.get("durationS", 0.0)),
            homeMotors=bool(d.get("homeMotors", False)),
            endsCycle=bool(d.get("endsCycle", False)),
        )


@dataclass
class RideProfile:
    """Complete ride profile loaded from a JSON file."""
    name: str
    rideDurationS: float
    segments: list[ProfileSegment] = field(default_factory=list)

    @classmethod
    def fromJson(cls, path: str) -> RideProfile:
        """Load and parse a ride profile from a JSON file."""
        logger.info(f"Loading ride profile from {path}")
        with open(path, "r") as f:
            data = json.load(f)

        segments = [ProfileSegment.fromDict(s) for s in data.get("segments", [])]
        profile = cls(
            name=data["name"],
            rideDurationS=float(data["rideDurationS"]),
            segments=segments,
        )
        logger.info(f"Loaded profile '{profile.name}' with {len(segments)} segment(s)")
        return profile
