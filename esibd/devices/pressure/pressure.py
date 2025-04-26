# pylint: disable=[missing-module-docstring]  # see class docstrings
import re
import time

import numpy as np
import serial

from esibd.core import PARAMETERTYPE, PLUGINTYPE, PRINT, Channel, DeviceController, Parameter, TimeoutLock, getTestMode, parameterDict
from esibd.plugins import Device, Plugin


def providePlugins() -> list['Plugin']:
    """Return list of provided plugins. Indicates that this module provides plugins."""
    return [Pressure]


class Pressure(Device):
    """Bundle pressure values form an Edwards TIC and Pfeiffer MaxiGauge into a consistent list of channels.

    This demonstrates handling of values on a logarithmic scale.
    """

    name = 'Pressure'
    version = '1.0'
    supportedVersion = '0.8'
    pluginType = PLUGINTYPE.OUTPUTDEVICE
    unit = 'mbar'
    iconFile = 'pressure_light.png'
    iconFileDark = 'pressure_dark.png'

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.channelType = PressureChannel
        self.controller = PressureController(controllerParent=self)
        self.logY = True

    def finalizeInit(self) -> None:
        super().finalizeInit()
        self.print('This plugin is deprecated and will be removed in the future. Use TIC and MAXIGAUGE instead.', flag=PRINT.WARNING)

    def getDefaultSettings(self) -> dict[str, dict]:
        defaultSettings = super().getDefaultSettings()
        defaultSettings[f'{self.name}/Interval'][Parameter.VALUE] = 500  # overwrite default value
        defaultSettings[f'{self.name}/TIC COM'] = parameterDict(value='COM1', toolTip='COM port of Edwards TIC.', items=','.join([f'COM{x}' for x in range(1, 25)]),
                                          parameterType=PARAMETERTYPE.COMBO, attr='TICCOM')
        defaultSettings[f'{self.name}/TPG366 COM'] = parameterDict(value='COM1', toolTip='COM port of Pfeiffer MaxiGauge.', items=','.join([f'COM{x}' for x in range(1, 25)]),
                                          parameterType=PARAMETERTYPE.COMBO, attr='TPGCOM')
        defaultSettings[f'{self.name}/{self.MAXDATAPOINTS}'][Parameter.VALUE] = 1E6  # overwrite default value
        return defaultSettings


class PressureChannel(Channel):
    """UI for pressure with integrated functionality."""

    CONTROLLER = 'Controller'
    TIC = 'TIC'
    TPG = 'TPG'
    ID = 'ID'

    def getDefaultChannel(self) -> dict[str, dict]:
        channel = super().getDefaultChannel()
        channel[self.VALUE][Parameter.HEADER] = 'P (mbar)'
        channel[self.CONTROLLER] = parameterDict(value=self.TIC, parameterType=PARAMETERTYPE.COMBO, advanced=True,
                                        items=f'{self.TIC},{self.TPG}', attr='pressure_controller', toolTip='Controller used for communication.')
        channel[self.ID] = parameterDict(value=1, parameterType=PARAMETERTYPE.INTCOMBO, advanced=True,
                                        items='0, 1, 2, 3, 4, 5, 6', attr='id', toolTip='ID of channel on device.')
        return channel

    def setDisplayedParameters(self) -> None:
        super().setDisplayedParameters()
        self.displayedParameters.append(self.CONTROLLER)
        self.displayedParameters.append(self.ID)


