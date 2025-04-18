# pylint: disable=[missing-module-docstring] # see class docstrings
import time
from random import choices
import serial
import numpy as np
from esibd.plugins import Device
from esibd.core import Parameter, parameterDict, PluginManager, Channel, PRINT, DeviceController, getTestMode

def providePlugins():
    """Indicates that this module provides plugins. Returns list of provided plugins."""
    return [MIPS]

class MIPS(Device):
    """Contains a list of voltages channels from one or multiple MIPS power supplies with 8 channels each.
    The voltages are monitored and a warning is given if the set potentials are not reached."""

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
        super().initGUI()
        self.controller = VoltageController(_parent=self, COMs = self.getCOMs()) # after all channels loaded

    def getDefaultSettings(self):
        defaultSettings = super().getDefaultSettings()
        defaultSettings[f'{self.name}/Interval'][Parameter.VALUE] = 1000 # overwrite default value
        defaultSettings[f'{self.name}/{self.MAXDATAPOINTS}'][Parameter.VALUE] = 1E5 # overwrite default value
        return defaultSettings

    def getCOMs(self): # get list of unique used COMs
        """List of COM ports."""
        return list(set([channel.com for channel in self.channels]))

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
        self.COMs   = COMs or ['COM1']
        self.ports  = [None]*len(self.COMs)
        self.maxID  = max([channel.id if channel.real else 0 for channel in self.device.getChannels()]) # used to query correct amount of monitors

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
        self.values = np.zeros([len(self.COMs), self.maxID+1])
        return super().initComplete()

    def closeCommunication(self):
        for i, port in enumerate(self.ports):
            if port is not None:
                with self.lock.acquire_timeout(1, timeoutMessage=f'Could not acquire lock before closing {port.port}.'):
                    port.close()
                    self.ports[i] = None
        super().closeCommunication()

    def applyValue(self, channel):
        self.MIPSWriteRead(channel.com, message=f'SDCB,{channel.id},{channel.value if (channel.enabled and self.device.isOn()) else 0}\r\n')

    def updateValues(self):
        # Overwriting to use values for multiple COM ports
        if getTestMode():
            self.fakeNumbers()
        else:
            for channel in self.device.getChannels():
                if channel.enabled and channel.real:
                    channel.monitor = self.values[self.COMs.index(channel.com)][channel.id-1]

    def toggleOn(self):
        for channel in self.device.getChannels():
            self.applyValueFromThread(channel)

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
                                    self.values[i][ID] = float(self.MIPSWriteRead(self.COMs[i], f'GDCBV,{ID+1}\r\n', lock_acquired=lock_acquired))
                                except ValueError as e:
                                    self.print(f'Error while reading voltage {e}')
                                    self.errorCount += 1
                                    self.values[i][ID] = np.nan
                    self.signalComm.updateValuesSignal.emit() # signal main thread to update GUI
            time.sleep(self.device.interval/1000)

    def MIPSWrite(self, COM, message):
        """MIPS specific serial write.

        :param COM: The COM port be used.
        :type COM: str
        :param message: The serial message to be send.
        :type message: str
        """
        self.serialWrite(self.ports[self.COMs.index(COM)], message)

    def MIPSRead(self, COM):
        """MIPS specific serial read.

        :param COM: The COM port be used.
        :type COM: str
        """
        # only call from thread! # make sure lock is acquired before and released after
        if not getTestMode() and self.initialized or self.initializing:
            return self.serialRead(self.ports[self.COMs.index(COM)], EOL='\r', strip='b\x06')

    def MIPSWriteRead(self, COM, message, lock_acquired=False):
        """MIPS specific serial write and read.

        :param COM: The COM port be used.
        :type COM: str
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
                    self.MIPSWrite(COM, message) # get channel name
                    response = self.MIPSRead(COM)
        return response
