# pylint: disable=[missing-module-docstring] # only single class in module
from threading import Thread
import time
from random import choices
import numpy as np
from PyQt6.QtCore import pyqtSignal
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
    pluginType = PluginManager.TYPE.INPUTDEVICE
    unit = 'V'

    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.channelType = VoltageChannel

    def initGUI(self):
        """:meta private:"""
        super().initGUI()
        self.controller = VoltageController(device=self) # after all channels loaded

    def finalizeInit(self, aboutFunc=None):
        """:meta private:"""
        self.onAction = self.pluginManager.DeviceManager.addStateAction(event=self.voltageON, toolTipFalse='RSPD3303C on.', iconFalse=self.makeIcon('RSPD3303C_off.png'),
                                                                  toolTipTrue='RSPD3303C off.', iconTrue=self.getIcon(),
                                                                 before=self.pluginManager.DeviceManager.aboutAction)
        super().finalizeInit(aboutFunc)

    def getIcon(self):
        return self.makeIcon('RSPD3303C.png')

    ADDRESS    = 'Address'

    def getDefaultSettings(self):
        """:meta private:"""
        ds = super().getDefaultSettings()
        ds[f'{self.name}/Interval'][Parameter.VALUE] = 1000 # overwrite default value
        ds[f'{self.name}/{self.MAXDATAPOINTS}'][Parameter.VALUE] = 1E5 # overwrite default value
        ds[f'{self.name}/{self.ADDRESS}'] = parameterDict(value='USB0::0xF4EC::0x1430::SPD3EGGD7R2257::INSTR', widgetType=Parameter.TYPE.TEXT, advanced=True, attr='address')
        return ds
        
    def initializeCommunication(self):
        """:meta private:"""
        self.onAction.state = self.controller.ON
        super().initializeCommunication()

    def closeCommunication(self):
        """:meta private:"""
        self.controller.voltageON(on=False, parallel=False)
        super().closeCommunication()

    def applyValues(self, apply=False):
        for c in self.channels:
            c.applyVoltage(apply) # only actually sets voltage if configured and value has changed

    def voltageON(self):
        if self.initialized():
            self.updateValues(apply=True) # apply voltages before turning on or off
            self.controller.voltageON(self.onAction.state)
        elif self.onAction.state is True:
            self.controller.ON = self.onAction.state
            self.initializeCommunication()

class VoltageChannel(Channel):
    """UI for single voltage channel with integrated functionality"""

    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.lastAppliedValue = None # keep track of last value to identify what has changed
        self.warningStyleSheet = f'background: rgb({255},{0},{0})'
        self.defaultStyleSheet = None # will be initialized when color is set

    MONITOR   = 'Monitor'
    CURRENT   = 'Current'
    POWER     = 'Power'
    ID        = 'ID'

    def getDefaultChannel(self):
        channel = super().getDefaultChannel()
        channel[self.VALUE][Parameter.HEADER] = 'Voltage (V)' # overwrite to change header
        channel[self.MIN ][Parameter.VALUE] = 0
        channel[self.MAX ][Parameter.VALUE] = 1 # start with safe limits
        channel[self.MONITOR ] = parameterDict(value=0, widgetType=Parameter.TYPE.FLOAT, advanced=False,
                                    event=self.monitorChanged, indicator=True, attr='monitor')
        channel[self.POWER ] = parameterDict(value=0, widgetType=Parameter.TYPE.FLOAT, advanced=False,
                                                               indicator=True, attr='power')
        channel[self.CURRENT ] = parameterDict(value=0, widgetType=Parameter.TYPE.FLOAT, advanced=True,
                                                               indicator=True, attr='current')
        channel[self.ID      ] = parameterDict(value=0, widgetType= Parameter.TYPE.INT, advanced=True,
                                    header='ID', _min=0, _max=99, attr='id')
        return channel

    def setDisplayedParameters(self):
        super().setDisplayedParameters()
        self.insertDisplayedParameter(self.MONITOR, before=self.MIN)
        self.insertDisplayedParameter(self.CURRENT, before=self.MIN)
        self.insertDisplayedParameter(self.POWER, before=self.MIN)
        self.displayedParameters.append(self.ID)

    def tempParameters(self):
        return super().tempParameters() + [self.MONITOR,self.POWER,self.CURRENT]

    def applyVoltage(self, apply): # this actually sets the voltage on the power supply!
        if self.real and ((self.value != self.lastAppliedValue) or apply):
            self.device.controller.applyVoltage(self)
            self.lastAppliedValue = self.value

    def updateColor(self):
        color = super().updateColor()
        self.defaultStyleSheet = f'background-color: {color.name()}'

    def monitorChanged(self):
        if self.enabled and self.device.controller.acquiring and ((self.device.controller.ON and abs(self.monitor - self.value) > 1)
                                                                    or (not self.device.controller.ON and abs(self.monitor - 0) > 1)):
            self.getParameterByName(self.MONITOR).getWidget().setStyleSheet(self.warningStyleSheet)
        else:
            self.getParameterByName(self.MONITOR).getWidget().setStyleSheet(self.defaultStyleSheet)

    def realChanged(self):
        self.getParameterByName(self.MONITOR).getWidget().setVisible(self.real)
        self.getParameterByName(self.POWER).getWidget().setVisible(self.real)
        self.getParameterByName(self.CURRENT).getWidget().setVisible(self.real)
        self.getParameterByName(self.ID).getWidget().setVisible(self.real)
        super().realChanged()

    def appendValue(self, lenT, nan=False):
        # super().appendValue() # overwrite to use monitors if available
        if nan:
            self.monitor=np.nan
        if self.enabled and self.real:
            self.values.add(self.monitor, lenT)
        else:
            self.values.add(self.value, lenT)

