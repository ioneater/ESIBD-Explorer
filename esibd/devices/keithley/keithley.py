# pylint: disable=[missing-module-docstring]  # see class docstrings
import time

import numpy as np
import pyvisa

from esibd.core import PARAMETERTYPE, PLUGINTYPE, PRINT, Channel, DeviceController, Parameter, getTestMode, parameterDict
from esibd.plugins import Device, Plugin


def providePlugins() -> list['Plugin']:
    """Return list of provided plugins. Indicates that this module provides plugins."""
    return [KEITHLEY]


class KEITHLEY(Device):
    """Contains a list of current channels, each corresponding to a single KEITHLEY 6487 picoammeter."""

    name = 'KEITHLEY'
    version = '1.0'
    supportedVersion = '0.8'
    pluginType = PLUGINTYPE.OUTPUTDEVICE
    unit = 'pA'
    iconFile = 'keithley.png'

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.useOnOffLogic = True
        self.channelType = CurrentChannel
        self.useBackgrounds = True  # record backgrounds for data correction

    def initGUI(self) -> None:
        super().initGUI()
        self.addAction(event=lambda: self.resetCharge(), toolTip=f'Reset accumulated charge for {self.name}.', icon='battery-empty.png')

    def getDefaultSettings(self) -> dict[str, dict]:
        defaultSettings = super().getDefaultSettings()
        defaultSettings[f'{self.name}/Interval'][Parameter.VALUE] = 100  # overwrite default value
        return defaultSettings

    def resetCharge(self) -> None:
        """Reset the charge of each channel."""
        for channel in self.channels:
            channel.resetCharge()

    def updateTheme(self) -> None:
        super().updateTheme()
        self.onAction.iconTrue = self.getIcon()
        self.onAction.updateIcon(self.isOn())


