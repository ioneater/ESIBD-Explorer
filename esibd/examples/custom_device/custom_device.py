# pylint: disable=[missing-module-docstring]  # see class docstrings
import time

from PyQt6.QtWidgets import QMessageBox

from esibd.core import PARAMETERTYPE, PLUGINTYPE, PRINT, Channel, DeviceController, Parameter, getTestMode, parameterDict
from esibd.plugins import Device, Plugin

# TODO It is recommended to edit a copy of this file using VS Code with the Better Comments extension installed to highlight the sections that need to be customized.


def providePlugins() -> list['Plugin']:
    """Return list of provided plugins. Indicates that this module provides plugins."""
    return [CustomDevice]


class CustomDevice(Device):
    """The minimal code in *examples/CustomDevice.py* is an example of how to integrate a custom device.

    Usually only a fraction of the methods shown here need to be implemented. Look at the other examples and :ref:`sec:plugin_system` for more details.
    """

    documentation = """The minimal code in examples/CustomDevice.py is an example of how to integrate a custom device.
     Usually only a fraction of the methods shown here need to be implemented. Look at the other examples for more details."""

    name = 'CustomDevice'
    version = '1.0'
    supportedVersion = '0.8'
    pluginType = PLUGINTYPE.INPUTDEVICE
    iconFile = 'cookie.png'
    # TODO adjust flags to choose default behavior. All default functions can be extended or overwritten if more customization is required.
    useMonitors = True
    useBackgrounds = False
    useDisplays = True
    useOnOffLogic = True

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.channelType = CustomChannel
        self.controller = CustomController(controllerParent=self)
        self.messageBox = QMessageBox(QMessageBox.Icon.Information, 'Custom Dialog', 'Custom Dialog', buttons=QMessageBox.StandardButton.Ok)
        # TODO (optional) initialize any custom variables

    def initGUI(self) -> None:
        """Initialize your custom user interface."""
        super().initGUI()
        # a base UI is provided by parent class, it can be extended like this if required
        self.customAction = self.addAction(self.customActionEvent, 'Custom tooltip.', self.makeIcon('cookie.png'))

    def finalizeInit(self) -> None:
        # TODO (optional) add code that should be executed after all other Plugins are initialized.
        super().finalizeInit()

    def runTestParallel(self) -> None:
        self.testControl(self.customAction, self.customAction.state)
        # TODO (optional) add custom tests (avoid tests that require user interaction!)
        super().runTestParallel()

    def setOn(self, on=None) -> None:
        super().setOn(on)
        # TODO (optional) do something if device is turned on or off
        if self.isOn():
            self.customActionEvent()

    def customActionEvent(self) -> None:
        """Execute your custom code."""
        if not self.testing or self.pluginManager.closing:
            self.messageBox.setWindowTitle('Custom Dialog')
            self.messageBox.setWindowIcon(self.getIcon())
            self.messageBox.setText(f'This could run your custom code.\nThe value of your custom setting is {self.custom}.\nThe value of your custom setting is {"on" if self.isOn() else "off"}.')
            self.messageBox.open()  # show non blocking
            self.messageBox.raise_()

    def intervalChanged(self) -> None:
        # TODO (optional) add code to be executed in case the interval changes if needed
        pass

    customSetting = 'Custom/Setting'

    def getDefaultSettings(self) -> dict[str, dict]:
        settings = super().getDefaultSettings()
        settings[self.customSetting] = parameterDict(value=100, minimum=100, maximum=10000, toolTip='Custom Tooltip',
                                                                                    parameterType=PARAMETERTYPE.INT, attr='custom')
        # TODO (optional) add additional custom settings as needed
        return settings

    def closeCommunication(self) -> None:
        # TODO (optional) add final communication to set device into save state
        super().closeCommunication()

    def updateTheme(self) -> None:
        super().updateTheme()
        # TODO (optional) add custom code to handle themed icons or other custom themed widgets


