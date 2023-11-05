# pylint: disable=[missing-module-docstring] # only single class in module
import socket
from threading import Thread
import time
from random import choices
import numpy as np
from PyQt6.QtCore import pyqtSignal
from esibd.plugins import Device#, StaticDisplay
from esibd.core import Parameter, parameterDict, PluginManager, Channel, PRINT, DeviceController, getDarkMode, getTestMode

########################## Voltage user interface #################################################

def providePlugins():
    return [Voltage]

class Voltage(Device):
    """Device that contains a list of voltages channels from an ISEG ECH244 power supply.
    The voltages are monitored and a warning is given if the set potentials are not reached."""
    documentation = None # use __doc__

    name = 'ISEG'
    version = '1.1'
    pluginType = PluginManager.TYPE.INPUTDEVICE
    unit = 'V'

    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.channelType = VoltageChannel

    def initGUI(self):
        """:meta private:"""
        super().initGUI()
        self.controller = VoltageController(device=self, modules = self.getModules()) # after all channels loaded

    def finalizeInit(self, aboutFunc=None):
        """:meta private:"""
        # use stateAction.state instead of attribute as attribute would be added to DeviceManager rather than self
        self.onAction = self.pluginManager.DeviceManager.addStateAction(func=self.voltageON, toolTipFalse='ISEG on.', iconFalse=self.getIcon(),
                                                                  toolTipTrue='ISEG off.', iconTrue=self.makeIcon('ISEG_on.png'),
                                                                 before=self.pluginManager.DeviceManager.aboutAction)
        super().finalizeInit(aboutFunc)

    def getIcon(self):
        return self.makeIcon('ISEG_off_dark.png') if getDarkMode() else self.makeIcon('ISEG_off_light.png')

    def getDefaultSettings(self):
        """:meta private:"""
        ds = super().getDefaultSettings()
        ds[f'{self.name}/IP']       = parameterDict(value='169.254.163.182', toolTip='IP address of ECH244',
                                                                widgetType=Parameter.TYPE.TEXT, attr='ip')
        ds[f'{self.name}/Port']     = parameterDict(value=10001, toolTip='SCPI port of ECH244',
                                                                widgetType=Parameter.TYPE.INT, attr='port')
        ds[f'{self.name}/Interval'][Parameter.VALUE] = 1000 # overwrite default value
        ds[f'{self.name}/{self.MAXDATAPOINTS}'][Parameter.VALUE] = 1E5 # overwrite default value
        return ds

    def getModules(self): # get list of used modules
        return set([channel.module for channel in self.channels])

    def init(self):
        """:meta private:"""
        super().init()
        self.onAction.state = self.controller.ON
        self.controller.init(IP=self.ip, port=int(self.port))

    def stop(self):
        """:meta private:"""
        super().stop()
        self.controller.close()

    def stopAcquisition(self):
        """:meta private:"""
        super().stopAcquisition()
        self.controller.close()

    def close(self):
        """:meta private:"""
        super().close()
        self.updateValues(apply=True) # apply voltages before turning modules on or off
        self.controller.voltageON(on=False)
        self.stopAcquisition()

    def initialized(self):
        return self.controller.initialized

    def apply(self, apply=False):
        for c in self.channels:
            c.setVoltage(apply) # only actually sets voltage if configured and value has changed

    def voltageON(self):
        if self.initialized():
            self.updateValues(apply=True) # apply voltages before turning modules on or off
            self.controller.voltageON(self.onAction.state)
        elif self.onAction.state is True:
            self.controller.ON = self.onAction.state
            self.init()

    def updateTheme(self):
        """:meta private:"""
        super().updateTheme()
        self.onAction.iconFalse = self.getIcon()
        self.onAction.updateIcon(self.onAction.state) # self.on not available on start

