# pylint: disable=[missing-module-docstring] # only single class in module
import time
import h5py
import serial
import numpy as np
from PyQt6.QtCore import pyqtSignal
from esibd.plugins import Device, StaticDisplay, Scan
from esibd.core import Parameter, parameterDict, PluginManager, Channel, PRINT, DeviceController, MetaChannel, getTestMode

def providePlugins():
    return [Current]

class Current(Device):
    """Device that contains a list of current channels, each corresponding to a single RBD
    9103 picoammeter. The channels show the accumulated charge over time,
    which is proportional to the number of deposited ions. It can also
    reveal on which elements ions are lost."""
    documentation = None # use __doc__

    name = 'RBD'
    version = '1.0'
    supportedVersion = '0.6'
    pluginType = PluginManager.TYPE.OUTPUTDEVICE
    unit = 'pA'

    class StaticDisplay(StaticDisplay):
        """A display for device data from files."""

        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.previewFileTypes.append('.cur.rec')
            self.previewFileTypes.append('.cur.h5')
            self.previewFileTypes.append('OUT.h5')

        def loadDataInternal(self, file):
            """Extending to support legacy files"""
            if file.name.endswith('.cur.rec'):  # legacy ESIBD Control file
                with open(file,'r', encoding=self.UTF8) as f:
                    f.readline()
                    headers = f.readline().split(',') # read names from second line
                try:
                    data = np.loadtxt(file, skiprows=4, delimiter=',', unpack=True)
                except ValueError as e:
                    self.print(f'Error when loading from {file.name}: {e}', PRINT.ERROR)
                    return
                if data.shape[0] == 0:
                    self.print(f'No data found in file {file.name}.', PRINT.ERROR)
                    return
                for d, n in zip(data, headers):
                    self.outputs.append(MetaChannel(name=n.strip(), data=np.array(d), background=np.zeros(d.shape[0]), unit='pA', channel=self.parentPlugin.getChannelByName(n.strip())))
                if len(self.outputs) > 0: # might be empty
                    # need to fake time axis as it was not implemented
                    self.inputs.append(MetaChannel(name=self.TIME, data=np.linspace(0, 120000, self.outputs[0].data.shape[0])))
            elif file.name.endswith('.cur.h5'):
                with h5py.File(file, 'r') as f:
                    self.inputs.append(MetaChannel(name=self.TIME, data=f[self.TIME][:]))
                    g = f['Current']
                    for name, item in g.items():
                        if '_BG' in name:
                            self.outputs[-1].background = item[:]
                        else:
                            self.outputs.append(MetaChannel(name=name, data=item[:], unit='pA', channel=self.parentPlugin.getChannelByName(name)))
            elif file.name.endswith('OUT.h5'): # old Output format when EBD was the only output
                with h5py.File(file,'r') as f:
                    self.inputs.append(MetaChannel(name=self.TIME, data=f[Scan.INPUTCHANNELS][self.TIME][:]))
                    g = f[Scan.OUTPUTCHANNELS]
                    for name, item in g.items():
                        if '_BG' in name:
                            self.outputs[-1].background = item[:]
                        else:
                            self.outputs.append(MetaChannel(name=name, data=item[:], unit=item.attrs[Scan.UNIT] if Scan.UNIT in item.attrs else '',
                                                            channel=self.parentPlugin.getChannelByName(name)))
            else:
                return super().loadDataInternal(file)
            return True

    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.channelType = CurrentChannel
        self.useBackgrounds = True # record backgrounds for data correction

    def getIcon(self):
        return self.makeIcon('RBD.png')

    def initGUI(self):
        super().initGUI()
        self.addAction(func=self.resetCharge, toolTip='Reset accumulated charge.', icon='battery-empty.png')

    def getDefaultSettings(self):
        """ Define device specific settings that will be added to the general settings tab.
        These will be included if the settings file is deleted and automatically regenerated.
        Overwrite as needed."""
        ds = super().getDefaultSettings()
        ds[f'{self.name}/Interval'][Parameter.VALUE] = 100 # overwrite default value
        return ds

    def getInitializedChannels(self):
        return [d for d in self.channels if (d.enabled and (d.controller.port is not None or self.getTestMode())) or not d.active]

    def init(self):
        super().init()
        for channel in self.channels:
            if channel.enabled:
                channel.controller.init()
            elif channel.controller.acquiring:
                channel.controller.stopAcquisition()

    def startAcquisition(self):
        for channel in self.channels:
            if channel.enabled:
                channel.controller.startAcquisition()

    def stopAcquisition(self):
        for channel in self.channels:
            channel.controller.stopAcquisition()
        super().stopAcquisition()

    def stop(self):
        super().stop()
        for channel in self.channels:
            channel.controller.close()

    def resetCharge(self):
        for d in self.channels:
            d.resetCharge()

    def initialized(self):
        return any([c.controller.initialized for c in self.channels])

    def close(self):
        for channel in self.channels:
            channel.controller.close()
        super().close()