class CustomChannel(Channel):
    """Custom channel. Usually only a fraction of the methods shown here need to be implemented. Look at the other examples for more details."""

    ID = 'ID'

    def __init__(self, device, tree) -> None:
        super().__init__(device, tree)
        # TODO (optional) initialize any custom variables

    def initGUI(self, item) -> None:
        super().initGUI(item)
        # TODO (optional) make any final modifications after channels have been initialized.
        channelId = self.getParameterByName(self.ID)
        self.print(repr(channelId.getWidget()), flag=PRINT.MESSAGE)

    def getDefaultChannel(self) -> dict[str, dict]:
        channel = super().getDefaultChannel()
        channel[self.VALUE][Parameter.HEADER] = 'Value (X)'  # overwrite to change header
        channel[self.ID] = parameterDict(value=0, parameterType=PARAMETERTYPE.INT, advanced=True, header='ID    ', attr='id')
        # TODO (optional) add and modify any channel parameters as needed
        return channel

    def setDisplayedParameters(self) -> None:
        super().setDisplayedParameters()
        self.displayedParameters.append(self.ID)
        # TODO (optional) add all custom parameters to determine if GUI elements are created and in what order

    def tempParameters(self) -> None:
        return super().tempParameters()  # + [self.ID]
        # TODO (optional) add parameters that should not be restored from file

    def enabledChanged(self) -> None:
        super().enabledChanged()
        # TODO (optional) add any custom code that is needed when a channel is enabled or disabled

    def realChanged(self) -> None:
        self.getParameterByName(self.ID).getWidget().setVisible(self.real)
        # TODO (optional) hide parameters that are only used by real channels
        super().realChanged()

    def updateColor(self) -> None:
        color = super().updateColor()  # noqa: F841
        # TODO (optional) implement any custom reaction to color changes

    def appendValue(self, lenT, nan=False) -> None:
        super().appendValue(lenT, nan)
        # TODO (optional) adjust what values should be plotted. E.g. when using monitors, your might want to plot these instead of the set value.


class CustomController(DeviceController):
    """Custom Device controller. Usually only a fraction of the methods shown here need to be implemented. Look at the other examples for more details."""

    def __init__(self, controllerParent) -> None:
        super().__init__(controllerParent=controllerParent)
        # TODO (optional) initialize any custom variables

    def closeCommunication(self) -> None:
        if self.initialized and self.port is not None:
            with self.lock.acquire_timeout(1, timeoutMessage='Could not acquire lock before closing port.'):
                # TODO replace with device and communication protocol specific code to close communication
                # try to close port even if lock could not be acquired! resulting errors should be excepted
                self.port.close()
                self.port = None
        super().closeCommunication()

    def initializeCommunication(self) -> None:
        # TODO set any flags needed for initialization
        super().initializeCommunication()

    def runInitialization(self) -> None:
        try:
            # TODO add custom initialization code here
            self.signalComm.initCompleteSignal.emit()
        except Exception as e:  # pylint: disable=[broad-except]
            self.print(f'Error while initializing: {e}', PRINT.ERROR)
        finally:
            self.initializing = False

    def initComplete(self) -> None:
        super().initComplete()
        # TODO (optional) any custom code here. This is the first time the communication is established and you might want to configure the hardware, and turn power supplies on at this point.

    def startAcquisition(self) -> None:
        if True:  # TODO (optional) add custom condition for acquisition
            super().startAcquisition()

    def runAcquisition(self, acquiring: callable) -> None:
        while acquiring():
            with self.lock.acquire_timeout(1, timeoutMessage='Could not acquire lock to acquire data') as lock_acquired:
                if lock_acquired:
                    if getTestMode():
                        self.values = [channel.value for channel in self.device.getChannels()]  # TODO implement fake feedback
                    elif True:
                        # TODO implement real feedback
                        pass
                    else:
                        # TODO increment error count if you catch a communication error here
                        self.errorCount += 1
                    self.signalComm.updateValuesSignal.emit()
            time.sleep(self.device.interval / 1000)  # release lock before waiting!

    def applyValue(self, channel) -> None:
        # TODO (optional) overwrite depending on hardware
        # Pseudocode: Apply channel.value to channel with channel.id
        pass

    def updateValues(self) -> None:
        # TODO (optional) adjust how you want to update values to the gui
        pass
