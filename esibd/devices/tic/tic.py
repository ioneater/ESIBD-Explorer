# pylint: disable=[missing-module-docstring]  # see class docstrings
import re
from typing import TYPE_CHECKING

import numpy as np
import serial

from esibd.core import PRINT
from esibd.devices.omnicontrol.omnicontrol import OMNICONTROL, PressureController

if TYPE_CHECKING:
    from esibd.plugins import Plugin


def providePlugins() -> list['Plugin']:
    """Return list of provided plugins. Indicates that this module provides plugins."""
    return [TIC]


class TIC(OMNICONTROL):
    """Read pressure values form an Edwards TIC.

    This is inheriting many functions from the OMNICONTROL plugin.
    Thus it exemplifies how to build a new plugin by only changing a few specific lines of code.
    As an added advantage, all improvements and bug fixes made to the OMNICONTROL plugin will be inherited as well.
    """

    name = 'TIC'
    iconFile = 'edwards_tic.png'

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.controller = TICPressureController(controllerParent=self)


class TICPressureController(PressureController):

    TICgaugeID = (913, 914, 915, 934, 935, 936)

    def runInitialization(self) -> None:
        try:
            self.port = serial.Serial(
                f'{self.device.COM}', baudrate=9600, bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE, xonxoff=True, timeout=2)
            TICStatus = self.TICWriteRead(message=902)
            self.print(f'Status: {TICStatus}')  # query status
        except Exception as e:  # pylint: disable=[broad-except]  # noqa: BLE001
            self.print(f'Error while initializing: {e}', PRINT.ERROR)
        else:
            if not TICStatus:
                msg = 'TIC did not return status.'
                raise ValueError(msg)
            self.signalComm.initCompleteSignal.emit()
        finally:
            self.initializing = False

    def readNumbers(self) -> None:
        for i, channel in enumerate(self.device.getChannels()):
            if channel.enabled and channel.active and channel.real:
                if self.initialized:
                    msg = self.TICWriteRead(message=f'{self.TICgaugeID[channel.id]}', already_acquired=True)
                    try:
                        self.values[i] = float(re.split(r' |;', msg)[1]) / 100  # parse and convert to mbar = 0.01 Pa
                    except Exception as e:  # noqa: BLE001
                        self.print(f'Failed to parse pressure from {msg}: {e}', PRINT.ERROR)
                        self.errorCount += 1
                        self.values[i] = np.nan
                else:
                    self.values[i] = np.nan

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
                self.serialWrite(self.port, f'?V{message}\r')
                # Note: unlike most other devices TIC terminates messages with \r and not \r\n
                response = self.serialRead(self.port, EOL='\r')  # reads return value
        return response
