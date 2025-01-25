# pylint: disable=[missing-module-docstring] # only single class in module
from threading import Thread
import time
from random import choices
import numpy as np
import pyvisa
from esibd.plugins import Device
from esibd.core import Parameter, parameterDict, PluginManager, Channel, PRINT, DeviceController, getTestMode

def providePlugins():
    return [RSPD3303C]

class RSPD3303C(Device):
    """Device that contains a list of voltages channels from a single RSPD3303C power supplies with 2 analog outputs.
    In case of any issues, first test communication independently with EasyPowerX."""
    documentation = None # use __doc__

    name = 'RSPD3303C'
    version = '1.0'
    supportedVersion = '0.7'
    pluginType = PluginManager.TYPE.INPUTDEVICE
    unit = 'V'
    useMonitors = True

    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.useOnOffLogic = True
        self.channelType = VoltageChannel

    def initGUI(self):
        """:meta private:"""
        super().initGUI()
        self.controller = VoltageController(_parent=self) # after all channels loaded

    def getIcon(self, **kwargs):
        return self.makeIcon('RSPD3303C.png', **kwargs)

    ADDRESS = 'Address'

    def getDefaultSettings(self):
        """:meta private:"""
        ds = super().getDefaultSettings()
        ds[f'{self.name}/Interval'][Parameter.VALUE] = 1000 # overwrite default value
        ds[f'{self.name}/{self.MAXDATAPOINTS}'][Parameter.VALUE] = 1E5 # overwrite default value
        ds[f'{self.name}/{self.ADDRESS}'] = parameterDict(value='USB0::0xF4EC::0x1430::SPD3EGGD7R2257::INSTR', widgetType=Parameter.TYPE.TEXT, advanced=True, attr='address')
        return ds

    def closeCommunication(self):
        """:meta private:"""
        self.setOn(False)
        self.controller.voltageON(parallel=False)
        super().closeCommunication()

    def applyValues(self, apply=False):
        for channel in self.channels:
            channel.applyVoltage(apply) # only actually sets voltage if configured and value has changed

    def setOn(self, on=None):
        super().setOn(on)
        if self.initialized():
            self.updateValues(apply=True) # apply voltages before turning on or off
            self.controller.voltageON()
        elif self.isOn():
            self.initializeCommunication()

class VoltageChannel(Channel):

    CURRENT   = 'Current'
    POWER     = 'Power'
    ID        = 'ID'

    def getDefaultChannel(self):
        channel = super().getDefaultChannel()
        channel[self.VALUE][Parameter.HEADER] = 'Voltage (V)' # overwrite to change header
        channel[self.MIN ][Parameter.VALUE] = 0
        channel[self.MAX ][Parameter.VALUE] = 1 # start with safe limits
        channel[self.POWER ] = parameterDict(value=0, widgetType=Parameter.TYPE.FLOAT, advanced=False,
                                                               indicator=True, attr='power')
        channel[self.CURRENT ] = parameterDict(value=0, widgetType=Parameter.TYPE.FLOAT, advanced=True,
                                                               indicator=True, attr='current')
        channel[self.ID      ] = parameterDict(value=0, widgetType= Parameter.TYPE.INT, advanced=True,
                                    header='ID', _min=0, _max=99, attr='id')
        return channel

    def setDisplayedParameters(self):
        super().setDisplayedParameters()
        self.insertDisplayedParameter(self.CURRENT, before=self.MIN)
        self.insertDisplayedParameter(self.POWER, before=self.MIN)
        self.displayedParameters.append(self.ID)

    def tempParameters(self):
        return super().tempParameters() + [self.POWER, self.CURRENT]

    def applyVoltage(self, apply): # this actually sets the voltage on the power supply!
        if self.real and ((self.value != self.lastAppliedValue) or apply):
            self.device.controller.applyVoltage(self)
            self.lastAppliedValue = self.value

    def monitorChanged(self):
        # overwriting super().monitorChanged() to set 0 as expected value when device is off
        self.updateWarningState(self.enabled and self.device.controller.acquiring and ((self.device.isOn() and abs(self.monitor - self.value) > 1)
                                                                    or (not self.device.isOn() and abs(self.monitor - 0) > 1)))

    def realChanged(self):
        self.getParameterByName(self.POWER).getWidget().setVisible(self.real)
        self.getParameterByName(self.CURRENT).getWidget().setVisible(self.real)
        self.getParameterByName(self.ID).getWidget().setVisible(self.real)
        super().realChanged()

