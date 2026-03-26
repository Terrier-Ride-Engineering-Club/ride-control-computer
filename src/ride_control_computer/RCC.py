# Ride Control Computer for TREC's REC
    # Made by Jackson Justus (jackjust@bu.edu)

import logging
import threading
import time
from enum import Enum

from ride_control_computer.fault_monitor import Fault, FaultMonitor, FaultSeverity
from ride_control_computer.motor_controller.mc_faults import registerMotorControllerFaults
from ride_control_computer.loop_timer import LoopTimer
from ride_control_computer.motor_controller.MotorController import MotorController
from ride_control_computer.RideTimer import RideTimer, RideTimingData
from ride_control_computer.ride_profile import RideProfile
from ride_control_computer.ride_sequencer import RideSequencer
from ride_control_computer.theming_controller.ThemingController import ThemingController
from ride_control_computer.webserver.WebserverController import WebserverController
from ride_control_computer.control_panel.ControlPanel import ControlPanel, MomentaryButtonState, MomentarySwitchState, SustainedSwitchState
from ride_control_computer.RideTelemetry import RideTelemetryLogger

logger = logging.getLogger(__name__)


class RCCState(Enum):
    OFF         = 0   # Key switch at OFF; awaiting power-on
    IDLE        = 1   # Powered and ready for operator input
    RUNNING     = 2   # Ride actively executing sequence
    STOPPING    = 3   # Controlled return to home/loading position (7s timeout → ESTOP)
    RESETTING   = 4   # 1-second fault-check window after E-Stop reset is pressed
    ESTOP       = 5   # All motion halted; requires reset to clear
    FAULT       = 6   # Safety PLC has cut ride power (terminal until power-cycle)
    MAINTENANCE = 7   # Maintenance jog mode; dispatch unavailable


