# Ride sequencer for TREC's REC Ride Control Computer
    # Made by Jackson Justus (jackjust@bu.edu)

from __future__ import annotations

import time
import logging
from typing import Callable

from ride_control_computer.motor_controller.MotorController import MotorController
from ride_control_computer.ride_profile import RideProfile, ProfileSegment

logger = logging.getLogger(__name__)


class RideSequencer:
    """
    Executes a RideProfile by issuing motor commands and polling for segment completion.

    The RCC calls tick() every loop iteration while in RUNNING state.
    When all segments complete, isComplete() returns True and the RCC restarts
    the profile by calling start() again.

    If a segment exceeds its timeoutS, abort() is called and the onTimeout
    callback fires so the RCC can latch ESTOP.
    """

    def __init__(
        self,
        mc: MotorController,
        profile: RideProfile,
        onTimeout: Callable[[], None] | None = None,
    ):
        self._mc = mc
        self._profile = profile
        self._onTimeout = onTimeout

        self._currentSegmentIndex: int = 0
        self._segmentStartTime: float = 0.0
        self._active: bool = False
        self._complete: bool = False

    # =========================================================================
    #                           PUBLIC API
    # =========================================================================

    def start(self) -> None:
        """Issue commands for the first segment and start the clock."""
        self._currentSegmentIndex = 0
        self._complete = False
        self._active = True
        self._startSegment(0)

    def tick(self) -> None:
        """
        Called every RCC loop tick while in RUNNING state.
        Checks if the current segment is done; advances to the next on completion.
        Calls abort() and fires onTimeout if a segment exceeds its timeout.
        """
        if not self._active or self._complete:
            return

        segment = self._currentSegment()
        elapsed = time.monotonic() - self._segmentStartTime

        # Timeout check (takes priority over completion)
        if elapsed > segment.timeoutS:
            logger.warning(
                f"Segment '{segment.name}' timed out after {elapsed:.1f}s "
                f"(limit {segment.timeoutS}s) — triggering E-Stop"
            )
            self.abort()
            if self._onTimeout:
                self._onTimeout()
            return

        # Completion check
        if self._isSegmentComplete(segment):
            nextIndex = self._currentSegmentIndex + 1
            if nextIndex >= len(self._profile.segments):
                logger.info(f"Segment '{segment.name}' complete — all segments finished")
                self._complete = True
                self._active = False
            else:
                logger.info(f"Segment '{segment.name}' complete — advancing to next")
                self._startSegment(nextIndex)

    def isComplete(self) -> bool:
        """True when all segments in the profile have been executed."""
        return self._complete

    def abort(self) -> None:
        """Stop segment advancement. Does not issue any motor stop commands."""
        self._active = False

    # =========================================================================
    #                           INTERNAL HELPERS
    # =========================================================================

    def _startSegment(self, index: int) -> None:
        self._currentSegmentIndex = index
        self._segmentStartTime = time.monotonic()
        segment = self._profile.segments[index]

        logger.info(f"Starting segment [{index + 1}/{len(self._profile.segments)}]: '{segment.name}'")

        if segment.motor1 is not None:
            cmd = segment.motor1
            self._mc.driveToPosition(1, cmd.position, cmd.speed, cmd.accel, cmd.decel)

        if segment.motor2 is not None:
            cmd = segment.motor2
            self._mc.driveToPosition(2, cmd.position, cmd.speed, cmd.accel, cmd.decel)

    def _currentSegment(self) -> ProfileSegment:
        return self._profile.segments[self._currentSegmentIndex]

    def _isSegmentComplete(self, segment: ProfileSegment) -> bool:
        elapsed = time.monotonic() - self._segmentStartTime

        if segment.completionMode == "waitForBoth":
            return self._mc.isMotorNearTarget(1) and self._mc.isMotorNearTarget(2)
        elif segment.completionMode == "waitForEither":
            return self._mc.isMotorNearTarget(1) or self._mc.isMotorNearTarget(2)
        elif segment.completionMode == "duration":
            return elapsed >= segment.durationS
        else:
            logger.error(f"Unknown completionMode '{segment.completionMode}' — treating as complete")
            return True
