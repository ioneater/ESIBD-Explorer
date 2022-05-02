# pylint: disable=[missing-module-docstring] # only single class in module
import time
from threading import Thread
import serial
import numpy as np
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot

class CurrentChannel(QObject):
    """Implements serial comminication with RBD 9103.
    While this is keept as general as possible, some access to the management and UI parts are required for proper integration"""

    initCompleteSignal = pyqtSignal()
    updateCurrentSignal = pyqtSignal(float, bool, bool, str)
    updatePortSignal = pyqtSignal(serial.serialwin32.Serial, str)

    def __init__(self, esibdWindow, device):
        super().__init__()
        #setup port
        self.device = device
        self.esibdWindow = esibdWindow
        self.initThread = None
        self.aquisitionThread = None
        self.port = None # have to store port here as thread dies after initialization. Still we should avoid to use the port outside of the thread to avoid race conditions
        # self.init() only init once explicitly called
        self.updatePortSignal.connect(self.updatePort)
        self.initCompleteSignal.connect(self.initComplete)
        self.updateCurrentSignal.connect(self.updateCurrent)
        self.acquiring = False
        self.initialized = False
        self.interval = 100
        self.restart = False
        self.phase = np.random.rand()*10 # used in test mode
        self.offset = np.random.rand()*10 # used in test mode

    def init(self, restart):
        if self.device.enabled and self.device.real:
            if self.aquisitionThread is not None and self.initialized:
                self.acquiring = False # terminate old thread before starting new one
                self.aquisitionThread.join() # wait for it to terminate
                if self.port is not None:
                    self.port.close()
                self.initialized=False
            # threads cannot be restarted -> make new thread every time. possibly there are cleaner solutions
            self.restart=restart
            self.initThread = Thread(target = self.runInitialization)
            self.initThread.daemon = True
            self.initThread.start() # initialize in separate thread
            # startSampling will called by main app shortly, no need to restart here

    @pyqtSlot(serial.serialwin32.Serial,str)
    def updatePort(self, port, name):
        self.port=port
        self.device.name = name

    @pyqtSlot()
    def initComplete(self):
        self.initialized = True
        if self.restart:
            self.startSampling(interval = 100)
            self.restart=False

    @pyqtSlot(float, bool, bool, str)
    def updateCurrent(self,current,outOfRange,unstable,error):
        self.device.current = current
        self.device.outOfRange = outOfRange
        self.device.unstable = unstable
        self.device.error = error

    def startSampling(self, interval = 100):
        self.interval = interval
        if self.port is not None or self.esibdWindow.testMode: # otherwise init failed
            self.aquisitionThread = Thread(target = self.runAcquisition, args =(lambda : self.acquiring,))
            self.aquisitionThread.daemon = True
            self.acquiring = True # terminate old thread before starting new one
            self.aquisitionThread.start() # read samples in separate thread

    def stopSampling(self):
        if self.aquisitionThread is not None:
            self.acquiring = False
            self.aquisitionThread.join()

    def close(self):
        self.stopSampling()
        if self.port is not None:
            self.port.close()
        self.initialized = False

    def runInitialization(self):
        """Initializes serial port in paralel thread"""
        # self.esibdWindow.signalComm.printFromThreadSignal.emit('runInitialization started')
        if self.esibdWindow.testMode:
            self.initCompleteSignal.emit()
        else:
            try:
                port=serial.Serial(
                    f'{self.device.com}',
                    baudrate=57600,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    xonxoff=False,
                    timeout=1)
                port.write(self.message(f'R{self.device.rangeComboBox.currentIndex()}')) # set range
                port.readline()
                _filter = self.device.averageComboBox.currentIndex()
                _filter = 2**_filter if _filter > 0 else 0
                port.write(self.message(f'F0{_filter:02}')) # set filter
                port.readline()
                port.write(self.message('G0')) # input grounding off
                port.readline()
                port.write(self.message(f'B{int(self.device.bias)}')) # set bias
                port.readline()
                port.write(self.message('P')) # get device name
                name = port.readline().decode('utf-8').rstrip()
                if '=' in name:
                    name = name.split('=')[1]
                else:
                    name = 'Not connected'
                self.updateCurrentSignal.emit(0,False,False,f'9103 initialized at {self.device.com}')
                self.updatePortSignal.emit(port,name)
                self.initCompleteSignal.emit()
            except serial.serialutil.SerialException as e:
                self.updateCurrentSignal.emit(0,False,False,f'9103 not found at {self.device.com}: {e}')

        # self.esibdWindow.signalComm.printFromThreadSignal.emit('runInitialization finished')

    def runAcquisition(self,acquiring):
        # self.esibdWindow.signalComm.printFromThreadSignal.emit('runAcquisition started')
        if self.esibdWindow.testMode:
            while acquiring():
                self.fakeSingleNum()
        else:
            self.port.write(self.message(f'I{self.interval:04d}')) # start sampling with given interval (implement high speed communication if available)
            self.port.readline()
            while acquiring():
                self.readSingleNum()
                # self.esibdWindow.signalComm.printFromThreadSignal.emit('runAcquisition running')
            self.port.write(self.message("I0000")) # stop sampling
            self.port.readline()
        # self.esibdWindow.signalComm.printFromThreadSignal.emit('runAcquisition finished')

    def command_identify(self):
        self.port.write(self.message('Q')) # put in autorange
        # self.esibdWindow.signalComm.printFromThreadSignal.emit(self.port.read()) # only works if you specify number of bites
        for _ in range(13):
            message = self.port.readline().decode('utf-8').rstrip()
            self.esibdWindow.signalComm.printFromThreadSignal.emit(message)
            #if 'PID' in message:
           #     return message.split('=')[1] # return device name
       # return 'Device name not found'
                # self.esibdWindow.signalComm.printFromThreadSignal.emit(message,message.split('='))
        # self.esibdWindow.signalComm.printFromThreadSignal.emit(self.port.readline()) # -> b'RBD Instruments: PicoAmmeter\r\n'
        # self.esibdWindow.signalComm.printFromThreadSignal.emit(self.port.readline()) # -> b'Firmware Version: 02.09\r\n'
        # self.esibdWindow.signalComm.printFromThreadSignal.emit(self.port.readline()) # -> b'Build: 1-25-18\r\n'
        # self.esibdWindow.signalComm.printFromThreadSignal.emit(self.port.readline()) # -> b'R, Range=AutoR\r\n'
        # self.esibdWindow.signalComm.printFromThreadSignal.emit(self.port.readline()) # -> b'I, sample Interval=0000 mSec\r\n'
        # self.esibdWindow.signalComm.printFromThreadSignal.emit(self.port.readline()) # -> b'L, Chart Log Update Interval=0200 mSec\r\n'
        # self.esibdWindow.signalComm.printFromThreadSignal.emit(self.port.readline()) # -> b'F, Filter=032\r\n'
        # self.esibdWindow.signalComm.printFromThreadSignal.emit(self.port.readline()) # -> b'B, BIAS=OFF\r\n'
        # self.esibdWindow.signalComm.printFromThreadSignal.emit(self.port.readline()) # -> b'V, FormatLen=5\r\n'
        # self.esibdWindow.signalComm.printFromThreadSignal.emit(self.port.readline()) # -> b'G, AutoGrounding=DISABLED\r\n'
        # self.esibdWindow.signalComm.printFromThreadSignal.emit(self.port.readline()) # -> b'Q, State=MEASURE\r\n'
        # self.esibdWindow.signalComm.printFromThreadSignal.emit(self.port.readline()) # -> b'P, PID=TRACKSMURF\r\n'
        # self.esibdWindow.signalComm.printFromThreadSignal.emit(self.port.readline()) # -> b'P, PID=TRACKSMURF\r\n'


    def fakeSingleNum(self):
        time.sleep(self.interval/1000)
        # self.esibdWindow.signalComm.printFromThreadSignal.emit('fake single num')
        self.updateCurrentSignal.emit(np.sin(time.time()/5+self.phase)*10+np.random.rand()+self.offset,False,False,'ATTENTION: This signal is autogenerated!')
        #self.device.current = np.sin(time.time()/10)*10 # generate fake signal

    def readSingleNum(self):
        msg=self.port.readline().decode('utf-8').rstrip()
        parsed = self.parse_message_for_sample(msg)
        # self.esibdWindow.signalComm.printFromThreadSignal.emit(msg,parsed)
        if any (sym in parsed for sym in ['<','>']):
            self.updateCurrentSignal.emit(0,True,False,parsed)
        elif '*' in parsed:
            self.updateCurrentSignal.emit(0,False,True,parsed)
        elif parsed == '':
            self.updateCurrentSignal.emit(0,False,False,'got empty message')
        else:
            self.updateCurrentSignal.emit(self.readingToNum(parsed),False,False,'')

    #Convert string to bytes for message to 9103_port
    #all messages must end with newline
    def message(self,message_string):
        return bytes('&'+ message_string + '\n','utf-8')

    #Single sample (standard speed) message parsing
    def parse_message_for_sample(self, msg):
        if '&S' in msg:
            return msg.strip('&')
        else:
            return ''

    def readingToNum(self, parsed):  # convert to pA
        """Converts string to float value of pA based on unit"""
        try:
            _,_,x,u = parsed.split(',')
            x=float(x)
        except ValueError as e:
            self.esibdWindow.signalComm.printFromThreadSignal.emit(f'Error while parsing current: parsed: {parsed}, Error: {e}')
            return self.device.current # keep last valid value
        if u == 'mA':
            return x*1E9
        if u == 'uA':
            return x*1E6
        if u == 'nA':
            return x*1E3
        if u == 'pA':
            return x*1
        else:
            self.esibdWindow.signalComm.printFromThreadSignal.emit(f'No handler for unit {u} implemented!')
            return self.device.current # keep last valid value
            #raise ValueError(f'No handler for unit {u} implemented!')