class VoltageChannel(Channel):
    """UI for single voltage channel with integrated functionality"""

    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.lastAppliedValue = None # keep track of last value to identify what has changed
        self.warningStyleSheet = f'background: rgb({255},{0},{0})'
        self.defaultStyleSheet = None # will be initialized when color is set

    MONITOR   = 'Monitor'
    MODULE    = 'Module'
    ID        = 'ID'

    def getDefaultChannel(self):
        channel = super().getDefaultChannel()
        channel[self.VALUE][Parameter.HEADER] = 'Voltage (V)' # overwrite to change header
        channel[self.MONITOR ] = parameterDict(value=0, widgetType=Parameter.TYPE.FLOAT, advanced=False,
                                    event=self.monitorChanged, indicator=True, attr='monitor')
        channel[self.MODULE  ] = parameterDict(value=0, widgetType= Parameter.TYPE.INT, advanced=True,
                                    header='Mod', _min=0, _max=99, attr='module')
        channel[self.ID      ] = parameterDict(value=0, widgetType= Parameter.TYPE.INT, advanced=True,
                                    header='ID', _min=0, _max=99, attr='id')
        return channel

    def setDisplayedParameters(self):
        super().setDisplayedParameters()
        self.insertDisplayedParameter(self.MONITOR, before=self.MIN)
        self.insertDisplayedParameter(self.MODULE, before=self.COLOR)
        self.insertDisplayedParameter(self.ID, before=self.COLOR)

    def tempParameters(self):
        return super().tempParameters() + [self.MONITOR]

    def enabledChanged(self):
        super().enabledChanged()
        self.device.resetPlot()

    def initGUI(self, item):
        super().initGUI(item)
        # overwrite limits with specific save voltage range. all other properties for self.MIN/self.MAX are inherited from parent
        # note that this is just to get a reasonable witdh for the controls
        # the real savety limits are the values of min max as defined in the user interface and configuration file
        _min = self.getParameterByName(self.MIN)
        _min.spin.setMinimum(-5000)
        _min.spin.setMaximum(5000)
        _max = self.getParameterByName(self.MAX)
        _max.spin.setMinimum(-5000)
        _max.spin.setMaximum(5000)

    def setVoltage(self, apply): # this actually sets the voltage on the powersupply!
        if self.real and ((self.value != self.lastAppliedValue) or apply):
            self.device.controller.setVoltage(self)
            self.lastAppliedValue = self.value

    def updateColor(self):
        color = super().updateColor()
        self.defaultStyleSheet = f'background-color: {color.name()}'

    def monitorChanged(self):
        if self.enabled and self.device.controller.acquiring and ((self.device.controller.ON and abs(self.monitor - self.value) > 1)
                                                                    or (not self.device.controller.ON and abs(self.monitor - 0) > 1)):
            self.getParameterByName(self.MONITOR).getWidget().setStyleSheet(self.warningStyleSheet)
        else:
            self.getParameterByName(self.MONITOR).getWidget().setStyleSheet(self.defaultStyleSheet)

    def realChanged(self):
        self.getParameterByName(self.MONITOR).getWidget().setVisible(self.real)
        self.getParameterByName(self.MODULE).getWidget().setVisible(self.real)
        self.getParameterByName(self.ID).getWidget().setVisible(self.real)
        super().realChanged()

    def appendValue(self, lenT):
        # super().appendValue() # overwrite to use readbacks if available
        self.values.add(self.monitor, lenT)

