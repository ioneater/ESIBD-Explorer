# pylint: disable=[missing-module-docstring] # only single class in module
import socket
from threading import Thread
import time
import numpy as np
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot
import ES_IBD_configuration as conf

class VoltageManager(QObject): # no channels needed
    """Implements SCPI comminication with ISEG ECH244.
    While this is keept as general as possible, some access to the management and UI parts are required for proper integration"""

    updateMonitorsSignal= pyqtSignal()
    initCompleteSignal= pyqtSignal(socket.socket)

    def __init__(self, esibdWindow = None, parent=None, modules = None):
        super().__init__()
        self.esibdWindow=esibdWindow
        self.parent     = parent
        self.modules    = modules or [0]
        self.updateMonitorsSignal.connect(self.updateMonitors)
        self.initCompleteSignal.connect(self.initComplete)
        self.IP = 'localhost'
        self.port = 0
        self.s          = None
        self.restart = False
        self.initialized= False
        self.initThread = None
        self.monitoringThread = None
        self.monitoring = False
        self.voltages   = np.zeros([len(modules),24])

    def init(self, IP='localhost', port = 0, restart = False):
        self.IP = IP
        self.port = port
        self.restart = restart
        self.initThread = Thread(target = self.runInit)
        self.initThread.daemon=True
        self.initThread.start() # init in background

    def runInit(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((self.IP, self.port))
            s.sendall('*IDN?\r\n'.encode('utf-8'))
            self.esibdWindow.signalComm.printFromThreadSignal.emit(s.recv(4096).decode("utf-8"))
            self.initialized = True
            self.initCompleteSignal.emit(s)
            # threads cannot be restarted -> make new thread every time. possibly there are cleaner solutions
        except OSError:
            self.esibdWindow.signalComm.printFromThreadSignal.emit(f'Could not establish SCPI connection to {self.IP} on port {self.port}')

    @pyqtSlot(socket.socket)
    def initComplete(self, s):
        self.s = s
        self.monitoringThread = Thread(target = self.runMonitoring, args =(lambda : self.monitoring,))
        self.monitoringThread.daemon=True
        self.monitoring=True
        self.monitoringThread.start() # read samples in separate thread
        self.voltageON(self.restart)

    def close(self):
        if self.monitoringThread is not None:
            self.monitoring=False
            self.monitoringThread.join()
            self.initialized = False

    def read(self, initializing = False):
        if self.initialized or initializing:
            return self.s.recv(4096).decode("utf-8")

    def setVoltage(self, channel):
        if self.initialized:
            self.s.sendall(f':VOLT {channel.voltage if channel.enabled else 0},(#{channel.module}@{channel.id})\r\n'.encode('utf-8'))
            self.read()

    @pyqtSlot()
    def updateMonitors(self):
        """read actual voltages and send them to user interface"""
        for m in self.modules:
            self.s.sendall(f':MEAS:VOLT? (#{m}@0-24)\r\n'.encode('utf-8'))
            res = self.read()#. rstripreplace('\r\n','')
            if res != '':
                try:
                    monitors = [float(x[:-1]) for x in res[:-4].split(',')] # res[:-4] to remove trainling '\r\n'
                    # fill up to 24 to handle all modules the same independent of the number of channels. Need to increase when using modules with more than 24 channels
                    self.voltages[m] = np.hstack([monitors,np.zeros(24-len(monitors))])
                except ValueError as e:
                    self.esibdWindow.signalComm.printFromThreadSignal.emit(f'ValueError: {e} for {res}')
        # if self.voltages:
        for channel in self.parent.channels:
            if channel.real:
                channel.monitor = self.voltages[channel.module][channel.id]

    def voltageON(self, on = False): # this can run in main thread
        self.esibdWindow.voltageConfig.updateVoltage(True) # apply voltages before turning modules on or off
        if self.initialized:
            for m in self.modules:
                self.s.sendall(f":VOLT {'ON' if on else 'OFF'},(#{m}@0-23)\r\n".encode('utf-8'))
                self.read()

    def runMonitoring(self,monitoring):
        while monitoring():
            self.updateMonitorsSignal.emit() # signal main thread that data should be collected / avoid directly accessing socket from parallel thread
            time.sleep(self.esibdWindow.settingsMgr[conf.MONITORINTERVAL].value/1000)
