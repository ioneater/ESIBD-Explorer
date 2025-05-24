# pylint: disable=[missing-module-docstring]  # see class docstrings
import time

import numpy as np
import pfeiffer_vacuum_protocol as pvp
import serial

from esibd.core import PARAMETERTYPE, PLUGINTYPE, PRINT, Channel, DeviceController, Parameter, getTestMode, parameterDict
from esibd.plugins import Device, Plugin


def providePlugins() -> list['type[Plugin]']:
    """Return list of provided plugins. Indicates that this module provides plugins."""
    return [OMNICONTROL]


class OMNICONTROL(Device):
    """Reads pressure values form an Pfeiffer Omnicontrol using the Pfeiffer Vacuum Protocol."""

    name = 'OMNICONTROL'
    version = '1.0'
    supportedVersion = '0.8'
    pluginType = PLUGINTYPE.OUTPUTDEVICE
    unit = 'mbar'
    iconFile = 'pfeiffer_omni.png'
    channels: 'list[PressureChannel]'

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.channelType = PressureChannel
        self.controller = PressureController(controllerParent=self)
        self.logY = True

    com: str

    def getDefaultSettings(self) -> dict[str, dict]:
        defaultSettings = super().getDefaultSettings()
        defaultSettings[f'{self.name}/Interval'][Parameter.VALUE] = 500  # overwrite default value
        defaultSettings[f'{self.name}/COM'] = parameterDict(value='COM1', toolTip='COM port.', items=','.join([f'COM{x}' for x in range(1, 25)]),
                                          parameterType=PARAMETERTYPE.COMBO, attr='com')
        defaultSettings[f'{self.name}/{self.MAXDATAPOINTS}'][Parameter.VALUE] = 1E6  # overwrite default value
        return defaultSettings


class PressureChannel(Channel):
    """UI for pressure with integrated functionality."""

    ID = 'ID'
    channelParent: OMNICONTROL

    def getDefaultChannel(self) -> dict[str, dict]:

        # definitions for type hinting
        self.id: int

        channel = super().getDefaultChannel()
        channel[self.VALUE][Parameter.HEADER] = 'P (mbar)'
        channel[self.ID] = parameterDict(value=1, parameterType=PARAMETERTYPE.INTCOMBO, advanced=True,
                                        items='0, 1, 2, 3, 4, 5, 6', attr='id')
        return channel

    def setDisplayedParameters(self) -> None:
        super().setDisplayedParameters()
        self.displayedParameters.append(self.ID)


class PressureController(DeviceController):

    controllerParent: OMNICONTROL

    def closeCommunication(self) -> None:
        super().closeCommunication()
        if self.port is not None:
            with self.lock.acquire_timeout(1, timeoutMessage='Could not acquire lock before closing port.'):
                self.port.close()
                self.port = None
        self.initialized = False

    def runInitialization(self) -> None:
        try:
            self.port = serial.Serial(self.controllerParent.com, timeout=1)
            pvp.enable_valid_char_filter()
            self.signalComm.initCompleteSignal.emit()
        except Exception as e:  # pylint: disable=[broad-except]  # noqa: BLE001
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
            if isinstance(channel, PressureChannel) and channel.enabled and channel.active and channel.real:
                try:
                    pressure = pvp.read_pressure(self.port, channel.id)
                    self.print(f'readNumbers channel.id: {channel.id}, response {pressure}', flag=PRINT.TRACE)
                    self.values[i] = np.nan if pressure == 0 else pressure * 1000
                except ValueError as e:
                    self.print(f'Error while reading pressure {e}')
                    self.errorCount += 1
                    self.values[i] = np.nan

    def fakeNumbers(self) -> None:
        for i, channel in enumerate(self.controllerParent.getChannels()):
            if channel.enabled and channel.active and channel.real:
                self.values[i] = self.rndPressure() if np.isnan(self.values[i]) else self.values[i] * self.rng.uniform(.99, 1.01)  # allow for small fluctuation

    def rndPressure(self) -> float:
        """Return a random pressure."""
        exp = float(self.rng.integers(-11, 3))
        significand = 0.9 * self.rng.random() + 0.1
        return significand * 10**exp
