# pylint: disable=[missing-module-docstring]  # see class docstrings
import nidaqmx

from esibd.core import PARAMETERTYPE, PLUGINTYPE, PRINT, Channel, DeviceController, Parameter, parameterDict
from esibd.plugins import Device, Plugin


def providePlugins() -> list['Plugin']:
    """Return list of provided plugins. Indicates that this module provides plugins."""
    return [NI9263]


class NI9263(Device):
    """Contains a list of voltages channels from one or multiple NI9263 power supplies with 4 analog outputs each."""

    name = 'NI9263'
    version = '1.0'
    supportedVersion = '0.8'
    pluginType = PLUGINTYPE.INPUTDEVICE
    unit = 'V'
    iconFile = 'NI9263.png'

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.useOnOffLogic = True
        self.channelType = VoltageChannel

    def initGUI(self) -> None:
        super().initGUI()
        self.controller = VoltageController(controllerParent=self)  # after all channels loaded


class VoltageChannel(Channel):

    ADDRESS = 'Address'

    def getDefaultChannel(self) -> dict[str, dict]:
        channel = super().getDefaultChannel()
        channel[self.VALUE][Parameter.HEADER] = 'Voltage (V)'  # overwrite to change header
        channel[self.MIN][Parameter.VALUE] = 0
        channel[self.MAX][Parameter.VALUE] = 1  # start with safe limits
        channel[self.ADDRESS] = parameterDict(value='cDAQ1Mod1/ao0', toolTip='Address of analog output',
                                          parameterType=PARAMETERTYPE.TEXT, advanced=True, attr='address')
        return channel

    def setDisplayedParameters(self) -> None:
        super().setDisplayedParameters()
        self.displayedParameters.append(self.ADDRESS)

    def realChanged(self) -> None:
        self.getParameterByName(self.ADDRESS).getWidget().setVisible(self.real)
        super().realChanged()


class VoltageController(DeviceController):

    def runInitialization(self) -> None:
        try:
            with nidaqmx.Task() as task:
                task.ao_channels  # will raise exception if connection failed  # noqa: B018
            self.signalComm.initCompleteSignal.emit()
        except Exception as e:  # pylint: disable=[broad-except]  # socket does not throw more specific exception  # noqa: BLE001
            self.closeCommunication()
            self.print(f'Could not establish connection at {self.device.channels[0].address}. Exception: {e}', PRINT.WARNING)
        finally:
            self.initializing = False

    def applyValue(self, channel) -> None:
        with self.lock.acquire_timeout(1, timeoutMessage=f'Cannot acquire lock to set voltage of {channel.name}.') as lock_acquired:
            if lock_acquired:
                with nidaqmx.Task() as task:
                    task.ao_channels.add_ao_voltage_chan(channel.address)
                    task.write(channel.value if (channel.enabled and self.device.isOn()) else 0)

    def toggleOn(self) -> None:
        for channel in self.device.getChannels():
            if channel.real:
                self.applyValueFromThread(channel)

    def runAcquisition(self, acquiring: callable) -> None:
        pass  # nothing to acquire, no readbacks
