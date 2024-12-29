# pylint: disable=[missing-module-docstring] # only single class in module
import time
import serial
import numpy as np
import pfeiffer_vacuum_protocol as pvp
from esibd.plugins import Device
from esibd.core import Parameter, PluginManager, Channel, parameterDict, DeviceController, PRINT, getTestMode

def providePlugins():
    return [OMNICONTROL]

class OMNICONTROL(Device):
    """Device that reads pressure values form an Pfeiffer Omnicontrol using the Pfeiffer Vacuum Protocol."""

    documentation = None # use __doc__
    name = 'OMNICONTROL'
    version = '1.0'
    supportedVersion = '0.6'
    pluginType = PluginManager.TYPE.OUTPUTDEVICE
    unit = 'mbar'

    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.channelType = PressureChannel
        self.controller = PressureController(_parent=self)
        self.logY = True

    def getIcon(self):
        return self.makeIcon('pfeiffer_omni.png')

    def getDefaultSettings(self):
        ds = super().getDefaultSettings()
        ds[f'{self.name}/Interval'][Parameter.VALUE] = 500 # overwrite default value
        ds[f'{self.name}/COM'] = parameterDict(value='COM1', toolTip='COM port of Omnicontrol.', items=','.join([f'COM{x}' for x in range(1, 25)]),
                                          widgetType=Parameter.TYPE.COMBO, attr='com')
        ds[f'{self.name}/{self.MAXDATAPOINTS}'][Parameter.VALUE] = 1E6 # overwrite default value
        return ds

    def getInitializedChannels(self):
        return [channel for channel in self.channels if (channel.enabled and (self.controller.port is not None) or self.getTestMode()) or not channel.active]

class PressureChannel(Channel):
    """UI for pressure with integrated functionality"""

    ID = 'ID'

    def getDefaultChannel(self):
        channel = super().getDefaultChannel()
        channel[self.VALUE][Parameter.HEADER] = 'P (mbar)' # overwrite existing parameter to change header
        # channel[self.VALUE][Parameter.INDICATOR] = False # overwrite existing parameter to change header
        channel[self.VALUE][Parameter.WIDGETTYPE] = Parameter.TYPE.EXP # overwrite existing parameter to change to use exponent notation
        channel[self.ID] = parameterDict(value=1, widgetType=Parameter.TYPE.INTCOMBO, advanced=True,
                                        items='0, 1, 2, 3, 4, 5, 6', attr='id')
        return channel

    def setDisplayedParameters(self):
        super().setDisplayedParameters()
        self.displayedParameters.append(self.ID)

class PressureController(DeviceController):

    def __init__(self, _parent):
        super().__init__(_parent=_parent)
        self.pressures = []

    def closeCommunication(self):
        if self.port is not None:
            with self.lock.acquire_timeout(1, timeoutMessage='Could not acquire lock before closing port.'):
                self.port.close()
                self.port = None
        super().closeCommunication()

    def runInitialization(self):
        self.pressures = [np.nan]*len(self.device.channels)
        if getTestMode():
            time.sleep(2)
            self.signalComm.initCompleteSignal.emit()
            self.print('Faking values for testing!', PRINT.WARNING)
        else:
            self.initializing = True
            try:
                self.port=serial.Serial(self.device.com, timeout=1)
                pvp.enable_valid_char_filter()
                self.signalComm.initCompleteSignal.emit()
            except Exception as e: # pylint: disable=[broad-except]
                self.print(f'Omnicontrol error while initializing: {e}', PRINT.ERROR)
            self.initializing = False

    def runAcquisition(self, acquiring):
        while acquiring():
            with self.lock.acquire_timeout(1) as lock_acquired:
                if lock_acquired:
                    self.fakeNumbers() if getTestMode() else self.readNumbers()
                    self.signalComm.updateValueSignal.emit()
            time.sleep(self.device.interval/1000)

    def readNumbers(self):
        for i, channel in enumerate(self.device.channels):
            if channel.enabled and channel.active:
                try:
                    pressure = pvp.read_pressure(self.port, channel.id)
                    self.pressures[i] = np.nan if pressure == 0 else pressure*1000
                except ValueError as e:
                    self.print(f'Error while reading pressure {e}')
                    self.pressures[i] = np.nan

    def fakeNumbers(self):
        for i, pressure in enumerate(self.pressures):
            self.pressures[i] = self.rndPressure() if np.isnan(pressure) else pressure*np.random.uniform(.99, 1.01) # allow for small fluctuation

    def rndPressure(self):
        exp = np.random.randint(-11, 3)
        significand = 0.9 * np.random.random() + 0.1
        return significand * 10**exp

    def updateValue(self):
        for channel, pressure in zip(self.device.channels, self.pressures):
            channel.value = pressure
