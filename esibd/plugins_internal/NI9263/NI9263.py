# pylint: disable=[missing-module-docstring] # only single class in module
import serial
from threading import Thread
import time
from random import choices
import numpy as np
from PyQt6.QtCore import pyqtSignal
# install nidaqmx in esibd environment
# conda activate esibd
# pip install nidaqmx
import nidaqmx
from esibd.plugins import Device, LiveDisplay, StaticDisplay
from esibd.core import Parameter, parameterDict, PluginManager, Channel, PRINT, DeviceController, getDarkMode, getTestMode

########################## Voltage user interface #################################################

def providePlugins():
    return [NI9263]

class NI9263(Device):
    """Device that contains a list of voltages channels from one or multiple NI9263 power supplies with 4 analog outputs each."""
    documentation = None # use __doc__

    name = 'NI9263'
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
        # use stateAction.state instead of attribute as attribute would be added to DeviceManager rather than self
        self.onAction = self.pluginManager.DeviceManager.addStateAction(event=self.voltageON, toolTipFalse='NI9263 on.', iconFalse=self.makeIcon('NI9263_off.png'),
                                                                  toolTipTrue='NI9263 off.', iconTrue=self.getIcon(),
                                                                 before=self.pluginManager.DeviceManager.aboutAction)
        super().finalizeInit(aboutFunc)

    def getIcon(self):
        return self.makeIcon('NI9263.png')

    def getDefaultSettings(self):
        """:meta private:"""
        ds = super().getDefaultSettings()
        ds[f'{self.name}/Interval'][Parameter.VALUE] = 1000 # overwrite default value
        ds[f'{self.name}/{self.MAXDATAPOINTS}'][Parameter.VALUE] = 1E5 # overwrite default value
        return ds
        
    def initializeCommunication(self):
        """:meta private:"""
        super().initializeCommunication()
        self.onAction.state = self.controller.ON
        self.controller.initializeCommunication()

    def stopAcquisition(self):
        """:meta private:"""
        super().stopAcquisition()
        self.controller.stopAcquisition()

    def closeCommunication(self):
        self.controller.voltageON(on=False, parallel=False)
        super().closeCommunication()
    
    def initialized(self):
        return self.controller.initialized

    def apply(self, apply=False):
        for c in self.channels:
            c.setVoltage(apply) # only actually sets voltage if configured and value has changed

    def voltageON(self):
        if self.initialized():
            self.updateValues(apply=True) # apply voltages before turning on or off
            self.controller.voltageON(self.onAction.state)
        elif self.onAction.state is True:
            self.controller.ON = self.onAction.state
            self.init()

class VoltageChannel(Channel):
    """UI for single voltage channel with integrated functionality"""

    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.lastAppliedValue = None # keep track of last value to identify what has changed
        self.warningStyleSheet = f'background: rgb({255},{0},{0})'
        self.defaultStyleSheet = None # will be initialized when color is set

    MONITOR   = 'Monitor'
    ADDRESS   = 'Address'

    def getDefaultChannel(self):
        channel = super().getDefaultChannel()
        channel[self.VALUE][Parameter.HEADER] = 'Voltage (V)' # overwrite to change header
        channel[self.MIN ][Parameter.VALUE] = 0
        channel[self.MAX ][Parameter.VALUE] = 1 # start with safe limits
        channel[self.MONITOR ] = parameterDict(value=0, widgetType=Parameter.TYPE.FLOAT, advanced=False,
                                    event=self.monitorChanged, indicator=True, attr='monitor')
        channel[self.ADDRESS] = parameterDict(value='cDAQ1Mod1/ao0', toolTip='Address of analog output',
                                          widgetType=Parameter.TYPE.TEXT, advanced=True, attr='address')
        return channel

    def setDisplayedParameters(self):
        super().setDisplayedParameters()
        # self.insertDisplayedParameter(self.MONITOR, before=self.MIN) TODO show when monitors are fixed
        self.displayedParameters.append(self.ADDRESS)

    def tempParameters(self):
        return super().tempParameters() + [self.MONITOR]

    def setVoltage(self, apply): # this actually sets the voltage on the power supply!
        if self.real and ((self.value != self.lastAppliedValue) or apply):
            self.device.controller.setVoltage(self)
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
        # self.getParameterByName(self.MONITOR).getWidget().setVisible(self.real)
        self.getParameterByName(self.ADDRESS).getWidget().setVisible(self.real)
        super().realChanged()

    def appendValue(self, lenT, nan=False):
        # super().appendValue() # overwrite to use monitors if available        
        # if nan:
        #     self.monitor=np.nan
        # if self.enabled and self.real:
        #     self.values.add(self.monitor, lenT)
        # else:
        #     self.values.add(self.value, lenT)
        pass # TODO fix monitors

