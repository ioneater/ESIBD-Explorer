# pylint: disable=[missing-module-docstring] # see class docstrings
import time
import serial
import numpy as np
from PyQt6.QtWidgets import QMessageBox
from esibd.plugins import Device
from esibd.core import Parameter, PluginManager, Channel, parameterDict, PRINT, DeviceController, getDarkMode, getTestMode

def providePlugins():
    """Indicates that this module provides plugins. Returns list of provided plugins."""
    return [Temperature]

class Temperature(Device):
    """Reads the temperature of a silicon diode sensor via Sunpower CryoTel controller.
    It allows to switch units between K and °C."""

    name = 'Temperature'
    version = '1.0'
    supportedVersion = '0.7'
    pluginType = PluginManager.TYPE.INPUTDEVICE
    unit = 'K'
    useMonitors = True
    iconFile = 'temperature.png'

    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.useOnOffLogic = True
        self.channelType = TemperatureChannel
        self.controller = TemperatureController(_parent=self)

    def initGUI(self):
        super().initGUI()
        self.unitAction = self.addStateAction(event=lambda: self.changeUnit(), toolTipFalse='Change to °C', iconFalse=self.makeIcon('tempC_dark.png'),
                                               toolTipTrue='Change to K', iconTrue=self.makeIcon('tempK_dark.png'), attr='displayC')

    def runTestParallel(self):
        self.testControl(self.unitAction, self.unitAction.state)
        super().runTestParallel()

    def changeUnit(self):
        """Update plots to account for change of unit."""
        if self.liveDisplayActive():
            self.clearPlot()
            self.liveDisplay.plot()
        if self.staticDisplayActive():
            self.staticDisplay.plot()

    def getDefaultSettings(self):
        defaultSettings = super().getDefaultSettings()
        defaultSettings[f'{self.name}/Interval'][Parameter.VALUE] = 5000 # overwrite default value
        defaultSettings[f'{self.name}/CryoTel COM'] = parameterDict(value='COM3', toolTip='COM port of Sunpower CryoTel.', items=','.join([f'COM{x}' for x in range(1, 25)]),
                                          widgetType=Parameter.TYPE.COMBO, attr='CRYOTELCOM')
        defaultSettings[f'{self.name}/Toggle threshold'] = parameterDict(value=15, toolTip='Cooler is toggled on and off to stay within threshold from set value.',
                                          widgetType=Parameter.TYPE.INT, attr='toggleThreshold')
        defaultSettings[f'{self.name}/{self.MAXDATAPOINTS}'][Parameter.VALUE] = 1E6 # overwrite default value
        return defaultSettings

    def convertDataDisplay(self, data):
        return data - 273.15 if self.unitAction.state else data

    def getUnit(self):
        return '°C' if self.unitAction.state else self.unit

    def updateTheme(self):
        super().updateTheme()
        self.unitAction.iconFalse = self.makeIcon('tempC_dark.png' if getDarkMode() else 'tempC_light.png')
        self.unitAction.iconTrue = self.makeIcon('tempK_dark.png' if getDarkMode() else 'tempK_light.png')
        self.unitAction.updateIcon(self.unitAction.state)

class TemperatureChannel(Channel):
    """UI for pressure with integrated functionality"""

    CRYOTEL = 'CryoTel'

    def getDefaultChannel(self):
        channel = super().getDefaultChannel()
        channel[self.VALUE][Parameter.HEADER ] = 'Temp (K)'
        return channel