class CurrentChannel(Channel):
    """UI for picoampmeter with integrated functionality"""

    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.controller = CurrentController(channel=self)
        self.preciceCharge = 0 # store independent of spin box precision to avoid rounding errors

    CHARGE     = 'Charge'
    COM        = 'COM'
    DEVICENAME = 'Devicename'
    RANGE      = 'Range'
    AVERAGE    = 'Average'
    BIAS       = 'Bias'
    OUTOFRANGE = 'OutOfRange'
    UNSTABLE   = 'Unstable'
    ERROR      = 'Error'

    def getDefaultChannel(self):
        """Gets default settings and values."""
        channel = super().getDefaultChannel()
        channel[self.VALUE][Parameter.HEADER ] = 'I (pA)' # overwrite existing parameter to change header
        channel[self.CHARGE     ] = parameterDict(value=0, widgetType=Parameter.TYPE.FLOAT, advanced=False, header='C (pAh)', indicator=True, attr='charge')
        channel[self.COM        ] = parameterDict(value='COM1', widgetType=Parameter.TYPE.COMBO, advanced=True,
                                        items=','.join([f'COM{x}' for x in range(1, 25)]), header='COM', attr='com')
        channel[self.DEVICENAME ] = parameterDict(value='smurf', widgetType=Parameter.TYPE.LABEL, advanced=True, attr='devicename')
        channel[self.RANGE      ] = parameterDict(value='auto', widgetType=Parameter.TYPE.COMBO, advanced=True,
                                        items='auto, 2 nA, 20 nA, 200 nA, 2 µA, 20 µA, 200 µA, 2 mA', attr='range',
                                        event=self.updateRange)
        channel[self.AVERAGE    ] = parameterDict(value='off', widgetType=Parameter.TYPE.COMBO, advanced=True,
                                        items='off, 2, 4, 8, 16, 32', attr='average',
                                        event=self.updateAverage)
        channel[self.BIAS       ] = parameterDict(value=False, widgetType=Parameter.TYPE.BOOL, advanced=True,
                                        toolTip='Apply internal bias.', attr='bias',
                                        event=self.updateBias)
        channel[self.OUTOFRANGE ] = parameterDict(value=False, widgetType=Parameter.TYPE.BOOL, advanced=False, indicator=True,
                                        header='OoR', toolTip='Indicates if signal is out of range.', attr='outOfRange')
        channel[self.UNSTABLE   ] = parameterDict(value=False, widgetType=Parameter.TYPE.BOOL, advanced=False, indicator=True,
                                        header='U', toolTip='Indicates if signal is out of unstable.', attr='unstable')
        channel[self.ERROR      ] = parameterDict(value='', widgetType=Parameter.TYPE.LABEL, advanced=False, attr='error', indicator=True)
        return channel

    def setDisplayedParameters(self):
        super().setDisplayedParameters()
        self.insertDisplayedParameter(self.CHARGE, before=self.DISPLAY)
        self.insertDisplayedParameter(self.COM, before=self.COLOR)
        self.insertDisplayedParameter(self.DEVICENAME, before=self.COLOR)
        self.insertDisplayedParameter(self.RANGE, before=self.COLOR)
        self.insertDisplayedParameter(self.AVERAGE, before=self.COLOR)
        self.insertDisplayedParameter(self.BIAS, before=self.COLOR)
        self.insertDisplayedParameter(self.OUTOFRANGE, before=self.COLOR)
        self.insertDisplayedParameter(self.UNSTABLE, before=self.COLOR)
        self.insertDisplayedParameter(self.ERROR, before=self.COLOR)

    def tempParameters(self):
        return super().tempParameters() + [self.CHARGE, self.OUTOFRANGE, self.UNSTABLE, self.ERROR]

    def enabledChanged(self): # overwrite parent method
        """Handle changes while acquisition is running. All other changes will be handled when acquisition starts."""
        if self.device.liveDisplayActive() and self.device.liveDisplay.recording:
            if self.enabled:
                self.controller.init()
            elif self.controller.acquiring:
                self.controller.stopAcquisition()

    def appendValue(self, lenT):
        # calculate deposited charge in last timestep for all channels
        # this does not only monitor the deosition sample but also on what lenses charge is lost
        # make sure that the data interval is the same as used in data acquisition
        super().appendValue(lenT)
        chargeIncrement = (self.value-self.background)*self.device.interval/1000/3600 if self.values.size > 1 else 0
        self.preciceCharge += chargeIncrement # display accumulated charge # don't use np.sum(self.charges) to allow
        self.charge = self.preciceCharge # pylint: disable=[attribute-defined-outside-init] # attribute defined dynamically

    def clearHistory(self, max_size=None):
        super().clearHistory(max_size)
        self.resetCharge()

    def resetCharge(self):
        self.charge = 0 # pylint: disable=[attribute-defined-outside-init] # attribute defined dynamically
        self.preciceCharge = 0

    def realChanged(self):
        self.getParameterByName(self.COM).getWidget().setVisible(self.real)
        self.getParameterByName(self.RANGE).getWidget().setVisible(self.real)
        self.getParameterByName(self.AVERAGE).getWidget().setVisible(self.real)
        self.getParameterByName(self.BIAS).getWidget().setVisible(self.real)
        self.getParameterByName(self.OUTOFRANGE).getWidget().setVisible(self.real)
        self.getParameterByName(self.UNSTABLE).getWidget().setVisible(self.real)
        super().realChanged()

    def updateAverage(self):
        if self.controller is not None and self.controller.acquiring:
            self.controller.updateAverageFlag = True

    def updateRange(self):
        if self.controller is not None and self.controller.acquiring:
            self.controller.updateRangeFlag = True

    def updateBias(self):
        if self.controller is not None and self.controller.acquiring:
            self.controller.updateBiasFlag = True

