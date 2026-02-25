# Fault monitor for TREC's REC Ride Control Computer
# Made by Jackson Justus (jackjust@bu.edu)

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

logger = logging.getLogger(__name__)


class FaultSeverity(Enum):
    LOW    = 1   # Logged; operation continues uninterrupted
    MEDIUM = 2   # Logged; operation continues uninterrupted
    HIGH   = 3   # Triggers automatic Level 1 E-Stop


@dataclass
class Fault:
    """A single monitored fault condition."""
    code: str                                # Unique identifier (e.g. "MC_COMM_FAILURE")
    severity: FaultSeverity
    description: str | Callable[[], str]    # Human-readable message logged on activation;
                                            # callable form is evaluated at fault-fire time
    condition: Callable[[], bool]           # Returns True when the fault is active
    active: bool = field(default=False, init=False, repr=False)


class FaultMonitor:
    """
    Continuously evaluates registered fault conditions and classifies them by severity.

    HIGH faults trigger an automatic Level 1 E-Stop (the caller is responsible for
    acting on the returned list). LOW and MEDIUM faults are logged but do not
    interrupt operation.

    All fault state transitions are logged:
      - Activation: logged at the level matching severity (error/warning/info)
      - Clearance: logged at info level
    """

    def __init__(self):
        self._faults: list[Fault] = []

    def register(self, fault: Fault) -> None:
        """Add a fault condition to be evaluated each tick."""
        self._faults.append(fault)

    def evaluate(self) -> list[Fault]:
        """
        Evaluate every registered fault condition.

        Returns:
            Faults that became active this tick (rising-edge only). The caller
            is responsible for acting on HIGH-severity entries (e.g. latching E-Stop).
        """
        newlyActive: list[Fault] = []
        for fault in self._faults:
            wasActive = fault.active
            try:
                fault.active = fault.condition()
            except Exception as e:
                logger.error(f"Exception evaluating fault [{fault.code}]: {e}")
                fault.active = True   # Treat evaluation failure as an active fault

            if fault.active and not wasActive:
                desc = fault.description() if callable(fault.description) else fault.description
                if fault.severity == FaultSeverity.HIGH:
                    logger.error(f"HIGH FAULT [{fault.code}]: {desc}")
                elif fault.severity == FaultSeverity.MEDIUM:
                    logger.warning(f"MEDIUM FAULT [{fault.code}]: {desc}")
                else:
                    logger.info(f"LOW FAULT [{fault.code}]: {desc}")
                newlyActive.append(fault)

            elif not fault.active and wasActive:
                logger.info(f"Fault cleared [{fault.code}]")

        return newlyActive

    def hasActiveFaults(self) -> bool:
        """True if any registered fault is currently active."""
        return any(f.active for f in self._faults)

    def getActiveFaults(self) -> list[Fault]:
        """Returns all currently active faults."""
        return [f for f in self._faults if f.active]
