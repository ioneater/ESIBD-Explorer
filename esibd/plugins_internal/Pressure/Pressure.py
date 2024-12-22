# pylint: disable=[missing-module-docstring] # only single class in module
import time
import re
import serial
import numpy as np
from esibd.plugins import Device
from esibd.core import Parameter, PluginManager, Channel, parameterDict, DeviceController, getDarkMode, PRINT, getTestMode, TimeoutLock

def providePlugins():
    return [Pressure]

class Pressure(Device):
    """Device that bundles pressure values form an Edwards TIC and Pfeiffer MaxiGauge into
    a consistent list of channels. This demonstrates handling of values on a logarithmic scale."""

    documentation = None # use __doc__
    name = 'Pressure'
    version = '1.0'
    supportedVersion = '0.6'
    pluginType = PluginManager.TYPE.OUTPUTDEVICE
    unit = 'mbar'

    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.channelType = PressureChannel
        self.controller = PressureController(device=self)
        self.logY = True

    def getIcon(self):
        return self.makeIcon('pressure_dark.png') if getDarkMode() else self.makeIcon('pressure_light.png')

    def getDefaultSettings(self):
        ds = super().getDefaultSettings()
        ds[f'{self.name}/Interval'][Parameter.VALUE] = 500 # overwrite default value
        ds[f'{self.name}/TIC COM'] = parameterDict(value='COM1', toolTip='COM port of Edwards TIC.', items=','.join([f'COM{x}' for x in range(1, 25)]),
                                          widgetType=Parameter.TYPE.COMBO, attr='TICCOM')
        ds[f'{self.name}/TPG366 COM'] = parameterDict(value='COM1', toolTip='COM port of Pfeiffer MaxiGauge.', items=','.join([f'COM{x}' for x in range(1, 25)]),
                                          widgetType=Parameter.TYPE.COMBO, attr='TPGCOM')
        ds[f'{self.name}/{self.MAXDATAPOINTS}'][Parameter.VALUE] = 1E6 # overwrite default value
        return ds

    def getInitializedChannels(self):
        return [channel for channel in self.channels if (channel.enabled and
                                             ((channel.controller == channel.TIC and self.controller.ticPort is not None)
                                              or (channel.controller == channel.TPG and self.controller.tpgPort is not None)
                                              or self.getTestMode())) or not channel.active]

    def initializeCommunication(self):
        super().initializeCommunication()
        self.controller.initializeCommunication()

    def startAcquisition(self):
        super().startAcquisition()
        self.controller.startAcquisition()

    def stopAcquisition(self):
        super().stopAcquisition()
        self.controller.stopAcquisition()

    def initialized(self):
        return self.controller.initialized

    def closeCommunication(self):
        self.controller.closeCommunication()
        super().closeCommunication()

class PressureChannel(Channel):
    """UI for pressure with integrated functionality"""

    CONTROLLER = 'Controller'
    TIC = 'TIC'
    TPG = 'TPG'
    ID = 'ID'

    def getDefaultChannel(self):
        """Gets default settings and values."""
        channel = super().getDefaultChannel()
        channel[self.VALUE][Parameter.HEADER] = 'P (mbar)' # overwrite existing parameter to change header
        channel[self.VALUE][Parameter.WIDGETTYPE] = Parameter.TYPE.EXP # overwrite existing parameter to change to use exponent notation
        channel[self.CONTROLLER] = parameterDict(value=self.TIC, widgetType=Parameter.TYPE.COMBO, advanced=True,
                                        items=f'{self.TIC},{self.TPG}', attr='controller', toolTip='Controller used for communication.')
        channel[self.ID] = parameterDict(value=1, widgetType=Parameter.TYPE.INTCOMBO, advanced=True,
                                        items='0, 1, 2, 3, 4, 5, 6', attr='id', toolTip='ID of channel on device.')
        return channel

    def setDisplayedParameters(self):
        super().setDisplayedParameters()
        self.displayedParameters.append(self.CONTROLLER)
        self.displayedParameters.append(self.ID)

    def enabledChanged(self):
        """Handle changes while acquisition is running. All other changes will be handled when acquisition starts."""
        super().enabledChanged()
        if self.device.liveDisplayActive() and self.device.pluginManager.DeviceManager.recording:
            self.device.initializeCommunication()

