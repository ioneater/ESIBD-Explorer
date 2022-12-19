# pylint: disable=[missing-module-docstring] # only single class in module
import socket
from threading import Thread
import time
from random import choices
import numpy as np
from PyQt6.QtCore import QObject,pyqtSignal,pyqtSlot
from ES_IBD_core import INOUT,ESIBD_Parameter,parameterDict
from ES_IBD_controls import ESIBD_Input_Device,ESIBD_Input_Channel

########################## Voltage user interface #################################################

def initialize(esibdWindow):
    VoltageConfig(esibdWindow=esibdWindow)

class VoltageConfig(ESIBD_Input_Device):
    """Bundles multiple real and virtual voltage channels into a single object to handle shared functionality"""
    # internal settings keys

    def __init__(self,**kwargs):
        super().__init__(**kwargs,name = 'ISEG',channelType = VoltageConfigItem)

        self.voltageMgr = VoltageManager(parent=self,modules = self.getModules()) # after all channels loaded
        self.addButton(1,0,'Init',func=lambda : self.init(restart = self.onButton.isChecked()),toolTip='(Re-)initialize device.')
        self.onButton = self.esibdWindow.outputWidget.addButton(0,-1,f'{self.name} ON',func=self.voltageON,toolTip='Turn ON/OFF',checkable=True)
        self.unit = 'V'

    def getDefaultSettings(self):
        """ Define device specific settings that will be added to the general settings tab.
        These will be included if the settings file is deleted and automatically regenerated.
        Overwrite as needed."""
        settings = super().getDefaultSettings()
        settings['ISEG/IP']       = parameterDict(value = '169.254.163.182',toolTip = 'IP address of ECH244',
                                                                widgetType = ESIBD_Parameter.WIDGETTEXT,attr = 'ip')
        settings['ISEG/Port']     = parameterDict(value = 10001,toolTip = 'SCPI port of ECH244',
                                                                widgetType = ESIBD_Parameter.WIDGETINT,attr = 'port')
        settings['ISEG/Interval'] = parameterDict(value = 1000,toolTip = 'Interval for monitoring in ms',
                                                                widgetType = ESIBD_Parameter.WIDGETINT,_min = 100,_max = 10000,attr = 'interval')
        return settings

    def getModules(self): # get list of used modules
        return set([channel.module for channel in self.channels])

    def init(self,restart = False):
        if restart:
            self.onButton.setChecked(restart)
            self.onButton.setStyleSheet('background-color : #ee7878')
        self.voltageMgr.init(IP = self.ip,port = int(self.port),restart = restart)

    def close(self):
        super().close()
        self.esibdWindow.outputWidget.globalUpdate(apply = True,inout = INOUT.IN) # apply voltages before turning modules on or off
        self.voltageMgr.voltageON(False)
        self.voltageMgr.close()

    def apply(self,apply):
        for c in self.channels:
            c.setVoltage(apply) # only actually sets voltage if configured and value has changed

    def voltageON(self):
        if self.voltageMgr.initialized or self.getTestmode():
            self.esibdWindow.outputWidget.globalUpdate(apply = True,inout = INOUT.IN) # apply voltages before turning modules on or off
            self.voltageMgr.voltageON(self.onButton.isChecked())
        else:
            self.init(restart=True)
        self.onButton.setStyleSheet('background-color : #ee7878' if self.onButton.isChecked() else '')

