# pylint: disable=[missing-module-docstring] # only single class in module
import serial
from threading import Thread
import time
from random import choices
import numpy as np
from PyQt6.QtCore import pyqtSignal
from esibd.plugins import Device
from esibd.core import Parameter, parameterDict, PluginManager, Channel, PRINT, DeviceController, getTestMode

def providePlugins():
    return [MIPS]

class MIPS(Device):
    """Device that contains a list of voltages channels from one or multiple MIPS power supplies with 8 channels each.
    The voltages are monitored and a warning is given if the set potentials are not reached."""
    documentation = None # use __doc__

    name = 'MIPS'
    version = '1.0'
    pluginType = PluginManager.TYPE.INPUTDEVICE
    unit = 'V'

    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.channelType = VoltageChannel

    def initGUI(self):
        """:meta private:"""
        super().initGUI()
        self.controller = VoltageController(device=self, COMs = self.getCOMs()) # after all channels loaded

    def finalizeInit(self, aboutFunc=None):
        """:meta private:"""
        self.onAction = self.pluginManager.DeviceManager.addStateAction(event=self.voltageON, toolTipFalse='MIPS on.', iconFalse=self.makeIcon('mips_off.png'),
                                                                  toolTipTrue='MIPS off.', iconTrue=self.getIcon(),
                                                                 before=self.pluginManager.DeviceManager.aboutAction)
        super().finalizeInit(aboutFunc)

    def getIcon(self):
        return self.makeIcon('mips.png')

    def getDefaultSettings(self):
        """:meta private:"""
        ds = super().getDefaultSettings()
        ds[f'{self.name}/Interval'][Parameter.VALUE] = 1000 # overwrite default value
        ds[f'{self.name}/{self.MAXDATAPOINTS}'][Parameter.VALUE] = 1E5 # overwrite default value
        return ds

    def getCOMs(self): # get list of unique used COMs
        return list(set([channel.com for channel in self.channels]))
        
    def initializeCommunication(self):
        """:meta private:"""
        self.onAction.state = self.controller.ON
        super().initializeCommunication()

    def closeCommunication(self):
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
    COM        = 'COM'
    ID        = 'ID'

    def getDefaultChannel(self):
        channel = super().getDefaultChannel()
        channel[self.VALUE][Parameter.HEADER] = 'Voltage (V)' # overwrite to change header
        channel[self.MONITOR ] = parameterDict(value=0, widgetType=Parameter.TYPE.FLOAT, advanced=False,
                                    event=self.monitorChanged, indicator=True, attr='monitor')
        channel[self.COM] = parameterDict(value='COM1', toolTip='COM port of MIPS.', items=','.join([f'COM{x}' for x in range(1, 25)]),
                                          widgetType=Parameter.TYPE.COMBO, advanced=True, attr='com')
        channel[self.ID      ] = parameterDict(value=0, widgetType= Parameter.TYPE.INT, advanced=True,
                                    header='ID', _min=1, _max=8, attr='id')
        return channel

    def setDisplayedParameters(self):
        super().setDisplayedParameters()
        self.insertDisplayedParameter(self.MONITOR, before=self.MIN)
        self.displayedParameters.append(self.COM)
        self.displayedParameters.append(self.ID)

    def tempParameters(self):
        return super().tempParameters() + [self.MONITOR]

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
        self.getParameterByName(self.COM).getWidget().setVisible(self.real)
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

    def __init__(self, device, COMs):
        super().__init__(_parent=device)
        self.device     = device
        self.COMs       = COMs or ['COM1']
        self.signalComm.applyMonitorsSignal.connect(self.applyMonitors)
        self.ON         = False
        self.s          = [None]*len(self.COMs)
        self.maxID = max([c.id if c.real else 0 for c in self.device.channels]) # used to query correct amount of monitors
        self.voltages   = np.zeros([len(self.COMs), self.maxID+1])

    def runInitialization(self):
        """initializes socket for SCPI communication"""
        if getTestMode():
            self.print('Faking monitor values for testing!', PRINT.WARNING)
            self.initialized = True
            self.signalComm.initCompleteSignal.emit()
        else:
            self.initializing = True
            try:                
                self.s = [serial.Serial(baudrate = 9600, port = COM, parity = serial.PARITY_NONE, stopbits = serial.STOPBITS_ONE, bytesize = serial.EIGHTBITS) for COM in self.COMs]
                self.initialized = True
                self.signalComm.initCompleteSignal.emit()
            except Exception as e: # pylint: disable=[broad-except] # socket does not throw more specific exception
                self.print(f'Could not establish Serial connection to a MIPS at {self.COMs}. Exception: {e}', PRINT.WARNING)
            finally:
                self.initializing = False

    def initComplete(self):
        super().startAcquisition()
        if self.ON:
            self.device.updateValues(apply=True) # apply voltages before turning on or off
        self.voltageON(self.ON)
    
    def closeCommunication(self):
        for i, COM in enumerate(self.COMs):
            if self.s[i] is not None:
                with self.lock.acquire_timeout(1, timeoutMessage=f'Could not acquire lock before closing {COM}.') as lock_acquired:
                    self.s[i].close()
                    self.s[i] = None
        super().closeCommunication()
        
    def applyVoltage(self, channel):
        if not getTestMode() and self.initialized:
            Thread(target=self.applyVoltageFromThread, args=(channel,), name=f'{self.device.name} applyVoltageFromThreadThread').start()

    def applyVoltageFromThread(self, channel):
        if not getTestMode() and self.initialized:
            self.MIPSWriteRead(channel.com, message=f'SDCB,{channel.id},{channel.value if (channel.enabled and self.ON) else 0}\r\n')

    def applyMonitors(self):
        if getTestMode():
            self.fakeMonitors()
        else:
            for channel in self.device.channels:
                if channel.real:
                    channel.monitor = self.voltages[self.COMs.index(channel.com)][channel.id-1]

    def voltageON(self, on=False, parallel=True): # this can run in main thread
        self.ON = on
        if not getTestMode() and self.initialized:
            if parallel:
                Thread(target=self.voltageONFromThread, args=(on,), name=f'{self.device.name} voltageONFromThreadThread').start()
            else:
                self.voltageONFromThread(on=on) # use to make sure this is completed before closing connection
        elif getTestMode():
            self.fakeMonitors()

    def voltageONFromThread(self, on=False):
        for channel in self.device.channels:
            self.applyVoltageFromThread(channel)

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
            pass
            with self.lock.acquire_timeout(1, timeoutMessage='MIPS acquisition timeout Test') as lock_acquired: # TODO remove message
                if lock_acquired:
                    if not getTestMode():
                        for i in range(len(self.COMs)):
                            for ID in range(8):
                                try:
                                    self.voltages[i][ID] = float(self.MIPSWriteRead(self.COMs[i], f'GDCBV,{ID+1}\r\n', lock_acquired=True))
                                except ValueError:
                                    self.voltages[i][ID] = np.nan
                    self.signalComm.applyMonitorsSignal.emit() # signal main thread to update GUI
            time.sleep(self.device.interval/1000)

    def MIPSWrite(self, COM, message):
        m = self.COMs.index(COM)        
        self.serialWrite(self.s[m], message)

    def MIPSRead(self, COM):
        # only call from thread! # make sure lock is acquired before and released after
        m = self.COMs.index(COM)     
        if not getTestMode() and self.initialized:
            return self.serialRead(self.s[m], EOL='\r', strip='b\x06')

    def MIPSWriteRead(self, COM, message, lock_acquired=False):
        """Allows to write and read while using lock with timeout."""
        response = ''
        if not getTestMode():
            if lock_acquired: # already acquired -> save to use
                self.MIPSWrite(COM, message) # get channel name
                response = self.MIPSRead(COM)
            else:
                with self.lock.acquire_timeout(1, timeoutMessage=f'Cannot acquire lock for MIPS communication. Query {message}.') as lock_acquired:
                    if lock_acquired:
                        self.MIPSWrite(COM, message) # get channel name
                        response = self.MIPSRead(COM)
        return response
