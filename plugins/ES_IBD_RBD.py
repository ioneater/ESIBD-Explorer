# pylint: disable=[missing-module-docstring] # only single class in module
import time
from threading import Thread
import serial
import numpy as np
from PyQt6.QtCore import QObject,pyqtSignal,pyqtSlot
from ES_IBD_core import ESIBD_Parameter,parameterDict
from ES_IBD_controls import ESIBD_Output_Device,ESIBD_Output_Channel

def initialize(esibdWindow):
    CurrentConfig(esibdWindow=esibdWindow)

class CurrentConfig(ESIBD_Output_Device):
    """Bundles multiple real and virtual current channels into a single object to handle shared functionality"""

    def __init__(self,**kwargs):
        super().__init__(**kwargs,name = 'RBD',channelType = CurrentConfigItem)
        self.addButton(1,0,'Reset C',func=self.resetCharge,toolTip='Plot values')
        self.addButton(1,1,'Init',func=lambda : self.init(restart=self.esibdWindow.outputWidget.acquiring),toolTip='Initialize communication')
        self.unit = 'pA'

    def getDefaultSettings(self):
        """ Define device specific settings that will be added to the general settings tab.
        These will be included if the settings file is deleted and automatically regenerated.
        Overwrite as needed."""
        settings = super().getDefaultSettings()
        settings['RBD/Interval'] = parameterDict(value = 100,_min = 100,_max = 10000,toolTip = 'Smurf meter sampling interval in ms',
                                                                widgetType = ESIBD_Parameter.WIDGETINT,event = self.restart,attr = 'interval')
        return settings

    def getInitializedChannels(self):
        return [d for d in self.channels if d.enabled and (d.device.port is not None or self.getTestmode() or not d.active)]

    def init(self, restart=False):
        for channel in self.channels:
            if channel.enabled:
                channel.device.init(restart)
            elif channel.device.acquiring:
                channel.device.stopSampling()
        self.initialized = True

    def startSampling(self):
        for channel in self.channels:
            if channel.enabled:
                channel.device.startSampling()

    def stopSampling(self):
        for channel in self.channels:
            channel.device.stopSampling()

    def restart(self):
        for channel in self.channels:
            channel.restart()

    def resetCharge(self):
        for d in self.channels:
            d.charge = 0
            d.preciceCharge = 0

    def close(self):
        super().close()
        for channel in self.channels:
            channel.device.close()

    # from https://stackoverflow.com/questions/12090503/listing-available-com-ports-with-python
    # this slows down program start too much -> skip this test and see which ports connect or give an error
    def serial_ports(self):
        """ Lists serial port names
            :raises EnvironmentError:
                On unsupported or unknown platforms
            :returns:
                A list of the serial ports available on the system
        """
        # ports = ['COM%s' % (i + 1) for i in range(20)] # need to increase if ever using more than 20 com ports
        # result = []
        # for port in ports:
            # try:
                # s = serial.Serial(port)
                # s.close()
                # result.append(port)
            # except (OSError,serial.SerialException):
                # pass
        # return result
        return ','.join([f'COM{x}' for x in range(3,25)]) # need to increase maximum COM port if needed