class CurrentChannel(Channel):
    """UI for picoammeter with integrated functionality."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.controller = CurrentController(controllerParent=self)
        self.preciseCharge = 0  # store independent of spin box precision to avoid rounding errors

    CHARGE     = 'Charge'
    ADDRESS    = 'Address'
    VOLTAGE    = 'Voltage'

    def getDefaultChannel(self) -> dict[str, dict]:
        channel = super().getDefaultChannel()
        channel[self.VALUE][Parameter.HEADER] = 'I (pA)'
        channel[self.CHARGE] = parameterDict(value=0, parameterType=PARAMETERTYPE.FLOAT, advanced=False, header='C (pAh)', indicator=True, attr='charge')
        channel[self.ADDRESS] = parameterDict(value='GPIB0::22::INSTR', parameterType=PARAMETERTYPE.TEXT, advanced=True, attr='address')
        channel[self.VOLTAGE] = parameterDict(value=0, parameterType=PARAMETERTYPE.FLOAT, advanced=False, attr='voltage', event=lambda: self.controller.applyVoltage())
        return channel

    def setDisplayedParameters(self) -> None:
        super().setDisplayedParameters()
        self.insertDisplayedParameter(self.CHARGE, before=self.DISPLAY)
        self.insertDisplayedParameter(self.VOLTAGE, before=self.DISPLAY)
        self.displayedParameters.append(self.ADDRESS)

    def tempParameters(self) -> None:
        return [*super().tempParameters(), self.CHARGE]

    def enabledChanged(self) -> None:
        super().enabledChanged()
        if self.device.liveDisplayActive() and self.device.recording:
            if self.enabled:
                self.controller.initializeCommunication()
            elif self.controller.acquiring:
                self.controller.stopAcquisition()

    def appendValue(self, lenT, nan=False) -> None:
        super().appendValue(lenT, nan=nan)
        if not nan and not np.isnan(self.value) and not np.isinf(self.value):
            chargeIncrement = (self.value - self.background) * self.device.interval / 1000 / 3600 if self.values.size > 1 else 0
            self.preciseCharge += chargeIncrement  # display accumulated charge  # don't use np.sum(self.charges) to allow
            self.charge = self.preciseCharge  # pylint: disable=[attribute-defined-outside-init]  # attribute defined dynamically

    def clearHistory(self, max_size=None) -> None:
        super().clearHistory(max_size)
        self.resetCharge()

    def resetCharge(self) -> None:
        """Reset the charge."""
        self.charge = 0  # pylint: disable=[attribute-defined-outside-init]  # attribute defined dynamically
        self.preciseCharge = 0

    def realChanged(self) -> None:
        self.getParameterByName(self.ADDRESS).getWidget().setVisible(self.real)
        super().realChanged()


class CurrentController(DeviceController):
    """Implements visa communication with KEITHLEY 6487."""

    def __init__(self, controllerParent) -> None:
        super().__init__(controllerParent=controllerParent)
        self.channel = controllerParent
        self.device = self.channel.getDevice()
        self.port = None
        self.phase = self.rng.random() * 10  # used in test mode
        self.omega = self.rng.random()  # used in test mode
        self.offset = self.rng.random() * 10  # used in test mode

    def initializeCommunication(self) -> None:
        if self.channel.enabled and self.channel.active and self.channel.real:
            super().initializeCommunication()
        else:
            self.stopAcquisition()

    def closeCommunication(self) -> None:
        if self.port is not None:
            with self.lock.acquire_timeout(1, timeoutMessage='Could not acquire lock before closing port.'):
                self.port.close()
                self.port = None
        super().closeCommunication()

    def runInitialization(self) -> None:
        try:
            # use rm.list_resources() to check for available resources
            self.rm = pyvisa.ResourceManager()
            self.port = self.rm.open_resource(self.channel.address)
            self.port.write("*RST")
            self.device.print(self.port.query('*IDN?'))
            self.port.write("SYST:ZCH OFF")
            self.port.write("CURR:NPLC 6")
            self.port.write("SOUR:VOLT:RANG 50")
            self.signalComm.initCompleteSignal.emit()
        except Exception:
            self.signalComm.updateValuesSignal.emit(np.nan)
        finally:
            self.initializing = False

    def startAcquisition(self) -> None:
        if self.channel.active:
            super().startAcquisition()

    def runAcquisition(self, acquiring: callable) -> None:
        while acquiring():
            with self.lock.acquire_timeout(1) as lock_acquired:
                if lock_acquired:
                    if getTestMode():
                        self.fakeNumbers()
                    else:
                        self.readNumbers()
                    self.signalComm.updateValuesSignal.emit()
                    # no sleep needed, timing controlled by waiting during readNumbers
            if getTestMode():
                time.sleep(self.channel.device.interval / 1000)

    def applyVoltage(self) -> None:
        # NOTE this is different from the general applyValue function as this is not setting the channel value but an additional custom channel parameter
        """Apply voltage value."""
        if self.port is not None:
            self.port.write(f"SOUR:VOLT {self.channel.voltage}")

    def toggleOn(self) -> None:
        self.applyVoltage()  # apply voltages before turning power supply on or off
        self.port.write(f"SOUR:VOLT:STAT {'ON' if self.device.isOn() else 'OFF'}")

    def fakeNumbers(self) -> None:
        if not self.channel.pluginManager.closing and self.channel.enabled and self.channel.active and self.channel.real:
            self.values = [np.sin(self.omega * time.time() / 5 + self.phase) * 10 + self.rng.random() + self.offset]

    def readNumbers(self) -> None:
        if not self.channel.pluginManager.closing and self.channel.enabled and self.channel.active and self.channel.real:
            try:
                self.port.write("INIT")
                self.values = [float(self.port.query("FETCh?").split(',')[0][:-1]) * 1E12]
            except (pyvisa.errors.VisaIOError, pyvisa.errors.InvalidSession, AttributeError) as e:
                self.print(f'Error while reading current {e}', flag=PRINT.ERROR)
                self.errorCount += 1
                self.values = [np.nan]
