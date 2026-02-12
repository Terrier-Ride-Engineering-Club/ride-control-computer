# Ride Control Computer for TREC's REC
    # Made by Jackson Justus (jackjust@bu.edu)

import logging
import threading
import time
from enum import Enum

from ride_control_computer.loop_timer import LoopTimer
from ride_control_computer.motor_controller.MotorController import MotorController
from ride_control_computer.RideTimer import RideTimer, RideTimingData
from ride_control_computer.theming_controller.ThemingController import ThemingController
from ride_control_computer.webserver.WebserverController import WebserverController
from ride_control_computer.control_panel.ControlPanel import ControlPanel, MomentaryButtonState, MomentarySwitchState, SustainedSwitchState

logger = logging.getLogger(__name__)


class RCCState(Enum):
    IDLE =          0
    RUNNING =       1
    ESTOP =         2
    MAINTENANCE =   3


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

    __state: RCCState
    __maintenanceSwitchOn: bool

    __lastTelemPrintTime: float
    __loopTimer: LoopTimer
    __rideTimer: RideTimer
    TELEMETRY_PRINT_INTERVAL = 2; # time in s

    def __init__(
            self,
            motorController: MotorController,
            controlPanel: ControlPanel,
            themingController: ThemingController,
            #webserverController: WebserverController
            ):
        self.__motorController = motorController
        self.__controlPanel = controlPanel
        self.__themingController = themingController
        self.__webserverController = None

        self.__state = RCCState.IDLE
        self.__maintenanceSwitchOn = False

        self.__lastTelemPrintTime = 0
        self.__loopTimer = LoopTimer()
        self.__rideTimer = RideTimer()

        # Map control panel callbacks
        controlPanel.addDispatchCallback(self.__onDispatch)
        controlPanel.addResetCallback(self.__onReset)
        controlPanel.addStopCallback(self.__onStop)
        controlPanel.addEstopCallback(self.__onEstop)
        controlPanel.addMaintenanceSwitchCallback(self.__onMaintenanceSwitch)
        controlPanel.addMaintenanceJogSwitchCallback(self.__onMaintenanceJogSwitch)

    def set_webserver(self,webserverController: WebserverController):
        """sets the webserver controller that will be used"""
        self.__webserverController = webserverController
    # =========================================================================
    #                           LIFECYCLE
    # =========================================================================

    def run(self):
        """Blocking call to start the Ride Control Computer."""

        threading.Thread(
            target=self.__controlPanel.run,
            daemon=True,
            name="ControlPanelListener"
            ).start()

        threading.Thread(
            target=self.__webserverController.start,
            daemon=True,
            name="WebserverMainThread"
            ).start()

        self.__motorController.start()

        time.sleep(0.05)

        while True:
            self.__controlPanel.triggerCallbacks()

            if self.__state != RCCState.ESTOP:
                # Latch E-Stop if hardware reports it active
                if self.__motorController.isEstopActive():
                    logger.warning("Hardware E-Stop detected — latching")
                    self.__setState(RCCState.ESTOP)
                else:
                    self.__checkSafetyConstraints()

            self.__printTelemetry()

            self.__loopTimer.tick()
            time.sleep(0.001)

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
        if oldState == RCCState.ESTOP:
            self.__rideTimer.endEstop()

        # Enter actions
        if newState == RCCState.RUNNING:
            self.__rideTimer.startRide()
        if newState == RCCState.ESTOP:
            self.__rideTimer.startEstop()
            self.__motorController.haltMotion()
            self.__themingController.stopShow()

    def getState(self) -> RCCState:
        """Returns the current RCC state."""
        return self.__state

    # =========================================================================
    #                           SAFETY
    # =========================================================================

    def __checkSafetyConstraints(self):
        """
        Run all safety constraint checks. If any constraint fails,
        latch the E-Stop. Add new constraints as elif branches below.
        """
        violation = self.__evaluateConstraints()
        if violation is not None:
            logger.warning(f"Safety constraint violated: {violation} — latching E-Stop")
            self.__setState(RCCState.ESTOP)

    def __evaluateConstraints(self) -> str | None:
        """
        Evaluate all safety constraints.

        Returns:
            A description of the first violated constraint, or None if all pass.
        """
        # MOTOR CONTROLLER CONSTR.
        mcEStopActive = self.__motorController.isEstopActive()
        if mcEStopActive:
            return f"MC E-Stop Active."
        if self.__motorController.isTelemetryStale():
            return f"MC Telemetry stale -> {self.__motorController.getTelemetryAge()}s since last fetch."
        controllerStatus = self.__motorController.getControllerStatus()
        if controllerStatus != "Normal":
            return f"MC Abnormal Status: {controllerStatus}"

        return None

    # =========================================================================
    #                                E-STOP
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
            self.__motorController.startRideSequence()
            self.__setState(RCCState.RUNNING)

    def __onReset(self, state: MomentaryButtonState) -> None:
        if state == MomentaryButtonState.PRESSED:
            logger.info("Reset pressed")

            if self.__state != RCCState.ESTOP:
                return

            if self.__motorController.isEstopActive():
                logger.warning("Cannot reset: hardware E-Stop still active")
                return

            logger.info("E-Stop cleared — releasing latch")
            if self.__maintenanceSwitchOn:
                self.__setState(RCCState.MAINTENANCE)
            else:
                self.__setState(RCCState.IDLE)

    def __onStop(self, state: MomentaryButtonState) -> None:
        if state == MomentaryButtonState.PRESSED:
            logger.info("Stop pressed")

            self.__motorController.stopMotion()
            self.__themingController.stopShow()

            if self.__state == RCCState.RUNNING:
                self.__setState(RCCState.IDLE)

    def __onEstop(self, state: MomentaryButtonState) -> None:
        if state == MomentaryButtonState.PRESSED:
            logger.warning("E-Stop button pressed — latching")
            self.__setState(RCCState.ESTOP)

    def __onMaintenanceSwitch(self, state: SustainedSwitchState) -> None:
        if state == SustainedSwitchState.ON:
            logger.info("Maintenance switch ON")
            self.__maintenanceSwitchOn = True

            if self.__state == RCCState.IDLE:
                self.__setState(RCCState.MAINTENANCE)
            elif self.__state == RCCState.RUNNING:
                logger.warning("Maintenance switch during RUNNING — fault")
                self.__motorController.stopMotion()
                self.__setState(RCCState.ESTOP)

        elif state == SustainedSwitchState.OFF:
            logger.info("Maintenance switch OFF")
            self.__maintenanceSwitchOn = False

            if self.__state == RCCState.MAINTENANCE:
                self.__setState(RCCState.IDLE)

    def __onMaintenanceJogSwitch(self, state: MomentarySwitchState) -> None:
        if self.__state != RCCState.MAINTENANCE:
            return

        if state == MomentarySwitchState.UP:
            logger.info("Jog forward")
            self.__motorController.jogMotor(1,1)
            self.__motorController.jogMotor(2,1)

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
'''
            # Print telemetry data
            logger.info("======================== Telemetry ========================")
            logger.info(f"[RCC State]: {self.__state.name}")
            logger.debug(f"[MC Type]: {str(type(self.__motorController))}")
            logger.info(f"[MC Connection]: {mcStatus}")
            logger.info(f"[MC State]: {self.__motorController.getState()}")
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

            logger.debug(    f"Alive threads ({threading.active_count()}): {thread_names}")

            logger.info("===========================================================")
            '''
