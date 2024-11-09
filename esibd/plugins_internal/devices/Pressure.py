# pylint: disable=[missing-module-docstring] # only single class in module
import time
import re
import serial
import numpy as np
from esibd.plugins import Device, LiveDisplay, StaticDisplay
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

    class LiveDisplay(LiveDisplay):

        def initGUI(self):
            super().initGUI()
            self.livePlotWidget.setLogMode(False, True)

    class StaticDisplay(StaticDisplay):

        def initGUI(self):
            super().initGUI()
            self.staticPlotWidget.setLogMode(False, True)

    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.channelType = PressureChannel
        self.controller = PressureController(device=self)

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
        return [c for c in self.channels if (c.enabled and
                                             ((c.controller == c.TIC and self.controller.TICport is not None)
                                              or (c.controller == c.TPG and self.controller.TPGport is not None)
                                              or self.getTestMode())) or not c.active]

    def init(self):
        super().init()
        self.controller.init()

    def startAcquisition(self):
        self.controller.startAcquisition()

    def stopAcquisition(self):
        super().stopAcquisition()
        self.controller.stopAcquisition()

    def stop(self):
        super().stop()
        self.controller.close()

    def initialized(self):
        return self.controller.initialized

    def close(self):
        self.controller.close()
        super().close()

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
        # channel[self.VALUE][Parameter.INDICATOR] = False # overwrite existing parameter to change header
        channel[self.VALUE][Parameter.WIDGETTYPE] = Parameter.TYPE.EXP # overwrite existing parameter to change to use exponent notation
        channel[self.CONTROLLER] = parameterDict(value=self.TIC, widgetType=Parameter.TYPE.COMBO, advanced=True,
                                        items=f'{self.TIC},{self.TPG}', attr='controller')
        channel[self.ID] = parameterDict(value=1, widgetType=Parameter.TYPE.INTCOMBO, advanced=True,
                                        items='0, 1, 2, 3, 4, 5, 6', attr='id')
        return channel

    def setDisplayedParameters(self):
        super().setDisplayedParameters()
        self.insertDisplayedParameter(self.CONTROLLER, before=self.COLOR)
        self.insertDisplayedParameter(self.ID, before=self.COLOR)

    def enabledChanged(self): # overwrite parent method
        """Handle changes while acquisition is running. All other changes will be handled when acquisition starts."""
        if self.device.liveDisplayActive() and self.device.pluginManager.DeviceManager.recording:
            self.device.init()

