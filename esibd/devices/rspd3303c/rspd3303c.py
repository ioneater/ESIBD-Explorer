# pylint: disable=[missing-module-docstring]  # see class docstrings
import time
from random import choices

import numpy as np
import pyvisa
from PyQt6.QtCore import QTimer

from esibd.core import PARAMETERTYPE, PLUGINTYPE, PRINT, Channel, DeviceController, Parameter, getTestMode, parameterDict
from esibd.plugins import Device, Plugin


def providePlugins() -> list['Plugin']:
    """Return list of provided plugins. Indicates that this module provides plugins."""
    return [RSPD3303C]


class RSPD3303C(Device):
    """Contains a list of voltages channels from a single RSPD3303C power supplies with 2 analog outputs.

    In case of any issues, first test communication independently with EasyPowerX.
    """

    name = 'RSPD3303C'
    version = '1.0'
    supportedVersion = '0.8'
    pluginType = PLUGINTYPE.INPUTDEVICE
    unit = 'V'
    useMonitors = True
    iconFile = 'RSPD3303C.png'

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.useOnOffLogic = True
        self.channelType = VoltageChannel
        self.shutDownTimer = QTimer(self)
        self.shutDownTimer.timeout.connect(self.updateTimer)

    def initGUI(self) -> None:
        super().initGUI()
        self.controller = VoltageController(controllerParent=self)  # after all channels loaded

    def finalizeInit(self) -> None:
        self.shutDownTime = 0
        super().finalizeInit()

    ADDRESS = 'Address'
    SHUTDOWNTIMER = 'Shutdown timer'

    def getDefaultSettings(self) -> dict[str, dict]:
        defaultSettings = super().getDefaultSettings()
        defaultSettings[f'{self.name}/Interval'][Parameter.VALUE] = 1000  # overwrite default value
        defaultSettings[f'{self.name}/{self.MAXDATAPOINTS}'][Parameter.VALUE] = 1E5  # overwrite default value
        defaultSettings[f'{self.name}/{self.SHUTDOWNTIMER}'] = parameterDict(value=0, parameterType=PARAMETERTYPE.INT, attr='shutDownTime', instantUpdate=False,
                                                                     toolTip=f'Time in minutes. Starts a countdown which turns {self.name} off once expired.',
                                                                     event=self.initTimer, internal=True)
        defaultSettings[f'{self.name}/{self.ADDRESS}'] = parameterDict(value='USB0::0xF4EC::0x1430::SPD3EGGD7R2257::INSTR', parameterType=PARAMETERTYPE.TEXT, attr='address')
        return defaultSettings

    def initTimer(self) -> None:
        """Initialize the shutdown timer."""
        if self.shutDownTime != 0:
            if (self.shutDownTime < 10 or  # notify every minute  # noqa: PLR0916, PLR2004
            (self.shutDownTime < 60 and self.shutDownTime % 10 == 0) or  # notify every 10 minutes  # noqa: PLR2004
            (self.shutDownTime < 600 and self.shutDownTime % 60 == 0) or  # notify every hour  # noqa: PLR2004
            (self.shutDownTime % 600 == 0)):  # notify every 10 hours
                self.print(f'Will turn off in {self.shutDownTime} minutes.')
            self.shutDownTimer.start(60000)  # 1 min steps steps

    def updateTimer(self) -> None:
        """Update the shutdowntimer, notifies about remaining time and turns of the device once expired."""
        self.shutDownTime = max(0, self.shutDownTime - 1)
        if self.shutDownTime == 1:
            self.print('Timer expired. Setting PID off and heater voltages to 0 V.')
            if hasattr(self.pluginManager, 'PID'):
                self.pluginManager.PID.setOn(on=False)
            for channel in self.channels:
                channel.value = 0
        if self.shutDownTime == 0:
            self.print('Timer expired. Turning off.')
            self.shutDownTimer.stop()
            self.setOn(on=False)


