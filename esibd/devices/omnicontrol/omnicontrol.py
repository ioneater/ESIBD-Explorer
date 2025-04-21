# pylint: disable=[missing-module-docstring]  # see class docstrings
import time
import serial
import numpy as np
import pfeiffer_vacuum_protocol as pvp
from esibd.plugins import Device
from esibd.core import Parameter, PluginManager, Channel, parameterDict, DeviceController, PRINT, getTestMode


def providePlugins() -> None:
    """Indicates that this module provides plugins. Returns list of provided plugins."""
    return [OMNICONTROL]


class OMNICONTROL(Device):
    """Reads pressure values form an Pfeiffer Omnicontrol using the Pfeiffer Vacuum Protocol."""

    name = 'OMNICONTROL'
    version = '1.0'
    supportedVersion = '0.7'
    pluginType = PluginManager.TYPE.OUTPUTDEVICE
    unit = 'mbar'
    iconFile = 'pfeiffer_omni.png'

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.channelType = PressureChannel
        self.controller = PressureController(_parent=self)
        self.logY = True

    def getDefaultSettings(self) -> None:
        defaultSettings = super().getDefaultSettings()
        defaultSettings[f'{self.name}/Interval'][Parameter.VALUE] = 500  # overwrite default value
        defaultSettings[f'{self.name}/COM'] = parameterDict(value='COM1', toolTip='COM port.', items=','.join([f'COM{x}' for x in range(1, 25)]),
                                          widgetType=Parameter.TYPE.COMBO, attr='com')
        defaultSettings[f'{self.name}/{self.MAXDATAPOINTS}'][Parameter.VALUE] = 1E6  # overwrite default value
        return defaultSettings


class PressureChannel(Channel):
    """UI for pressure with integrated functionality."""

    ID = 'ID'

    def getDefaultChannel(self) -> None:
        channel = super().getDefaultChannel()
        channel[self.VALUE][Parameter.HEADER] = 'P (mbar)'
        channel[self.ID] = parameterDict(value=1, widgetType=Parameter.TYPE.INTCOMBO, advanced=True,
                                        items='0, 1, 2, 3, 4, 5, 6', attr='id')
        return channel

    def setDisplayedParameters(self) -> None:
        super().setDisplayedParameters()
        self.displayedParameters.append(self.ID)


class PressureController(DeviceController):

    def closeCommunication(self) -> None:
        if self.port is not None:
            with self.lock.acquire_timeout(1, timeoutMessage='Could not acquire lock before closing port.'):
                self.port.close()
                self.port = None
        super().closeCommunication()

    def runInitialization(self) -> None:
        try:
            self.port=serial.Serial(self.device.com, timeout=1)
            pvp.enable_valid_char_filter()
            self.signalComm.initCompleteSignal.emit()
        except Exception as e:  # pylint: disable=[broad-except]
            self.print(f'Error while initializing: {e}', PRINT.ERROR)
        finally:
            self.initializing = False

    def runAcquisition(self, acquiring: callable) -> None:
        while acquiring():
            with self.lock.acquire_timeout(1) as lock_acquired:
                if lock_acquired:
                    self.fakeNumbers() if getTestMode() else self.readNumbers()
                    self.signalComm.updateValuesSignal.emit()
            time.sleep(self.device.interval / 1000)

    def readNumbers(self) -> None:
        for i, channel in enumerate(self.device.getChannels()):
            if channel.enabled and channel.active and channel.real:
                try:
                    pressure = pvp.read_pressure(self.port, channel.id)
                    self.values[i] = np.nan if pressure == 0 else pressure * 1000
                except ValueError as e:
                    self.print(f'Error while reading pressure {e}')
                    self.errorCount += 1
                    self.values[i] = np.nan

    def fakeNumbers(self) -> None:
        for i, channel in enumerate(self.device.getChannels()):
            if channel.enabled and channel.active and channel.real:
                self.values[i] = self.rndPressure() if np.isnan(self.values[i]) else self.values[i] * np.random.uniform(.99, 1.01)  # allow for small fluctuation

    def rndPressure(self) -> float:
        """Returns a random pressure."""
        exp = np.random.randint(-11, 3)
        significand = 0.9 * np.random.random() + 0.1
        return significand * 10**exp
