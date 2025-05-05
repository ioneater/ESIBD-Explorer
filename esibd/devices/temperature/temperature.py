# pylint: disable=[missing-module-docstring]  # see class docstrings
import time

import numpy as np
import serial
from PyQt6.QtWidgets import QMessageBox

from esibd.core import PARAMETERTYPE, PLUGINTYPE, PRINT, Channel, DeviceController, Parameter, getDarkMode, getTestMode, parameterDict
from esibd.plugins import Device, Plugin


def providePlugins() -> list['Plugin']:
    """Return list of provided plugins. Indicates that this module provides plugins."""
    return [Temperature]


class Temperature(Device):
    """Reads the temperature of a silicon diode sensor via Sunpower CryoTel controller.

    It allows to switch units between K and °C.
    """

    name = 'Temperature'
    version = '1.0'
    supportedVersion = '0.8'
    pluginType = PLUGINTYPE.INPUTDEVICE
    unit = 'K'
    useMonitors = True
    iconFile = 'temperature.png'

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.useOnOffLogic = True
        self.channelType = TemperatureChannel
        self.controller = TemperatureController(controllerParent=self)

    def initGUI(self) -> None:
        super().initGUI()
        self.unitAction = self.addStateAction(event=self.changeUnit, toolTipFalse='Change to °C', iconFalse=self.makeIcon('tempC_dark.png'),
                                               toolTipTrue='Change to K', iconTrue=self.makeIcon('tempK_dark.png'), attr='displayC')

    def runTestParallel(self) -> None:
        self.testControl(self.unitAction, self.unitAction.state)
        super().runTestParallel()

    def changeUnit(self) -> None:
        """Update plots to account for change of unit."""
        if self.liveDisplayActive():
            self.clearPlot()
            self.liveDisplay.plot()
        if self.staticDisplayActive():
            self.staticDisplay.plot()

    def getDefaultSettings(self) -> dict[str, dict]:
        defaultSettings = super().getDefaultSettings()
        defaultSettings[f'{self.name}/Interval'][Parameter.VALUE] = 5000  # overwrite default value
        defaultSettings[f'{self.name}/CryoTel COM'] = parameterDict(value='COM3', toolTip='COM port of Sunpower CryoTel.', items=','.join([f'COM{x}' for x in range(1, 25)]),
                                          parameterType=PARAMETERTYPE.COMBO, attr='CRYOTELCOM')
        defaultSettings[f'{self.name}/Toggle threshold'] = parameterDict(value=15, toolTip='Cooler is toggled on and off to stay within threshold from set value.',
                                          parameterType=PARAMETERTYPE.INT, attr='toggleThreshold')
        defaultSettings[f'{self.name}/{self.MAXDATAPOINTS}'][Parameter.VALUE] = 1E6  # overwrite default value
        return defaultSettings

    def convertDataDisplay(self, data) -> None:
        return data - 273.15 if self.unitAction.state else data

    def getUnit(self) -> str:
        return '°C' if self.unitAction.state else self.unit

    def updateTheme(self) -> None:
        super().updateTheme()
        self.unitAction.iconFalse = self.makeIcon('tempC_dark.png' if getDarkMode() else 'tempC_light.png')
        self.unitAction.iconTrue = self.makeIcon('tempK_dark.png' if getDarkMode() else 'tempK_light.png')
        self.unitAction.updateIcon(self.unitAction.state)


class TemperatureChannel(Channel):
    """UI for pressure with integrated functionality."""

    CRYOTEL = 'CryoTel'

    def getDefaultChannel(self) -> dict[str, dict]:
        channel = super().getDefaultChannel()
        channel[self.VALUE][Parameter.HEADER] = 'Temp (K)'
        return channel


