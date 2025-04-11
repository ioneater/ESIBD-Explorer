# pylint: disable=[missing-module-docstring] # see class docstrings
import nidaqmx
from esibd.plugins import Device
from esibd.core import Parameter, parameterDict, PluginManager, Channel, PRINT, DeviceController

def providePlugins():
    """Indicates that this module provides plugins. Returns list of provided plugins."""
    return [NI9263]

class NI9263(Device):
    """Contains a list of voltages channels from one or multiple NI9263 power supplies with 4 analog outputs each."""

    name = 'NI9263'
    version = '1.0'
    supportedVersion = '0.7'
    pluginType = PluginManager.TYPE.INPUTDEVICE
    unit = 'V'
    iconFile = 'NI9263.png'

    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.useOnOffLogic = True
        self.channelType = VoltageChannel

    def initGUI(self):
        super().initGUI()
        self.controller = VoltageController(_parent=self) # after all channels loaded

class VoltageChannel(Channel):

    ADDRESS = 'Address'

    def getDefaultChannel(self):
        channel = super().getDefaultChannel()
        channel[self.VALUE][Parameter.HEADER] = 'Voltage (V)' # overwrite to change header
        channel[self.MIN ][Parameter.VALUE] = 0
        channel[self.MAX ][Parameter.VALUE] = 1 # start with safe limits
        channel[self.ADDRESS] = parameterDict(value='cDAQ1Mod1/ao0', toolTip='Address of analog output',
                                          widgetType=Parameter.TYPE.TEXT, advanced=True, attr='address')
        return channel

    def setDisplayedParameters(self):
        super().setDisplayedParameters()
        self.displayedParameters.append(self.ADDRESS)

    def realChanged(self):
        self.getParameterByName(self.ADDRESS).getWidget().setVisible(self.real)
        super().realChanged()

class VoltageController(DeviceController):

    def runInitialization(self):
        try:
            with nidaqmx.Task() as task:
                task.ao_channels # will raise exception if connection failed
            self.signalComm.initCompleteSignal.emit()
        except Exception as e: # pylint: disable=[broad-except] # socket does not throw more specific exception
            self.print(f'Could not establish connection at {self.device.channels[0].address}. Exception: {e}', PRINT.WARNING)
        finally:
            self.initializing = False

    def applyValue(self, channel):
        with self.lock.acquire_timeout(1, timeoutMessage=f'Cannot acquire lock to set voltage of {channel.name}.') as lock_acquired:
            if lock_acquired:
                with nidaqmx.Task() as task:
                    task.ao_channels.add_ao_voltage_chan(channel.address)
                    task.write(channel.value if (channel.enabled and self.device.isOn()) else 0)

    def toggleOn(self):
        for channel in self.device.getChannels():
            if channel.real:
                self.applyValueFromThread(channel)

    def runAcquisition(self, acquiring):
        pass # nothing to acquire, no readbacks