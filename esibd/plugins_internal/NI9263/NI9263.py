# pylint: disable=[missing-module-docstring] # only single class in module
import time
from threading import Thread
import nidaqmx
from esibd.plugins import Device
from esibd.core import Parameter, parameterDict, PluginManager, Channel, PRINT, DeviceController, getTestMode

def providePlugins():
    return [NI9263]

class NI9263(Device):
    """Device that contains a list of voltages channels from one or multiple NI9263 power supplies with 4 analog outputs each.
    There are no monitors to verify the applied voltages."""
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
        self.controller = VoltageController(_parent=self) # after all channels loaded

    def finalizeInit(self, aboutFunc=None):
        """:meta private:"""
        self.onAction = self.pluginManager.DeviceManager.addStateAction(event=self.voltageON, toolTipFalse='NI9263 on.', iconFalse=self.makeIcon('NI9263_off.png'),
                                                                  toolTipTrue='NI9263 off.', iconTrue=self.getIcon(),
                                                                 before=self.pluginManager.DeviceManager.aboutAction)
        super().finalizeInit(aboutFunc)

    def getIcon(self):
        return self.makeIcon('NI9263.png')
        
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

    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.lastAppliedValue = None # keep track of last value to identify what has changed
        self.warningStyleSheet = f'background: rgb({255},{0},{0})'
        self.defaultStyleSheet = None # will be initialized when color is set

    ADDRESS = 'Address'

    def getDefaultChannel(self):
        channel = super().getDefaultChannel()
        channel[self.VALUE][Parameter.HEADER] = 'Voltage (V)' # overwrite to change header
        channel[self.MIN ][Parameter.VALUE] = 0
        channel[self.MAX ][Parameter.VALUE] = 1 # start with safe limits
        channel[self.ADDRESS] = parameterDict(value='cDAQ1Mod1/ao0', toolTip='Address of analog output',
                                          widgetType=Parameter.TYPE.TEXT, advanced=True, attr='address')
        return channel

    def setDisplayedParameters(self):
        super().setDisplayedParameters()
        self.displayedParameters.append(self.ADDRESS)

    def applyVoltage(self, apply): # this actually sets the voltage on the power supply!
        if self.real and ((self.value != self.lastAppliedValue) or apply):
            self.device.controller.applyVoltage(self)
            self.lastAppliedValue = self.value

    def realChanged(self):
        self.getParameterByName(self.ADDRESS).getWidget().setVisible(self.real)
        super().realChanged()

class VoltageController(DeviceController): 

    def __init__(self, _parent):
        super().__init__(_parent=_parent)
        self.ON         = False

    def runInitialization(self):
        if getTestMode():
            time.sleep(2)
            self.signalComm.initCompleteSignal.emit()
        else:
            self.initializing = True
            try:
                with nidaqmx.Task() as task:
                    task.ao_channels # will raise exception if connection failed
                self.signalComm.initCompleteSignal.emit()
            except Exception as e: # pylint: disable=[broad-except] # socket does not throw more specific exception
                self.print(f'Could not establish connection at {self.device.channels[0].address}. Exception: {e}', PRINT.WARNING)
            finally:
                self.initializing = False

    def initComplete(self):
        super().initComplete()
        if self.ON:
            self.device.updateValues(apply=True) # apply voltages before turning on or off
        self.voltageON(self.ON)
                    
    def applyVoltage(self, channel):
        if not getTestMode() and self.initialized:
            Thread(target=self.applyVoltageFromThread, args=(channel,), name=f'{self.device.name} applyVoltageFromThreadThread').start()

    def applyVoltageFromThread(self, channel):
        with self.lock.acquire_timeout(1, timeoutMessage=f'Cannot acquire lock to set voltage of {channel.name}.') as lock_acquired:
            if lock_acquired:
                with nidaqmx.Task() as task:
                    task.ao_channels.add_ao_voltage_chan(channel.address)
                    task.write(channel.value if (channel.enabled and self.ON) else 0)

    def voltageON(self, on=False, parallel=True): # this can run in main thread
        self.ON = on
        if not getTestMode() and self.initialized:
            if parallel:
                Thread(target=self.voltageONFromThread, args=(on,), name=f'{self.device.name} voltageONFromThreadThread').start()
            else:
                self.voltageONFromThread(on=on)

    def voltageONFromThread(self, on=False):
        for channel in self.device.channels:
            if channel.real:
                self.applyVoltageFromThread(channel)

    def runAcquisition(self, acquiring):
        pass # nothing to acquire, no read backs 