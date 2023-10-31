# pylint: disable=[missing-module-docstring] # only single class in module
import time
from threading import Thread
import serial
import numpy as np
from PyQt6.QtWidgets import QMessageBox
from esibd.plugins import Device
from esibd.core import Parameter, PluginManager, Channel, parameterDict, PRINT, DeviceController, getDarkMode

def providePlugins():
    return [Temperature]

class Temperature(Device):
    """Device that reads the temperature of a silicon diode sensor via Sunpower CryoTel controller.
    It allows to switch units between K and °C."""

    name = 'Temperature'
    version = '1.0'
    supportedVersion = '0.6'
    pluginType = PluginManager.TYPE.INPUTDEVICE
    unit = 'K'

    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.channelType = TemperatureChannel
        self.controller = TemperatureController(device=self)

    def initGUI(self):
        super().initGUI()
        self.addStateAction(func=self.changeUnit, toolTipFalse='Change to °C', iconFalse=self.makeIcon('tempC.png'),
                                               toolTipTrue='Change to K', iconTrue=self.makeIcon('tempK.png'), attr='displayC')

    def finalizeInit(self, aboutFunc=None):
        # use stateAction.state instead of attribute as attribute would be added to DeviceManager rather than self
        self.onAction = self.pluginManager.DeviceManager.addStateAction(func=self.cryoON, toolTipFalse='Cryo on.', iconFalse=self.getIcon(), toolTipTrue='Cryo off.',
                                                                  iconTrue=self.makeIcon('temperature_on.png'), before=self.pluginManager.DeviceManager.aboutAction)
        super().finalizeInit(aboutFunc)

    def getIcon(self):
        return self.makeIcon('temperature_dark.png') if getDarkMode() else self.makeIcon('temperature_light.png')

    def changeUnit(self):
        if self.liveDisplayActive():
            self.resetPlot()
            self.liveDisplay.plot()
        if self.staticDisplayActive():
            self.staticDisplay.plot()

    def getDefaultSettings(self):
        ds = super().getDefaultSettings()
        ds[f'{self.name}/Interval'][Parameter.VALUE] = 5000 # overwrite default value
        ds[f'{self.name}/CryoTel COM'] = parameterDict(value='COM3', toolTip='COM port of Sunpower CryoTel.', items=','.join([f'COM{x}' for x in range(1, 25)]),
                                          widgetType=Parameter.TYPE.COMBO, attr='CRYOTELCOM')
        ds[f'{self.name}/{self.MAXDATAPOINTS}'][Parameter.VALUE] = 1E6 # overwrite default value
        return ds

    def getInitializedChannels(self):
        return [d for d in self.channels if (d.enabled and (self.controller.port is not None or self.getTestMode())) or not d.active]

    def init(self):
        super().init()
        self.controller.restart = self.onAction.state
        self.controller.init()

    def startAcquisition(self):
        self.controller.startAcquisition()

    def stopAcquisition(self):
        super().stopAcquisition()
        self.controller.stopAcquisition()

    def stop(self):
        super().stop()
        self.controller.close()

    def initialized(self):
        return self.controller.initialized

    def close(self):
        self.controller.close()
        super().close()

    def convertDataDisplay(self, data):
        if self.displayC:
            return data - 273.15
        else:
            return data

    def getUnit(self):
        """Overwrite if you want to change units dynamically."""
        return '°C' if self.displayC else self.unit

    def cryoON(self):
        if self.initialized():
            self.controller.cryoON(self.onAction.state)
        else:
            self.init()

    def apply(self, apply=False): # pylint: disable = unused-argument # keep default signature
        for c in self.channels:
            c.setTemperature() # only actually sets voltage if configured and value has changed

    def updateTheme(self):
        super().updateTheme()
        self.onAction.iconFalse = self.getIcon()
        self.onAction.updateIcon(self.onAction.state) # self.on not available on start