class PressureController(DeviceController):
    # need to inherit from QObject to allow use of signals
    """Implements serial communication with RBD 9103.
    While this is kept as general as possible, some access to the management and UI parts are required for proper integration."""

    def __init__(self, device):
        super().__init__(_parent=device)
        self.device = device
        self.ticPort = None
        self.ticLock = TimeoutLock()
        self.tpgPort = None
        self.tpgLock = TimeoutLock()
        self.TICgaugeID = [913, 914, 915, 934, 935, 936]
        self.ticInitialized = False
        self.tpgInitialized = False
        self.pressures = []
        self.initPressures()

    def closeCommunication(self):
        if self.ticPort is not None:
            with self.ticLock.acquire_timeout(2) as acquired:
                if acquired:
                    self.ticPort.close()
                    self.ticPort = None
                else:
                    self.print('Cannot acquire lock to close ticPort.', PRINT.WARNING)
        if self.tpgPort is not None:
            with self.tpgLock.acquire_timeout(2) as acquired:
                if acquired:
                    self.tpgPort.close()
                    self.tpgPort = None
                else:
                    self.print('Cannot acquire lock to close tpgPort.', PRINT.WARNING)
        self.ticInitialized = False
        self.tpgInitialized = False
        super().closeCommunication()

    def runInitialization(self):
        """Initializes serial ports in parallel thread"""
        if getTestMode():
            self.signalComm.initCompleteSignal.emit()
        else:
            self.initializing = True
            try:
                self.ticPort=serial.Serial(
                    f'{self.device.TICCOM}',
                    baudrate=9600,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    xonxoff=True,
                    timeout=2)
                TICStatus = self.TICWriteRead(message=902)
                self.print(f"TIC Status: {TICStatus}") # query status
                if TICStatus == '':
                    raise ValueError('TIC did not return status.')
                self.ticInitialized = True
            except Exception as e: # pylint: disable=[broad-except]
                self.print(f'TIC Error while initializing: {e}', PRINT.ERROR)
            try:
                self.tpgPort=serial.Serial(
                    f'{self.device.TPGCOM}',
                    baudrate=9600,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    xonxoff=False,
                    timeout=2)
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

    def initComplete(self):
        self.initPressures()
        super().initComplete()
        if getTestMode():
            self.print('Faking values for testing!', PRINT.WARNING)

    def initPressures(self):
        self.pressures = [np.nan]*len(self.device.getChannels())

    def startAcquisition(self):
        # only run if init successful, or in test mode. if channel is not active it will calculate value independently
        if (self.ticPort is not None and self.tpgPort is not None) or getTestMode():
            super().startAcquisition()

    def runAcquisition(self, acquiring):
        # runs in parallel thread
        while acquiring():
            with self.lock.acquire_timeout(2):
                if getTestMode():
                    self.fakeNumbers()
                else:
                    self.readNumbers()
                self.signalComm.updateValueSignal.emit()
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
        """read pressures for all channels"""
        for i, channel in enumerate(self.device.getChannels()):
            if channel.enabled and channel.active:
                if channel.controller == channel.TIC and self.ticInitialized:
                    msg = self.TICWriteRead(message=f'{self.TICgaugeID[channel.id]}')
                    try:
                        self.pressures[i] = float(re.split(' |;', msg)[1])/100 # parse and convert to mbar = 0.01 Pa
                        # self.print(f'Read pressure for channel {c.name}', flag=PRINT.DEBUG)
                    except Exception as e:
                        self.print(f'Failed to parse pressure from {msg}: {e}', PRINT.ERROR)
                        self.pressures[i] = np.nan
                elif channel.controller == channel.TPG and self.tpgInitialized:
                    msg = self.TPGWriteRead(message=f'PR{channel.id}')
                    try:
                        a, pressure = msg.split(',')
                        if a == '0':
                            self.pressures[i] = float(pressure) # set unit to mbar on device
                            # self.print(f'Read pressure for channel {channel.name}', flag=PRINT.DEBUG)
                        else:
                            self.print(f'Could not read pressure for {channel.name}: {self.PRESSURE_READING_STATUS[int(a)]}.', PRINT.WARNING)
                            self.pressures[i] = np.nan
                    except Exception as e:
                        self.print(f'Failed to parse pressure from {msg}: {e}', PRINT.ERROR)
                        self.pressures[i] = np.nan
                else:
                    self.pressures[i] = np.nan

    def fakeNumbers(self):
        for i, pressure in enumerate(self.pressures):
            self.pressures[i] = self.rndPressure() if np.isnan(pressure) else pressure*np.random.uniform(.99, 1.01) # allow for small fluctuation

    def rndPressure(self):
        exp = np.random.randint(-11, 3)
        significand = 0.9 * np.random.random() + 0.1
        return significand * 10**exp

    def updateValue(self):
        for channel, pressure in zip(self.device.getChannels(), self.pressures):
            channel.value = pressure

    def TICWrite(self, _id):
        self.serialWrite(self.ticPort, f'?V{_id}\r')

    def TICRead(self):
        # Note: unlike most other devices TIC terminates messages with \r and not \r\n
        return self.serialRead(self.ticPort, EOL='\r')

    def TICWriteRead(self, message):
        """Allows to write and read while using lock with timeout."""
        response = ''
        with self.ticLock.acquire_timeout(2) as acquired:
            if acquired:
                self.TICWrite(message)
                response = self.TICRead() # reads return value
            else:
                self.print(f'Cannot acquire lock for TIC communication. Query: {message}', PRINT.WARNING)
        return response

    def TPGWrite(self, message):
        # return
        #self.tpgPort.write(bytes(f'{message}\r','ascii'))
        #ack = self.tpgPort.readline()
        #self.print(f"ACK: {ack}") # b'\x06\r\n' means ACK or acknowledgment b'\x15\r\n' means NAK or not acknowledgment
        self.serialWrite(self.tpgPort, f'{message}\r', encoding='ascii')
        self.serialRead(self.tpgPort, encoding='ascii') # read acknowledgment

    def TPGRead(self):
        # return 'none'
        #self.tpgPort.write(bytes('\x05\r','ascii')) # \x05 is equivalent to ENQ or enquiry
        #enq = self.tpgPort.readlines() # response followed by NAK
        #self.print(f"enq: {enq}") # read acknowledgment
        #return enq[0].decode('ascii').rstrip()
        self.serialWrite(self.tpgPort, '\x05\r', encoding='ascii') # Enquiry prompts sending return from previously send mnemonic
        enq =  self.serialRead(self.tpgPort, encoding='ascii') # response
        self.serialRead(self.tpgPort, encoding='ascii') # followed by NAK
        return enq

    def TPGWriteRead(self, message):
        """Allows to write and read while using lock with timeout."""
        response = ''
        with self.tpgLock.acquire_timeout(2) as acquired:
            if acquired:
                self.TPGWrite(message)
                response = self.TPGRead() # reads return value
            else:
                self.print(f'Cannot acquire lock for Maxigauge communication. Query: {message}', PRINT.WARNING)
        return response