class VoltageController(DeviceController):
    """Implements Serial communication with MIPS.
    While this is kept as general as possible, some access to the management and UI parts are required for proper integration."""

    class SignalCommunicate(DeviceController.SignalCommunicate):
        applyMonitorsSignal= pyqtSignal()

    def __init__(self, device):
        super().__init__(_parent=device)
        self.device     = device
        self.signalComm.applyMonitorsSignal.connect(self.applyMonitors)
        self.ON         = False
        self.voltages   = [np.nan]*len(self.device.channels)
        self.currents   = [np.nan]*len(self.device.channels)

    def initializeCommunication(self, IP='localhost', port=0):
        self.IP = IP
        self.port = port
        super().initializeCommunication()

    def runInitialization(self):
        """initializes socket for SCPI communication"""
        if getTestMode():
            self.print('Faking monitor values for testing!', PRINT.WARNING)
            self.initialized = True
            self.signalComm.initCompleteSignal.emit()
        else:
            self.initializing = True
            try:
                rm = pyvisa.ResourceManager()
                # name = rm.list_resources()
                self.port = rm.open_resource(self.device.address, open_timeout=500)
                self.device.print(self.port.query('*IDN?'))
                self.initialized = True
                self.signalComm.initCompleteSignal.emit()
            except Exception as e: # pylint: disable=[broad-except] # socket does not throw more specific exception
                self.print(f'Could not establish connection to {self.device.address}. Exception: {e}', PRINT.WARNING)
            finally:
                self.initializing = False

    def initComplete(self):
        super().startAcquisition()
        if self.ON:
            self.device.updateValues(apply=True) # apply voltages before turning on or off
        self.voltageON(self.ON)
            
    def applyVoltage(self, channel):
        if not getTestMode() and self.initialized:
            Thread(target=self.applyVoltageFromThread, args=(channel,), name=f'{self.device.name} applyVoltageFromThreadThread').start()

    def applyVoltageFromThread(self, channel):
        self.RSWrite(f'CH{channel.id}:VOLT {channel.value}')

    def applyMonitors(self):
        if getTestMode():
            self.fakeMonitors()
        else:
            for i, channel in enumerate(self.device.channels):
                if channel.real:
                    channel.monitor = self.voltages[i]
                    channel.current = self.currents[i]
                    channel.power = channel.monitor*channel.current

    def voltageON(self, on=False, parallel=True): # this can run in main thread
        self.ON = on
        if not getTestMode() and self.initialized:
            if parallel:
                Thread(target=self.voltageONFromThread, args=(on,), name=f'{self.device.name} voltageONFromThreadThread').start()
            else:
                self.voltageONFromThread(on=on)
        elif getTestMode():
            self.fakeMonitors()

    def voltageONFromThread(self, on=False):
        for channel in self.device.channels:
            self.RSWrite(f"OUTPUT CH{channel.id},{'ON' if on else 'OFF'}")

    def fakeMonitors(self):
        for channel in self.device.channels:
            if channel.real:
                if self.device.controller.ON and channel.enabled:
                    # fake values with noise and 10% channels with offset to simulate defect channel or short
                    channel.monitor = channel.value + 5*choices([0, 1],[.98,.02])[0] + np.random.rand()
                else:
                    channel.monitor = 0             + 5*choices([0, 1],[.9,.1])[0] + np.random.rand()
                channel.current = 50/channel.monitor if channel.monitor != 0 else 0 # simulate 50 W                
                channel.power = channel.monitor*channel.current

    def runAcquisition(self, acquiring):
        """monitor potentials continuously"""
        while acquiring():
            with self.lock.acquire_timeout(1) as lock_acquired:
                if lock_acquired:
                    if not getTestMode():
                        for i, channel in enumerate(self.device.channels):
                            self.voltages[i] = self.RSQuery(f'MEAS:VOLT? CH{channel.id}', lock_acquired=True)
                            self.currents[i] = self.RSQuery(f'MEAS:CURR? CH{channel.id}', lock_acquired=True)
                    self.signalComm.applyMonitorsSignal.emit() # signal main thread to update GUI
            time.sleep(self.device.interval/1000)

    def RSWrite(self, message):        
        with self.lock.acquire_timeout(1, timeoutMessage=f'Cannot acquire lock for communication. Query {message}.') as lock_acquired:
            if lock_acquired:
                self.port.write(message)

    def RSQuery(self, message, lock_acquired=False):        
        response = ''
        if lock_acquired:
            response = self.port.query(message)
        else:
            with self.lock.acquire_timeout(1, timeoutMessage=f'Cannot acquire lock for communication. Query {message}.') as lock_acquired:
                if lock_acquired:
                    response = self.port.query(message)
        return response
