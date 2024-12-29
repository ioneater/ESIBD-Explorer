# pylint: disable=[missing-module-docstring] # only single class in module
import time
import numpy as np
import ctypes
# Download PicoSDK as described here https://github.com/picotech/picosdk-python-wrappers/tree/master
# If needed, add SDK installation path to PATH
from picosdk.usbPT104 import usbPt104 as pt104
from picosdk.functions import assert_pico_ok
from esibd.plugins import Device
from esibd.core import Parameter, PluginManager, Channel, parameterDict, PRINT, DeviceController, getDarkMode, getTestMode

def providePlugins():
    return [PICO]

class PICO(Device):
    """Device that reads the temperature of sensors attached to a pico PT-104.
    It allows to switch units between K and °C."""
    documentation = None # use __doc__

    name = 'PICO'
    version = '1.0'
    supportedVersion = '0.6'
    pluginType = PluginManager.TYPE.OUTPUTDEVICE
    unit = 'K'

    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.channelType = TemperatureChannel
        self.controller = TemperatureController(_parent=self)

    def initGUI(self):
        super().initGUI()
        self.unitAction = self.addStateAction(event=self.changeUnit, toolTipFalse='Change to °C', iconFalse=self.makeIcon('tempC_dark.png'),
                                               toolTipTrue='Change to K', iconTrue=self.makeIcon('tempK_dark.png'), attr='displayC')

    def getIcon(self):
        return self.makeIcon('pico_104.png')

    def changeUnit(self):
        if self.liveDisplayActive():
            self.clearPlot()
            self.liveDisplay.plot(apply=True)
        if self.staticDisplayActive():
            self.staticDisplay.plot()

    def getDefaultSettings(self):
        ds = super().getDefaultSettings()
        ds[f'{self.name}/Interval'][Parameter.VALUE] = 5000 # overwrite default value
        ds[f'{self.name}/{self.MAXDATAPOINTS}'][Parameter.VALUE] = 1E6 # overwrite default value
        return ds

    def getInitializedChannels(self):
        return [d for d in self.channels if (d.enabled and (self.controller.port is not None or self.getTestMode())) or not d.active]

    def convertDataDisplay(self, data):
        if self.unitAction.state:
            return data - 273.15
        else:
            return data

    def getUnit(self):
        """Overwrite if you want to change units dynamically."""
        return '°C' if self.unitAction.state else self.unit

    def updateTheme(self):
        super().updateTheme()
        self.unitAction.iconFalse = self.makeIcon('tempC_dark.png' if getDarkMode() else 'tempC_light.png')
        self.unitAction.iconTrue = self.makeIcon('tempK_dark.png' if getDarkMode() else 'tempK_light.png')
        self.unitAction.updateIcon(self.unitAction.state)

class TemperatureChannel(Channel):
    """UI for pressure with integrated functionality"""

    CHANNEL = 'Channel'
    DATATYPE = 'Datatype'
    NOOFWIRES = 'noOfWires'

    def getDefaultChannel(self):
        channel = super().getDefaultChannel()
        channel[self.VALUE][Parameter.HEADER ] = 'Temp (K)' # overwrite existing parameter to change header
        channel[self.VALUE][Parameter.VALUE ] = np.nan # undefined until communication established
        channel[self.CHANNEL ] = parameterDict(value='USBPT104_CHANNEL_1', widgetType=Parameter.TYPE.COMBO, advanced=True,
                                    attr='channel', items='USBPT104_CHANNEL_1, USBPT104_CHANNEL_2, USBPT104_CHANNEL_3, USBPT104_CHANNEL_4')
        channel[self.DATATYPE ] = parameterDict(value='USBPT104_PT100', widgetType=Parameter.TYPE.COMBO, advanced=True,
                                    attr='datatype', items='USBPT104_PT100')
        channel[self.NOOFWIRES ] = parameterDict(value='4', widgetType=Parameter.TYPE.COMBO, advanced=True,
                                    attr='noOfWires', items='2, 3, 4')
        return channel

    def setDisplayedParameters(self):
        super().setDisplayedParameters()
        self.displayedParameters.append(self.CHANNEL)
        self.displayedParameters.append(self.DATATYPE)
        self.displayedParameters.append(self.NOOFWIRES)

class TemperatureController(DeviceController):

    chandle = ctypes.c_int16()

    def closeCommunication(self):
        if self.initialized:
            with self.lock.acquire_timeout(1, timeoutMessage='Cannot acquire lock to close PT-104.'):
                pt104.UsbPt104CloseUnit(self.chandle)
        super().closeCommunication()

    def runInitialization(self):
        self.temperatures = [np.nan]*len(self.device.channels)
        if getTestMode():
            time.sleep(2)
            self.signalComm.initCompleteSignal.emit()
            self.print('Faking values for testing!', PRINT.WARNING)
        else:
            self.initializing = True
            try:
                pt104.UsbPt104OpenUnit(ctypes.byref(self.chandle), 0)
                for channel in self.device.channels:
                    assert_pico_ok(pt104.UsbPt104SetChannel(self.chandle, pt104.PT104_CHANNELS[channel.channel],
                                                            pt104.PT104_DATA_TYPE[channel.datatype], ctypes.c_int16(int(channel.noOfWires))))
                self.signalComm.initCompleteSignal.emit()
            except Exception as e: # pylint: disable=[broad-except]
                self.print(f'Error while initializing: {e}', PRINT.ERROR)
            finally:
                self.initializing = False

    def runAcquisition(self, acquiring):
        while acquiring():
            with self.lock.acquire_timeout(1) as lock_acquired:
                if lock_acquired:
                    if getTestMode():
                        self.fakeNumbers()
                    else:
                        self.readNumbers()
                    self.signalComm.updateValueSignal.emit()
            time.sleep(self.device.interval/1000)

    def readNumbers(self):
        for i, channel in enumerate(self.device.channels):
            try:
                meas = ctypes.c_int32()
                pt104.UsbPt104GetValue(self.chandle, pt104.PT104_CHANNELS[channel.channel], ctypes.byref(meas), 1)
                if meas.value != ctypes.c_long(0).value: # 0 during initialization phase
                    self.temperatures[i] = float(meas.value)/1000 + 273.15 # always return Kelvin
                else:
                    self.temperatures[i] = np.nan
            except ValueError as e:
                self.print(f'Error while reading temp: {e}', PRINT.ERROR)
                self.temperatures[i] = np.nan

    def fakeNumbers(self):
        for i, t in enumerate(self.temperatures):
            # exponentially approach target or room temp + small fluctuation
            self.temperatures[i] = np.random.randint(1, 300) if np.isnan(t) else t*np.random.uniform(.99, 1.01) # allow for small fluctuation

    def rndTemperature(self):
        return np.random.uniform(0, 400)

    def updateValue(self):
        for channel, pressure in zip(self.device.channels, self.temperatures):
            channel.value = pressure