class RCC:
    """
    Class which holds the main ride control computer instance.

    Will own a ControlPanel, MotorController, and other implementations
    to interface with the rest of the ride.
    """

    __motorController: MotorController
    __controlPanel: ControlPanel
    __themingController: ThemingController
    __webserverController: WebserverController
    __sequencer: RideSequencer
    __faultMonitor: FaultMonitor

    __state: RCCState
    __preEstopState: RCCState

    __stateEntryTime: float

    __lastTelemPrintTime: float
    __loopTimer: LoopTimer
    __rideTimer: RideTimer

    TELEMETRY_PRINT_INTERVAL = 2    # seconds
    STOPPING_TIMEOUT_S       = 7.0  # max time in STOPPING before E-Stop
    RESETTING_DURATION_S     = 1.0  # fault-check window after reset pressed
    PROFILE_PATH             = "profiles/default.json"

    def __init__(
            self,
            motorController: MotorController,
            controlPanel: ControlPanel,
            themingController: ThemingController,
            webserverController: WebserverController,
            watchdogPort: str | None = None,
            watchdogBaud: int = 115200,
            ):
        self.__motorController = motorController
        self.__controlPanel = controlPanel
        self.__themingController = themingController
        self.__webserverController = webserverController

        profile = RideProfile.fromJson(self.PROFILE_PATH)
        self.__sequencer = RideSequencer(
            motorController,
            profile,
            onTimeout=lambda: self.__latchEstop([{
                "code": "SEQUENCER_TIMEOUT",
                "severity": "HIGH",
                "description": f"Ride segment '{self.__sequencer._currentSegment().name}' timed out",
            }]),
        )

        self.__faultMonitor = FaultMonitor()
        self.__registerFaults()

        if watchdogPort is not None:
            from ride_control_computer.plc_watchdog import PLCWatchdog
            self.__watchdog: PLCWatchdog | None = PLCWatchdog(
                port=watchdogPort,
                baud=watchdogBaud,
                getRccState=self.getState,
                mc=motorController,
            )
            self.__faultMonitor.register(Fault(
                code="WATCHDOG_PLC_TIMEOUT",
                severity=FaultSeverity.HIGH,
                description="No valid packet received from PLC within watchdog timeout",
                condition=self.__watchdog.isTimedOut,
            ))
            self.__faultMonitor.register(Fault(
                code="PLC_FAULT_WATCHDOG",
                severity=FaultSeverity.HIGH,
                description="PLC: RCC packets stopped (PLC-side watchdog fired)",
                condition=self.__watchdog.isWatchdogFault,
            ))
            self.__faultMonitor.register(Fault(
                code="PLC_FAULT_LIMIT_MISMATCH",
                severity=FaultSeverity.HIGH,
                description="PLC: limit switch readings disagree between PLC and RCC",
                condition=self.__watchdog.isLimitSwitchMismatch,
            ))
            self.__faultMonitor.register(Fault(
                code="PLC_FAULT_BAD_CRC",
                severity=FaultSeverity.HIGH,
                description="PLC: received RCC packet with invalid CRC",
                condition=self.__watchdog.isBadCrcFault,
            ))
            self.__faultMonitor.register(Fault(
                code="PLC_FAULT_ECHO_COUNTER",
                severity=FaultSeverity.HIGH,
                description="PLC: RCC not echoing PLC counter within allowed lag",
                condition=self.__watchdog.isEchoFault,
            ))
            self.__faultMonitor.register(Fault(
                code="PLC_FAULT_MOTION",
                severity=FaultSeverity.HIGH,
                description="PLC: motion envelope violation (motor speed exceeded 9500 QPPS)",
                condition=self.__watchdog.isMotionFault,
            ))
            self.__faultMonitor.register(Fault(
                code="PLC_FAULT_LEVEL0",
                severity=FaultSeverity.HIGH,
                description="PLC: Level 0 fault — relay cut, key must be cycled to OFF to recover",
                condition=self.__watchdog.isLevel0Fault,
            ))
        else:
            self.__watchdog = None

        self._stopEvent = threading.Event()

        self.__state = RCCState.IDLE
        self.__preEstopState = RCCState.IDLE
        self.__lastEstopFaults: list[dict] = []

        self.__stateEntryTime = 0.0

        self.__lastTelemPrintTime = 0
        self.__loopTimer = LoopTimer()
        self.__rideTimer = RideTimer()

        self.__telemetryLogger = RideTelemetryLogger()

        # Map control panel callbacks
        controlPanel.addDispatchCallback(self.__onDispatch)
        controlPanel.addResetCallback(self.__onReset)
        controlPanel.addStopCallback(self.__onStop)
        controlPanel.addEstopCallback(self.__onEstop)
        controlPanel.addPowerSwitchCallback(self.__onPowerSwitch)
        controlPanel.addMaintenanceJogSwitchCallback(self.__onMaintenanceJogSwitch)

    def set_webserver(self,webserverController: WebserverController):
        """sets the webserver controller that will be used"""
        self.__webserverController = webserverController
    # =========================================================================
    #                           LIFECYCLE
    # =========================================================================

    def run(self):
        """Blocking call to start the Ride Control Computer."""

        self.__controlPanel.start()

        threading.Thread(
            target=self.__webserverController.start,
            daemon=True,
            name="WebserverMainThread"
            ).start()

        try:
            self.__motorController.start()
        except Exception as e:
            logger.critical(f"Motor controller failed to start: {e} — entering FAULT state")
            self.__setState(RCCState.FAULT)

        if self.__watchdog is not None:
            self.__watchdog.start()

        time.sleep(0.05)

        while not self._stopEvent.is_set():
            self.__motorController.heartbeat()
            self.__processInputs()
            self.__updateState()
            self.__monitorSafety()
            self.__controlPanel.updateIndicators(self.__state, self.__faultMonitor.hasActiveFaults())
            self.__printTelemetry()

            self.__telemetryLogger.logSample(self.__webserverController.getElapsedTime(),self.__webserverController.getPositions(),self.__webserverController.getSpeed(),self.__webserverController.getCurrents(),self.__webserverController.getVoltage(),self.__webserverController.getTemperatures())

            self.__loopTimer.tick()
            time.sleep(0.001)

    def shutdown(self) -> None:
        """Stop the main loop and cleanly shut down all subsystems."""
        logger.info("RCC shutting down")
        self._stopEvent.set()
        self.__controlPanel.shutdown()
        self.__themingController.stopShow()
        self.__motorController.shutdown()
        if self.__watchdog is not None:
            self.__watchdog.shutdown()

    # =========================================================================
    #                           STATE MANAGEMENT
    # =========================================================================

    def __setState(self, newState: RCCState):
        """
        Centralized state transition. All state changes go through here.
        Handles exit/entry actions and ride timer events.
        """
        if newState == self.__state:
            return

        oldState = self.__state
        self.__state = newState
        logger.info(f"RCC State: {oldState.name} -> {newState.name}")

        # Exit actions
        if oldState == RCCState.RUNNING:
            self.__rideTimer.endRide()
            self.__telemetryLogger.endRide()

        if oldState == RCCState.RESETTING:
            self.__rideTimer.endEstop()

        # Entry actions
        if newState == RCCState.RUNNING:
            self.__rideTimer.startRide()
            self.__telemetryLogger.startRide()

        elif newState == RCCState.ESTOP:
            self.__preEstopState = oldState
            self.__rideTimer.startEstop()
            self.__motorController.haltMotion()
            self.__themingController.stopShow()
        elif newState == RCCState.STOPPING:
            self.__stateEntryTime = time.monotonic()
            self.__sequencer.abort()
            self.__motorController.homeMotors()
            self.__themingController.stopShow()
        elif newState == RCCState.RESETTING:
            self.__stateEntryTime = time.monotonic()
            self.__lastEstopFaults = []
        elif newState == RCCState.FAULT:
            # The safety PLC will cut ride power immediately on FAULT entry,
            # which means the Pi loses power. haltMotion() here is best-effort.
            self.__motorController.haltMotion()
            logger.critical("FAULT state entered — safety PLC should cut power imminently")

    def getState(self) -> RCCState:
        """Returns the current RCC state."""
        return self.__state

    # =========================================================================
    #                           MAIN LOOP STEPS
    # =========================================================================

    def __processInputs(self):
        """Drain the control panel callback queue, firing any pending button/switch events."""
        self.__controlPanel.triggerCallbacks()

    def __updateState(self):
        """Advance any timed state transitions (RUNNING sequence, STOPPING timeout, RESETTING window)."""
        if self.__state == RCCState.RUNNING:
            self.__checkRunningProgress()
        elif self.__state == RCCState.STOPPING:
            self.__checkStoppingProgress()
        elif self.__state == RCCState.RESETTING:
            self.__checkResettingComplete()

    def __latchEstop(self, cause: list[dict]) -> None:
        """Save the E-Stop cause and transition to ESTOP state."""
        self.__lastEstopFaults = cause
        self.__setState(RCCState.ESTOP)

    def __monitorSafety(self):
        """Evaluate all fault conditions; latch E-Stop on any HIGH fault."""
        if self.__state in (RCCState.RESETTING, RCCState.FAULT, RCCState.OFF):
            return

        newlyActive = self.__faultMonitor.evaluate()

        if self.__state == RCCState.ESTOP:
            # Already in E-Stop — keep fault states current for display, but don't
            # overwrite __lastEstopFaults or re-trigger a state transition.
            if newlyActive:
                codes = ", ".join(f.code for f in newlyActive)
                logger.warning(f"Additional fault(s) became active during E-Stop: {codes}")
            return

        highFaults = [f for f in newlyActive if f.severity == FaultSeverity.HIGH]
        if highFaults:
            codes = ", ".join(f.code for f in highFaults)
            logger.warning(f"High-severity fault(s) detected — latching E-Stop: {codes}")
            self.__latchEstop(self.__serializeFaults(highFaults))

    # =========================================================================
    #                           TIMED STATE TRANSITIONS
    # =========================================================================

    def __checkRunningProgress(self):
        """
        Called every loop tick while in RUNNING.
        Advances the ride sequencer; restarts it automatically when the profile completes.
        """
        self.__sequencer.tick()
        if self.__sequencer.isComplete():
            logger.info("Ride profile complete — restarting profile")
            self.__sequencer.start()

    def __checkStoppingProgress(self):
        """
        Called every loop tick while in STOPPING.
        Transitions to IDLE once homing is confirmed complete,
        or triggers ESTOP if the 7-second timeout expires.
        """
        elapsed = time.monotonic() - self.__stateEntryTime
        if elapsed > self.STOPPING_TIMEOUT_S:
            logger.warning("Stopping timed out — latching E-Stop")
            self.__latchEstop([{
                "code": "STOPPING_TIMEOUT",
                "severity": "HIGH",
                "description": f"Motors did not reach home within {self.STOPPING_TIMEOUT_S:.0f}s timeout",
            }])
        elif self.__motorController.isHomingComplete():
            logger.info("Homing complete — returning to IDLE")
            self.__setState(RCCState.IDLE)

    def __checkResettingComplete(self):
        """
        Called every loop tick while in RESETTING.
        After RESETTING_DURATION_S, re-evaluates all faults.
        Transitions to IDLE (or MAINTENANCE) if all clear, back to ESTOP if any fault is active.
        """
        elapsed = time.monotonic() - self.__stateEntryTime
        if elapsed >= self.RESETTING_DURATION_S:
            self.__faultMonitor.evaluate()
            activeFaults = self.__faultMonitor.getActiveFaults()
            if activeFaults:
                codes = ", ".join(f.code for f in activeFaults)
                logger.warning(f"Reset blocked: active fault(s) [{codes}] — returning to E-Stop")
                self.__latchEstop(self.__serializeFaults(activeFaults))
            elif self.__preEstopState == RCCState.MAINTENANCE:
                self.__setState(RCCState.MAINTENANCE)
            else:
                self.__setState(RCCState.IDLE)

    # =========================================================================
    #                           FAULT REGISTRATION
    # =========================================================================

    def __registerFaults(self) -> None:
        """Register all monitored fault conditions with the fault monitor."""
        registerMotorControllerFaults(
            self.__faultMonitor,
            self.__motorController,
            isMotionForbidden=lambda: self.__state in (RCCState.IDLE, RCCState.OFF),
            isMotor1AtTopLimit= lambda: self.__motorController.isAtTopLimit(1),
            isMotor2AtTopLimit= lambda: self.__motorController.isAtTopLimit(2),
            isMotor1AtBottomLimit= lambda: self.__motorController.isAtBottomLimit(1),
            isMotor2AtBottomLimit= lambda: self.__motorController.isAtBottomLimit(2),

        )

    # =========================================================================
    #                           PUBLIC ACCESSORS
    # =========================================================================

    def isEstopResetInhibited(self) -> bool:
        """Returns True if software is inhibiting E-Stop reset."""
        return self.__state == RCCState.ESTOP

    def getRideTimingData(self) -> RideTimingData:
        """Returns the ride timing data object. Used by webserver."""
        return self.__rideTimer.data

    def getCurrentRideElapsed(self) -> float:
        """Returns the current ride elapsed time. Used by webserver."""
        return self.__rideTimer.data.getCurrentRideElapsed()

    def getAverageRideDuration(self) -> float:
        """Returns the average ride elapsed time. Used by webserver."""
        return self.__rideTimer.data.getAverageRideDuration()

    def getTelemetryLogger(self):
        return self.__telemetryLogger

    def getWatchdogStatus(self) -> str:
        """Returns watchdog status as a display string: DISABLED, DISCONNECTED, OK, PLC_ERROR, or TIMEOUT."""
        if self.__watchdog is None:
            return "DISABLED"
        details = self.__watchdog.getDetails()
        if not details["portOpen"]:
            return "DISCONNECTED"
        if self.__watchdog.isTimedOut():
            return "TIMEOUT"
        if not self.__watchdog.isPlcOk():
            return "PLC_ERROR"
        return "OK"

    def getWatchdogDetails(self) -> dict:
        """Returns detailed watchdog communication state for the webserver."""
        if self.__watchdog is None:
            return {"status": "DISABLED"}
        details = self.__watchdog.getDetails()
        details["status"] = self.getWatchdogStatus()
        return details

    def __serializeFaults(self, faults) -> list[dict]:
        result = []
        for f in faults:
            desc = f.description() if callable(f.description) else f.description
            result.append({"code": f.code, "severity": f.severity.name, "description": desc})
        return result

    def getActiveFaults(self) -> list[dict]:
        """Returns currently active fault conditions (live peek, no side effects)."""
        return self.__serializeFaults(self.__faultMonitor.peekActiveFaults())

    def getLastEstopFaults(self) -> list[dict]:
        """Returns the faults that triggered the most recent E-Stop latch.
        Persists until the operator presses reset (cleared on RESETTING entry).
        """
        return self.__lastEstopFaults

    # =========================================================================
    #                           CONTROL PANEL CALLBACKS
    # =========================================================================

    def __onDispatch(self, state: MomentaryButtonState) -> None:
        if state == MomentaryButtonState.PRESSED:
            logger.info("Dispatch pressed")

            if self.__state != RCCState.IDLE:
                logger.info(f"Dispatch ignored: state is {self.__state.name}")
                return

            self.__themingController.startShow()
            self.__sequencer.start()
            self.__setState(RCCState.RUNNING)

    def __onReset(self, state: MomentaryButtonState) -> None:
        if state == MomentaryButtonState.PRESSED:
            logger.info("Reset pressed")

            if self.__state != RCCState.ESTOP:
                return

            if self.__motorController.isEstopActive():
                logger.warning("Cannot reset: hardware E-Stop still active")
                return

            logger.info("Hardware E-Stop cleared — entering RESETTING")
            self.__setState(RCCState.RESETTING)

    def __onStop(self, state: MomentaryButtonState) -> None:
        if state == MomentaryButtonState.PRESSED:
            logger.info("Stop pressed")

            if self.__state == RCCState.RUNNING:
                self.__setState(RCCState.STOPPING)

    def __onEstop(self, state: MomentaryButtonState) -> None:
        if state == MomentaryButtonState.PRESSED:
            if self.__state == RCCState.OFF:
                logger.warning("E-Stop pressed in OFF state — ignored")
                return
            logger.warning("E-Stop button pressed — latching")
            self.__latchEstop([{
                "code": "MANUAL_ESTOP",
                "severity": "HIGH",
                "description": "E-Stop button pressed by operator",
            }])

    def __onPowerSwitch(self, state: SustainedSwitchState) -> None:
        """
        Handles the 3-position key switch: OFF / ON / MAINTENANCE.

        SustainedSwitchState.OFF         → key switch at OFF position
        SustainedSwitchState.ON          → key switch at ON position (normal operation)
        SustainedSwitchState.MAINTENANCE → key switch at MAINTENANCE position
        """
        if state == SustainedSwitchState.MAINTENANCE:
            logger.info("Key switch → MAINTENANCE")
            if self.__state == RCCState.OFF:
                self.__setState(RCCState.MAINTENANCE)
            elif self.__state == RCCState.RUNNING:
                logger.warning("Key switch to MAINTENANCE during RUNNING — fault")
                self.__latchEstop([{
                    "code": "KEY_SWITCH_FAULT",
                    "severity": "HIGH",
                    "description": "Key switch moved to MAINTENANCE while ride was active",
                }])

        elif state == SustainedSwitchState.ON:
            logger.info("Key switch → ON")
            if self.__state in (RCCState.MAINTENANCE, RCCState.OFF):
                self.__setState(RCCState.IDLE)

        elif state == SustainedSwitchState.OFF:
            logger.info("Key switch → OFF")

            if self.__state == RCCState.IDLE:
                self.__setState(RCCState.OFF)
            # Per spec: if ride is active (not IDLE), no action is taken

    def __onMaintenanceJogSwitch(self, state: MomentarySwitchState) -> None:
        if self.__state != RCCState.MAINTENANCE:
            return

        if state == MomentarySwitchState.UP:
            logger.info("Jog forward")
            self.__motorController.jogMotor(1, 1)
            self.__motorController.jogMotor(2, 1)

        elif state == MomentarySwitchState.DOWN:
            logger.info("Jog reverse")
            self.__motorController.jogMotor(1, -1)
            self.__motorController.jogMotor(2, -1)

        elif state == MomentarySwitchState.NEUTRAL:
            logger.info("Jog released")
            self.__motorController.stopMotion()

    # =========================================================================
    #                              TELEMETRY
    # =========================================================================

    def __printTelemetry(self):
        """Periodically prints telemetry data."""

        elapsed = time.monotonic() - self.__lastTelemPrintTime
        if elapsed >= self.TELEMETRY_PRINT_INTERVAL:
            self.__lastTelemPrintTime = time.monotonic()
            mcStatus = "DEAD" if self.__motorController.isTelemetryStale() else "HEALTHY"

            logger.info("======================== Telemetry ========================")
            logger.info(f"[RCC State]: {self.__state.name}")
            logger.debug(f"[MC Type]: {str(type(self.__motorController))}")
            logger.info(f"[MC Connection]: {mcStatus}")
            logger.info(f"[MC State]: {self.__motorController.getState()}")
            logger.info(f"[Watchdog]: {self.getWatchdogDetails()}")
            rt = self.__rideTimer.data
            rideStatus = f"RUNNING ({rt.getCurrentRideElapsed():.1f}s)" if rt.rideActive else "—"
            logger.info(f"[Uptime]: {rt.getUptime():.1f}s")
            logger.info(f"[Ride]: {rideStatus}")
            logger.info(f"[Rides]: {rt.totalRideCycles} total | last: {rt.lastRideDuration:.2f}s | avg: {rt.getAverageRideDuration():.2f}s")
            logger.info(f"[E-Stop]: count={rt.totalEstopCount} | total time={rt.totalEstopTime:.1f}s")
            lt = self.__loopTimer
            thread_names = [t.name for t in threading.enumerate()]
            logger.debug(f"[RCC dt]: {lt.dt * 1000:.2f} ms | avg: {lt.avg * 1000:.2f} ms | p95: {lt.p95 * 1000:.2f} ms. ")
            lt.reset()

            cp_lt = self.__controlPanel.loopTimer
            logger.debug(f"    [ControlPanel dt]:   {cp_lt.dt * 1000:.2f} ms | avg: {cp_lt.avg * 1000:.2f} ms | p95: {cp_lt.p95 * 1000:.2f} ms")
            cp_lt.reset()

            mc_lt = self.__motorController.loopTimer
            if mc_lt is not None:
                logger.debug(f"    [MC dt]:   {mc_lt.dt * 1000:.2f} ms | avg: {mc_lt.avg * 1000:.2f} ms | p95: {mc_lt.p95 * 1000:.2f} ms")
                mc_lt.reset()

            logger.debug(f"Alive threads ({threading.active_count()}): {thread_names}")

            logger.info("===========================================================")