class CurrentController(DeviceController):
    # need to inherit from QObject to allow use of signals
    """Implements serial communication with RBD 9103.
    While this is kept as general as possible, some access to the management and UI parts are required for proper integration."""

    class SignalCommunicate(DeviceController.SignalCommunicate):
        updateValueSignal = pyqtSignal(float, bool, bool, str)
        updateDeviceNameSignal = pyqtSignal(str)

    def __init__(self, channel):
        super().__init__(parent=channel)
        #setup port
        self.channel = channel
        self.device = self.channel.device
        self.port = None
        self.signalComm.updateDeviceNameSignal.connect(self.updateDeviceName)
        self.updateAverageFlag = False
        self.updateRangeFlag = False
        self.updateBiasFlag = False
        self.phase = np.random.rand()*10 # used in test mode
        self.omega = np.random.rand() # used in test mode
        self.offset = np.random.rand()*10 # used in test mode

    def init(self):
        if self.channel.enabled and self.channel.active:
            super().init()

    def stop(self):
        self.channel.device.stop()

    def close(self):
        super().close()
        if self.port is not None:
            with self.lock:
                if self.initialized:  # pylint: disable=[access-member-before-definition] # defined in DeviceController class
                    self.RBDWrite('I0000') # stop sampling
                    self.RBDRead()
                self.port.close()
        self.initialized = False

    def stopAcquisition(self):
        if super().stopAcquisition():
            if self.channel.device.pluginManager.closing:
                time.sleep(.1)

    def runInitialization(self):
        """Initializes serial port in parallel thread."""
        if getTestMode():
            self.signalComm.initCompleteSignal.emit()
        else:
            self.initializing = True
            try:
                self.port=serial.Serial(
                    f'{self.channel.com}',
                    baudrate=57600,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    xonxoff=False,
                    timeout=3)
                self.setRange()
                self.setAverage()
                self.setGrounding()
                self.setBias()
                name = self.getName()
                if name == '':
                    self.signalComm.updateValueSignal.emit(0, False, False, f'Device at port {self.channel.com} did not provide a name. Abort initialization.')
                    return
                self.signalComm.updateValueSignal.emit(0, False, False, f'{name} initialized at {self.channel.com}')
                self.signalComm.updateDeviceNameSignal.emit(name) # pass port to main thread as init thread will die
                self.signalComm.initCompleteSignal.emit()
            except serial.serialutil.PortNotOpenError as e:
                self.signalComm.updateValueSignal.emit(0, False, False, f'Port {self.channel.com} is not open: {e}')
            except serial.serialutil.SerialException as e:
                self.signalComm.updateValueSignal.emit(0, False, False, f'9103 not found at {self.channel.com}: {e}')
            finally:
                self.initializing = False

    def initComplete(self):
        super().initComplete()
        if getTestMode():
            self.print(f'{self.channel.devicename} faking values for testing!', PRINT.WARNING)

    def startAcquisition(self):
        # only run if init succesful, or in test mode. if channel is not active it will calculate value independently
        if (self.port is not None or getTestMode()) and self.channel.active:
            super().startAcquisition()

    def runAcquisition(self, acquiring):
        if getTestMode():
            while acquiring():
                self.fakeSingleNum()
                self.updateParameters()
                time.sleep(self.channel.device.interval/1000)
        else:
            with self.lock:
                self.RBDWrite(f'I{self.channel.device.interval:04d}') # start sampling with given interval (implement high speed communication if available)
                self.RBDRead()
            while acquiring():
                with self.lock:
                    self.readSingleNum()
                    self.updateParameters()

    def updateDeviceName(self, name):
        self.channel.devicename = name

    def updateValue(self, value, outOfRange, unstable, error=''): # # pylint: disable=[arguments-differ] # arguments differ by intention
        self.channel.value = value
        self.channel.outOfRange = outOfRange
        self.channel.unstable = unstable
        self.channel.error = error
        if error != '' and self.channel.device.log:
            self.print(error)

    def setRange(self):
        if not getTestMode():
            with self.lock:
                self.RBDWrite(f'R{self.channel.getParameterByName(self.channel.RANGE).getWidget().currentIndex()}') # set range
                self.RBDRead()
        self.updateRangeFlag=False

    def setAverage(self):
        _filter = self.channel.getParameterByName(self.channel.AVERAGE).getWidget().currentIndex()
        _filter = 2**_filter if _filter > 0 else 0
        if not getTestMode():
            with self.lock:
                self.RBDWrite(f'F0{_filter:02}') # set filter
                self.RBDRead()
        self.updateAverageFlag=False

    def setBias(self):
        if not getTestMode():
            with self.lock:
                self.RBDWrite(f'B{int(self.channel.bias)}') # set bias, convert from bool to int
                self.RBDRead()
        self.updateBiasFlag=False

    def setGrounding(self):
        if not getTestMode():
            with self.lock:
                self.RBDWrite('G0') # input grounding off
                self.RBDRead()

    def getName(self):
        if not getTestMode():
            with self.lock:
                self.RBDWrite('P') # get channel name
                name = self.RBDRead()
        else:
            name = 'UNREALSMURF'
        if '=' in name:
            return name.split('=')[1]
        else:
            return ''

    def updateParameters(self):
        # call from runAcquisition to make sure there are no race conditions
        if self.updateRangeFlag:
            self.setRange()
        if self.updateAverageFlag:
            self.setAverage()
        if self.updateBiasFlag:
            self.setBias()

    def command_identify(self):
        with self.lock:
            self.RBDWrite('Q') # put in autorange
            for _ in range(13):
                message = self.RBDRead()
                self.print(message)
            #if 'PID' in message:
           #     return message.split('=')[1] # return channel name
       # return 'channel name not found'
        # self.print(message, message.split('='))
        # self.print(self.RBDRead()) # -> b'RBD Instruments: PicoAmmeter\r\n'
        # self.print(self.RBDRead()) # -> b'Firmware Version: 02.09\r\n'
        # self.print(self.RBDRead()) # -> b'Build: 1-25-18\r\n'
        # self.print(self.RBDRead()) # -> b'R, Range=AutoR\r\n'
        # self.print(self.RBDRead()) # -> b'I, sample Interval=0000 mSec\r\n'
        # self.print(self.RBDRead()) # -> b'L, Chart Log Update Interval=0200 mSec\r\n'
        # self.print(self.RBDRead()) # -> b'F, Filter=032\r\n'
        # self.print(self.RBDRead()) # -> b'B, BIAS=OFF\r\n'
        # self.print(self.RBDRead()) # -> b'V, FormatLen=5\r\n'
        # self.print(self.RBDRead()) # -> b'G, AutoGrounding=DISABLED\r\n'
        # self.print(self.RBDRead()) # -> b'Q, State=MEASURE\r\n'
        # self.print(self.RBDRead()) # -> b'P, PID=TRACKSMURF\r\n'
        # self.print(self.RBDRead()) # -> b'P, PID=TRACKSMURF\r\n'

    def fakeSingleNum(self):
        if not self.channel.device.pluginManager.closing:
            self.signalComm.updateValueSignal.emit(np.sin(self.omega*time.time()/5+self.phase)*10+np.random.rand()+self.offset, False, False,'')

    def readSingleNum(self):
        if not self.channel.device.pluginManager.closing:
            msg=self.RBDRead()
            parsed = self.parse_message_for_sample(msg)
            if any (sym in parsed for sym in ['<','>']):
                self.signalComm.updateValueSignal.emit(0, True, False, f'{self.channel.devicename}: {parsed}')
            elif '*' in parsed:
                self.signalComm.updateValueSignal.emit(0, False, True, f'{self.channel.devicename}: {parsed}')
            elif parsed == '':
                self.signalComm.updateValueSignal.emit(0, False, False, f'{self.channel.devicename}: got empty message')
            else:
                self.signalComm.updateValueSignal.emit(self.readingToNum(parsed), False, False,'')

    #Single sample (standard speed) message parsing
    def parse_message_for_sample(self, msg):
        if '&S' in msg:
            return msg.strip('&')
        else:
            return ''

    def readingToNum(self, parsed):  # convert to pA
        """Converts string to float value of pA based on unit"""
        try:
            _, _, x, u = parsed.split(',')
            x=float(x)
        except ValueError as e:
            self.print(f'{self.channel.devicename}: Error while parsing current; {parsed}, Error: {e}', PRINT.ERROR)
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
            self.print(f'{self.channel.devicename}: Error: No handler for unit {u} implemented!', PRINT.ERROR)
            return self.channel.value # keep last valid value
            #raise ValueError(f'No handler for unit {u} implemented!')

    def RBDWrite(self, message):
        self.serialWrite(self.port, f'&{message}\n')

    def RBDRead(self):
        return self.serialRead(self.port)