class VoltageController(DeviceController): # no channels needed
    # need to inherit from QObject to allow use of signals
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

    def runInitialization(self):
        """initializes socket for SCPI communication"""
        if getTestMode():
            self.print('Faking monitor values for testing!', PRINT.WARNING)
            self.initialized = True
            self.signalComm.initCompleteSignal.emit()
        else:
            self.initializing = True
            try:
                # no initialization needed, just try to address channels
                with nidaqmx.Task() as task:
                    task.ao_channels # will raise exception if connection failed
                self.initialized = True
                self.signalComm.initCompleteSignal.emit()
                # threads cannot be restarted -> make new thread every time. possibly there are cleaner solutions
            except Exception as e: # pylint: disable=[broad-except] # socket does not throw more specific exception
                self.print(f'Could not establish connection at {self.device.channels[0].address}. Exception: {e}', PRINT.WARNING)
            finally:
                self.initializing = False

    def initComplete(self):
        # super().startAcquisition() TODO fix monitors
        if self.ON:
            self.device.updateValues(apply=True) # apply voltages before turning on or off
        self.voltageON(self.ON)
                    
    def setVoltage(self, channel):
        if not getTestMode() and self.initialized:
            Thread(target=self.setVoltageFromThread, args=(channel,), name=f'{self.device.name} setVoltageFromThreadThread').start()

    def setVoltageFromThread(self, channel):
        with self.lock.acquire_timeout(2) as acquired:
            if acquired:
                with nidaqmx.Task() as task:
                    task.ao_channels.add_ao_voltage_chan(channel.address)
                    task.write(channel.value if (channel.enabled and self.ON) else 0)
            else:
                self.print(f'Cannot acquire lock to set voltage of {channel.name}.', PRINT.WARNING)

    def applyMonitors(self):
        if getTestMode():
            self.fakeMonitors()
        else:
            for i, channel in enumerate(self.device.channels):
                if channel.real:
                    channel.monitor = self.voltages[i]

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
            if channel.real:
                self.setVoltageFromThread(channel)

    def fakeMonitors(self):
        for channel in self.device.channels:
            if channel.real:
                if self.device.controller.ON and channel.enabled:
                    # fake values with noise and 10% channels with offset to simulate defect channel or short
                    channel.monitor = channel.value + 5*choices([0, 1],[.98,.02])[0] + np.random.rand()
                else:
                    channel.monitor = 0             + 5*choices([0, 1],[.9,.1])[0] + np.random.rand()

    def runAcquisition(self, acquiring):
        """monitor potentials continuously"""
        while acquiring():
            with self.lock.acquire_timeout(2):
                if not getTestMode():
                    for i, channel in enumerate(self.device.channels):
                        # with nidaqmx.Task() as task: TODO
                        #     task.ao_channels.add_ao_voltage_chan(channel.address)
                        #     self.voltages[i] = task.write(str.encode('0.0'))
                        self.voltages[i] = np.nan 
                            
                self.signalComm.applyMonitorsSignal.emit() # signal main thread to update GUI
                time.sleep(self.device.interval/1000)
