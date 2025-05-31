# pylint: disable=[missing-module-docstring] # only single class in module
# install lakeshore drivers from here if not automatically installed via windows updates: https://www.lakeshore.com/resources/software/drivers
import time

import numpy as np
from lakeshore import Model335

from esibd.core import (
    PARAMETERTYPE,
    PLUGINTYPE,
    PRINT,
    Channel,
    DeviceController,
    Parameter,
    ToolButton,
    getDarkMode,
    getTestMode,
    parameterDict,
)
from esibd.plugins import Device, Plugin


def providePlugins() -> list['type[Plugin]']:
    """Indicate that this module provides plugins. Returns list of provided plugins."""
    return [LS335]


class LS335(Device):
    """Device that reads and controls temperature using a LakeShore 335.

    It allows to switch units between K and °C.
    """

    name = 'LS335'
    version = '1.0'
    supportedVersion = '0.8'
    iconFile = 'LS335_on.png'
    pluginType = PLUGINTYPE.INPUTDEVICE
    unit = 'K'
    useMonitors = True

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

    COM: str

    def getDefaultSettings(self) -> dict[str, dict]:
        defaultSettings = super().getDefaultSettings()
        defaultSettings[f'{self.name}/Interval'][Parameter.VALUE] = 5000  # overwrite default value
        defaultSettings[f'{self.name}/LS335 COM'] = parameterDict(value='COM3', toolTip='COM port of LakeShore 335.', items=','.join([f'COM{x}' for x in range(1, 25)]),
                                          parameterType=PARAMETERTYPE.COMBO, attr='COM')
        defaultSettings[f'{self.name}/{self.MAXDATAPOINTS}'][Parameter.VALUE] = 1E6  # overwrite default value
        return defaultSettings

    def convertDataDisplay(self, data: np.ndarray) -> np.ndarray:
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

    ID = 'ID'
    HEATER = 'HEATER'
    active = True
    channelParent: LS335

    def getDefaultChannel(self) -> dict[str, dict]:

        # definitions for type hinting
        self.id: str
        self.heater: int
        self.channel_active: bool

        channel = super().getDefaultChannel()
        channel.pop(Channel.EQUATION)
        channel[self.VALUE][Parameter.HEADER] = 'Set Temp (K)'  # overwrite existing parameter to change header
        channel[self.VALUE][Parameter.INSTANTUPDATE] = False
        channel[self.ACTIVE] = parameterDict(value=False, parameterType=PARAMETERTYPE.BOOL, attr='channel_active', toolTip='Activate PID control.',
                                              event=lambda: self.channelParent.controller.toggleOnFromThread(parallel=True))
        channel[self.ID] = parameterDict(value='A', parameterType=PARAMETERTYPE.COMBO, advanced=True,
                                        items='A, B', attr='id')
        channel[self.HEATER] = parameterDict(value=1, parameterType=PARAMETERTYPE.INTCOMBO, advanced=True,
                                        items='1, 2', attr='heater')
        return channel

    def setDisplayedParameters(self) -> None:
        super().setDisplayedParameters()
        self.displayedParameters.remove(self.EQUATION)
        self.insertDisplayedParameter(self.ACTIVE, before=self.NAME)
        self.displayedParameters.append(self.ID)
        self.displayedParameters.append(self.HEATER)

    def initGUI(self, item) -> None:
        super().initGUI(item)
        active = self.getParameterByName(self.ACTIVE)
        value = active.value
        active.widget = ToolButton()
        active.applyWidget()
        if active.check:
            active.check.setMaximumHeight(active.rowHeight)
            active.check.setText(self.ACTIVE.title())
            active.check.setMinimumWidth(5)
            active.check.setCheckable(True)
        active.value = value


class TemperatureController(DeviceController):
    """Implements communication with LakeShore 335.

    PID control will only be active if activated on channel and device level.
    """

    ls335 = None
    controllerParent: LS335

    def closeCommunication(self) -> None:
        super().closeCommunication()
        if self.ls335 is not None:
            with self.lock.acquire_timeout(1, timeoutMessage='Could not acquire lock before closing port.'):
                self.ls335.disconnect_usb()
        self.initialized = False

    def runInitialization(self) -> None:
        try:
            self.ls335 = Model335(baud_rate=57600, com_port=self.controllerParent.COM)  # may raise AttributeError that can not be excepted
            self.signalComm.initCompleteSignal.emit()
        except (AttributeError, Exception) as e:  # pylint: disable=[broad-except]
            self.print(f'Error while initializing: {e}', PRINT.ERROR)
        finally:
            self.initializing = False

    def runAcquisition(self) -> None:
        while self.acquiring:
            with self.lock.acquire_timeout(1) as lock_acquired:
                if lock_acquired:
                    self.fakeNumbers() if getTestMode() else self.readNumbers()
                    self.signalComm.updateValuesSignal.emit()
            time.sleep(self.controllerParent.interval / 1000)

    def readNumbers(self) -> None:
        for i, channel in enumerate(self.controllerParent.getChannels()):
            if isinstance(channel, TemperatureChannel) and self.ls335:
                value = self.ls335.get_kelvin_reading(channel.id)
                try:
                    self.values[i] = float(value)
                except ValueError as e:
                    self.print(f'Error while reading temp: {e}', PRINT.ERROR)
                    self.values[i] = np.nan

    def fakeNumbers(self) -> None:
        for i, channel in enumerate(self.controllerParent.getChannels()):
            # exponentially approach target or room temp + small fluctuation
            if channel.enabled and channel.real:
                self.values[i] = max((self.values[i] + self.rng.uniform(-1, 1)) + 0.1 * ((channel.value if self.controllerParent.isOn() else 300) - self.values[i]), 0)

    def rndTemperature(self) -> float:
        """Return a random temperature."""
        return self.rng.uniform(0, 400)

    def toggleOn(self) -> None:
        for channel in self.controllerParent.channels:
            if isinstance(channel, TemperatureChannel) and self.ls335:
                if channel.channel_active and self.controllerParent.isOn():
                    # self.ls335.set_heater_pid(output=channel.heater, gain=200, integral=14, derivative=100)  # noqa: ERA001
                    # self.ls335._set_autotune(output=channel.heater, mode=self.ls335.AutotuneMode.P_I_D)  # noqa: ERA001
                    # self.ls335.set_heater_output_mode(output=channel.heater, mode=self.ls335.HeaterOutputMode.CLOSED_LOOP, channel=channel.id)  # noqa: ERA001
                    # self.ls335.set_heater_setup_one(self.ls335.HeaterResistance.HEATER_50_OHM, 0.6, self.ls335.HeaterOutputDisplay.POWER)  # noqa: ERA001
                    self.ls335.set_heater_range(channel.heater, self.ls335.HeaterRange.HIGH)
                    self.set_control_setpoint(channel=channel)
                    # self.ls335.turn_relay_on(relay_number=channel.heater)  # noqa: ERA001
                else:
                    # self.ls335.set_heater_output_mode(output=channel.heater, mode=self.ls335.HeaterOutputMode.OFF, channel=channel.id)  # noqa: ERA001
                    self.ls335.set_heater_range(channel.heater, self.ls335.HeaterRange.OFF)

    def set_control_setpoint(self, channel) -> None:
        """Set the heater and temperature setpoint for the given channel.

        :param channel: The channel for which to set the setpoint.
        :type channel: esibd.code.Channel
        """
        if self.ls335:
            self.ls335.set_control_setpoint(output=channel.heater, value=channel.value)

    def applyValue(self, channel) -> None:
        self.set_control_setpoint(channel)