class VoltageController(DeviceController): # no channels needed
    # need to inherit from QObject to allow use of signals
    """Implements SCPI communication with ISEG ECH244.
    While this is kept as general as possible, some access to the management and UI parts are required for proper integration."""

    class SignalCommunicate(DeviceController.SignalCommunicate):
        applyMonitorsSignal= pyqtSignal()

    def __init__(self, device, modules):
        super().__init__(parent=device)
        self.device     = device
        self.modules    = modules or [0]
        self.signalComm.applyMonitorsSignal.connect(self.applyMonitors)
        self.IP = 'localhost'
        self.port = 0
        self.ON         = False
        self.s          = None
        self.maxID = max([c.id if c.real else 0 for c in self.device.channels]) # used to query correct amount of monitors
        self.voltages   = np.zeros([len(self.modules), self.maxID+1])

    def init(self, IP='localhost', port=0):
        self.IP = IP
        self.port = port
        super().init()

    def runInitialization(self):
        """initializes socket for SCPI communication"""
        if getTestMode():
            self.print('Faking monitor values for testing!', PRINT.WARNING)
            self.initialized = True
            self.signalComm.initCompleteSignal.emit()
        else:
            self.initializing = True
            try:
                # self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.s = socket.create_connection(address=(self.IP, self.port), timeout=3)
                with self.lock:
                    self.s.sendall('*IDN?\r\n'.encode('utf-8'))
                    self.print(self.read())
                self.initialized = True
                self.signalComm.initCompleteSignal.emit()
                # threads cannot be restarted -> make new thread every time. possibly there are cleaner solutions
            except Exception as e: # pylint: disable=[broad-except] # socket does not throw more specific exception
                self.print(f'Could not establish SCPI connection to {self.IP} on port {self.port}. Exception: {e}', PRINT.WARNING)
            finally:
                self.initializing = False

    def initComplete(self):
        super().startAcquisition()
        if self.ON:
            self.device.updateValues(apply=True) # apply voltages before turning modules on or off
        self.voltageON(self.ON)

    def stop(self):
        self.device.stop()

    def stopAcquisition(self):
        if super().stopAcquisition():
            self.initialized = False
            if self.device.pluginManager.closing:
                time.sleep(.1) # allow for time to finish last event before application is closed and external thread looses access to elements in main thread

    def read(self, initializing=False):
        # only call from thread! # make sure lock is aquired before and relased after
        if not getTestMode() and (self.initialized or initializing):
            return self.s.recv(4096).decode("utf-8")

    def setVoltage(self, channel):
        if not getTestMode() and self.initialized:
            Thread(target=self.setVoltageFromThread, args=(channel,)).start()

    def setVoltageFromThread(self, channel):
        with self.lock:
            self.s.sendall(f':VOLT {channel.value if channel.enabled else 0},(#{channel.module}@{channel.id})\r\n'.encode('utf-8'))
            self.read()

    def applyMonitors(self):
        if getTestMode():
            self.fakeMonitors()
        else:
            for channel in self.device.channels:
                if channel.real:
                    channel.monitor = self.voltages[channel.module][channel.id]

    def voltageON(self, on=False): # this can run in main thread
        self.ON = on
        if not getTestMode() and self.initialized:
            Thread(target=self.voltageONFromThread, args=(on,)).start()
        elif getTestMode():
            self.fakeMonitors()

    def voltageONFromThread(self, on=False):
        with self.lock:
            for m in self.modules:
                self.s.sendall(f":VOLT {'ON' if on else 'OFF'},(#{m}@0-{self.maxID})\r\n".encode('utf-8'))
                self.read()

    def fakeMonitors(self):
        for channel in self.device.channels:
            if channel.real:
                if self.device.controller.ON and channel.enabled:
                    # fake values with noise and 10% channels with offset to simulate defect channel or short
                    channel.monitor = channel.value + 5*choices([0, 1],[.98,.02])[0] + np.random.rand()
                else:
                    channel.monitor = 0             + 5*choices([0, 1],[.9,.1])[0] + np.random.rand()

    def runAcquisition(self, acquiring):
        """monitor potentials continuously"""
        while acquiring():
            if not getTestMode():
                with self.lock:
                    for m in self.modules:
                        self.s.sendall(f':MEAS:VOLT? (#{m}@0-{self.maxID+1})\r\n'.encode('utf-8'))
                        res = self.read()#. rstripreplace('\r\n','')
                        if res != '':
                            try:
                                monitors = [float(x[:-1]) for x in res[:-4].split(',')] # res[:-4] to remove trainling '\r\n'
                                # fill up to self.maxID to handle all modules the same independent of the number of channels.
                                self.voltages[m] = np.hstack([monitors, np.zeros(self.maxID+1-len(monitors))])
                            except (ValueError, TypeError) as e:
                                self.print(f'Monitor parsing error: {e} for {res}.')
            self.signalComm.applyMonitorsSignal.emit() # signal main thread to update GUI
            time.sleep(self.device.interval/1000)
