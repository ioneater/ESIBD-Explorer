# pylint: disable=[missing-module-docstring] # only single class in module
import time
from threading import Thread
import numpy as np
from PyQt6.QtCore import pyqtSignal
# install pyvisa in esibd environment
# conda activate esibd
# pip install pyvisa
import pyvisa
from esibd.plugins import Device
from esibd.core import Parameter, parameterDict, PluginManager, Channel, PRINT, DeviceController, getTestMode

def providePlugins():
    return [Current]

class Current(Device):
    """Device that contains a list of current channels, each corresponding to a single KEITHLEY 6487 picoammeter."""
    documentation = None # use __doc__

    name = 'KEITHLEY'
    version = '1.0'
    supportedVersion = '0.6'
    pluginType = PluginManager.TYPE.OUTPUTDEVICE
    unit = 'pA'

    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.channelType = CurrentChannel
        self.useBackgrounds = True # record backgrounds for data correction

    def finalizeInit(self, aboutFunc=None):
        """:meta private:"""
        # use stateAction.state instead of attribute as attribute would be added to DeviceManager rather than self
        self.onAction = self.pluginManager.DeviceManager.addStateAction(event=self.voltageON, toolTipFalse='KEITHLEY on.', iconFalse=self.makeIcon('keithley_off.png'),
                                                                  toolTipTrue='KEITHLEY off.', iconTrue=self.getIcon(),
                                                                 before=self.pluginManager.DeviceManager.aboutAction)
        super().finalizeInit(aboutFunc)

    def getIcon(self):
        return self.makeIcon('keithley.png')

    def initGUI(self):
        super().initGUI()
        self.addAction(event=self.resetCharge, toolTip='Reset accumulated charge.', icon='battery-empty.png')

    def getDefaultSettings(self):
        """ Define device specific settings that will be added to the general settings tab.
        These will be included if the settings file is deleted and automatically regenerated.
        Overwrite as needed."""
        ds = super().getDefaultSettings()
        ds[f'{self.name}/Interval'][Parameter.VALUE] = 100 # overwrite default value
        return ds

    def getInitializedChannels(self):
        return [d for d in self.channels if (d.enabled and (d.controller.port is not None or self.getTestMode())) or not d.active]

    def resetCharge(self):
        for channel in self.channels:
            channel.resetCharge()

    def closeCommunication(self):
        for channel in self.channels:
            channel.controller.voltageON(on=False, parallel=False)
        super().closeCommunication()
        
    def voltageON(self):
        if self.initialized():
            for channel in self.channels:
                channel.controller.voltageON(self.onAction.state)
        elif self.onAction.state is True:
            self.init()

    def updateTheme(self):
        """:meta private:"""
        super().updateTheme()
        self.onAction.iconTrue = self.getIcon()
        self.onAction.updateIcon(self.onAction.state) # self.on not available on start

class CurrentChannel(Channel):
    """UI for picoammeter with integrated functionality"""

    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.controller = CurrentController(channel=self)
        self.preciseCharge = 0 # store independent of spin box precision to avoid rounding errors

    CHARGE     = 'Charge'
    ADDRESS    = 'Address'
    VOLTAGE    = 'Voltage'

    def getDefaultChannel(self):
        """Gets default settings and values."""
        channel = super().getDefaultChannel()
        channel[self.VALUE][Parameter.HEADER ] = 'I (pA)' # overwrite existing parameter to change header
        channel[self.CHARGE     ] = parameterDict(value=0, widgetType=Parameter.TYPE.FLOAT, advanced=False, header='C (pAh)', indicator=True, attr='charge')
        channel[self.ADDRESS    ] = parameterDict(value='GPIB0::22::INSTR', widgetType=Parameter.TYPE.TEXT, advanced=True, attr='address')
        channel[self.VOLTAGE    ] = parameterDict(value=0, widgetType=Parameter.TYPE.FLOAT, advanced=False, attr='voltage', event=lambda : self.controller.setVoltage())
        return channel

    def setDisplayedParameters(self):
        super().setDisplayedParameters()
        self.insertDisplayedParameter(self.CHARGE, before=self.DISPLAY)
        self.insertDisplayedParameter(self.VOLTAGE, before=self.DISPLAY)
        self.displayedParameters.append(self.ADDRESS)

    def tempParameters(self):
        return super().tempParameters() + [self.CHARGE]

    def enabledChanged(self): # overwrite parent method
        """Handle changes while acquisition is running. All other changes will be handled when acquisition starts."""
        super().enabledChanged()
        if self.device.liveDisplayActive() and self.device.recording:
            if self.enabled:
                self.controller.init()
            elif self.controller.acquiring:
                self.controller.stopAcquisition()

    def appendValue(self, lenT, nan=False):
        # calculate deposited charge in last time step for all channels
        # this does not only monitor the deposition sample but also on what lenses charge is lost
        # make sure that the data interval is the same as used in data acquisition
        super().appendValue(lenT, nan=nan)
        if not nan and not self.value == np.inf:
            chargeIncrement = (self.value-self.background)*self.device.interval/1000/3600 if self.values.size > 1 else 0
            self.preciseCharge += chargeIncrement # display accumulated charge # don't use np.sum(self.charges) to allow
            self.charge = self.preciseCharge # pylint: disable=[attribute-defined-outside-init] # attribute defined dynamically

    def clearHistory(self, max_size=None):
        super().clearHistory(max_size)
        self.resetCharge()

    def resetCharge(self):
        self.charge = 0 # pylint: disable=[attribute-defined-outside-init] # attribute defined dynamically
        self.preciseCharge = 0

    def realChanged(self):
        self.getParameterByName(self.ADDRESS).getWidget().setVisible(self.real)
        super().realChanged()

