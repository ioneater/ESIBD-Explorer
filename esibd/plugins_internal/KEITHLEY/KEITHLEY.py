# pylint: disable=[missing-module-docstring] # see class docstrings
import time
import numpy as np
import pyvisa
from esibd.plugins import Device
from esibd.core import Parameter, parameterDict, PluginManager, Channel, PRINT, DeviceController, getTestMode

def providePlugins():
    """Indicates that this module provides plugins. Returns list of provided plugins."""
    return [KEITHLEY]

class KEITHLEY(Device):
    """Device that contains a list of current channels, each corresponding to a single KEITHLEY 6487 picoammeter."""
    documentation = None # use __doc__

    name = 'KEITHLEY'
    version = '1.0'
    supportedVersion = '0.7'
    pluginType = PluginManager.TYPE.OUTPUTDEVICE
    unit = 'pA'
    iconFile = 'keithley.png'

    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.useOnOffLogic = True
        self.channelType = CurrentChannel
        self.useBackgrounds = True # record backgrounds for data correction

    def initGUI(self):
        super().initGUI()
        self.addAction(event=lambda: self.resetCharge(), toolTip=f'Reset accumulated charge for {self.name}.', icon='battery-empty.png')

    def getDefaultSettings(self):
        defaultSettings = super().getDefaultSettings()
        defaultSettings[f'{self.name}/Interval'][Parameter.VALUE] = 100 # overwrite default value
        return defaultSettings

    def resetCharge(self):
        """Resets the charge of each channel."""
        for channel in self.channels:
            channel.resetCharge()

    def updateTheme(self):
        super().updateTheme()
        self.onAction.iconTrue = self.getIcon()
        self.onAction.updateIcon(self.isOn())

class CurrentChannel(Channel):
    """UI for picoammeter with integrated functionality"""

    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.controller = CurrentController(_parent=self)
        self.preciseCharge = 0 # store independent of spin box precision to avoid rounding errors

    CHARGE     = 'Charge'
    ADDRESS    = 'Address'
    VOLTAGE    = 'Voltage'

    def getDefaultChannel(self):
        channel = super().getDefaultChannel()
        channel[self.VALUE][Parameter.HEADER ] = 'I (pA)'
        channel[self.CHARGE     ] = parameterDict(value=0, widgetType=Parameter.TYPE.FLOAT, advanced=False, header='C (pAh)', indicator=True, attr='charge')
        channel[self.ADDRESS    ] = parameterDict(value='GPIB0::22::INSTR', widgetType=Parameter.TYPE.TEXT, advanced=True, attr='address')
        channel[self.VOLTAGE    ] = parameterDict(value=0, widgetType=Parameter.TYPE.FLOAT, advanced=False, attr='voltage', event=lambda: self.controller.applyVoltage())
        return channel

    def setDisplayedParameters(self):
        super().setDisplayedParameters()
        self.insertDisplayedParameter(self.CHARGE, before=self.DISPLAY)
        self.insertDisplayedParameter(self.VOLTAGE, before=self.DISPLAY)
        self.displayedParameters.append(self.ADDRESS)

    def tempParameters(self):
        return super().tempParameters() + [self.CHARGE]

    def enabledChanged(self):
        super().enabledChanged()
        if self.device.liveDisplayActive() and self.device.recording:
            if self.enabled:
                self.controller.initializeCommunication()
            elif self.controller.acquiring:
                self.controller.stopAcquisition()

    def appendValue(self, lenT, nan=False):
        super().appendValue(lenT, nan=nan)
        if not nan and not np.isnan(self.value) and not np.isinf(self.value):
            chargeIncrement = (self.value-self.background)*self.device.interval/1000/3600 if self.values.size > 1 else 0
            self.preciseCharge += chargeIncrement # display accumulated charge # don't use np.sum(self.charges) to allow
            self.charge = self.preciseCharge # pylint: disable=[attribute-defined-outside-init] # attribute defined dynamically

    def clearHistory(self, max_size=None):
        super().clearHistory(max_size)
        self.resetCharge()

    def resetCharge(self):
        """Resets the charge."""
        self.charge = 0 # pylint: disable=[attribute-defined-outside-init] # attribute defined dynamically
        self.preciseCharge = 0

    def realChanged(self):
        self.getParameterByName(self.ADDRESS).getWidget().setVisible(self.real)
        super().realChanged()

class CurrentController(DeviceController):
    """Implements visa communication with KEITHLEY 6487."""

    def __init__(self, _parent):
        super().__init__(_parent=_parent)
        #setup port
        self.channel = _parent
        self.device = self.channel.getDevice()
        self.port = None
        self.phase = np.random.rand()*10 # used in test mode
        self.omega = np.random.rand() # used in test mode
        self.offset = np.random.rand()*10 # used in test mode

    def initializeCommunication(self):
        if self.channel.enabled and self.channel.active and self.channel.real:
            super().initializeCommunication()
        else:
            self.stopAcquisition()

    def closeCommunication(self):
        if self.port is not None:
            with self.lock.acquire_timeout(1, timeoutMessage='Could not acquire lock before closing port.'):
                self.port.close()
                self.port = None
        super().closeCommunication()

    def runInitialization(self):
        try:
            # name = rm.list_resources()
            self.rm = pyvisa.ResourceManager()
            self.port = self.rm.open_resource(self.channel.address)
            self.port.write("*RST")
            self.device.print(self.port.query('*IDN?'))
            self.port.write("SYST:ZCH OFF")
            self.port.write("CURR:NPLC 6")
            self.port.write("SOUR:VOLT:RANG 50")
            self.signalComm.initCompleteSignal.emit()
        except Exception:
            self.signalComm.updateValuesSignal.emit(np.nan)
        finally:
            self.initializing = False

    def startAcquisition(self):
        if self.channel.active:
            super().startAcquisition()

    def runAcquisition(self, acquiring):
        while acquiring():
            with self.lock.acquire_timeout(1) as lock_acquired:
                if lock_acquired:
                    if getTestMode():
                        self.fakeNumbers()
                    else:
                        self.readNumbers()
                    self.signalComm.updateValuesSignal.emit()
                        # no sleep needed, timing controlled by waiting during readNumbers
            if getTestMode():
                time.sleep(self.channel.device.interval/1000)

    def applyVoltage(self):
        # NOTE this is different from the general applyValue function as this is not setting the channel value but a custom channel parameter
        """Applies voltage value."""
        if self.port is not None:
            self.port.write(f"SOUR:VOLT {self.channel.voltage}")

    def toggleOn(self):
        self.applyVoltage() # apply voltages before turning power supply on or off
        self.port.write(f"SOUR:VOLT:STAT {'ON' if self.device.isOn() else 'OFF'}")

    def fakeNumbers(self):
        if not self.channel.device.pluginManager.closing:
            if self.channel.enabled and self.channel.active and self.channel.real:
                self.values=[np.sin(self.omega*time.time()/5+self.phase)*10+np.random.rand()+self.offset]

    def readNumbers(self):
        if not self.channel.device.pluginManager.closing:
            if self.channel.enabled and self.channel.active and self.channel.real:
                try:
                    self.port.write("INIT")
                    self.values=[float(self.port.query("FETCh?").split(',')[0][:-1])*1E12]
                except (pyvisa.errors.VisaIOError, pyvisa.errors.InvalidSession, AttributeError) as e:
                    self.print(f'Error while reading current {e}', flag=PRINT.ERROR)
                    self.errorCount += 1
                    self.values=[np.nan]
