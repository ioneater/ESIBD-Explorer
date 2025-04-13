# pylint: disable=[missing-module-docstring] # see class docstrings
import time
import re
import serial
import numpy as np
from esibd.plugins import Device
from esibd.core import Parameter, PluginManager, Channel, parameterDict, DeviceController, PRINT, getTestMode, TimeoutLock

def providePlugins():
    """Indicates that this module provides plugins. Returns list of provided plugins."""
    return [Pressure]

class Pressure(Device):
    """Bundles pressure values form an Edwards TIC and Pfeiffer MaxiGauge into
    a consistent list of channels. This demonstrates handling of values on a logarithmic scale."""

    name = 'Pressure'
    version = '1.0'
    supportedVersion = '0.7'
    pluginType = PluginManager.TYPE.OUTPUTDEVICE
    unit = 'mbar'
    iconFile = 'pressure_light.png'
    iconFileDark = 'pressure_dark.png'

    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.channelType = PressureChannel
        self.controller = PressureController(_parent=self)
        self.logY = True

    def finalizeInit(self, aboutFunc=None):
        super().finalizeInit(aboutFunc)
        self.print('This plugin is deprecated and will be removed in the future. Use TIC and MAXIGAUGE instead.', flag=PRINT.WARNING)

    def getDefaultSettings(self):
        defaultSettings = super().getDefaultSettings()
        defaultSettings[f'{self.name}/Interval'][Parameter.VALUE] = 500 # overwrite default value
        defaultSettings[f'{self.name}/TIC COM'] = parameterDict(value='COM1', toolTip='COM port of Edwards TIC.', items=','.join([f'COM{x}' for x in range(1, 25)]),
                                          widgetType=Parameter.TYPE.COMBO, attr='TICCOM')
        defaultSettings[f'{self.name}/TPG366 COM'] = parameterDict(value='COM1', toolTip='COM port of Pfeiffer MaxiGauge.', items=','.join([f'COM{x}' for x in range(1, 25)]),
                                          widgetType=Parameter.TYPE.COMBO, attr='TPGCOM')
        defaultSettings[f'{self.name}/{self.MAXDATAPOINTS}'][Parameter.VALUE] = 1E6 # overwrite default value
        return defaultSettings

class PressureChannel(Channel):
    """UI for pressure with integrated functionality"""

    CONTROLLER = 'Controller'
    TIC = 'TIC'
    TPG = 'TPG'
    ID = 'ID'

    def getDefaultChannel(self):
        channel = super().getDefaultChannel()
        channel[self.VALUE][Parameter.HEADER] = 'P (mbar)'
        channel[self.CONTROLLER] = parameterDict(value=self.TIC, widgetType=Parameter.TYPE.COMBO, advanced=True,
                                        items=f'{self.TIC},{self.TPG}', attr='_controller', toolTip='Controller used for communication.')
        channel[self.ID] = parameterDict(value=1, widgetType=Parameter.TYPE.INTCOMBO, advanced=True,
                                        items='0, 1, 2, 3, 4, 5, 6', attr='id', toolTip='ID of channel on device.')
        return channel

    def setDisplayedParameters(self):
        super().setDisplayedParameters()
        self.displayedParameters.append(self.CONTROLLER)
        self.displayedParameters.append(self.ID)

