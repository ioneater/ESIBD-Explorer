# pylint: disable=[missing-module-docstring] # only single class in module
import socket
from threading import Thread
import time
import numpy as np
from esibd.plugins import Device
from esibd.core import Parameter, parameterDict, PluginManager, Channel, PRINT, DeviceController, getTestMode

def providePlugins():
    return [Voltage]

class Voltage(Device):
    """Device that contains a list of voltages channels from an ISEG ECH244 power supply.
    The voltages are monitored and a warning is given if the set potentials are not reached.
    In case of any issues, first make sure ISEG ECH244 and all modules are turned on, and communicating.
    Use SNMP Control to quickly test this independent of this plugin."""
    documentation = None # use __doc__

    name = 'ISEG'
    version = '1.1'
    supportedVersion = '0.7'
    pluginType = PluginManager.TYPE.INPUTDEVICE
    unit = 'V'
    useMonitors = True
    iconFile = 'ISEG.png'

    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.channelType = VoltageChannel
        self.useOnOffLogic = True

    def initGUI(self):
        """:meta private:"""
        super().initGUI()
        self.controller = VoltageController(_parent=self, modules = self.getModules()) # after all channels loaded

    def getDefaultSettings(self):
        """:meta private:"""
        defaultSettings = super().getDefaultSettings()
        defaultSettings[f'{self.name}/IP']       = parameterDict(value='169.254.163.182', toolTip='IP address of ECH244',
                                                                widgetType=Parameter.TYPE.TEXT, attr='ip')
        defaultSettings[f'{self.name}/Port']     = parameterDict(value=10001, toolTip='SCPI port of ECH244',
                                                                widgetType=Parameter.TYPE.INT, attr='port')
        defaultSettings[f'{self.name}/Interval'][Parameter.VALUE] = 1000 # overwrite default value
        defaultSettings[f'{self.name}/{self.MAXDATAPOINTS}'][Parameter.VALUE] = 1E5 # overwrite default value
        return defaultSettings

    def getModules(self): # get list of used modules
        return set([channel.module for channel in self.channels])

    def closeCommunication(self):
        """:meta private:"""
        self.setOn(False)
        self.controller.voltageON(parallel=False)
        super().closeCommunication()

    def applyValues(self, apply=False):
        for channel in self.getChannels():
            channel.applyVoltage(apply) # only actually sets voltage if configured and value has changed

    def setOn(self, on=None):
        super().setOn(on=on)
        if self.initialized():
            self.updateValues(apply=True) # apply voltages before turning modules on or off
            self.controller.voltageON()
        elif self.isOn():
            self.initializeCommunication()

class VoltageChannel(Channel):

    MODULE    = 'Module'
    ID        = 'ID'

    def getDefaultChannel(self):
        channel = super().getDefaultChannel()
        channel[self.VALUE][Parameter.HEADER] = 'Voltage (V)' # overwrite to change header
        channel[self.MODULE  ] = parameterDict(value=0, widgetType= Parameter.TYPE.INT, advanced=True,
                                    header='Mod', _min=0, _max=99, attr='module')
        channel[self.ID      ] = parameterDict(value=0, widgetType= Parameter.TYPE.INT, advanced=True,
                                    header='ID', _min=0, _max=99, attr='id')
        return channel

    def setDisplayedParameters(self):
        super().setDisplayedParameters()
        self.displayedParameters.append(self.MODULE)
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
        self.getParameterByName(self.MODULE).getWidget().setVisible(self.real)
        self.getParameterByName(self.ID).getWidget().setVisible(self.real)
        super().realChanged()

