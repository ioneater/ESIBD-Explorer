# pylint: disable=[missing-module-docstring] # only single class in module
import socket
from threading import Thread
import time
from random import choices
import numpy as np
from PyQt6.QtCore import pyqtSignal
from esibd.plugins import Device
from esibd.core import Parameter, parameterDict, PluginManager, Channel, PRINT, DeviceController, getDarkMode, getTestMode

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
    pluginType = PluginManager.TYPE.INPUTDEVICE
    unit = 'V'

    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.channelType = VoltageChannel

    def initGUI(self):
        """:meta private:"""
        super().initGUI()
        self.controller = VoltageController(_parent=self, modules = self.getModules()) # after all channels loaded

    def finalizeInit(self, aboutFunc=None):
        """:meta private:"""
        self.onAction = self.pluginManager.DeviceManager.addStateAction(event=self.voltageON, toolTipFalse='ISEG on.', iconFalse=self.getIcon(),
                                                                  toolTipTrue='ISEG off.', iconTrue=self.makeIcon('ISEG_on.png'),
                                                                 before=self.pluginManager.DeviceManager.aboutAction)
        super().finalizeInit(aboutFunc)

    def getIcon(self):
        return self.makeIcon('ISEG_off_dark.png') if getDarkMode() else self.makeIcon('ISEG_off_light.png')

    def getDefaultSettings(self):
        """:meta private:"""
        ds = super().getDefaultSettings()
        ds[f'{self.name}/IP']       = parameterDict(value='169.254.163.182', toolTip='IP address of ECH244',
                                                                widgetType=Parameter.TYPE.TEXT, attr='ip')
        ds[f'{self.name}/Port']     = parameterDict(value=10001, toolTip='SCPI port of ECH244',
                                                                widgetType=Parameter.TYPE.INT, attr='port')
        ds[f'{self.name}/Interval'][Parameter.VALUE] = 1000 # overwrite default value
        ds[f'{self.name}/{self.MAXDATAPOINTS}'][Parameter.VALUE] = 1E5 # overwrite default value
        return ds

    def getModules(self): # get list of used modules
        return set([channel.module for channel in self.channels])

    def initializeCommunication(self):
        """:meta private:"""
        super().initializeCommunication()
        self.onAction.state = self.controller.ON
        
    def closeCommunication(self):
        """:meta private:"""
        self.controller.voltageON(on=False, parallel=False)
        super().closeCommunication()

    def applyValues(self, apply=False):
        for channel in self.getChannels():
            channel.applyVoltage(apply) # only actually sets voltage if configured and value has changed

    def voltageON(self):
        if self.initialized():
            self.updateValues(apply=True) # apply voltages before turning modules on or off
            self.controller.voltageON(self.onAction.state)
        elif self.onAction.state is True:
            self.controller.ON = self.onAction.state
            self.initializeCommunication()

    def updateTheme(self):
        """:meta private:"""
        super().updateTheme()
        self.onAction.iconFalse = self.getIcon()
        self.onAction.updateIcon(self.onAction.state)

class VoltageChannel(Channel):

    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.lastAppliedValue = None # keep track of last value to identify what has changed
        self.warningStyleSheet = f'background: rgb({255},{0},{0})'
        self.defaultStyleSheet = None # will be initialized when color is set

    MODULE    = 'Module'
    ID        = 'ID'

    def getDefaultChannel(self):
        channel = super().getDefaultChannel()
        channel[self.VALUE][Parameter.HEADER] = 'Voltage (V)' # overwrite to change header
        channel[self.MONITOR ] = parameterDict(value=0, widgetType=Parameter.TYPE.FLOAT, advanced=False,
                                    event=self.monitorChanged, indicator=True, attr='monitor')
        channel[self.MODULE  ] = parameterDict(value=0, widgetType= Parameter.TYPE.INT, advanced=True,
                                    header='Mod', _min=0, _max=99, attr='module')
        channel[self.ID      ] = parameterDict(value=0, widgetType= Parameter.TYPE.INT, advanced=True,
                                    header='ID', _min=0, _max=99, attr='id')
        return channel

    def setDisplayedParameters(self):
        super().setDisplayedParameters()
        self.insertDisplayedParameter(self.MONITOR, before=self.MIN)
        self.displayedParameters.append(self.MODULE)
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
        self.getParameterByName(self.MODULE).getWidget().setVisible(self.real)
        self.getParameterByName(self.ID).getWidget().setVisible(self.real)
        super().realChanged()

    def appendValue(self, lenT, nan=False):
        # super().appendValue() # overwrite to use monitors
        if nan:
            self.monitor=np.nan
        if self.enabled and self.real:
            self.values.add(self.monitor, lenT)
        else:
            self.values.add(self.value, lenT)