class CurrentController(DeviceController):
    # need to inherit from QObject to allow use of signals
    """Implements visa communication with KEITHLEY 6487."""

    class SignalCommunicate(DeviceController.SignalCommunicate):
        updateValueSignal = pyqtSignal(float)

    def __init__(self, channel):
        super().__init__(_parent=channel)
        #setup port
        self.channel = channel
        self.device = self.channel.device
        self.port = None
        self.phase = np.random.rand()*10 # used in test mode
        self.omega = np.random.rand() # used in test mode
        self.offset = np.random.rand()*10 # used in test mode

    def initializeCommunication(self):
        if self.channel.enabled and self.channel.active:
            super().initializeCommunication()

    def closeCommunication(self):
        if self.port is not None:
            with self.lock.acquire_timeout(2) as acquired:
                if acquired:
                    self.port.close()
                else:
                    self.print(f'Cannot acquire lock to close port of {self.channel.name}.', PRINT.WARNING)
        super().closeCommunication()

    def runInitialization(self):
        """Initializes serial port in parallel thread."""
        if getTestMode():
            self.signalComm.initCompleteSignal.emit()
        else:
            self.initializing = True
            try:                
                rm = pyvisa.ResourceManager()
                # name = rm.list_resources()
                self.port = rm.open_resource(self.channel.address)
                self.port.write("*RST")
                self.device.print(self.port.query('*IDN?'))
                self.port.write("SYST:ZCH OFF")
                self.port.write("CURR:NPLC 6")
                self.port.write("SOUR:VOLT:RANG 50")                
                self.signalComm.initCompleteSignal.emit()
            except Exception:
                self.signalComm.updateValueSignal.emit(np.nan)
            finally:
                self.initializing = False

    def initComplete(self):
        super().initComplete()
        if getTestMode():
            self.print(f'{self.channel.name} faking values for testing!', PRINT.WARNING)
        else:            
            self.voltageON(self.device.onAction.state)

    def startAcquisition(self):
        # only run if init successful, or in test mode. if channel is not active it will calculate value independently
        if (self.port is not None or getTestMode()) and self.channel.active:
            super().startAcquisition()

    def runAcquisition(self, acquiring):
        while acquiring():
            with self.lock.acquire_timeout(2):
                if getTestMode():
                    self.fakeSingleNum()
                    time.sleep(self.channel.device.interval/1000)
                else:
                    self.readSingleNum()
                    # no sleep needed, timing controlled by waiting during readSingleNum

    def updateValue(self, value):
        self.channel.value = value

    def setVoltage(self):
        if self.port is not None:
            self.port.write(f"SOUR:VOLT {self.channel.voltage}")
    
    def voltageON(self, on=False, parallel=True): # this can run in main thread
        if not getTestMode() and self.initialized:
            self.setVoltage() # apply voltages before turning power supply on or off
            if parallel:
                Thread(target=self.voltageONFromThread, args=(on,), name=f'{self.device.name} voltageONFromThreadThread').start()
            else:
                self.voltageONFromThread(on=on)

    def voltageONFromThread(self, on=False):
        self.port.write(f"SOUR:VOLT:STAT {'ON' if on else 'OFF'}")   

    def fakeSingleNum(self):
        if not self.channel.device.pluginManager.closing:
            self.signalComm.updateValueSignal.emit(np.sin(self.omega*time.time()/5+self.phase)*10+np.random.rand()+self.offset)

    def readSingleNum(self):
        if not self.channel.device.pluginManager.closing:
            try:                
                self.port.write("INIT")
                self.signalComm.updateValueSignal.emit(float(self.port.query("FETCh?").split(',')[0][:-1])*1E12)
            except (pyvisa.errors.VisaIOError,pyvisa.errors.InvalidSession) as e:
                self.print(f'Error while reading current {e}')
                self.signalComm.updateValueSignal.emit(np.nan)

            
