from ride_control_computer.motor_controller.MotorController import MotorController
from ride_control_computer.theming_controller.ThemingController import ThemingController
from ride_control_computer.webserver import WebserverController
from ride_control_computer.control_panel.ControlPanel import ControlPanel, MomentaryButtonState, MomentarySwitchState, SustainedSwitchState
import threading


class RCC:
    """
    Class which holds the main ride control computer instance.

    Will own a ControlPanel, MotorController, and other implementations to interface with the rest of the ride.
    """

    __motorController: MotorController
    __controlPanel: ControlPanel
    __themingController: ThemingController
    __webserverController: WebserverController

    __maintenance_mode: bool

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

        # Map control panel callbacks
        controlPanel.addDispatchCallback(self.__onDispatch)
        controlPanel.addResetCallback(self.__onReset)
        controlPanel.addStopCallback(self.__onStop)
        controlPanel.addEstopCallback(self.__onEstop)
        controlPanel.addMaintenanceSwitchCallback(self.__onMaintenanceSwitch)
        controlPanel.addMaintenanceJogSwitchCallback(self.__onMaintenanceJogSwitch)

    def run(self):
        """Blocking call to start the Ride Control Computer"""
        # Launch control panel thread

        threading.Thread(
            target=self.__controlPanel.run,
            daemon=True).start()

        threading.Thread(
            target=self.__webserverController.start,
            daemon=True).start()
        
        while (True):
            self.__controlPanel.triggerCallbacks()
        

    def __onDispatch(self, state: MomentaryButtonState) -> None:
        if state == MomentaryButtonState.PRESSED:
            print("Dispatch pressed")

            if not self.__maintenance_mode:
                self.__themingController.startShow()
                self.__motorController.dispatch()
            else:
                print("Dispatch ignored: maintenance mode active")

    def __onReset(self, state: MomentaryButtonState) -> None:
        if state == MomentaryButtonState.PRESSED:
            print("Reset pressed")

            self.__motorController.resetFaults()
            self.__themingController.resetShow()

    def __onStop(self, state: MomentaryButtonState) -> None:
        if state == MomentaryButtonState.PRESSED:
            print("Stop pressed")

            self.__motorController.stop()
            self.__themingController.stopShow()

    def __onEstop(self, state: MomentaryButtonState) -> None:
        if state == MomentaryButtonState.PRESSED:
            print("E-Stop pressed")

            self.__motorController.emergencyStop()
            self.__themingController.emergencyStop()

    def __onMaintenanceSwitch(self, state: SustainedSwitchState) -> None:
        if state == SustainedSwitchState.ON:
            print("Maintenance mode enabled")
            self.__maintenance_mode = True

            self.__motorController.enterMaintenanceMode()
            self.__themingController.enterMaintenanceMode()

        elif state == SustainedSwitchState.OFF:
            print("Maintenance mode disabled")
            self.__maintenance_mode = False

            self.__motorController.exitMaintenanceMode()
            self.__themingController.exitMaintenanceMode()

    def __onMaintenanceJogSwitch(self, state: MomentarySwitchState) -> None:
        if not self.__maintenance_mode:
            return

        if state == MomentarySwitchState.UP:
            print("Jog forward")
            self.__motorController.jogForward()

        elif state == MomentarySwitchState.DOWN:
            print("Jog reverse")
            self.__motorController.jogReverse()

        elif state == MomentarySwitchState.NEUTRAL:
            print("Jog released")
            self.__motorController.jogStop()