class VoltageController(DeviceController):

    class SignalCommunicate(DeviceController.SignalCommunicate):
        applyMonitorsSignal= pyqtSignal()

    def __init__(self, _parent, modules):
        super().__init__(_parent=_parent)
        self.modules    = modules or [0]
        self.signalComm.applyMonitorsSignal.connect(self.applyMonitors)
        self.IP = 'localhost'
        self.port = 0
        self.ON         = False
        self.s          = None
        self.maxID = max([channel.id if channel.real else 0 for channel in self.device.getChannels()]) # used to query correct amount of monitors
        self.voltages   = np.zeros([len(self.modules), self.maxID+1])

    def initializeCommunication(self):
        self.IP = self.device.ip
        self.port = int(self.device.port)
        super().initializeCommunication()

    def runInitialization(self):
        if getTestMode():
            time.sleep(2)
            self.signalComm.initCompleteSignal.emit()
            self.print('Faking monitor values for testing!', PRINT.WARNING)
        else:
            self.initializing = True
            try:
                self.s = socket.create_connection(address=(self.IP, self.port), timeout=3)
                self.print(self.ISEGWriteRead(message='*IDN?\r\n'.encode('utf-8')))
                self.signalComm.initCompleteSignal.emit()
            except Exception as e: # pylint: disable=[broad-except] # socket does not throw more specific exception
                self.print(f'Could not establish SCPI connection to {self.IP} on port {self.port}. Exception: {e}', PRINT.WARNING)
            finally:
                self.initializing = False

    def initComplete(self):
        super().initComplete()
        if self.ON:
            self.device.updateValues(apply=True) # apply voltages before turning modules on or off
        self.voltageON(self.ON)

    def applyVoltage(self, channel):
        if not getTestMode() and self.initialized:
            Thread(target=self.applyVoltageFromThread, args=(channel,), name=f'{self.device.name} applyVoltageFromThreadThread').start()

    def applyVoltageFromThread(self, channel):
        self.ISEGWriteRead(message=f':VOLT {channel.value if channel.enabled else 0},(#{channel.module}@{channel.id})\r\n'.encode('utf-8'))

    def applyMonitors(self):
        if getTestMode():
            self.fakeMonitors()
        else:
            for channel in self.device.getChannels():
                if channel.real:
                    channel.monitor = self.voltages[channel.module][channel.id]

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
        for module in self.modules:
            self.ISEGWriteRead(message=f":VOLT {'ON' if on else 'OFF'},(#{module}@0-{self.maxID})\r\n".encode('utf-8'))

    def fakeMonitors(self):
        for channel in self.device.getChannels():
            if channel.real:
                if self.device.controller.ON and channel.enabled:
                    # fake values with noise and 10% channels with offset to simulate defect channel or short
                    channel.monitor = channel.value + 5*choices([0, 1],[.98,.02])[0] + np.random.rand()
                else:
                    channel.monitor = 0             + 5*choices([0, 1],[.9,.1])[0] + np.random.rand()

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
                                    self.print(f'Monitor parsing error: {e} for {res}.')
                self.signalComm.applyMonitorsSignal.emit() # signal main thread to update GUI
            time.sleep(self.device.interval/1000)

    def ISEGWrite(self, message):
        self.s.sendall(message)

    def ISEGRead(self):
        # only call from thread! # make sure lock is acquired before and released after
        if not getTestMode() and self.initialized:
            return self.s.recv(4096).decode("utf-8")

    def ISEGWriteRead(self, message, lock_acquired=False):
        response = ''
        if not getTestMode():
            if lock_acquired: # already acquired -> safe to use
                self.ISEGWrite(message) # get channel name
                return self.ISEGRead()
            else:
                with self.lock.acquire_timeout(1, timeoutMessage=f'Cannot acquire lock for message: {message}.') as lock_acquired:
                    if lock_acquired:
                        self.ISEGWrite(message) # get channel name
                        response = self.ISEGRead()
        return response