class VoltageChannel(Channel):

    CURRENT = 'Current'
    POWER = 'Power'
    ID = 'ID'

    def getDefaultChannel(self) -> dict[str, dict]:
        channel = super().getDefaultChannel()
        channel[self.VALUE][Parameter.HEADER] = 'Voltage (V)'  # overwrite to change header
        channel[self.MIN][Parameter.VALUE] = 0
        channel[self.MAX][Parameter.VALUE] = 1  # start with safe limits
        channel[self.POWER] = parameterDict(value=0, parameterType=PARAMETERTYPE.FLOAT, advanced=False,
                                                               indicator=True, attr='power')
        channel[self.CURRENT] = parameterDict(value=0, parameterType=PARAMETERTYPE.FLOAT, advanced=True,
                                                               indicator=True, attr='current')
        channel[self.ID] = parameterDict(value=0, parameterType=PARAMETERTYPE.INT, advanced=True,
                                    header='ID', minimum=0, maximum=99, attr='id')
        return channel

    def setDisplayedParameters(self) -> None:
        super().setDisplayedParameters()
        self.insertDisplayedParameter(self.CURRENT, before=self.MIN)
        self.insertDisplayedParameter(self.POWER, before=self.MIN)
        self.displayedParameters.append(self.ID)

    def tempParameters(self) -> None:
        return [*super().tempParameters(), self.POWER, self.CURRENT]

    def monitorChanged(self) -> None:
        # overwriting super().monitorChanged() to set 0 as expected value when device is off
        self.updateWarningState(self.enabled and self.device.controller.acquiring and ((self.device.isOn() and abs(self.monitor - self.value) > 1)
                                                                    or (not self.device.isOn() and abs(self.monitor - 0) > 1)))

    def realChanged(self) -> None:
        self.getParameterByName(self.POWER).getWidget().setVisible(self.real)
        self.getParameterByName(self.CURRENT).getWidget().setVisible(self.real)
        self.getParameterByName(self.ID).getWidget().setVisible(self.real)
        super().realChanged()


class VoltageController(DeviceController):

    def __init__(self, controllerParent) -> None:
        super().__init__(controllerParent=controllerParent)

    def runInitialization(self) -> None:
        try:
            rm = pyvisa.ResourceManager()
            # name = rm.list_resources()  # noqa: ERA001
            self.port = rm.open_resource(self.device.address, open_timeout=500)
            self.device.print(self.port.query('*IDN?'))
            self.signalComm.initCompleteSignal.emit()
        except Exception as e:  # pylint: disable=[broad-except]  # socket does not throw more specific exception  # noqa: BLE001
            self.print(f'Could not establish connection to {self.device.address}. Exception: {e}', PRINT.WARNING)
        finally:
            self.initializing = False

    def initComplete(self) -> None:
        self.currents = [np.nan] * len(self.device.getChannels())
        self.values = [np.nan] * len(self.device.getChannels())
        super().initComplete()

    def applyValue(self, channel) -> None:
        self.RSWrite(f'CH{channel.id}:VOLT {channel.value if channel.enabled else 0}')

    def updateValues(self) -> None:
        # Overwriting to also update custom current and power parameters.
        if getTestMode():
            self.fakeNumbers()
        else:
            for i, channel in enumerate(self.device.getChannels()):
                if channel.enabled and channel.real:
                    channel.monitor = self.values[i]
                    channel.current = self.currents[i]
                    channel.power = channel.monitor * channel.current

    def toggleOn(self) -> None:
        for channel in self.device.getChannels():
            self.RSWrite(f"OUTPUT CH{channel.id},{'ON' if self.device.isOn() else 'OFF'}")

    def fakeNumbers(self) -> None:
        for channel in self.device.getChannels():
            if channel.enabled and channel.real:
                if self.device.isOn() and channel.enabled:
                    # fake values with noise and 10% channels with offset to simulate defect channel or short
                    channel.monitor = channel.value + 5 * choices([0, 1], [.98, .02])[0] + self.rng.random()
                else:
                    channel.monitor = 0 + 5 * choices([0, 1], [.9, .1])[0] + self.rng.random()
                channel.current = 50 / channel.monitor if channel.monitor != 0 else 0  # simulate 50 W
                channel.power = channel.monitor * channel.current

    def runAcquisition(self, acquiring: callable) -> None:
        while acquiring():
            with self.lock.acquire_timeout(1) as lock_acquired:
                if lock_acquired:
                    if not getTestMode():
                        for i, channel in enumerate(self.device.getChannels()):
                            self.values[i] = self.RSQuery(f'MEAS:VOLT? CH{channel.id}', already_acquired=lock_acquired)
                            self.currents[i] = self.RSQuery(f'MEAS:CURR? CH{channel.id}', already_acquired=lock_acquired)
                    self.signalComm.updateValuesSignal.emit()  # signal main thread to update GUI
            time.sleep(self.device.interval / 1000)

    def RSWrite(self, message) -> None:
        """RS specific pyvisa write.

        :param message: The message to be send.
        :type message: str
        """
        with self.lock.acquire_timeout(1, timeoutMessage=f'Cannot acquire lock for message {message}.') as lock_acquired:
            if lock_acquired:
                self.port.write(message)

    def RSQuery(self, message, already_acquired=False) -> str:
        """RS specific pyvisa query.

        :param message: The message to be send.
        :type message: str
        :param already_acquired: Indicates if the lock has already been acquired, defaults to False
        :type already_acquired: bool, optional
        :return: The response received.
        :rtype: str
        """
        response = ''
        with self.lock.acquire_timeout(1, timeoutMessage=f'Cannot acquire lock for query {message}.', already_acquired=already_acquired) as lock_acquired:
            if lock_acquired:
                response = self.port.query(message)
        return response