class PressureController(DeviceController):

    def __init__(self, controllerParent) -> None:
        super().__init__(controllerParent=controllerParent)
        self.ticPort = None
        self.ticLock = TimeoutLock(lockParent=self)
        self.tpgPort = None
        self.tpgLock = TimeoutLock(lockParent=self)
        self.TICgaugeID = [913, 914, 915, 934, 935, 936]
        self.ticInitialized = False
        self.tpgInitialized = False

    def closeCommunication(self) -> None:
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

    def runInitialization(self) -> None:
        try:
            self.ticPort = serial.Serial(
                f'{self.device.TICCOM}', baudrate=9600, bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE, xonxoff=True, timeout=2)
            TICStatus = self.TICWriteRead(message=902)
            self.print(f'TIC Status: {TICStatus}')  # query status
        except Exception as e:  # pylint: disable=[broad-except]  # noqa: BLE001
            self.print(f'TIC Error while initializing: {e}', PRINT.ERROR)
        else:
            if not TICStatus:
                msg = 'TIC did not return status.'
                raise ValueError(msg)
            self.ticInitialized = True
        try:
            self.tpgPort = serial.Serial(
                f'{self.device.TPGCOM}', baudrate=9600, bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE, xonxoff=False, timeout=2)
            TPGStatus = self.TPGWriteRead(message='TID')
            self.print(f'MaxiGauge Status: {TPGStatus}')  # gauge identification
        except Exception as e:  # pylint: disable=[broad-except]  # noqa: BLE001
            self.print(f'TPG Error while initializing: {e}', PRINT.ERROR)
        else:
            if not TPGStatus:
                msg = 'TPG did not return status.'
                raise ValueError(msg)
            self.tpgInitialized = True
        if self.ticInitialized or self.tpgInitialized:
            self.signalComm.initCompleteSignal.emit()
        self.initializing = False

    def runAcquisition(self, acquiring: callable) -> None:
        while acquiring():
            with self.lock.acquire_timeout(1) as lock_acquired:
                if lock_acquired:
                    self.fakeNumbers() if getTestMode() else self.readNumbers()
                    self.signalComm.updateValuesSignal.emit()
            time.sleep(self.device.interval / 1000)

    PRESSURE_READING_STATUS = {  # noqa: RUF012
      0: 'Measurement data okay',
      1: 'Underrange',
      2: 'Overrange',
      3: 'Sensor error',
      4: 'Sensor off',
      5: 'No sensor',
      6: 'Identification error',
    }

    def readNumbers(self) -> None:
        for i, channel in enumerate(self.device.getChannels()):
            if channel.enabled and channel.active and channel.real:
                if channel.pressure_controller == channel.TIC and self.ticInitialized:
                    msg = self.TICWriteRead(message=f'{self.TICgaugeID[channel.id]}', already_acquired=True)
                    try:
                        self.values[i] = float(re.split(r' |;', msg)[1]) / 100  # parse and convert to mbar = 0.01 Pa
                    except Exception as e:  # noqa: BLE001
                        self.print(f'Failed to parse pressure from {msg}: {e}', PRINT.ERROR)
                        self.errorCount += 1
                        self.values[i] = np.nan
                elif channel.pressure_controller == channel.TPG and self.tpgInitialized:
                    msg = self.TPGWriteRead(message=f'PR{channel.id}', already_acquired=True)
                    try:
                        a, pressure = msg.split(',')
                        if a == '0':
                            self.values[i] = float(pressure)  # set unit to mbar on device
                        else:
                            self.print(f'Could not read pressure for {channel.name}: {self.PRESSURE_READING_STATUS[int(a)]}.', PRINT.WARNING)
                            self.values[i] = np.nan
                    except Exception as e:  # noqa: BLE001
                        self.print(f'Failed to parse pressure from {msg}: {e}', PRINT.ERROR)
                        self.errorCount += 1
                        self.values[i] = np.nan
                else:
                    self.values[i] = np.nan

    def fakeNumbers(self) -> None:
        for i, channel in enumerate(self.device.getChannels()):
            if channel.enabled and channel.active and channel.real:
                self.values[i] = self.rndPressure() if np.isnan(self.values[i]) else self.values[i] * self.rng.uniform(.99, 1.01)  # allow for small fluctuation

    def rndPressure(self) -> float:
        """Return a random pressure."""
        exp = float(self.rng.integers(-11, 3))
        significand = 0.9 * self.rng.random() + 0.1
        return significand * 10**exp

    def TICWrite(self, _id) -> None:
        """TIC specific serial write.

        :param _id: The sensor id to be send.
        :type _id: str
        """
        self.serialWrite(self.ticPort, f'?V{_id}\r')

    def TICRead(self) -> str:
        """TIC specific serial read."""
        # Note: unlike most other devices TIC terminates messages with \r and not \r\n
        return self.serialRead(self.ticPort, EOL='\r')

    def TICWriteRead(self, message, already_acquired=False) -> str:
        """TIC specific serial write and read.

        :param message: The serial message to be send.
        :type message: str
        :param already_acquired: Indicates if the lock has already been acquired, defaults to False
        :type already_acquired: bool, optional
        :return: The serial response received.
        :rtype: str
        """
        response = ''
        with self.ticLock.acquire_timeout(2, timeoutMessage=f'Cannot acquire lock for message: {message}', already_acquired=already_acquired) as lock_acquired:
            if lock_acquired:
                self.TICWrite(message)
                response = self.TICRead()  # reads return value
        return response

    def TPGWrite(self, message) -> None:
        """TPG specific serial write.

        :param message: The serial message to be send.
        :type message: str
        """
        self.serialWrite(self.tpgPort, f'{message}\r', encoding='ascii')
        self.serialRead(self.tpgPort, encoding='ascii')  # read acknowledgment

    def TPGRead(self) -> str:
        """TPG specific serial read.

        :return: The serial response received.
        :rtype: str
        """
        self.serialWrite(self.tpgPort, '\x05\r', encoding='ascii')  # Enquiry prompts sending return from previously send mnemonic
        enq = self.serialRead(self.tpgPort, encoding='ascii')  # response
        self.serialRead(self.tpgPort, encoding='ascii')  # followed by NAK
        return enq

    def TPGWriteRead(self, message, already_acquired=False) -> str:
        """TPG specific serial write and read.

        :param message: The serial message to be send.
        :type message: str
        :param already_acquired: Indicates if the lock has already been acquired, defaults to False
        :type already_acquired: bool, optional
        :return: The serial response received.
        :rtype: str
        """
        response = ''
        with self.tpgLock.acquire_timeout(2, timeoutMessage=f'Cannot acquire lock for message: {message}', already_acquired=already_acquired) as lock_acquired:
            if lock_acquired:
                self.TPGWrite(message)
                response = self.TPGRead()  # reads return value
        return response
