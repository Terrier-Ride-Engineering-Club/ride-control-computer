# Ride Control Computer for TREC's REC
    # Made by Jackson Justus (jackjust@bu.edu)

import logging
import threading
import time

from ride_control_computer.loop_timer import LoopTimer
from ride_control_computer.motor_controller.MotorController import MotorController
from ride_control_computer.theming_controller.ThemingController import ThemingController
from ride_control_computer.webserver.WebserverController import WebserverController
from ride_control_computer.control_panel.ControlPanel import ControlPanel, MomentaryButtonState, MomentarySwitchState, SustainedSwitchState

logger = logging.getLogger(__name__)


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

    __maintenanceMode: bool
    __estopSoftwareLatched: bool

    __lastTelemPrintTime: float
    __loopTimer: LoopTimer
    TELEMETRY_PRINT_INTERVAL = 2; # time in s

    def __init__(
            self,
            motorController: MotorController,
            controlPanel: ControlPanel,
            themingController: ThemingController,
            webserverController: WebserverController
            ):
        self.__motorController = motorController
        self.__controlPanel = controlPanel
        self.__themingController = themingController
        self.__webserverController = webserverController

        self.__maintenanceMode = False
        self.__estopSoftwareLatched = False

        self.__lastTelemPrintTime = 0
        self.__loopTimer = LoopTimer()

        # Map control panel callbacks
        controlPanel.addDispatchCallback(self.__onDispatch)
        controlPanel.addResetCallback(self.__onReset)
        controlPanel.addStopCallback(self.__onStop)
        controlPanel.addEstopCallback(self.__onEstop)
        controlPanel.addMaintenanceSwitchCallback(self.__onMaintenanceSwitch)
        controlPanel.addMaintenanceJogSwitchCallback(self.__onMaintenanceJogSwitch)

    # =========================================================================
    #                           LIFECYCLE
    # =========================================================================

    def run(self):
        """Blocking call to start the Ride Control Computer."""

        threading.Thread(
            target=self.__controlPanel.run,
            daemon=True).start()

        threading.Thread(
            target=self.__webserverController.start,
            daemon=True).start()

        self.__motorController.start()

        while True:
            self.__controlPanel.triggerCallbacks()

            if not self.__estopSoftwareLatched:
                # Latch E-Stop if hardware reports it active
                if self.__motorController.isEstopActive():
                    logger.warning("Hardware E-Stop detected — latching")
                    self.__handleEstop()
                else:
                    self.__checkSafetyConstraints()

            self.__printTelemetry()

            self.__loopTimer.tick()
            time.sleep(0.001)

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
            self.__handleEstop()

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

    def __handleEstop(self):
        """Latch the software E-Stop and halt all systems."""
        self.__estopSoftwareLatched = True
        self.__motorController.haltMotion()
        self.__themingController.stopShow()

    def isEstopResetInhibited(self) -> bool:
        """Returns True if software is inhibiting E-Stop reset."""
        return self.__estopSoftwareLatched

    # =========================================================================
    #                           CONTROL PANEL CALLBACKS
    # =========================================================================

    def __onDispatch(self, state: MomentaryButtonState) -> None:
        if state == MomentaryButtonState.PRESSED:
            logger.info("Dispatch pressed")

            if self.__estopSoftwareLatched:
                logger.warning("Dispatch ignored: E-Stop active")
                return

            if not self.__maintenanceMode:
                self.__themingController.startShow()
                self.__motorController.startRideSequence()
            else:
                logger.info("Dispatch ignored: maintenance mode active")

    def __onReset(self, state: MomentaryButtonState) -> None:
        if state == MomentaryButtonState.PRESSED:
            logger.info("Reset pressed")

            if self.__estopSoftwareLatched:
                if self.__motorController.isEstopActive():
                    logger.warning("Cannot reset: hardware E-Stop still active")
                    return
                logger.info("Hardware E-Stop cleared — releasing latch")
                self.__estopSoftwareLatched = False

    def __onStop(self, state: MomentaryButtonState) -> None:
        if state == MomentaryButtonState.PRESSED:
            logger.info("Stop pressed")

            self.__motorController.stopMotion()
            self.__themingController.stopShow()

    def __onEstop(self, state: MomentaryButtonState) -> None:
        if state == MomentaryButtonState.PRESSED:
            logger.warning("E-Stop button pressed — latching")
            self.__handleEstop()

    def __onMaintenanceSwitch(self, state: SustainedSwitchState) -> None:
        if state == SustainedSwitchState.ON:
            logger.info("Maintenance mode enabled")
            self.__maintenanceMode = True
            self.__themingController.stopShow()

        elif state == SustainedSwitchState.OFF:
            logger.info("Maintenance mode disabled")
            self.__maintenanceMode = False

    def __onMaintenanceJogSwitch(self, state: MomentarySwitchState) -> None:
        if not self.__maintenanceMode or self.__estopSoftwareLatched:
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

            # Print telemetry data
            logger.info("======================== Telemetry ========================")
            logger.info(f"[E-Stop Software Latched]: {self.__estopSoftwareLatched}")
            logger.debug(f"[MC Type]: {str(type(self.__motorController))}")
            logger.info(f"[MC Connection Active]: {self.__motorController.isTelemetryStale()}")
            logger.info(f"[MC State]: {self.__motorController.getState()}")
            lt = self.__loopTimer
            logger.debug(f"[RCC dt]: {lt.dt * 1000:.2f} ms | avg: {lt.avg * 1000:.2f} ms | p95: {lt.p95 * 1000:.2f} ms")
            lt.reset()

            cp_lt = self.__controlPanel.loopTimer
            logger.debug(f"    [ControlPanel dt]:   {cp_lt.dt * 1000:.2f} ms | avg: {cp_lt.avg * 1000:.2f} ms | p95: {cp_lt.p95 * 1000:.2f} ms")
            cp_lt.reset()

            mc_lt = self.__motorController.loopTimer
            if mc_lt is not None:
                logger.debug(f"    [MC dt]:   {mc_lt.dt * 1000:.2f} ms | avg: {mc_lt.avg * 1000:.2f} ms | p95: {mc_lt.p95 * 1000:.2f} ms")
                mc_lt.reset()

            logger.info("===========================================================")