class VoltageController(DeviceController):

    def __init__(self, _parent):
        super().__init__(_parent=_parent)
        self.voltages   = [np.nan]*len(self.device.channels)
        self.currents   = [np.nan]*len(self.device.channels)

    def runInitialization(self):
        try:
            rm = pyvisa.ResourceManager()
            # name = rm.list_resources()
            self.port = rm.open_resource(self.device.address, open_timeout=500)
            self.device.print(self.port.query('*IDN?'))
            self.signalComm.initCompleteSignal.emit()
        except Exception as e: # pylint: disable=[broad-except] # socket does not throw more specific exception
            self.print(f'Could not establish connection to {self.device.address}. Exception: {e}', PRINT.WARNING)
        finally:
            self.initializing = False

    def initComplete(self):
        super().initComplete()
        if self.device.isOn():
            self.device.updateValues(apply=True) # apply voltages before turning on or off
        self.voltageON()

    def applyVoltage(self, channel):
        if not getTestMode() and self.initialized:
            Thread(target=self.applyVoltageFromThread, args=(channel,), name=f'{self.device.name} applyVoltageFromThreadThread').start()

    def applyVoltageFromThread(self, channel):
        self.RSWrite(f'CH{channel.id}:VOLT {channel.value if channel.enabled else 0}')

    def updateValue(self):
        if getTestMode():
            self.fakeNumbers()
        else:
            for i, channel in enumerate(self.device.channels):
                if channel.real:
                    channel.monitor = self.voltages[i]
                    channel.current = self.currents[i]
                    channel.power = channel.monitor*channel.current

    def voltageON(self, parallel=True): # this can run in main thread
        if not getTestMode() and self.initialized:
            if parallel:
                Thread(target=self.voltageONFromThread, name=f'{self.device.name} voltageONFromThreadThread').start()
            else:
                self.voltageONFromThread()
        elif getTestMode():
            self.fakeNumbers()

    def voltageONFromThread(self):
        for channel in self.device.channels:
            self.RSWrite(f"OUTPUT CH{channel.id},{'ON' if self.device.isOn() else 'OFF'}")

    def fakeNumbers(self):
        for channel in self.device.channels:
            if channel.real:
                if self.device.isOn() and channel.enabled:
                    # fake values with noise and 10% channels with offset to simulate defect channel or short
                    channel.monitor = channel.value + 5*choices([0, 1],[.98,.02])[0] + np.random.rand()
                else:
                    channel.monitor = 0             + 5*choices([0, 1],[.9,.1])[0] + np.random.rand()
                channel.current = 50/channel.monitor if channel.monitor != 0 else 0 # simulate 50 W
                channel.power = channel.monitor*channel.current

    def runAcquisition(self, acquiring):
        while acquiring():
            with self.lock.acquire_timeout(1) as lock_acquired:
                if lock_acquired:
                    if not getTestMode():
                        for i, channel in enumerate(self.device.channels):
                            self.voltages[i] = self.RSQuery(f'MEAS:VOLT? CH{channel.id}', lock_acquired=lock_acquired)
                            self.currents[i] = self.RSQuery(f'MEAS:CURR? CH{channel.id}', lock_acquired=lock_acquired)
                    self.signalComm.updateValueSignal.emit() # signal main thread to update GUI
            time.sleep(self.device.interval/1000)

    def RSWrite(self, message):
        with self.lock.acquire_timeout(1, timeoutMessage=f'Cannot acquire lock for message {message}.') as lock_acquired:
            if lock_acquired:
                self.port.write(message)

    def RSQuery(self, message, lock_acquired=False):
        response = ''
        with self.lock.acquire_timeout(1, timeoutMessage=f'Cannot acquire lock for query {message}.', lock_acquired=lock_acquired) as lock_acquired:
            if lock_acquired:
                response = self.port.query(message)
        return response
