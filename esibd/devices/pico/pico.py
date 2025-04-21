# pylint: disable=[missing-module-docstring]  # see class docstrings
import time
import ctypes
import numpy as np
from esibd.plugins import Device
from esibd.core import Parameter, PluginManager, Channel, parameterDict, PRINT, DeviceController, getDarkMode, getTestMode


def providePlugins() -> None:
    """Indicates that this module provides plugins. Returns list of provided plugins."""
    return [PICO]


class PICO(Device):
    """Reads the temperature of sensors attached to a pico PT-104.
    It allows to switch units between K and °C."""

    name = 'PICO'
    version = '1.0'
    supportedVersion = '0.7'
    pluginType = PluginManager.TYPE.OUTPUTDEVICE
    unit = 'K'
    iconFile = 'pico_104.png'

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.channelType = TemperatureChannel
        self.controller = TemperatureController(_parent=self)

    def initGUI(self) -> None:
        super().initGUI()
        self.unitAction = self.addStateAction(event=lambda: self.changeUnit(), toolTipFalse='Change to °C', iconFalse=self.makeIcon('tempC_dark.png'),
                                               toolTipTrue='Change to K', iconTrue=self.makeIcon('tempK_dark.png'), attr='displayC')

    def runTestParallel(self) -> None:
        self.testControl(self.unitAction, self.unitAction.state)
        super().runTestParallel()

    def changeUnit(self) -> None:
        """Update plots to account for change of unit."""
        if self.liveDisplayActive():
            self.clearPlot()
            self.liveDisplay.plot(apply=True)
        if self.staticDisplayActive():
            self.staticDisplay.plot()

    def getDefaultSettings(self) -> None:
        defaultSettings = super().getDefaultSettings()
        defaultSettings[f'{self.name}/Interval'][Parameter.VALUE] = 5000  # overwrite default value
        defaultSettings[f'{self.name}/{self.MAXDATAPOINTS}'][Parameter.VALUE] = 1E6  # overwrite default value
        return defaultSettings

    def convertDataDisplay(self, data) -> float:
        return data - 273.15 if self.unitAction.state else data

    def getUnit(self) -> str:
        return '°C' if self.unitAction.state else self.unit

    def updateTheme(self) -> None:
        super().updateTheme()
        self.unitAction.iconFalse = self.makeIcon('tempC_dark.png' if getDarkMode() else 'tempC_light.png')
        self.unitAction.iconTrue = self.makeIcon('tempK_dark.png' if getDarkMode() else 'tempK_light.png')
        self.unitAction.updateIcon(self.unitAction.state)


class TemperatureChannel(Channel):
    """UI for pressure with integrated functionality."""

    CHANNEL = 'Channel'
    DATATYPE = 'Datatype'
    NOOFWIRES = 'noOfWires'

    def getDefaultChannel(self) -> None:
        channel = super().getDefaultChannel()
        channel[self.VALUE][Parameter.HEADER ] = 'Temp (K)'
        channel[self.VALUE][Parameter.VALUE ] = np.nan  # undefined until communication established
        channel[self.CHANNEL ] = parameterDict(value='USBPT104_CHANNEL_1', widgetType=Parameter.TYPE.COMBO, advanced=True,
                                    attr='channel', items='USBPT104_CHANNEL_1, USBPT104_CHANNEL_2, USBPT104_CHANNEL_3, USBPT104_CHANNEL_4')
        channel[self.DATATYPE ] = parameterDict(value='USBPT104_PT100', widgetType=Parameter.TYPE.COMBO, advanced=True,
                                    attr='datatype', items='USBPT104_PT100')
        channel[self.NOOFWIRES ] = parameterDict(value='4', widgetType=Parameter.TYPE.COMBO, advanced=True,
                                    attr='noOfWires', items='2, 3, 4')
        return channel

    def setDisplayedParameters(self) -> None:
        super().setDisplayedParameters()
        self.displayedParameters.append(self.CHANNEL)
        self.displayedParameters.append(self.DATATYPE)
        self.displayedParameters.append(self.NOOFWIRES)


class TemperatureController(DeviceController):

    chandle = ctypes.c_int16()

    def __init__(self, _parent):
        super().__init__(_parent)
        # Download PicoSDK as described here https://github.com/picotech/picosdk-python-wrappers/tree/master
        # If needed, add SDK installation path to PATH
        # importing modules here makes sure that the module is loaded without errors.
        # Missing SDK is only raised if users enable this plugin.
        from picosdk.usbPT104 import usbPt104 as pt104
        from picosdk.functions import assert_pico_ok
        self.pt104 = pt104
        self.assert_pico_ok = assert_pico_ok

    def closeCommunication(self) -> None:
        if self.initialized:
            with self.lock.acquire_timeout(1, timeoutMessage='Cannot acquire lock to close PT-104.'):
                self.pt104.UsbPt104CloseUnit(self.chandle)
        super().closeCommunication()

    def runInitialization(self) -> None:
        try:
            self.pt104.UsbPt104OpenUnit(ctypes.byref(self.chandle), 0)
            for channel in self.device.getChannels():
                self.assert_pico_ok(self.pt104.UsbPt104SetChannel(self.chandle, self.pt104.PT104_CHANNELS[channel.channel],
                                                        self.pt104.PT104_DATA_TYPE[channel.datatype], ctypes.c_int16(int(channel.noOfWires))))
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
                    meas = ctypes.c_int32()
                    self.pt104.UsbPt104GetValue(self.chandle, self.pt104.PT104_CHANNELS[channel.channel], ctypes.byref(meas), 1)
                    if meas.value != ctypes.c_long(0).value:  # 0 during initialization phase
                        self.values[i] = float(meas.value) / 1000 + 273.15  # always return Kelvin
                    else:
                        self.values[i] = np.nan
                except ValueError as e:
                    self.print(f'Error while reading temp: {e}', PRINT.ERROR)
                    self.errorCount += 1
                    self.values[i] = np.nan

    def fakeNumbers(self) -> None:
        for i, channel in enumerate(self.device.getChannels()):
            if channel.enabled and channel.active and channel.real:
            # exponentially approach target or room temp + small fluctuation
                self.values[i] = np.random.randint(1, 300) if np.isnan(self.values[i]) else self.values[i] * np.random.uniform(.99, 1.01)  # allow for small fluctuation

    def rndTemperature(self) -> float:
        """Returns a random temperature."""
        return np.random.uniform(0, 400)