class CurrentConfigItem(ESIBD_Output_Channel):
    """UI for picoampmeter with integrated functionality"""

    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.device = RBDChannel(channel = self)
        self.preciceCharge = 0 # store independent of spin box precision to avoid rounding errors

    def getDefaultChannel(self):
        """Gets default settings and values."""
        channel = super().getDefaultChannel()
        channel[self.VALUE][ESIBD_Parameter.HEADER ] = 'I (pA)' # overwrite existing parameter to change header
        self.CHARGE                  = 'Charge'
        channel[self.CHARGE     ] = parameterDict(value = 0,widgetType = ESIBD_Parameter.WIDGETFLOAT,advanced = False,header = 'C (pAh)',attr = 'charge')
        self.COM        = 'COM'
        channel[self.COM        ] = parameterDict(value = 'COM1',widgetType = ESIBD_Parameter.WIDGETCOMBO,advanced = True,
                                        items = self.parent.serial_ports(),header = 'COM',attr = 'com')
        self.DEVICENAME = 'DEVICENAME'
        channel[self.DEVICENAME ] = parameterDict(value = 'smurf',widgetType = ESIBD_Parameter.WIDGETLABEL,advanced = True,attr = 'devicename')
        self.RANGE      = 'RANGE'
        channel[self.RANGE      ] = parameterDict(value = 'auto',widgetType = ESIBD_Parameter.WIDGETCOMBO,advanced = True,
                                        items = 'auto,2 nA,20 nA,200 nA,2 µA,20 µA,200 µA,2 mA',attr = 'range',
                                        event = self.updateRange)
        self.AVERAGE    = 'AVERAGE'
        channel[self.AVERAGE    ] = parameterDict(value = 'off',widgetType = ESIBD_Parameter.WIDGETCOMBO,advanced = True,
                                        items = 'off,2,4,8,16,32',attr = 'average',
                                        event = self.updateAverage)
        self.BIAS       = 'BIAS'
        channel[self.BIAS       ] = parameterDict(value = False,widgetType = ESIBD_Parameter.WIDGETBOOL,advanced = True,
                                        toolTip = 'Apply internal bias.',attr = 'bias',
                                        event = self.updateBias)
        self.OUTOFRANGE = 'OUTOFRANGE'
        channel[self.OUTOFRANGE ] = parameterDict(value = False,widgetType = ESIBD_Parameter.WIDGETBOOL,advanced = False,
                                        header = 'OoR',toolTip = 'Indicates if signal is out of range.',attr = 'outOfRange')
        self.UNSTABLE   = 'UNSTABLE'
        channel[self.UNSTABLE   ] = parameterDict(value = False,widgetType = ESIBD_Parameter.WIDGETBOOL,advanced = False,
                                        header = 'U',toolTip = 'Indicates if signal is out of unstable.',attr = 'unstable')
        self.ERROR      = 'ERROR'
        channel[self.ERROR      ] = parameterDict(value = '',widgetType = ESIBD_Parameter.WIDGETLABEL,advanced = False,attr = 'error')
        channel = {k: channel[k] for k in [self.ENABLED,self.NAME,self.VALUE,self.EQUATION,self.BACKGROUND,self.CHARGE,self.DISPLAY,self.ACTIVE,self.REAL,self.LINEWIDTH,
                                            self.COM,self.DEVICENAME,self.RANGE,self.AVERAGE,self.BIAS,self.OUTOFRANGE,self.UNSTABLE,self.ERROR,self.COLOR]}
        return channel

    def tempParameters(self):
        return super().tempParameters() + [self.CHARGE,self.OUTOFRANGE,self.UNSTABLE,self.ERROR]

    def enabledChanged(self): # overwrite parent method
        """Handle changes while acquisition is running. All other changes will be handled when acquisition starts."""
        if self.esibdWindow.outputWidget is not None and self.esibdWindow.outputWidget.acquiring:
            if self.enabled:
                self.device.init(restart=True)
            elif self.device.acquiring:
                self.device.stopSampling()
                self.clearHistory()

    def appendValue(self):
        # calculate deposited charge in last timestep for all channels
        # this does not only monitor the sample but also on what lenses charge is lost
        # make sure that the data interval is the same as used in data acquisition
        super().appendValue()
        chargeIncrement = (self.value-self.background)*self.parent.interval/1000/3600 if self.values.size > 1 else 0
        self.preciceCharge += chargeIncrement # display accumulated charge # don't use np.sum(self.charges) to allow
        self.charge = self.preciceCharge # pylint: disable=[attribute-defined-outside-init] # attribute defined by makeWrapper

    def clearHistory(self):
        super().clearHistory()
        self.charge = 0 # pylint: disable=[attribute-defined-outside-init] # attribute defined by makeWrapper

    def restart(self): # restart if parameters changed while acquiring
        if self.device is not None and self.device.acquiring:
            self.device.init(True)

    def realChanged(self):
        self.getParameterByName(self.COM).getWidget().setVisible(self.real)
        self.getParameterByName(self.RANGE).getWidget().setVisible(self.real)
        self.getParameterByName(self.AVERAGE).getWidget().setVisible(self.real)
        self.getParameterByName(self.BIAS).getWidget().setVisible(self.real)
        self.getParameterByName(self.OUTOFRANGE).getWidget().setVisible(self.real)
        self.getParameterByName(self.UNSTABLE).getWidget().setVisible(self.real)
        super().realChanged()

    def updateAverage(self):
        if self.device is not None and self.device.acquiring:
            self.device.updateAverageFlag = True

    def updateRange(self):
        if self.device is not None and self.device.acquiring:
            self.device.updateRangeFlag = True

    def updateBias(self):
        if self.device is not None and self.device.acquiring:
            self.device.updateBiasFlag = True

