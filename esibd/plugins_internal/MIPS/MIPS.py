# pylint: disable=[missing-module-docstring] # see class docstrings
import serial
from threading import Thread
import time
from random import choices
import numpy as np
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
    supportedVersion = '0.7'
    pluginType = PluginManager.TYPE.INPUTDEVICE
    unit = 'V'
    useMonitors = True
    iconFile = 'mips.png'

    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.useOnOffLogic = True
        self.channelType = VoltageChannel

    def initGUI(self):
        """:meta private:"""
        super().initGUI()
        self.controller = VoltageController(_parent=self, COMs = self.getCOMs()) # after all channels loaded

    def getDefaultSettings(self):
        """:meta private:"""
        defaultSettings = super().getDefaultSettings()
        defaultSettings[f'{self.name}/Interval'][Parameter.VALUE] = 1000 # overwrite default value
        defaultSettings[f'{self.name}/{self.MAXDATAPOINTS}'][Parameter.VALUE] = 1E5 # overwrite default value
        return defaultSettings

    def getCOMs(self): # get list of unique used COMs
        return list(set([channel.com for channel in self.channels]))

    def closeCommunication(self):
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

    COM        = 'COM'
    ID        = 'ID'

    def getDefaultChannel(self):
        channel = super().getDefaultChannel()
        channel[self.VALUE][Parameter.HEADER] = 'Voltage (V)' # overwrite to change header
        channel[self.COM] = parameterDict(value='COM1', toolTip='COM port of MIPS.', items=','.join([f'COM{x}' for x in range(1, 25)]),
                                          widgetType=Parameter.TYPE.COMBO, advanced=True, attr='com')
        channel[self.ID      ] = parameterDict(value=0, widgetType= Parameter.TYPE.INT, advanced=True,
                                    header='ID', _min=1, _max=8, attr='id')
        return channel

    def setDisplayedParameters(self):
        super().setDisplayedParameters()
        self.displayedParameters.append(self.COM)
        self.displayedParameters.append(self.ID)

    def applyVoltage(self, apply): # this actually sets the voltage on the power supply!
        if self.real and ((self.value != self.lastAppliedValue) or apply):
            self.device.controller.applyVoltage(self)
            self.lastAppliedValue = self.value

    def monitorChanged(self):
        # overwriting super().monitorChanged() to set 0 as expected value when device is off
        self.updateWarningState(self.enabled and self.device.controller.acquiring
                                and ((self.device.isOn() and abs(self.monitor - self.value) > 1)
                                or (not self.device.isOn() and abs(self.monitor - 0) > 1)))

    def realChanged(self):
        self.getParameterByName(self.COM).getWidget().setVisible(self.real)
        self.getParameterByName(self.ID).getWidget().setVisible(self.real)
        super().realChanged()

class VoltageController(DeviceController):

    def __init__(self, _parent, COMs):
        super().__init__(_parent=_parent)
        self.COMs       = COMs or ['COM1']
        self.ports      = [None]*len(self.COMs)
        self.maxID = max([channel.id if channel.real else 0 for channel in self.device.getChannels()]) # used to query correct amount of monitors
        self.voltages   = np.zeros([len(self.COMs), self.maxID+1])

    def runInitialization(self):
        try:
            self.ports = [serial.Serial(baudrate = 9600, port = COM, parity = serial.PARITY_NONE, stopbits = serial.STOPBITS_ONE,
                                        bytesize = serial.EIGHTBITS, timeout=2) for COM in self.COMs]
            result = self.MIPSWriteRead(self.COMs[0], 'GDCBV,1\r\n')
            if result != '':
                self.signalComm.initCompleteSignal.emit()
            else:
                self.closeCommunication()
                raise ValueError('Could not read values. Make sure MIPS is turned on.')
        except (ValueError, serial.serialutil.SerialException) as e: # pylint: disable=[broad-except] # socket does not throw more specific exception
            self.print(f'Could not establish Serial connection to a MIPS at {self.COMs}. Exception: {e}', PRINT.WARNING)
        finally:
            self.initializing = False

    def initComplete(self):
        super().initComplete()
        if self.device.isOn():
            self.device.updateValues(apply=True) # apply voltages before turning on or off
        self.voltageON()

    def closeCommunication(self):
        for i, port in enumerate(self.ports):
            if port is not None:
                with self.lock.acquire_timeout(1, timeoutMessage=f'Could not acquire lock before closing {port.port}.'):
                    port.close()
                    self.ports[i] = None
        super().closeCommunication()

    def applyVoltage(self, channel):
        if not getTestMode() and self.initialized:
            Thread(target=self.applyVoltageFromThread, args=(channel,), name=f'{self.device.name} applyVoltageFromThreadThread').start()

    def applyVoltageFromThread(self, channel):
        if not getTestMode() and self.initialized:
            self.MIPSWriteRead(channel.com, message=f'SDCB,{channel.id},{channel.value if (channel.enabled and self.device.isOn()) else 0}\r\n')

    def updateValue(self):
        if getTestMode():
            self.fakeNumbers()
        else:
            for channel in self.device.getChannels():
                if channel.enabled and channel.real:
                    channel.monitor = self.voltages[self.COMs.index(channel.com)][channel.id-1]

    def voltageON(self, parallel=True): # this can run in main thread
        if not getTestMode() and self.initialized:
            if parallel:
                Thread(target=self.voltageONFromThread, name=f'{self.device.name} voltageONFromThreadThread').start()
            else:
                self.voltageONFromThread() # use to make sure this is completed before closing connection
        elif getTestMode():
            self.fakeNumbers()

    def voltageONFromThread(self):
        for channel in self.device.getChannels():
            self.applyVoltageFromThread(channel)

    def fakeNumbers(self):
        for channel in self.device.getChannels():
            if channel.enabled and channel.real:
                if self.device.isOn() and channel.enabled:
                    # fake values with noise and 10% channels with offset to simulate defect channel or short
                    channel.monitor = channel.value + 5*choices([0, 1],[.98,.02])[0] + np.random.rand()
                else:
                    channel.monitor = 0             + 5*choices([0, 1],[.9,.1])[0] + np.random.rand()

    def runAcquisition(self, acquiring):
        while acquiring():
            pass
            with self.lock.acquire_timeout(1) as lock_acquired:
                if lock_acquired:
                    if not getTestMode():
                        for i in range(len(self.COMs)):
                            for ID in range(8):
                                try:
                                    self.voltages[i][ID] = float(self.MIPSWriteRead(self.COMs[i], f'GDCBV,{ID+1}\r\n', lock_acquired=lock_acquired))
                                except ValueError as e:
                                    self.print(f'Error while reading voltage {e}')
                                    self.errorCount += 1
                                    self.voltages[i][ID] = np.nan
                    self.signalComm.updateValueSignal.emit() # signal main thread to update GUI
            time.sleep(self.device.interval/1000)

    def MIPSWrite(self, COM, message):
        self.serialWrite(self.ports[self.COMs.index(COM)], message)

    def MIPSRead(self, COM):
        # only call from thread! # make sure lock is acquired before and released after
        if not getTestMode() and self.initialized or self.initializing:
            return self.serialRead(self.ports[self.COMs.index(COM)], EOL='\r', strip='b\x06')

    def MIPSWriteRead(self, COM, message, lock_acquired=False):
        response = ''
        if not getTestMode():
            with self.lock.acquire_timeout(1, timeoutMessage=f'Cannot acquire lock for message: {message}.', lock_acquired=lock_acquired) as lock_acquired:
                if lock_acquired:
                    self.MIPSWrite(COM, message) # get channel name
                    response = self.MIPSRead(COM)
        return response
