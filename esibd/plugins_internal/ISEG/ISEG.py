# pylint: disable=[missing-module-docstring] # see class docstrings
import socket
import time
import numpy as np
from esibd.plugins import Device
from esibd.core import Parameter, parameterDict, PluginManager, Channel, PRINT, DeviceController, getTestMode

def providePlugins():
    """Indicates that this module provides plugins. Returns list of provided plugins."""
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
        super().initGUI()
        self.controller = VoltageController(_parent=self, modules = self.getModules()) # after all channels loaded

    def getDefaultSettings(self):
        defaultSettings = super().getDefaultSettings()
        defaultSettings[f'{self.name}/IP']       = parameterDict(value='169.254.163.182', toolTip='IP address of ECH244',
                                                                widgetType=Parameter.TYPE.TEXT, attr='ip')
        defaultSettings[f'{self.name}/Port']     = parameterDict(value=10001, toolTip='SCPI port of ECH244',
                                                                widgetType=Parameter.TYPE.INT, attr='port')
        defaultSettings[f'{self.name}/Interval'][Parameter.VALUE] = 1000 # overwrite default value
        defaultSettings[f'{self.name}/{self.MAXDATAPOINTS}'][Parameter.VALUE] = 1E5 # overwrite default value
        return defaultSettings

    def getModules(self):
        """Get list of used modules."""
        return set([channel.module for channel in self.channels])

    def closeCommunication(self):
        self.setOn(False)
        self.controller.toggleOnFromThread(parallel=False)
        super().closeCommunication()

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
        self.values   = np.zeros([len(self.modules), self.maxID+1])

    def runInitialization(self):
        try:
            self.socket = socket.create_connection(address=(self.device.ip, int(self.device.port)), timeout=3)
            self.print(self.ISEGWriteRead(message='*IDN?\r\n'.encode('utf-8')))
            self.signalComm.initCompleteSignal.emit()
        except Exception as e: # pylint: disable=[broad-except] # socket does not throw more specific exception
            self.print(f'Could not establish SCPI connection to {self.device.ip} on port {int(self.device.port)}. Exception: {e}', PRINT.WARNING)
        finally:
            self.initializing = False

    def applyValue(self, channel):
        self.ISEGWriteRead(message=f':VOLT {channel.value if channel.enabled else 0},(#{channel.module}@{channel.id})\r\n'.encode('utf-8'))

    def updateValues(self):
        # Overwriting to use values for multiple modules
        if getTestMode():
            self.fakeNumbers()
        else:
            for channel in self.device.getChannels():
                if channel.enabled and channel.real:
                    channel.monitor = self.values[channel.module][channel.id]

    def toggleOn(self):
        for module in self.modules:
            self.ISEGWriteRead(message=f":VOLT {'ON' if self.device.isOn() else 'OFF'},(#{module}@0-{self.maxID})\r\n".encode('utf-8'))

    def fakeNumbers(self):
        for channel in self.device.getChannels():
            if channel.enabled and channel.real:
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
                                    self.values[module] = np.hstack([monitors, np.zeros(self.maxID+1-len(monitors))])
                                except (ValueError, TypeError) as e:
                                    self.print(f'Parsing error: {e} for {res}.')
                                    self.errorCount += 1
                    self.signalComm.updateValuesSignal.emit() # signal main thread to update GUI
            time.sleep(self.device.interval/1000)

    def ISEGWriteRead(self, message, lock_acquired=False):
        """ISEG specific serial write and read.

        :param message: The serial message to be send.
        :type message: str
        :param lock_acquired: Indicates if the lock has already been acquired, defaults to False
        :type lock_acquired: bool, optional
        :return: The serial response received.
        :rtype: str
        """
        response = ''
        if not getTestMode():
            with self.lock.acquire_timeout(1, timeoutMessage=f'Cannot acquire lock for message: {message}.', lock_acquired=lock_acquired) as lock_acquired:
                if lock_acquired:
                    self.socket.sendall(message) # get channel name
                    response = self.socket.recv(4096).decode("utf-8")
        return response