class TemperatureChannel(Channel):
    """UI for pressure with integrated functionality"""

    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.warningStyleSheet = f'background: rgb({255},{0},{0})'
        self.defaultStyleSheet = None # will be initialized when color is set

    def initGUI(self, item):
        super().initGUI(item)
        _min = self.getParameterByName(self.MIN)
        _min.spin.setMinimum(-5000)
        _min.spin.setMaximum(5000)
        _max = self.getParameterByName(self.MAX)
        _max.spin.setMinimum(-5000)
        _max.spin.setMaximum(5000)

    MONITOR   = 'Monitor'
    CONTROLER = 'Controler'
    CRYOTEL = 'CryoTel'

    def getDefaultChannel(self):
        """Gets default settings and values."""
        channel = super().getDefaultChannel()
        channel[self.VALUE][Parameter.HEADER ] = 'Temp (K)' # overwrite existing parameter to change header
        channel[self.MONITOR ] = parameterDict(value=0, widgetType=Parameter.TYPE.FLOAT, advanced=False,
                                    event=self.monitorChanged, indicator=True, attr='monitor')
        channel[self.CONTROLER] = parameterDict(value='None', widgetType=Parameter.TYPE.COMBO, advanced=True,
                                        items=f'{self.CRYOTEL}, None', attr='controler')
        return channel

    def setDisplayedParameters(self):
        super().setDisplayedParameters()
        self.insertDisplayedParameter(self.MONITOR, before=self.MIN)
        self.insertDisplayedParameter(self.CONTROLER, before=self.COLOR)

    def enabledChanged(self): # overwrite parent method
        """Handle changes while acquisition is running. All other changes will be handled when acquisition starts."""
        if self.device.liveDisplayActive() and self.device.pluginManager.DeviceManager.acquiring:
            self.device.init()

    def setTemperature(self): # this actually sets the voltage on the powersupply!
        if self.real:
            self.device.controller.setTemperature(self)

    def updateColor(self):
        color = super().updateColor()
        self.defaultStyleSheet = f'background-color: {color.name()}'

    def monitorChanged(self):
        if self.enabled and self.device.controller.initialized and ((self.device.controller.ON and abs(self.monitor - self.value) > 1)):
            self.getParameterByName(self.MONITOR).getWidget().setStyleSheet(self.warningStyleSheet)
        else:
            self.getParameterByName(self.MONITOR).getWidget().setStyleSheet(self.defaultStyleSheet)

    def appendValue(self, lenT):
        # super().appendValue() # overwrite to use readbacks
        self.values.add(self.monitor, lenT)

