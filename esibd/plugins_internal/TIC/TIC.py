# pylint: disable=[missing-module-docstring] # see class docstrings
import re
import serial
import numpy as np
from esibd.plugins_internal.OMNICONTROL.OMNICONTROL import OMNICONTROL, PressureController
from esibd.core import PRINT

def providePlugins():
    """Indicates that this module provides plugins. Returns list of provided plugins."""
    return [TIC]

class TIC(OMNICONTROL):
    """Device that reads pressure values form an Edwards TIC.

    This is inheriting many functions from the OMNICONTROL plugin.
    Thus it exemplifies how to build a new plugin by only changing a few specific lines of code.
    As an added advantage, all improvements and bug fixes made to the OMNICONTROL plugin will be inherited as well."""

    name = 'TIC'
    iconFile = 'edwards_tic.png'

    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.controller = TICPressureController(_parent=self)

class TICPressureController(PressureController):

    TICgaugeID = [913, 914, 915, 934, 935, 936]

    def runInitialization(self):
        try:
            self.port=serial.Serial(
                f'{self.device.COM}', baudrate=9600, bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE, xonxoff=True, timeout=2)
            TICStatus = self.TICWriteRead(message=902)
            self.print(f"Status: {TICStatus}") # query status
            if TICStatus == '':
                raise ValueError('TIC did not return status.')
            self.signalComm.initCompleteSignal.emit()
        except Exception as e: # pylint: disable=[broad-except]
            self.print(f'Error while initializing: {e}', PRINT.ERROR)
        finally:
            self.initializing = False

    def readNumbers(self):
        for i, channel in enumerate(self.device.getChannels()):
            if channel.enabled and channel.active and channel.real:
                if self.initialized:
                    msg = self.TICWriteRead(message=f'{self.TICgaugeID[channel.id]}', lock_acquired=True)
                    try:
                        self.pressures[i] = float(re.split(' |;', msg)[1])/100 # parse and convert to mbar = 0.01 Pa
                        # self.print(f'Read pressure for channel {c.name}', flag=PRINT.DEBUG)
                    except Exception as e:
                        self.print(f'Failed to parse pressure from {msg}: {e}', PRINT.ERROR)
                        self.errorCount += 1
                        self.pressures[i] = np.nan
                else:
                    self.pressures[i] = np.nan

    def TICWriteRead(self, message, lock_acquired=False):
        """TIC specific serial write and read.

        :param message: The serial message to be send.
        :type message: str
        :param lock_acquired: Indicates if the lock has already been acquired, defaults to False
        :type lock_acquired: bool, optional
        :return: The serial response received.
        :rtype: str
        """
        response = ''
        with self.ticLock.acquire_timeout(2, timeoutMessage=f'Cannot acquire lock for message: {message}', lock_acquired=lock_acquired) as lock_acquired:
            if lock_acquired:
                self.TICWrite(message)
                self.serialWrite(self.port, f'?V{message}\r')
                # Note: unlike most other devices TIC terminates messages with \r and not \r\n
                response = self.serialRead(self.port, EOL='\r') # reads return value
        return response