class VoltageConfigItem(ESIBD_Input_Channel):
    """UI for single voltage channel with integrated functionality"""

    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.lastAppliedVoltage = None # keep track of last value to identify what has changed
        self.warningStyleSheet = f'background: rgb({255},{0},{0})'
        self.defaultStyleSheet = None # will be initialized when color is set

    def getDefaultChannel(self):
        channel = super().getDefaultChannel()
        channel[self.VALUE][ESIBD_Parameter.HEADER] = 'Voltage (V)' # overwrite to change header
        self.MONITOR   = 'Monitor'
        channel[self.MONITOR ] = parameterDict(value = 0,widgetType = ESIBD_Parameter.WIDGETFLOAT,advanced = False,
                                    event = self.monitorChanged,attr = 'monitor')
        self.MODULE    = 'MODULE'
        channel[self.MODULE  ] = parameterDict(value = 0,widgetType =  ESIBD_Parameter.WIDGETINT,advanced = True,
                                    header = 'MOD',_min = 0,_max = 99,attr = 'module')
        self.ID        = 'ID'
        channel[self.ID      ] = parameterDict(value = 0,widgetType =  ESIBD_Parameter.WIDGETINT,advanced = True,
                                    header = 'ID',_min = 0,_max = 99,attr = 'id')
        channel = {k: channel[k] for k in [self.SELECT,self.ENABLED,self.NAME,self.VALUE,self.MONITOR,self.MIN,self.MAX,self.EQUATION,self.OPTIMIZE,
                                            self.ACTIVE,self.REAL,self.MODULE,self.ID,self.COLOR]}
        return channel

    def tempParameters(self):
        return super().tempParameters() + [self.MONITOR]

    def finalizeInit(self,item):
        super().finalizeInit(item)
        # overwrite limits with specific save voltage range. all other properties for self.MIN/self.MAX are inherited from parent
        _min = self.getParameterByName(self.MIN)
        _min.spin.setMinimum(-200)
        _min.spin.setMaximum(200)
        _max = self.getParameterByName(self.MAX)
        _max.spin.setMinimum(-200)
        _max.spin.setMaximum(200)

    def setVoltage(self,apply): # this actually sets the voltage on the powersupply!
        if self.real and ((self.value != self.lastAppliedVoltage) or apply):
            self.parent.voltageMgr.setVoltage(self)
            self.lastAppliedVoltage = self.value

    def updateColor(self):
        super().updateColor()
        self.defaultStyleSheet = f'background: rgb({self.color.red()},{self.color.green()},{self.color.blue()})'

    def monitorChanged(self):
        if self.enabled and self.parent.voltageMgr.monitoring and ((self.parent.voltageMgr.ON and abs(self.monitor - self.value) > 1)
                                                                    or (not self.parent.voltageMgr.ON and abs(self.monitor - 0) > 1)):
            self.getParameterByName(self.MONITOR).getWidget().setStyleSheet(self.warningStyleSheet)
        else:
            self.getParameterByName(self.MONITOR).getWidget().setStyleSheet(self.defaultStyleSheet)

    def realChanged(self):
        self.getParameterByName(self.MONITOR).getWidget().setVisible(self.real)
        self.getParameterByName(self.MODULE).getWidget().setVisible(self.real)
        self.getParameterByName(self.ID).getWidget().setVisible(self.real)
        super().realChanged()