class PressureController(DeviceController):

    def __init__(self, _parent):
        super().__init__(_parent=_parent)
        self.ticPort = None
        self.ticLock = TimeoutLock(_parent=self)
        self.tpgPort = None
        self.tpgLock = TimeoutLock(_parent=self)
        self.TICgaugeID = [913, 914, 915, 934, 935, 936]
        self.ticInitialized = False
        self.tpgInitialized = False

    def closeCommunication(self):
        if self.ticPort is not None:
            with self.ticLock.acquire_timeout(1, timeoutMessage='Could not acquire lock before closing ticPort.'):
                self.ticPort.close()
                self.ticPort = None
        if self.tpgPort is not None:
            with self.tpgLock.acquire_timeout(1, timeoutMessage='Could not acquire lock before closing tpgPort.'):
                self.tpgPort.close()
                self.tpgPort = None
        self.ticInitialized = False
        self.tpgInitialized = False
        super().closeCommunication()

    def runInitialization(self):
        try:
            self.ticPort=serial.Serial(
                f'{self.device.TICCOM}', baudrate=9600, bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE, xonxoff=True, timeout=2)
            TICStatus = self.TICWriteRead(message=902)
            self.print(f"TIC Status: {TICStatus}") # query status
            if TICStatus == '':
                raise ValueError('TIC did not return status.')
            self.ticInitialized = True
        except Exception as e: # pylint: disable=[broad-except]
            self.print(f'TIC Error while initializing: {e}', PRINT.ERROR)
        try:
            self.tpgPort=serial.Serial(
                f'{self.device.TPGCOM}', baudrate=9600, bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE, xonxoff=False, timeout=2)
            TPGStatus = self.TPGWriteRead(message='TID')
            self.print(f"MaxiGauge Status: {TPGStatus}") # gauge identification
            if TPGStatus == '':
                raise ValueError('TPG did not return status.')
            self.tpgInitialized = True
        except Exception as e: # pylint: disable=[broad-except]
            self.print(f'TPG Error while initializing: {e}', PRINT.ERROR)
        if self.ticInitialized or self.tpgInitialized:
            self.signalComm.initCompleteSignal.emit()
        self.initializing = False

    def runAcquisition(self, acquiring):
        while acquiring():
            with self.lock.acquire_timeout(1) as lock_acquired:
                if lock_acquired:
                    self.fakeNumbers() if getTestMode() else self.readNumbers()
                    self.signalComm.updateValuesSignal.emit()
            time.sleep(self.device.interval/1000)

    PRESSURE_READING_STATUS = {
      0: 'Measurement data okay',
      1: 'Underrange',
      2: 'Overrange',
      3: 'Sensor error',
      4: 'Sensor off',
      5: 'No sensor',
      6: 'Identification error'
    }

    def readNumbers(self):
        for i, channel in enumerate(self.device.getChannels()):
            if channel.enabled and channel.active and channel.real:
                if channel._controller == channel.TIC and self.ticInitialized:
                    msg = self.TICWriteRead(message=f'{self.TICgaugeID[channel.id]}', lock_acquired=True)
                    try:
                        self.values[i] = float(re.split(' |;', msg)[1])/100 # parse and convert to mbar = 0.01 Pa
                        # self.print(f'Read pressure for channel {c.name}', flag=PRINT.DEBUG)
                    except Exception as e:
                        self.print(f'Failed to parse pressure from {msg}: {e}', PRINT.ERROR)
                        self.errorCount += 1
                        self.values[i] = np.nan
                elif channel._controller == channel.TPG and self.tpgInitialized:
                    msg = self.TPGWriteRead(message=f'PR{channel.id}', lock_acquired=True)
                    try:
                        a, pressure = msg.split(',')
                        if a == '0':
                            self.values[i] = float(pressure) # set unit to mbar on device
                            # self.print(f'Read pressure for channel {channel.name}', flag=PRINT.DEBUG)
                        else:
                            self.print(f'Could not read pressure for {channel.name}: {self.PRESSURE_READING_STATUS[int(a)]}.', PRINT.WARNING)
                            self.values[i] = np.nan
                    except Exception as e:
                        self.print(f'Failed to parse pressure from {msg}: {e}', PRINT.ERROR)
                        self.errorCount += 1
                        self.values[i] = np.nan
                else:
                    self.values[i] = np.nan

    def fakeNumbers(self):
        for i, channel in enumerate(self.device.getChannels()):
            if channel.enabled and channel.active and channel.real:
                self.values[i] = self.rndPressure() if np.isnan(self.values[i]) else self.values[i]*np.random.uniform(.99, 1.01) # allow for small fluctuation

    def rndPressure(self):
        """Returns a random pressure."""
        exp = np.random.randint(-11, 3)
        significand = 0.9 * np.random.random() + 0.1
        return significand * 10**exp

    def TICWrite(self, _id):
        """TIC specific serial write.

        :param _id: The sensor id to be send.
        :type _id: str
        """
        self.serialWrite(self.ticPort, f'?V{_id}\r')

    def TICRead(self):
        """TIC specific serial read."""
        # Note: unlike most other devices TIC terminates messages with \r and not \r\n
        return self.serialRead(self.ticPort, EOL='\r')

    def TICWriteRead(self, message, lock_acquired=False):
        """TIC specific serial write and read.

        :param message: The serial message to be send.
        :type message: str
        :param lock_acquired: Indicates if the lock has already been acquired, defaults to False
        :type lock_acquired: bool, optional
        :return: The serial response received.
        :rtype: str
        """
        response = ''
        with self.ticLock.acquire_timeout(2, timeoutMessage=f'Cannot acquire lock for message: {message}', lock_acquired=lock_acquired) as lock_acquired:
            if lock_acquired:
                self.TICWrite(message)
                response = self.TICRead() # reads return value
        return response

    def TPGWrite(self, message):
        """TPG specific serial write.

        :param message: The serial message to be send.
        :type message: str
        """
        self.serialWrite(self.tpgPort, f'{message}\r', encoding='ascii')
        self.serialRead(self.tpgPort, encoding='ascii') # read acknowledgment

    def TPGRead(self):
        """TPG specific serial read.

        :return: The serial response received.
        :rtype: str
        """
        self.serialWrite(self.tpgPort, '\x05\r', encoding='ascii') # Enquiry prompts sending return from previously send mnemonic
        enq =  self.serialRead(self.tpgPort, encoding='ascii') # response
        self.serialRead(self.tpgPort, encoding='ascii') # followed by NAK
        return enq

    def TPGWriteRead(self, message, lock_acquired=False):
        """TPG specific serial write and read.

        :param message: The serial message to be send.
        :type message: str
        :param lock_acquired: Indicates if the lock has already been acquired, defaults to False
        :type lock_acquired: bool, optional
        :return: The serial response received.
        :rtype: str
        """
        response = ''
        with self.tpgLock.acquire_timeout(2, timeoutMessage=f'Cannot acquire lock for message: {message}', lock_acquired=lock_acquired) as lock_acquired:
            if lock_acquired:
                self.TPGWrite(message)
                response = self.TPGRead() # reads return value
        return response