class TemperatureController(DeviceController):

    def __init__(self, _parent):
        super().__init__(_parent)
        self.messageBox = QMessageBox(QMessageBox.Icon.Information, 'Water cooling!', 'Water cooling!', buttons=QMessageBox.StandardButton.Ok)

    def closeCommunication(self):
        if self.port is not None:
            with self.lock.acquire_timeout(1, timeoutMessage='Could not acquire lock before closing port.'):
                self.port.close()
                self.port = None
        super().closeCommunication()

    def runInitialization(self):
        try:
            self.port=serial.Serial(
                self.device.CRYOTELCOM,
                baudrate=9600, # used to be 4800
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                xonxoff=False,
                timeout=3)
            # self.CryoTelWriteRead('SET TBAND=5') # set temperature band
            # self.CryoTelWriteRead('SET PID=2')# set temperature control mode
            # self.CryoTelWriteRead('SET SSTOPM=0') # enable use of SET SSTOP
            # self.CryoTelWriteRead('SENSOR') # test if configured for correct temperature sensor DT-670
            # self.CryoTelWriteRead('SENSOR=DT-670') # set Sensor if applicable
            self.signalComm.initCompleteSignal.emit()
        except Exception as e: # pylint: disable=[broad-except]
            self.print(f'Error while initializing: {e}', PRINT.ERROR)
        finally:
            self.initializing = False

    def runAcquisition(self, acquiring):
        while acquiring():
            with self.lock.acquire_timeout(1) as lock_acquired:
                if lock_acquired:
                    self.fakeNumbers() if getTestMode() else self.readNumbers()
                    self.signalComm.updateValuesSignal.emit()
            time.sleep(self.device.interval/1000)

    toggleCounter = 0
    def readNumbers(self):
        for i, channel in enumerate(self.device.getChannels()):
            if channel.enabled and channel.real:
                value = self.CryoTelWriteRead(message='TC') # Display Cold-Tip Temperature (same on old and new controller)
                try:
                    self.values[i] = float(value)
                except ValueError as e:
                    self.print(f'Error while reading temp: {e}', PRINT.ERROR)
                    self.errorCount += 1
                    self.values[i] = np.nan

        # toggle cryo on off to stabilize at temperatures above what is possible with minimal power
        # temporary mode. to be replaced by temperature regulation using heater.
        # only test once a minute as cooler takes 30 s to turn on or off
        # in case of over current error the cooler won't turn on and there is no need for additional safety check
        self.toggleCounter += 1
        if self.device.isOn() and np.mod(self.toggleCounter, int(60000/self.device.interval)) == 0 and self.device.getChannels()[0].monitor != 0 and self.device.getChannels()[0].monitor != np.nan:
            if self.device.getChannels()[0].monitor < self.device.getChannels()[0].value - self.device.toggleThreshold:
                self.print(f'Toggle cooler off. {self.device.getChannels()[0].monitor} K is under lower threshold of {self.device.getChannels()[0].value - self.device.toggleThreshold} K.')
                self.CryoTelWriteRead(message='COOLER=OFF')
            elif self.device.getChannels()[0].monitor > self.device.getChannels()[0].value + self.device.toggleThreshold:
                if self.CryoTelWriteRead('COOLER') != 'POWER': # avoid sending command repeatedly
                    self.print(f'Toggle cooler on. {self.device.getChannels()[0].monitor} K is over upper threshold of {self.device.getChannels()[0].value + self.device.toggleThreshold} K.')
                    self.CryoTelWriteRead(message='COOLER=POWER')

    def fakeNumbers(self):
        for i, channel in enumerate(self.device.getChannels()):
            # exponentially approach target or room temp + small fluctuation
            if channel.enabled and channel.real:
                self.values[i] = max((self.values[i]+np.random.uniform(-1, 1)) + 0.1*((channel.value if self.device.isOn() else 300)-self.values[i]), 0)

    def rndTemperature(self):
        """Returns a random temperature."""
        return np.random.uniform(0, 400)

    def toggleOn(self):
        if self.device.isOn():
            self.CryoTelWriteRead(message='COOLER=POWER') # 'COOLER=ON' start (used to be 'SET SSTOP=0')
        else:
            self.CryoTelWriteRead(message='COOLER=OFF') # stop (used to be 'SET SSTOP=1')
        self.messageBox.setText(f"Remember to turn water cooling {'on' if self.device.isOn() else 'off'} and gas ballast {'off' if self.device.isOn() else 'on'}!")
        self.messageBox.setWindowIcon(self.device.getIcon())
        if not self.device.testing:
            self.messageBox.open() # show non blocking, defined outside so it does not get eliminated when the function completes.
            self.messageBox.raise_()
        self.processEvents()

    def applyValue(self, channel):
        self.CryoTelWriteRead(message=f'TTARGET={channel.value}') # used to be SET TTARGET=

    def CryoTelWriteRead(self, message):
        """CryoTel specific serial write and read.

        :param message: The serial message to be send.
        :type message: str
        :return: The serial response received.
        :rtype: str
        """
        response = ''
        with self.lock.acquire_timeout(1, timeoutMessage=f'Cannot acquire lock for message: {message}') as lock_acquired:
            if lock_acquired:
                self.CryoTelWrite(message)
                response = self.CryoTelRead() # reads return value
        return response

    def CryoTelWrite(self, message):
        """CryoTel specific serial write.

        :param message: The serial message to be send.
        :type message: str
        """
        self.serialWrite(self.port, f'{message}\r')
        self.CryoTelRead() # repeats query

    def CryoTelRead(self):
        """TPG specific serial read.

        :return: The response received.
        :rtype: str
        """
        return self.serialRead(self.port)