class PressureController(DeviceController):
    # need to inherit from QObject to allow use of signals
    """Implements serial communication with RBD 9103.
    While this is kept as general as possible, some access to the management and UI parts are required for proper integration."""

    def __init__(self, device):
        super().__init__(parent=device)
        self.device = device
        self.TICport = None
        self.TIClock = TimeoutLock()
        self.TPGport = None
        self.TPGlock = TimeoutLock()
        self.lock = None # avoid using by accident
        self.TICgaugeID = [913, 914, 915, 934, 935, 936]
        self.TICinitialized = False
        self.TPGinitialized = False
        self.pressures = []

    def stop(self):
        self.device.stop()

    def close(self):
        super().close()
        if self.TICport is not None:
            with self.TIClock.acquire_timeout(2) as acquired:
                if acquired:
                    self.TICport.close()
                    self.TICport = None
                else:
                    self.print('Cannot acquire lock to close TICport.', PRINT.WARNING)
        if self.TPGport is not None:
            with self.TPGlock.acquire_timeout(2) as acquired:
                if acquired:
                    self.TPGport.close()
                    self.TPGport = None
                else:
                    self.print('Cannot acquire lock to close TPGport.', PRINT.WARNING)
        self.initialized = False
        self.TICinitialized = False
        self.TPGinitialized = False

    def stopAcquisition(self):
        if super().stopAcquisition():
            if self.device.pluginManager.closing:
                time.sleep(.1)

    def runInitialization(self):
        """Initializes serial ports in paralel thread"""
        if getTestMode():
            self.signalComm.initCompleteSignal.emit()
        else:
            self.initializing = True
            try:
                self.TICport=serial.Serial(
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
                self.TICinitialized = True
            except Exception as e: # pylint: disable=[broad-except]
                self.print(f'TIC Error while initializing: {e}', PRINT.ERROR)
            try:
                self.TPGport=serial.Serial(
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
                self.TPGinitialized = True
            except Exception as e: # pylint: disable=[broad-except]
                self.print(f'TPG Error while initializing: {e}', PRINT.ERROR)
            if self.TICinitialized or self.TPGinitialized:
                self.signalComm.initCompleteSignal.emit()
            self.initializing = False

    def initComplete(self):
        self.pressures = [0]*len(self.device.channels)
        super().initComplete()
        if getTestMode():
            self.print('Faking values for testing!', PRINT.WARNING)

    def startAcquisition(self):
        # only run if init succesful, or in test mode. if channel is not active it will calculate value independently
        if (self.TICport is not None and self.TPGport is not None) or getTestMode():
            super().startAcquisition()

    def runAcquisition(self, acquiring):
        # runs in parallel thread
        while acquiring():
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
        for i, c in enumerate(self.device.channels):
            if c.enabled and c.active:
                if c.controller == c.TIC and self.TICinitialized:
                    msg = self.TICWriteRead(message=f'{self.TICgaugeID[c.id]}')
                    try:
                        self.pressures[i] = float(re.split(' |;', msg)[1])/100 # parse and convert to mbar = 0.01 Pa
                        # self.print(f'Read pressure for channel {c.name}', flag=PRINT.DEBUG)
                    except Exception as e:
                        self.print(f'Failed to parse pressure from {msg}: {e}', PRINT.ERROR)
                        self.pressures[i] = np.nan
                elif c.controller == c.TPG and self.TPGinitialized:
                    msg = self.TPGWriteRead(message=f'PR{c.id}')
                    try:
                        a, p = msg.split(',')
                        if a == '0':
                            self.pressures[i] = float(p) # set unit to mbar on device
                            # self.print(f'Read pressure for channel {c.name}', flag=PRINT.DEBUG)
                        else:
                            self.print(f'Could not read pressure for {c.name}: {self.PRESSURE_READING_STATUS[int(a)]}.', PRINT.WARNING)
                            self.pressures[i] = np.nan
                    except Exception as e:
                        self.print(f'Failed to parse pressure from {msg}: {e}', PRINT.ERROR)
                        self.pressures[i] = np.nan
                else:
                    self.pressures[i] = np.nan

    def fakeNumbers(self):
        for i, p in enumerate(self.pressures):
            self.pressures[i] = self.rndPressure() if p == 0 else p*np.random.uniform(.99, 1.01) # allow for small fluctuation

    def rndPressure(self):
        exp = np.random.randint(-11, 3)
        significand = 0.9 * np.random.random() + 0.1
        return significand * 10**exp

    def updateValue(self):
        for c, p in zip(self.device.channels, self.pressures):
            c.value = p

    def TICWrite(self, _id):
        self.serialWrite(self.TICport, f'?V{_id}\r')

    def TICRead(self):
        # Note: unlike most other devices TIC terminates messages with \r and not \r\n
        return self.serialRead(self.TICport, EOL='\r')

    def TICWriteRead(self, message):
        """Allows to write and read while using lock with timeout."""
        readback = ''
        with self.TIClock.acquire_timeout(2) as acquired:
            if acquired:
                self.TICWrite(message)
                readback = self.TICRead() # reads return value
            else:
                self.print(f'Cannot acquire lock for TIC communication. Query: {message}', PRINT.WARNING)
        return readback

    def TPGWrite(self, message):
        # return
        #self.TPGport.write(bytes(f'{message}\r','ascii'))
        #ack = self.TPGport.readline()
        #self.print(f"ACK: {ack}") # b'\x06\r\n' means ACK or acknowledgment b'\x15\r\n' means NAK or not acknowledgment
        self.serialWrite(self.TPGport, f'{message}\r', encoding='ascii')
        self.serialRead(self.TPGport, encoding='ascii') # read acknowledgment

    def TPGRead(self):
        # return 'none'
        #self.TPGport.write(bytes('\x05\r','ascii')) # \x05 is equivalent to ENQ or enquiry
        #enq = self.TPGport.readlines() # response followed by NAK
        #self.print(f"enq: {enq}") # read acknowledgment
        #return enq[0].decode('ascii').rstrip()
        self.serialWrite(self.TPGport, '\x05\r', encoding='ascii') # Enquiry propts sending return from previously send mnemonic
        enq =  self.serialRead(self.TPGport, encoding='ascii') # response
        self.serialRead(self.TPGport, encoding='ascii') # followed by NAK
        return enq

    def TPGWriteRead(self, message):
        """Allows to write and read while using lock with timeout."""
        readback = ''
        with self.TPGlock.acquire_timeout(2) as acquired:
            if acquired:
                self.TPGWrite(message)
                readback = self.TPGRead() # reads return value
            else:
                self.print(f'Cannot acquire lock for Maxigauge communication. Query: {message}', PRINT.WARNING)
        return readback