class VoltageManager(QObject): # no channels needed
    # need to inherit from QObject to allow use of signals
    """Implements SCPI communication with ISEG ECH244.
    While this is kept as general as possible,some access to the management and UI parts are required for proper integration."""
    updateMonitorsSignal= pyqtSignal()
    initCompleteSignal= pyqtSignal(socket.socket)

    def __init__(self,parent,modules):
        super().__init__()
        self.parent     = parent
        self.modules    = modules or [0]
        self.updateMonitorsSignal.connect(self.updateMonitors)
        self.initCompleteSignal.connect(self.initComplete)
        self.IP = 'localhost'
        self.port = 0
        self.ON         = False
        self.s          = None
        self.restart = False
        self.initialized= False
        self.initThread = None
        self.monitoringThread = None
        self.monitoring = False
        self.maxID = max([c.id if c.real else 0 for c in self.parent.channels]) # used to query correct amount of monitors
        self.voltages   = np.zeros([len(self.modules),self.maxID+1])

    def init(self,IP='localhost',port = 0,restart = False):
        if self.monitoringThread is not None:
            self.close() # terminate old thread before starting new one
        self.IP = IP
        self.port = port
        self.restart = restart
        self.initThread = Thread(target = self.runInit)
        self.initThread.daemon=True
        self.initThread.start() # init in background

    def runInit(self):
        """initializes socket for SCPI communication"""
        if self.parent.getTestmode():
            self.parent.printFromThread('ISEG Warning: Faking monitor values for testing!')
            self.initialized = False
            self.initCompleteSignal.emit(socket.socket())
        else:
            try:
                s = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
                s.connect((self.IP,self.port))
                s.sendall('*IDN?\r\n'.encode('utf-8'))
                self.parent.printFromThread(s.recv(4096).decode("utf-8"))
                self.initialized = True
                self.initCompleteSignal.emit(s)
                # threads cannot be restarted -> make new thread every time. possibly there are cleaner solutions
            except Exception as e: # pylint: disable=[broad-except] # socket does not throw more specific exception
                self.parent.printFromThread(
                    f'Warning: Could not establish SCPI connection to {self.IP} on port {self.port}. Exception: {e}')

    @pyqtSlot(socket.socket)
    def initComplete(self,s):
        self.s = s
        self.monitoringThread = Thread(target = self.runMonitoring,args =(lambda : self.monitoring,))
        self.monitoringThread.daemon=True
        self.monitoring=True
        self.monitoringThread.start() # read samples in separate thread
        self.voltageON(self.restart)

    def close(self):
        if self.monitoringThread is not None:
            self.monitoring=False
            self.monitoringThread.join()
            self.initialized = False

    def read(self,initializing = False):
        if self.initialized or initializing:
            return self.s.recv(4096).decode("utf-8")

    def setVoltage(self,channel):
        if self.initialized:
            self.s.sendall(f':VOLT {channel.value if channel.enabled else 0},(#{channel.module}@{channel.id})\r\n'.encode('utf-8'))
            self.read()

    @pyqtSlot()
    def updateMonitors(self):
        """read actual voltages and send them to user interface"""
        # print('updateMonitors',np.random.rand())
        if self.parent.getTestmode():
            self.fakeMonitors()
        else:
            for m in self.modules:
                self.s.sendall(f':MEAS:VOLT? (#{m}@0-{self.maxID+1})\r\n'.encode('utf-8'))
                res = self.read()#. rstripreplace('\r\n','')
                if res != '':
                    try:
                        monitors = [float(x[:-1]) for x in res[:-4].split(',')] # res[:-4] to remove trainling '\r\n'
                        # fill up to self.maxID to handle all modules the same independent of the number of channels.
                        self.voltages[m] = np.hstack([monitors,np.zeros(self.maxID+1-len(monitors))])
                    except ValueError as e:
                        self.parent.printFromThread(f'ValueError: {e} for {res}')
            for channel in self.parent.channels:
                if channel.real:
                    channel.monitor = self.voltages[channel.module][channel.id]

    def voltageON(self,on = False): # this can run in main thread
        self.ON = on
        if self.initialized:
            for m in self.modules:
                self.s.sendall(f":VOLT {'ON' if on else 'OFF'},(#{m}@0-{self.maxID})\r\n".encode('utf-8'))
                self.read()
        elif self.parent.getTestmode():
            self.fakeMonitors()

    def fakeMonitors(self):
        for channel in self.parent.channels:
            if channel.real:
                if self.parent.voltageMgr.ON and channel.enabled:
                    # fake values with noise and 10% channels with offset to simulate defect channel or short
                    channel.monitor = channel.value + 5*choices([0,1],[.9,.1])[0] + np.random.rand()
                else:
                    channel.monitor = 0             + 5*choices([0,1],[.9,.1])[0] + np.random.rand()

    def runMonitoring(self,monitoring):
        while monitoring():
            self.updateMonitorsSignal.emit() # signal main thread that data should be collected / avoid directly accessing socket from parallel thread
            time.sleep(self.parent.interval/1000)