class TemperatureController(DeviceController):
    # need to inherit from QObject to allow use of signals
    """Implements serial communication with RBD 9103.
    While this is kept as general as possible, some access to the management and UI parts are required for proper integration."""

    def __init__(self, device):
        super().__init__(parent=device)
        #setup port
        self.device = device
        self.ON = False
        # self.init() only init once explicitly called
        self.restart=False
        self.temperatures = []

    def stop(self):
        self.device.stop()

    def close(self):
        super().close()
        if self.ON:
            self.cryoON(on=False)
        if self.port is not None:
            with self.lock:
                self.port.close()
        self.initialized = False

    def stopAcquisition(self):
        if super().stopAcquisition():
            if self.device.pluginManager.closing:
                time.sleep(.1)

    def runInitialization(self):
        """Initializes serial port in paralel thread"""
        if self.device.getTestMode():
            self.signalComm.initCompleteSignal.emit()
        else:
            try:
                self.port=serial.Serial(
                    self.device.CRYOTELCOM,
                    baudrate=9600, # used to be 4800
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    xonxoff=False,
                    timeout=1)
                self.CryoTelClearBuffer()
                # self.CryoTelWrite('SET TBAND=5') # set temperature band
                # self.CryoTelRead()
                # self.CryoTelWrite('SET PID=2')# set temperature control mode
                # self.CryoTelRead()
                # self.CryoTelWrite('SET SSTOPM=0') # enable use of SET SSTOP
                # self.CryoTelRead()
                # self.CryoTelWrite('SENSOR') # test if configured for correct temperature sensor DT-670
                # self.CryoTelRead()
                # self.CryoTelWrite('SENSOR=DT-670') # set Sensor if applicable
                # self.CryoTelRead()
                self.signalComm.initCompleteSignal.emit()
            except Exception as e: # pylint: disable=[broad-except]
                self.print(f'Error while initializing: {e}', PRINT.ERROR)

    def initComplete(self):
        self.temperatures = [0]*len(self.device.channels)
        super().initComplete()
        if self.device.getTestMode():
            self.print('Faking values for testing!', PRINT.WARNING)
        if self.restart:
            self.cryoON(True)
            self.restart = False

    def startAcquisition(self):
        # only run if init succesful, or in test mode. if channel is not active it will calculate value independently
        if self.port is not None or self.device.getTestMode():
            super().startAcquisition()

    def runAcquisition(self, acquiring):
        # runs in parallel thread
        while acquiring():
            if self.device.getTestMode():
                self.fakeNumbers()
            else:
                self.readNumbers()
            self.signalComm.updateValueSignal.emit()
            time.sleep(self.device.interval/1000)

    def readNumbers(self):
        for i, c in enumerate(self.device.channels):
            if c.controler == c.CRYOTEL:
                with self.lock:
                    self.CryoTelWrite('TC') # Display Cold-Tip Temperature (same on old and new controller)
                    v = self.CryoTelRead() # response
                    try:
                        v = float(v)
                        self.temperatures[i] = v
                    except ValueError as e:
                        self.print(f'Error while reading temp: {e}', PRINT.ERROR)
                        self.temperatures[i] = np.nan
            else:
                self.temperatures[i] = np.nan

    def fakeNumbers(self):
        for i, c in enumerate(self.device.channels):
            self.temperatures[i] = c.value*np.random.uniform(.95, 1.05) # allow for small fluctuation

    def rndTemperature(self):
        return np.random.uniform(0, 400)

    def updateValue(self):
        for c, p in zip(self.device.channels, self.temperatures):
            c.monitor = p

    def cryoON(self, on=False):
        self.ON = on
        if not self.device.getTestMode() and self.initialized:
            with self.lock:
                if on:
                    self.CryoTelWrite('COOLER=ON') # start (used to be 'SET SSTOP=0')
                    self.CryoTelRead()
                else:
                    self.CryoTelWrite('COOLER=OFF') # stop (used to be 'SET SSTOP=1')
                    self.CryoTelRead()
        qm = QMessageBox(QMessageBox.Icon.Information ,'Water cooling!', f"Remember to turn {'on' if on else 'off'} water cooling!", buttons=QMessageBox.StandardButton.Ok)
        qm.setWindowIcon(self.device.getIcon())
        qm.exec()

    def setTemperature(self, channel):
        if not self.device.getTestMode() and self.initialized:
            if channel.controler == channel.CRYOTEL:
                Thread(target=self.setTemperatureFromThread, args=(channel,)).start()

    def setTemperatureFromThread(self, channel):
        with self.lock:
            self.CryoTelWrite(f'TTARGET={channel.value}') # used to be SET TTARGET=
            self.CryoTelRead()

    # use following from internal console for testing
    # Temperature.controller.lock.acquire();Temperature.controller.CryoTelWrite('TC'); print(Temperature.controller.CryoTelRead());Temperature.controller.lock.release()

    def CryoTelWrite(self, message):
        self.serialWrite(self.port, f'{message}\r')
        self.CryoTelRead() # repeats query

    def CryoTelRead(self):
        return self.serialRead(self.port)

    def CryoTelClearBuffer(self):
        x = self.port.inWaiting()
        if x > 0:
            self.port.read(x)
