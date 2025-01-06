# pylint: disable=[missing-module-docstring] # only single class in module
import time
# Users who add custom controls can use the build-in features at their own risk.
# If you want your module to be more independent, implement your own replacement for the following imports.
from PyQt6.QtWidgets import QMessageBox
from esibd.plugins import Device
from esibd.core import Parameter, parameterDict, PluginManager, Channel, DeviceController, getTestMode, PRINT

def providePlugins():
    return [CustomDevice]

class CustomDevice(Device):
    """The minimal code in *examples/CustomDevice.py* is an example of how to integrate a custom device.
    Usually only a fraction of the methods shown here need to be implemented. Look at the other examples and :ref:`sec:plugin_system` for more details.
    """
    documentation = """The minimal code in examples/CustomDevice.py is an example of how to integrate a custom device.
     Usually only a fraction of the methods shown here need to be implemented. Look at the other examples for more details."""

    name = 'CustomDevice'
    version = '1.0'
    supportedVersion = '0.6'
    pluginType = PluginManager.TYPE.INPUTDEVICE
    # TODO adjust flags to choose default behavior. All default functions can be extended or overwritten if more customization is required.
    useMonitors = True
    useBackgrounds = False
    useDisplays = True

    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.useOnOffLogic = True
        self.channelType = CustomChannel
        self.controller = CustomController(_parent=self)
        self.messageBox = QMessageBox(QMessageBox.Icon.Information, 'Custom Dialog', 'Custom Dialog', buttons=QMessageBox.StandardButton.Ok)
        # TODO initialize any custom variables

    def getIcon(self, **kwargs):
        return self.makeIcon('cookie.png', **kwargs)

    def initGUI(self):
        """Initialize your custom user interface"""
        super().initGUI()
        # a base UI is provided by parent class, it can be extended like this if required
        self.addAction(self.customAction, 'Custom tooltip.', self.makeIcon('cookie.png'))

    def finalizeInit(self, aboutFunc=None):
        # TODO add code that should be executed after all other Plugins are initialized.
        super().finalizeInit(aboutFunc)

    def runTestParallel(self):
        # self.testControl(self.customAction, self.customAction.state)
        # TODO add custom tests (avoid tests that require user interaction!)
        super().runTestParallel()

    def setOn(self, on=None):
        super().setOn(on)
        self.customAction()

    def customAction(self):
        """Execute your custom code"""
        if not self.testing or self.pluginManager.closing:
            self.messageBox.setWindowTitle('Custom Dialog')
            self.messageBox.setWindowIcon(self.getIcon())
            self.messageBox.setText(f'This could run your custom code.\nThe value of your custom setting is {self.custom}.\nThe value of your custom setting is {"on" if self.isOn() else "off"}.')
            self.messageBox.open() # show non blocking
            self.messageBox.raise_()

    def intervalChanged(self):
        pass # TODO add code to be executed in case the interval changes if needed

    def applyValues(self, apply=False):
        """ Executed when values have changed.
            Should only apply channels where value has changed."""
        for channel in self.getChannels():
            self.controller.applyValue(channel)

    customSetting = 'Custom/Setting'

    def getDefaultSettings(self):
        """Define device specific settings that will be added to the general settings tab.
        These will be included if the settings file is deleted and automatically regenerated.
        Overwrite as needed."""
        settings = super().getDefaultSettings()
        settings[self.customSetting] = parameterDict(value=100, _min=100, _max=10000, toolTip='Custom Tooltip',
                                                                                    widgetType=Parameter.TYPE.INT, attr='custom')
        # TODO add additional custom settings as needed
        return settings

    def closeCommunication(self):
        # TODO add final communication to set device into save state
        super().closeCommunication()

    def updateTheme(self):
        super().updateTheme()
        # TODO add custom code to handle themed icons or other custom themed widgets

class CustomChannel(Channel):
    """Custom channel. Usually only a fraction of the methods shown here need to be implemented. Look at the other examples for more details."""

    ID = 'ID'

    def __init__(self, device, tree):
        super().__init__(device, tree)
        # TODO initialize any custom variables

    def getDefaultChannel(self):
        channel = super().getDefaultChannel()
        channel[self.VALUE   ][Parameter.HEADER] = 'Value (X)' # overwrite to change header
        channel[self.ID] = parameterDict(value=0, widgetType=Parameter.TYPE.INT, advanced=True, header='ID    ', attr='id')
        # TODO add and modify any channel parameters as needed
        return channel

    def setDisplayedParameters(self):
        super().setDisplayedParameters()
        self.displayedParameters.append(self.ID)
        # TODO add all custom parameters to determine if GUI elements are created and in what order

    def tempParameters(self):
        return super().tempParameters() # + [self.ID]
        # TODO add parameters that should not be restored from file

    def finalizeInit(self, item):
        super().finalizeInit(item)
        # TODO make any final modifications after channels have been initialized.
        _id = self.getParameterByName(self.ID)
        print(_id.getWidget())

    def enabledChanged(self):
        super().enabledChanged()
        # TODO add any custom code that is needed when a channel is enabled or disabled

    def realChanged(self):
        self.getParameterByName(self.ID).getWidget().setVisible(self.real)
        # TODO hide parameters that are only used by real channels
        super().realChanged()

    def updateColor(self):
        color = super().updateColor()  # noqa: F841
        # TODO implement any custom reaction to color changes

    def appendValue(self, lenT, nan=False):
        super().appendValue(lenT, nan)
        # TODO adjust what values should be plotted. E.g. when using monitors, your might want to plot these instead of the set value.

class CustomController(DeviceController):
    """Custom Device controller. Usually only a fraction of the methods shown here need to be implemented. Look at the other examples for more details."""

    def __init__(self, _parent):
        super().__init__(_parent=_parent)
        # TODO initialize any custom variables

    def closeCommunication(self):
        if self.initialized and self.port is not None:
            with self.lock.acquire_timeout(1, timeoutMessage='Could not acquire lock before closing port.'):
                # TODO replace with device and communication protocol specific code to close communication
                # try to close port even if lock could not be acquired! resulting errors should be excepted
                self.port.close()
                self.port = None
        super().closeCommunication()

    def initializeCommunication(self):
        # TODO set any flags needed for initialization
        super().initializeCommunication()

    def runInitialization(self):
        self.initializing = True
        try:
            # TODO add custom initialization code here
            self.signalComm.initCompleteSignal.emit()
        except Exception as e: # pylint: disable=[broad-except]
            self.print(f'Error while initializing: {e}', PRINT.ERROR)
        finally:
            self.initializing = False

    def initComplete(self):
        super().initComplete()
        # TODO any custom code here. This is the first time the communication is established and you might want to configure the hardware, and turn power supplies on at this point.

    def startAcquisition(self):
        if True: # TODO add custom condition for acquisition
            super().startAcquisition()

    def runAcquisition(self, acquiring):
        while acquiring():
            with self.lock.acquire_timeout(1, timeoutMessage='Could not acquire lock to acquire data') as lock_acquired:
                if lock_acquired:
                    if getTestMode():
                        self.monitors = [channel.value for channel in self.device.channels] # TODO implement fake feedback
                    else:
                        pass # TODO implement real feedback
                    self.signalComm.updateValueSignal.emit()
            time.sleep(self.device.interval/1000) # release lock before waiting!

    def applyValue(self, channel):
        # Pseudocode: Apply channel.value to channel with channel.id
        pass # TODO implement depending on hardware

    def updateValue(self):
        # TODO adjust how you want to update values to the gui
        for channel, monitor in zip(self.device.getChannels(), self.monitors):
            channel.monitor = monitor