class VoltageController(DeviceController):

    def __init__(self, _parent, modules):
        super().__init__(_parent=_parent)
        self.modules    = modules or [0]
        self.socket     = None
        self.maxID = max([channel.id if channel.real else 0 for channel in self.device.getChannels()]) # used to query correct amount of monitors
        self.voltages   = np.zeros([len(self.modules), self.maxID+1])

    def runInitialization(self):
        try:
            self.socket = socket.create_connection(address=(self.device.ip, int(self.device.port)), timeout=3)
            self.print(self.ISEGWriteRead(message='*IDN?\r\n'.encode('utf-8')))
            self.signalComm.initCompleteSignal.emit()
        except Exception as e: # pylint: disable=[broad-except] # socket does not throw more specific exception
            self.print(f'Could not establish SCPI connection to {self.device.ip} on port {int(self.device.port)}. Exception: {e}', PRINT.WARNING)
        finally:
            self.initializing = False

    def initComplete(self):
        super().initComplete()
        if self.device.isOn():
            self.device.updateValues(apply=True) # apply voltages before turning modules on or off
        self.voltageON()

    def applyVoltage(self, channel):
        if not getTestMode() and self.initialized:
            Thread(target=self.applyVoltageFromThread, args=(channel,), name=f'{self.device.name} applyVoltageFromThreadThread').start()

    def applyVoltageFromThread(self, channel):
        self.ISEGWriteRead(message=f':VOLT {channel.value if channel.enabled else 0},(#{channel.module}@{channel.id})\r\n'.encode('utf-8'))

    def updateValue(self):
        if getTestMode():
            self.fakeNumbers()
        else:
            for channel in self.device.getChannels():
                if channel.real:
                    channel.monitor = self.voltages[channel.module][channel.id]

    def voltageON(self, parallel=True): # this can run in main thread
        if not getTestMode() and self.initialized:
            if parallel:
                Thread(target=self.voltageONFromThread, name=f'{self.device.name} voltageONFromThreadThread').start()
            else:
                self.voltageONFromThread()
        elif getTestMode():
            self.fakeNumbers()

    def voltageONFromThread(self):
        for module in self.modules:
            self.ISEGWriteRead(message=f":VOLT {'ON' if self.device.isOn() else 'OFF'},(#{module}@0-{self.maxID})\r\n".encode('utf-8'))

    def fakeNumbers(self):
        for channel in self.device.getChannels():
            if channel.real:
                # fake values with noise and 10% channels with offset to simulate defect channel or short
                channel.monitor = (channel.value if self.device.isOn() and channel.enabled else 0) + 5 * (np.random.choice([0, 1], p=[0.98, 0.02])) + np.random.random() - 0.5

    def runAcquisition(self, acquiring):
        while acquiring():
            with self.lock.acquire_timeout(1) as lock_acquired:
                if lock_acquired:
                    if not getTestMode():
                        for module in self.modules:
                            res = self.ISEGWriteRead(message=f':MEAS:VOLT? (#{module}@0-{self.maxID+1})\r\n'.encode('utf-8'), lock_acquired=lock_acquired)
                            if res != '':
                                try:
                                    monitors = [float(x[:-1]) for x in res[:-4].split(',')] # res[:-4] to remove trailing '\r\n'
                                    # fill up to self.maxID to handle all modules the same independent of the number of channels.
                                    self.voltages[module] = np.hstack([monitors, np.zeros(self.maxID+1-len(monitors))])
                                except (ValueError, TypeError) as e:
                                    self.print(f'Parsing error: {e} for {res}.')
                    self.signalComm.updateValueSignal.emit() # signal main thread to update GUI
            time.sleep(self.device.interval/1000)

    def ISEGWrite(self, message):
        self.socket.sendall(message)

    def ISEGRead(self):
        # only call from thread! # make sure lock is acquired before and released after
        if not getTestMode() and self.initialized or self.initializing:
            return self.socket.recv(4096).decode("utf-8")

    def ISEGWriteRead(self, message, lock_acquired=False):
        response = ''
        if not getTestMode():
            with self.lock.acquire_timeout(1, timeoutMessage=f'Cannot acquire lock for message: {message}.', lock_acquired=lock_acquired) as lock_acquired:
                if lock_acquired:
                    self.ISEGWrite(message) # get channel name
                    response = self.ISEGRead()
        return response