class TemperatureController(DeviceController):

    def __init__(self, controllerParent) -> None:
        super().__init__(controllerParent)
        self.messageBox = QMessageBox(QMessageBox.Icon.Information, 'Water cooling!', 'Water cooling!', buttons=QMessageBox.StandardButton.Ok)

    def closeCommunication(self) -> None:
        super().closeCommunication()
        if self.port is not None:
            with self.lock.acquire_timeout(1, timeoutMessage='Could not acquire lock before closing port.'):
                self.port.close()
                self.port = None
        self.initialized = False

    def runInitialization(self) -> None:
        try:
            self.port = serial.Serial(
                self.device.CRYOTELCOM,
                baudrate=9600,  # used to be 4800
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                xonxoff=False,
                timeout=3)
            # self.CryoTelWriteRead('SET TBAND=5')  # set temperature band  # noqa: ERA001
            # self.CryoTelWriteRead('SET PID=2')# set temperature control mode # noqa: ERA001
            # self.CryoTelWriteRead('SET SSTOPM=0')  # enable use of SET SSTOP # noqa: ERA001
            # self.CryoTelWriteRead('SENSOR')  # test if configured for correct temperature sensor DT-670 # noqa: ERA001
            # self.CryoTelWriteRead('SENSOR=DT-670')  # set Sensor if applicable # noqa: ERA001
            self.signalComm.initCompleteSignal.emit()
        except Exception as e:  # pylint: disable=[broad-except]  # noqa: BLE001
            self.closeCommunication()
            self.print(f'Error while initializing: {e}', PRINT.ERROR)
        finally:
            self.initializing = False

    def runAcquisition(self, acquiring: callable) -> None:
        while acquiring():
            with self.lock.acquire_timeout(1) as lock_acquired:
                if lock_acquired:
                    self.fakeNumbers() if getTestMode() else self.readNumbers()
                    self.signalComm.updateValuesSignal.emit()
            time.sleep(self.device.interval / 1000)

    toggleCounter = 0

    def readNumbers(self) -> None:
        for i, channel in enumerate(self.device.getChannels()):
            if channel.enabled and channel.real:
                value = self.CryoTelWriteRead(message='TC')  # Display Cold-Tip Temperature (same on old and new controller)
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
        if (self.device.isOn() and np.mod(self.toggleCounter, int(60000 / self.device.interval)) == 0 and
            self.device.getChannels()[0].monitor != 0 and not np.isnan(self.device.getChannels()[0].monitor)):
            if self.device.getChannels()[0].monitor < self.device.getChannels()[0].value - self.device.toggleThreshold:
                self.print(f'Toggle cooler off. {self.device.getChannels()[0].monitor} K is under lower threshold '
                           f'of {self.device.getChannels()[0].value - self.device.toggleThreshold} K.')
                self.CryoTelWriteRead(message='COOLER=OFF')
            elif self.device.getChannels()[0].monitor > self.device.getChannels()[0].value + self.device.toggleThreshold:
                if self.CryoTelWriteRead('COOLER') != 'POWER':  # avoid sending command repeatedly
                    self.print(f'Toggle cooler on. {self.device.getChannels()[0].monitor} K is over upper threshold '
                               f'of {self.device.getChannels()[0].value + self.device.toggleThreshold} K.')
                    self.CryoTelWriteRead(message='COOLER=POWER')

    def fakeNumbers(self) -> None:
        for i, channel in enumerate(self.device.getChannels()):
            # exponentially approach target or room temp + small fluctuation
            if channel.enabled and channel.real:
                self.values[i] = max((self.values[i] + self.rng.uniform(-1, 1)) + 0.1 * ((channel.value if self.device.isOn() else 300) - self.values[i]), 0)

    def rndTemperature(self) -> float:
        """Return a random temperature."""
        return self.rng.uniform(0, 400)

    def toggleOn(self) -> None:
        if self.device.isOn():
            self.CryoTelWriteRead(message='COOLER=POWER')  # 'COOLER=ON' start (used to be 'SET SSTOP=0')
        else:
            self.CryoTelWriteRead(message='COOLER=OFF')  # stop (used to be 'SET SSTOP=1')
        self.messageBox.setText(f"Remember to turn water cooling {'on' if self.device.isOn() else 'off'} and gas ballast {'off' if self.device.isOn() else 'on'}!")
        self.messageBox.setWindowIcon(self.device.getIcon())
        if not self.device.testing:
            self.messageBox.open()  # show non blocking, defined outside so it does not get eliminated when the function completes.
            self.messageBox.raise_()
        self.processEvents()

    def applyValue(self, channel) -> None:
        self.CryoTelWriteRead(message=f'TTARGET={channel.value}')  # used to be SET TTARGET=

    def CryoTelWriteRead(self, message: str) -> str:
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
                response = self.CryoTelRead()  # reads return value
        return response

    def CryoTelWrite(self, message: str) -> None:
        """CryoTel specific serial write.

        :param message: The serial message to be send.
        :type message: str
        """
        self.serialWrite(self.port, f'{message}\r')
        self.CryoTelRead()  # repeats query

    def CryoTelRead(self) -> str:
        """TPG specific serial read.

        :return: The response received.
        :rtype: str
        """
        return self.serialRead(self.port)
