# pylint: disable=[missing-module-docstring] # only single class in module
import time
from PyQt6.QtWidgets import QDialog, QLabel, QGridLayout
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

    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.channelType = CustomChannel
        self.controller = CustomController(_parent=self)
        self.messageBox = QMessageBox(QMessageBox.Icon.Information, 'Water cooling!', 'Water cooling!', buttons=QMessageBox.StandardButton.Ok)

    def getIcon(self):
        return self.makeIcon('cookie.png')

    def initGUI(self):
        """Initialize your custom user interface"""
        super().initGUI()
        # a base UI is provided by parent class, it can be extended like this if required
        self.addAction(self.customAction, 'Custom tooltip.', self.makeIcon('cookie.png'))
    
    def finalizeInit(self, aboutFunc=None):
        """:meta private:"""
        self.onAction = self.pluginManager.DeviceManager.addStateAction(event=self.customAction, toolTipFalse='Custom Device on.', iconFalse=self.makeIcon('cookie_off.png'),
                                                                  toolTipTrue='Custom Device off.', iconTrue=self.makeIcon('cookie.png'),
                                                                 before=self.pluginManager.DeviceManager.aboutAction)
        # TODO if applicable add action to DeviceManager, e.g. to quickly turn power supplies on or off
        super().finalizeInit(aboutFunc)

    def customAction(self):
        """Execute your custom code"""
        self.messageBox.setWindowTitle('Custom Dialog')
        self.messageBox.setWindowIcon(self.getIcon())
        self.messageBox.setText(f'This could run your custom code.\nThe value of your custom setting is {self.custom}')
        self.messageBox.open() # show non blocking
        self.messageBox.raise_()
        # dlg.setLayout(lay)
        # dlg.exec()

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
        channel[self.MONITOR ] = parameterDict(value=0, widgetType=Parameter.TYPE.FLOAT, advanced=False,
                                    event=self.monitorChanged, indicator=True, attr='monitor')
        # TODO add and modify any channel parameters as needed
        return channel

    def setDisplayedParameters(self):
        super().setDisplayedParameters()
        self.insertDisplayedParameter(self.MONITOR, before=self.MIN)
        self.displayedParameters.append(self.ID)
        # TODO add all custom parameters to determine if GUI elements are created and in what order

    def tempParameters(self):
        return super().tempParameters() + [self.MONITOR]
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
        self.getParameterByName(self.MONITOR).getWidget().setVisible(self.real)
        self.getParameterByName(self.ID).getWidget().setVisible(self.real)
        # TODO hide parameters that are only used by real channels
        super().realChanged()

    def updateColor(self):
        color = super().updateColor()
        # TODO implement any custom reaction to color changes

    def appendValue(self, lenT, nan=False):
        super().appendValue(lenT, nan)
        # TODO adjust what values should be plotted. E.g. when using monitors, your might want to plot these instead of the setValue.

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
        if getTestMode():
            time.sleep(2)
            self.signalComm.initCompleteSignal.emit()
            self.print('Faking values for testing!', PRINT.WARNING)
        else:
            self.initializing = True
            try:
                # TODO add custom initialization code here
                self.signalComm.initCompleteSignal.emit()
            except Exception as e: # pylint: disable=[broad-except]
                self.print(f'Error while initializing: {e}', PRINT.ERROR)
            finally:
                self.initializing = False

    def initComplete(self):
        # TODO any custom code here. This is the first time the comminication is established and you might want to configure the hardware, and turn power supplies on at this point.
        super().initComplete()

    def startAcquisition(self):
        if True: # TODO add custom condition for acquisition
            super().startAcquisition()

    def runAcquisition(self, acquiring):
        while acquiring():
            with self.lock.acquire_timeout(1, timeoutMessage='Could not acquire lock to acquire data') as lock_acquired:
                if lock_acquired:
                    if getTestMode():
                        pass # TODO implement fake feedback
                    else:
                        pass # TODO implement real feedback
                    self.signalComm.updateValueSignal.emit()
            time.sleep(self.device.interval/1000) # release lock before waiting!

    def applyValue(self, channel):
        pass # TODO implement depending on hardware

    def updateValue(self):
        pass # TODO update GUI