class RBDChannel(QObject):
    # need to inherit from QObject to allow use of signals
    """Implements serial communication with RBD 9103.
    While this is kept as general as possible,some access to the management and UI parts are required for proper integration."""

    class SignalCommunicate(QObject): # signals called from external thread and run in main thread
        initCompleteSignal = pyqtSignal()
        updateValueSignal = pyqtSignal(float,bool,bool,str)
        updatePortSignal = pyqtSignal(serial.serialwin32.Serial,str)

    def __init__(self,channel):
        super().__init__()
        #setup port
        self.channel = channel
        self.initThread = None
        self.aquisitionThread = None
        self.port = None # have to store port here as thread dies after initialization. Still we should avoid to use the port outside of the thread to avoid race conditions
        # self.init() only init once explicitly called
        self.signalComm = self.SignalCommunicate()
        self.signalComm.updatePortSignal.connect(self.updatePort)
        self.signalComm.initCompleteSignal.connect(self.initComplete)
        self.signalComm.updateValueSignal.connect(self.updateValue)
        self.updateAverageFlag = False
        self.updateRangeFlag = False
        self.updateBiasFlag = False
        self.acquiring = False
        self.initialized = False
        self.restart = False
        self.phase = np.random.rand()*10 # used in test mode
        self.offset = np.random.rand()*10 # used in test mode

    def init(self,restart):
        if self.channel.enabled and self.channel.active:
            self.close() # terminate old thread before starting new one
            # threads cannot be restarted -> make new thread every time. possibly there are cleaner solutions
            self.restart=restart
            self.initThread = Thread(target = self.runInitialization)
            self.initThread.daemon = True
            self.initThread.start() # initialize in separate thread
            # startSampling will called by main app shortly,no need to restart here

    @pyqtSlot(serial.serialwin32.Serial,str)
    def updatePort(self,port,name):
        self.port=port
        self.channel.devicename = name

    @pyqtSlot()
    def initComplete(self):
        self.initialized = True
        if self.restart:
            if self.channel.parent.getTestmode():
                self.signalComm.updateValueSignal.emit(0,False,False,f'{self.channel.devicename} Warning: Faking values for testing!')
            self.startSampling()
            self.restart=False

    @pyqtSlot(float,bool,bool,str)
    def updateValue(self,value,outOfRange,unstable,error=''):
        self.channel.value = value
        self.channel.outOfRange = outOfRange
        self.channel.unstable = unstable
        self.channel.error = error
        if error != '':
            self.channel.printFromThread(error)

    def startSampling(self):
        # only run if init succesful,or in test mode. if channel is not active it will calculate value independently
        if (self.port is not None or self.channel.parent.getTestmode()) and self.channel.active:
            self.aquisitionThread = Thread(target = self.runAcquisition,args =(lambda : self.acquiring,))
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
        if self.channel.parent.getTestmode():
            self.signalComm.initCompleteSignal.emit()
        else:
            try:
                port=serial.Serial(
                    f'{self.channel.com}',
                    baudrate=57600,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    xonxoff=False,
                    timeout=1)
                self.setRange(port)
                self.setAverage(port)
                self.setGrounding(port)
                self.setBias(port)
                name = self.getName(port)
                if name == '':
                    self.signalComm.updateValueSignal.emit(0,False,False,f'Device at port {self.channel.com} did not provide a name. Abort initialization.')
                    return
                self.signalComm.updateValueSignal.emit(0,False,False,f'{name} initialized at {self.channel.com}')
                self.signalComm.updatePortSignal.emit(port,name) # pass port to main thread as init thread will die
                self.signalComm.initCompleteSignal.emit()
            except serial.serialutil.PortNotOpenError as e:
                self.signalComm.updateValueSignal.emit(0,False,False,f'Port {self.channel.com} is not open: {e}')
            except serial.serialutil.SerialException as e:
                self.signalComm.updateValueSignal.emit(0,False,False,f'9103 not found at {self.channel.com}: {e}')

    def runAcquisition(self,acquiring):
        if self.channel.parent.getTestmode():
            while acquiring():
                self.fakeSingleNum()
                self.updateParameters()
        else:
            self.port.write(self.message(f'I{self.channel.parent.interval:04d}')) # start sampling with given interval (implement high speed communication if available)
            self.port.readline()
            while acquiring():
                self.readSingleNum()
                self.updateParameters()
            self.port.write(self.message("I0000")) # stop sampling
            self.port.readline()

    def setRange(self,port):
        port.write(self.message(f'R{self.channel.getParameterByName(self.channel.RANGE).getWidget().currentIndex()}')) # set range
        port.readline()
        self.updateRangeFlag=False

    def setAverage(self,port):
        _filter = self.channel.getParameterByName(self.channel.AVERAGE).getWidget().currentIndex()
        _filter = 2**_filter if _filter > 0 else 0
        port.write(self.message(f'F0{_filter:02}')) # set filter
        port.readline()
        self.updateAverageFlag=False

    def setBias(self,port):
        port.write(self.message(f'B{int(self.channel.bias)}')) # set bias, convert from bool to int
        port.readline()
        self.updateBiasFlag=False

    def setGrounding(self,port):
        port.write(self.message('G0')) # input grounding off
        port.readline()

    def getName(self,port):
        port.write(self.message('P')) # get channel name
        name = port.readline().decode('utf-8').rstrip()
        if '=' in name:
            return name.split('=')[1]
        else:
            return ''

    def updateParameters(self):
        # call from runAquisition to make sure there are no race conditions
        if self.updateRangeFlag:
            self.setRange(self.port)
        if self.updateAverageFlag:
            self.setAverage(self.port)
        if self.updateBiasFlag:
            self.setBias(self.port)

    def command_identify(self):
        self.port.write(self.message('Q')) # put in autorange
        for _ in range(13):
            message = self.port.readline().decode('utf-8').rstrip()
            self.printFromThread(message)
            #if 'PID' in message:
           #     return message.split('=')[1] # return channel name
       # return 'channel name not found'
        # self.channel.printFromThread(message,message.split('='))
        # self.channel.printFromThread(self.port.readline()) # -> b'RBD Instruments: PicoAmmeter\r\n'
        # self.channel.printFromThread(self.port.readline()) # -> b'Firmware Version: 02.09\r\n'
        # self.channel.printFromThread(self.port.readline()) # -> b'Build: 1-25-18\r\n'
        # self.channel.printFromThread(self.port.readline()) # -> b'R,Range=AutoR\r\n'
        # self.channel.printFromThread(self.port.readline()) # -> b'I,sample Interval=0000 mSec\r\n'
        # self.channel.printFromThread(self.port.readline()) # -> b'L,Chart Log Update Interval=0200 mSec\r\n'
        # self.channel.printFromThread(self.port.readline()) # -> b'F,Filter=032\r\n'
        # self.channel.printFromThread(self.port.readline()) # -> b'B,BIAS=OFF\r\n'
        # self.channel.printFromThread(self.port.readline()) # -> b'V,FormatLen=5\r\n'
        # self.channel.printFromThread(self.port.readline()) # -> b'G,AutoGrounding=DISABLED\r\n'
        # self.channel.printFromThread(self.port.readline()) # -> b'Q,State=MEASURE\r\n'
        # self.channel.printFromThread(self.port.readline()) # -> b'P,PID=TRACKSMURF\r\n'
        # self.channel.printFromThread(self.port.readline()) # -> b'P,PID=TRACKSMURF\r\n'

    def fakeSingleNum(self):
        time.sleep(self.channel.parent.interval/1000)
        self.signalComm.updateValueSignal.emit(np.sin(time.time()/5+self.phase)*10+np.random.rand()+self.offset,False,False,'')

    def readSingleNum(self):
        msg=self.port.readline().decode('utf-8').rstrip()
        parsed = self.parse_message_for_sample(msg)
        if any (sym in parsed for sym in ['<','>']):
            self.signalComm.updateValueSignal.emit(0,True,False,parsed)
        elif '*' in parsed:
            self.signalComm.updateValueSignal.emit(0,False,True,parsed)
        elif parsed == '':
            self.signalComm.updateValueSignal.emit(0,False,False,'got empty message')
        else:
            self.signalComm.updateValueSignal.emit(self.readingToNum(parsed),False,False,'')

    #Convert string to bytes for message to 9103_port
    #all messages must end with newline
    def message(self,message_string):
        return bytes('&'+ message_string + '\n','utf-8')

    #Single sample (standard speed) message parsing
    def parse_message_for_sample(self,msg):
        if '&S' in msg:
            return msg.strip('&')
        else:
            return ''

    def readingToNum(self,parsed):  # convert to pA
        """Converts string to float value of pA based on unit"""
        try:
            _,_,x,u = parsed.split(',')
            x=float(x)
        except ValueError as e:
            self.channel.printFromThread(f'Error while parsing current: parsed: {parsed},Error: {e}')
            return self.channel.value # keep last valid value
        if u == 'mA':
            return x*1E9
        if u == 'uA':
            return x*1E6
        if u == 'nA':
            return x*1E3
        if u == 'pA':
            return x*1
        else:
            self.channel.printFromThread(f'Error: No handler for unit {u} implemented!')
            return self.channel.value # keep last valid value
            #raise ValueError(f'No handler for unit {u} implemented!')
