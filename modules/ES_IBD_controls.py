""" This module contains only UI controls
The controls generally have a large amount of logic integrated and can act as an intelligent database.
This avoids complex and error prone synchronization between redundant data in the UI and a separate database.
Every parameter should only exist in one unique location at run time.
Separating the logic from the PyQt specific UI elements may be required in the future,
but only if there are practical and relevant advantages that outweigh the drawbacks."""

import time
from threading import Thread
from pathlib import Path # replaces os.path
import configparser
import itertools
import h5py
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backend_bases import MouseButton
import keyboard as kb
from asteval import Interpreter
from PyQt6.QtCore import QObject,pyqtSlot,pyqtSignal
from PyQt6.QtWidgets import QTreeWidget,QTreeWidgetItem,QToolButton,QFileDialog,QHeaderView,QComboBox
from PyQt6.QtGui import QBrush
import pyqtgraph as pg
import ES_IBD_core as core
from ES_IBD_core import ESIBD_Parameter,parameterDict,require_group,INOUT,dynamicNp,ESIBD_GUI
import ES_IBD_management as management
aeval = Interpreter()

def makeWrapper(name,docstring=None):
    """ Neutral property wrapper for convenient access to the value of an ESIBD_Parameter.
        If you need to handle events on value change,link these directly to the events of the corresponding control in the finalizeInit method.
    """
    def getter(self):
        return self.getParameterByName(name).value
    def setter(self,value):
        self.getParameterByName(name).value = value
    return property(getter,setter,doc=docstring)

class ESIBD_Device(ESIBD_GUI):
    """A generic device that manages multiple channels of the same type.
    Always use keyword arguments to allow forwarding to parent classes.
    """

    def __init__(self,esibdWindow,channelType,**kwargs):
        super().__init__(esibdWindow=esibdWindow,**kwargs)
        self.inout = INOUT.BOTH
        self.channels = []
        self.esibdWindow = esibdWindow
        self._advanced  = False
        self.loading = False
        # internal constants
        self.confINI = self.name + '.ini'
        self.channelType = channelType
        self.initialized = None

        self.esibdWindow.mainTabWidget.addTab(self,self.name)

        self.addButton(0,0,self.IMPORT,lambda : self.loadConfiguration(None),'Import controls and values.')
        self.addButton(0,1,self.EXPORT,lambda : self.exportConfiguration(None),'Export.')
        self.addButton(0,2,self.SAVE,self.saveConfiguration,'Save in current session.')
        self.advancedPushButton = self.addButton(0,3,ESIBD_Parameter.ADVANCED.title(),self.setAdvanced,'Show advanced options and virtual channels.',True)

        self.mainTreeWidget = QTreeWidget(self.esibdWindow)
        self.addContentWidget(self.mainTreeWidget)

        self.esibdWindow.settingsWidget.addDefaultSettings(self,self.getDefaultSettings())

        self.loadConfiguration(self.customConfigFile(self.confINI))

        self.setAdvanced()
        self.unit = ''

    def customConfigFile(self,file):
        return self.esibdWindow.configPath / file

    def getChannelbyName(self,name):
        return next((c for c in self.channels if c.name.strip().lower() == name.strip().lower()),None)

    def setAdvanced(self):
        for i,item in enumerate(self.channels[0].getDefaultChannel().values()):
            if item[ESIBD_Parameter.ADVANCED]:
                self.mainTreeWidget.setColumnHidden(i,not self.advancedPushButton.isChecked())

    def loadConfiguration(self,file = None):
        """loads channels from file"""
        if file is None: # get file via dialog
            file = Path(QFileDialog.getOpenFileName(parent=None,caption=self.SELECTFILE,filter = self.FILTER_INI_H5)[0])
        if file != Path('.'):
            self.loading=True
            self.mainTreeWidget.setUpdatesEnabled(False)
            self.mainTreeWidget.setRootIsDecorated(False) # no need to show expander
            self.channels=[]
            self.mainTreeWidget.clear()
            if file.suffix == core.FILE_INI:
                if file.exists(): # create default if not exist
                    confParser = configparser.ConfigParser()
                    confParser.read(file)
                    if len(confParser.items()) == 0:
                        self.print(f'Warning: File {file} does not contain valid channels. Repair the file manually or delete it,' +
                                                    ' to trigger generation of a valid default channel on next start.')
                    for name,item in confParser.items():
                        if not name in [ESIBD_Parameter.DEFAULT.upper(),core.VERSION,core.INFO]:
                            self.addChannel(item)
                else: # Generate default settings file if file was not found.
                    # To update files with new parameters,simply delete the old file and the new one will be generated.
                    self.print(f'Generating default config file {file}')
                    self.addChannel(item = {})
                    self.exportConfiguration(file,default = True)
            else: # file.suffix == core.FILE_H5:
                with h5py.File(name = file,mode = 'r',track_order = True) as f:
                    g = f[self.name]
                    items = [{} for _ in range(len(g[ESIBD_Parameter.NAME]))]
                    for i,name in enumerate(g[ESIBD_Parameter.NAME].asstr()):
                        items[i][ESIBD_Parameter.NAME] = name
                    default=self.channelType(esibdWindow = self.esibdWindow,parent = self,tree = None)
                    for name,parameter in default.getDefaultChannel().items():
                        if name in default.tempParameters():
                            continue # temp parameters are not saved
                        values = None
                        if parameter[ESIBD_Parameter.WIDGETTYPE] in [ESIBD_Parameter.WIDGETINT,ESIBD_Parameter.WIDGETFLOAT]:
                            values = g[name]
                        elif parameter[ESIBD_Parameter.WIDGETTYPE] == ESIBD_Parameter.WIDGETBOOL:
                            values = [str(b) for b in g[name]]
                        else:
                            values = g[name].asstr()
                        for i,v in enumerate(values):
                            items[i][name] = v
                    for item in items:
                        self.addChannel(item = item)

            self.mainTreeWidget.setHeaderLabels([(name.title() if dict[ESIBD_Parameter.HEADER] is None else dict[ESIBD_Parameter.HEADER])
                                                    for name,dict in self.channels[0].getDefaultChannel().items()])
            self.mainTreeWidget.header().setStretchLastSection(False)
            self.mainTreeWidget.header().setMinimumSectionSize(0)
            self.mainTreeWidget.header().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
            self.setAdvanced()
            self.mainTreeWidget.setUpdatesEnabled(True)
            self.loading=False
            self.esibdWindow.outputWidget.globalUpdate(inout = self.inout)
            # if there was a history,it has been invalidated by reinitializing all channels.
            # If only values should be loaded without complete reinitialization,use 'load' function instead.
            if self.esibdWindow.outputWidget is not None and self.esibdWindow.settingsWidget is not None:
                self.esibdWindow.outputWidget.clearHistory()

    def saveConfiguration(self):
        self.esibdWindow.measurementNumber += 1
        self.exportConfiguration(file = self.esibdWindow.settingsWidget.getMeasurementFileName(f'_{self.name}{core.FILE_H5}'))

    CHANNEL = 'Channel'
    SELECTFILE = 'Select File'

    def exportConfiguration(self,file = None,default = False):
        """Saves an .ini or .h5 file which contains only settings for this device. The ini file can be easily edited manually to add more channels."""
        if default:
            file = self.customConfigFile(self.confINI)
        if file is None: # get file via dialog
            file = Path(QFileDialog.getSaveFileName(parent=None,caption=self.SELECTFILE,filter = self.FILTER_INI_H5)[0])
        if file != Path('.'):
            if file.suffix == core.FILE_INI:
                config = configparser.ConfigParser()
                config[core.INFO] = core.infoDict(self.name)
                for i,channel in enumerate(self.channels):
                    config[f'{self.CHANNEL}_{i:03d}'] = channel.asDict()
                with open(file,'w',encoding = self.UTF8) as configfile:
                    config.write(configfile)
            else: # h5
                with h5py.File(file,'a',track_order = True) as f:
                    g = require_group(f,self.name)
                    for parameter in self.channels[0].asDict():
                        widgetType = self.channels[0].getParameterByName(parameter).widgetType
                        data = [c.getParameterByName(parameter).value for c in self.channels]
                        dtype = None
                        if widgetType == ESIBD_Parameter.WIDGETINT:
                            dtype = np.int32
                        elif widgetType == ESIBD_Parameter.WIDGETFLOAT:
                            dtype = np.float64
                        elif widgetType == ESIBD_Parameter.WIDGETBOOL:
                            dtype = np.bool8
                        elif widgetType == ESIBD_Parameter.WIDGETCOLOR:
                            data = [c.getParameterByName(parameter).value.name() for c in self.channels]
                            dtype = 'S7'
                        else: # widgetType in [ESIBD_Parameter.WIDGETCOMBO,ESIBD_Parameter.WIDGETINTCOMBO,ESIBD_Parameter.WIDGETTEXT,ESIBD_Parameter.WIDGETLABEL]:
                            dtype = f'S{len(max([str(d) for d in data],key = len))}' # use length of longest string as fixed length is required
                        g.create_dataset(name = parameter,data = np.asarray(data,dtype = dtype)) # do not save as attributes. very very memory intensive!
        if not self.esibdWindow.loading:
            self.esibdWindow.explorerWidget.populateTree()

    def init(self,restart = False):
        # overwrite intrument initialization as needed
        pass

    def getDefaultSettings(self):
        """ Define device specific settings that will be added to the general settings tab.
        These will be included if the settings file is deleted and automatically regenerated.
        Overwrite as needed."""
        settings = {}
        # the next line is only an example,the generic device class does not implement any settins. This is left to the inheriting classes
        # settings[self.customSetting] = parameterDict(value = 100,tooltip = 'Custom Tooltip',items = '',
        #                                                           widgetType = ESIBD_Parameter.WIDGETINT)
        return settings

    def addChannel(self,item):
        "maps dictionary to UI control"
        channel = self.channelType(esibdWindow = self.esibdWindow,parent = self,tree = self.mainTreeWidget)
        self.channels.append(channel)
        self.mainTreeWidget.addTopLevelItem(channel) # has to be added before populating
        channel.finalizeInit(item)

    def close(self):
        self.exportConfiguration(default = True)

    @property
    def LOADVALUES(self):
        return f'Load {self.name} values'

########################## Generic input device interface #########################################

class ESIBD_Input_Device(ESIBD_Device):
    """A generic input device that manages multiple channels of the same type
    In particular,this includes controls and logic for loading values from a file.
    Inherit from this class to add hardware specific functionality.
    """
    def __init__(self,**kwargs): # Always use keyword arguments to allow forwarding to parent classes.
        super().__init__(**kwargs)
        self.inout = INOUT.IN
        self.addButton(0,2,self.LOAD,lambda : self.loadValues(None),'Load values only.')
        self.addButton(0,4,'Plot',self.plot,'Plot values.')

    def loadValues(self,file = None):
        """load only potentials for channels matching in file and existing config"""
        if file is None: # get file via dialog
            file = Path(QFileDialog.getOpenFileName(parent=None,caption=self.SELECTFILE,filter=self.FILTER_INI_H5)[0])
        if file != Path('.'):
            if file.suffix == core.FILE_INI:
                confParser = configparser.ConfigParser()
                confParser.read(file)
                for name,item in confParser.items():
                    if not name in [ESIBD_Parameter.DEFAULT.upper(),core.VERSION,core.INFO]:
                        c=self.getChannelbyName(item.get(ESIBD_Parameter.NAME))
                        if c is not None:
                            c.value = float(item.get(ESIBD_Parameter.VALUE,'0'))
                        else:
                            self.print(f'Warning: Could not find channel {item.get(ESIBD_Parameter.NAME)}')
            else: # core.FILE_H5
                with h5py.File(name = file,mode = 'r',track_order = True) as f:
                    g = f[self.name]
                    for n,v in zip(g[ESIBD_Parameter.NAME].asstr(),g[ESIBD_Parameter.VALUE]):
                        if self.getChannelbyName(n) is not None:
                            self.getChannelbyName(n).value = v

    def setAdvanced(self):
        super().setAdvanced()
        for c in self.channels:
            c.setHidden((not self.advancedPushButton.isChecked()) and (not c.active))

    def plot(self):
        """plots values from all real channels"""
        lw = self.esibdWindow.lineWidget
        lw.axes[0].clear()
        y = [c.value for c in self.channels if c.real]
        labels = [c.name for c in self.channels if c.real]
        colors = [c.color.name() for c in self.channels if c.real]
        x = np.arange(len(y))
        lw.axes[0].scatter(x,y,marker='.',color = colors)
        lw.axes[0].set_ylabel(self.unit)
        lw.axes[0].set_xticks(x,labels,rotation=30,ha='right',rotation_mode='anchor')
        lw.fig.tight_layout()
        lw.canvas.draw_idle()
        self.esibdWindow.displayTabWidget.setCurrentWidget(lw)

########################## Generic input device interface #########################################

class ESIBD_Output_Device(ESIBD_Device):
    """A generic output device that manages multiple channels of the same type.
    Inherit from this class to add hardware specific functionality.
    """
    def __init__(self,**kwargs): # Always use keyword arguments to allow forwarding to parent classes.
        super().__init__(**kwargs)
        self.inout = INOUT.OUT
        self.addButton(0,3,'Set BG',self.setBackground,'Set background')

    def setBackground(self):
        for channel in self.channels: # save present signal as background
            # use average of last 10 datapoints of possible
            channel.background = np.mean(channel.getValues(subtractBackground = False)[-10:]) if len(channel.getValues(subtractBackground = False)) > 10 else channel.value

    def setAdvanced(self):
        super().setAdvanced()
        for c in self.channels:
            c.setHidden((not self.advancedPushButton.isChecked()) and (not c.active and not c.display))

########################## Generic channel ########################################################

class ESIBD_Channel(QTreeWidgetItem):
    """UI and functionality for genecic device channel.
    Always use keyword arguments to allow forwarding to parent classes.
    """

    class SignalCommunicate(QObject):
        updateValueSignal       = pyqtSignal(float)

    def __init__(self,esibdWindow,parent,tree):
        super().__init__(tree)
        self.esibdWindow = esibdWindow
        self.print = lambda string : esibdWindow.esibdPrint(string) # pylint: disable = unnecessary-lambda #, consistent access via lambda and self.print everywhere as in ESIBD_GUI
        self.printFromThread = lambda string : esibdWindow.signalComm.printFromThreadSignal.emit(string) # pylint: disable = unnecessary-lambda
        self.parent = parent
        self.tree = tree
        self.signalComm = self.SignalCommunicate()
        self.signalComm.updateValueSignal.connect(self.updateValueParallel)
        self.lastAppliedVoltage = None # keep track of last value to identify what has changed
        self.parameters = []
        self.values = dynamicNp()

        # self.value = None # will be replaced by wrapper
        # generate property for direct access of parameter values
        for name,default in self.getDefaultChannel().items():
            if ESIBD_Parameter.ATTR in default and default[ESIBD_Parameter.ATTR] is not None:
                setattr(self.__class__,default[ESIBD_Parameter.ATTR],makeWrapper(name))

        for i,(name,default) in enumerate(self.getDefaultChannel().items()):
            self.parameters.append(ESIBD_Parameter(esibdWindow=esibdWindow, parent=self, name=name, widgetType=default[ESIBD_Parameter.WIDGETTYPE],
                                                    items = default[ESIBD_Parameter.ITEMS] if ESIBD_Parameter.ITEMS in default else None,
                                                    _min = default[ESIBD_Parameter.MIN] if ESIBD_Parameter.MIN in default else None,
                                                    _max = default[ESIBD_Parameter.MAX] if ESIBD_Parameter.MAX in default else None,
                                                    toolTip = default[ESIBD_Parameter.TOOLTIP] if ESIBD_Parameter.TOOLTIP in default else None,
                                                    internal = default[ESIBD_Parameter.INTERNAL] if ESIBD_Parameter.INTERNAL in default else False,
                                                    itemWidget = self,index = i,tree = self.tree,
                                                    event = default[ESIBD_Parameter.EVENT] if ESIBD_Parameter.EVENT in default else None))
    HEADER      = 'HEADER'
    # basic property access. Overwrite with custom properties if necessary.

    def getDefaultChannel(self):
        """ Defines parameter(s) to use when generating default file.
            This is also use to assign widgetTypes and if settings are visible outside of advanced mode
            If parameters do not exist in the settings file,the default parameter will be added.
            Overwrite in dependent classes as needed.
        """
        channel = {}
        self.VALUE    = 'Value'
        self.ENABLED  = 'Enabled'
        channel[self.ENABLED] = parameterDict(value = True,widgetType = ESIBD_Parameter.WIDGETBOOL,advanced =  False,
                                    header =  'E',toolTip= 'If enabled,value will be applied to device.',
                                    event = self.enabledChanged,attr = 'enabled')
        self.NAME     = 'Name'
        channel[self.NAME    ] = parameterDict(value = 'parameter',widgetType = ESIBD_Parameter.WIDGETTEXT,advanced = False,attr = 'name')
        channel[self.VALUE   ] = parameterDict(value = 0,widgetType = ESIBD_Parameter.WIDGETFLOAT,advanced = False,
                                    header = 'Unit',attr = 'value')
        self.EQUATION = 'Equation'
        channel[self.EQUATION] = parameterDict(value = '',widgetType = ESIBD_Parameter.WIDGETTEXT,advanced = True,attr = 'equation')
        self.ACTIVE   = 'Active'
        channel[self.ACTIVE  ] = parameterDict(value = True,widgetType = ESIBD_Parameter.WIDGETBOOL,advanced = True,
                                    header = 'A',toolTip = 'If not active,value will be determined from equation.',
                                    event = self.activeChanged,attr = 'active')
        self.REAL     = 'Real'
        channel[self.REAL    ] = parameterDict(value = True,widgetType = ESIBD_Parameter.WIDGETBOOL,advanced = True,
                                    header = 'R',toolTip = 'Set to real for physically exiting channels.',
                                    event = self.realChanged,attr = 'real')
        self.COLOR    = 'Color'
        channel[self.COLOR   ] = parameterDict(value = '#b8b8b8',widgetType = ESIBD_Parameter.WIDGETCOLOR,advanced = True,
                                    event = self.updateColor,attr = 'color')
        # use following to determine order of parameters in child classes
        # list needs to be complete!
        # channel = {k: channel[k] for k in [self.ENABLED,self.NAME,self.VALUE,self.EQUATION,self.ACTIVE,self.REAL,self.COLOR]}
        return channel

    def tempParameters(self):
         # list of parameters to not export to file (e.g. information that only makes sense when it comes directly from a device)
        return []

    def getParameterByName(self,name):
        p = next((p for p in self.parameters if p.name.strip().lower() == name.strip().lower()),None)
        if p is None:
            self.print(f'Warning: Could not find parameter {name}.')
        return p

    def asDict(self):
        d = {}
        for p in self.parameters:
            if p.name not in self.tempParameters():
                if p.widgetType == ESIBD_Parameter.WIDGETCOLOR:
                    d[p.name] = p.value.name()
                else:
                    d[p.name] = p.value
        return d

    # @pyqtSlot(float) # not required,causes issues
    def updateValueParallel(self,value): # used to update from external threads
        self.value = value # pylint: disable=[attribute-defined-outside-init] # attribute defined by makeWrapper

    def activeChanged(self):
        self.updateColor()
        if not self.parent.loading:
            self.esibdWindow.outputWidget.globalUpdate(inout = INOUT.IN)

    def appendValue(self):
        self.values.add(self.value)

    def getValues(self):
        return self.values.get()

    def clearHistory(self): # overwrite as needed,e.g. when keeping history of more than one parametrer
        if self.esibdWindow.outputWidget is not None and (self.esibdWindow.settingsWidget is not None and not self.esibdWindow.settingsWidget.loading):
            self.values = dynamicNp(max_size = 600000/int(self.esibdWindow.outputWidget.interval)) # 600000 -> only keep last 10 min to save ram

    def updateColor(self):
        """Apply new color to all controls"""
        color = self.color if self.active else self.color.darker(115) # indicate passive channels by darker color
        qb = QBrush(color)
        for i in range(len(self.parameters)+1): # use highest index
            self.setBackground(i,qb) # use correct color even when widgets are hidden
        styleSheet = f'background: rgb({color.red()},{color.green()},{color.blue()})'
        for p in self.parameters:
            p.getWidget().setStyleSheet(styleSheet)

    def realChanged(self):
        self.getParameterByName(self.ENABLED).getWidget().setVisible(self.real)
        if not self.parent.loading:
            self.esibdWindow.outputWidget.globalUpdate(inout = INOUT.IN)

    def enabledChanged(self): # overwrite if needed (already linked to enabled checkbox!)
        if not self.parent.loading:
            pass

    def finalizeInit(self,item):
        """call after itemWidget has been added to treeWidget
            itemWidget needs parent for all graphics operations
        """
        for p in self.parameters:
            p.applyWidget()
        for name,default in self.getDefaultChannel().items():
            # add default value if not found in file. Will be saved to file later.
            if name in item and not name in self.tempParameters():
                self.getParameterByName(name).value = item[name]
            else:
                self.getParameterByName(name).value = default[self.VALUE]
                if not name in self.tempParameters() and not item == {}: # item == {} -> generating default file
                    self.print(f'Added missing parameter {name} to channel {self.name}.')

        line = self.getParameterByName(self.EQUATION).line
        line.setMinimumWidth(200)
        f = line.font()
        f.setPointSize(7)
        line.setFont(f)

        self.updateColor()
        self.realChanged()

########################## Input channel ########################################################

class ESIBD_Input_Channel(ESIBD_Channel):
    """UI and functionality for genecic device input channel.
    In particular,this includes controls and logic for input limits and events to handle input changes
    Always use keyword arguments to allow forwarding to parent classes.
    """
    # def __init__(self,**kwargs):
    #     super().__init__(**kwargs)

    def getDefaultChannel(self):
        channel = super().getDefaultChannel()
        channel[self.ENABLED][ESIBD_Parameter.EVENT] = lambda : self.esibdWindow.outputWidget.globalUpdate(inout = INOUT.IN)
        channel[self.VALUE][ESIBD_Parameter.EVENT] = lambda : self.esibdWindow.outputWidget.globalUpdate(inout = INOUT.IN)
        self.SELECT    = 'Select'
        channel[self.SELECT  ] = parameterDict(value = False,widgetType = ESIBD_Parameter.WIDGETBOOL,advanced = False,
                                    toolTip = 'Plots data as a function of selected channel.',event = self.setXChannel,attr = 'select')
        self.MIN       = 'Min'
        channel[self.MIN     ] = parameterDict(value = -50,widgetType = ESIBD_Parameter.WIDGETFLOAT,advanced = True,
                                    event = self.updateMin,attr = 'min')
        self.MAX       = 'Max'
        channel[self.MAX     ] = parameterDict(value = +50,widgetType = ESIBD_Parameter.WIDGETFLOAT,advanced = True,
                                    event =  self.updateMax,attr = 'max')
        self.OPTIMIZE  = 'Optimize'
        channel[self.OPTIMIZE] = parameterDict(value = False,widgetType = ESIBD_Parameter.WIDGETBOOL,advanced = False,
                                    header = 'O',toolTip = 'Selected channels will be optimized using GA',attr = 'optimize')
        channel = {k: channel[k] for k in [self.SELECT,self.ENABLED,self.NAME,self.VALUE,self.MIN,self.MAX,self.EQUATION,self.OPTIMIZE,self.ACTIVE,self.REAL,self.COLOR]}
        return channel

    def finalizeInit(self,item):
        """call after itemWidget has been added to treeWidget
            itemWidget needs parent for all graphics operations
        """
        super().finalizeInit(item)

        self.updateMin()
        self.updateMax()

        select = self.getParameterByName(self.SELECT)
        v = select.value
        select.widget = QToolButton() # hard to spot checked QCheckBox. QPushButton is too wide -> overwrite internal widget to QToolButton
        select.applyWidget()
        select.check.setText(self.SELECT.title())
        select.check.setMinimumWidth(5)
        select.check.setCheckable(True)
        select.value = v
        self.updateColor() # repeat updateColor to include newly generated QToolButton

    def updateMin(self):
        self.getParameterByName(self.VALUE).spin.setMinimum(self.min)
        self.esibdWindow.outputWidget.xChannelChanged()

    def updateMax(self):
        self.getParameterByName(self.VALUE).spin.setMaximum(self.max)
        self.esibdWindow.outputWidget.xChannelChanged()

    def setXChannel(self):
        """make sure only a singe input channel is selected at a time,then update X Channel"""
        for c in self.esibdWindow.outputWidget.channels(inout = INOUT.IN):
            if c is not self:
                c.select = False
        self.esibdWindow.outputWidget.xChannelChanged()

########################## Output channel ########################################################

class ESIBD_Output_Channel(ESIBD_Channel):
    """UI and functionality for genecic device output channel.
    In particular,this includes events to update non active channels when changing active or enabled state.
    Always use keyword arguments to allow forwarding to parent classes.
    """
    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.backgrounds = None # array of background history. managed by instrument manager to keep timing synchronous
        self.plotCurve = None

    def getDefaultChannel(self):
        channel = super().getDefaultChannel()
        channel[self.NAME][ESIBD_Parameter.EVENT] = self.updateDisplay
        channel[self.ENABLED][ESIBD_Parameter.EVENT] = self.enabledChanged
        channel[self.REAL][ESIBD_Parameter.EVENT] = lambda : self.esibdWindow.outputWidget.globalUpdate(inout = INOUT.OUT)
        self.BACKGROUND = 'Background'
        channel[self.BACKGROUND] = parameterDict(value = 0,widgetType = ESIBD_Parameter.WIDGETFLOAT,advanced = False,
                                    header = 'BG',attr = 'background')
        self.DISPLAY    = 'Display'
        channel[self.DISPLAY   ] = parameterDict(value = True,widgetType = ESIBD_Parameter.WIDGETBOOL,advanced = False,
                                    header = 'D',event = self.updateDisplay,attr = 'display')
        self.LINEWIDTH  = 'LINEWIDTH'
        channel[self.LINEWIDTH  ] = parameterDict(value = '4',widgetType = ESIBD_Parameter.WIDGETINTCOMBO,advanced = True,
                                        items = '2,4,6,8,10',attr = 'linewidth',event = self.updateDisplay)
        channel = {k: channel[k] for k in [self.ENABLED,self.NAME,self.VALUE,self.EQUATION,self.BACKGROUND,self.DISPLAY,self.LINEWIDTH,self.ACTIVE,self.REAL,self.COLOR]}
        return channel

    def tempParameters(self):
        return super().tempParameters() + [self.VALUE,self.BACKGROUND]

    # def finalizeInit(self,item):
    #     super().finalizeInit(item)

    def updateDisplay(self):
        if self.plotCurve is not None:
            # self.plotCurve = None # will be recreated if display is True
            if self.display:
                self.plotCurve.setPen(pg.mkPen(self.color,width=int(self.linewidth)))
                # self.plotCurve.clear() # cannot rename -> reinitialize manually if channel names change
                # self.plotCurve = self.esibdWindow.outputWidget.outputPlotWidget.plot(pen=pg.mkPen((self.color),width=int(self.linewidth)),name = self.name)
            else:
                #self.plotCurve = None
                self.plotCurve.setPen(pg.mkPen(None))

    def clearHistory(self): # overwrites method in parent class
        self.values = dynamicNp()
        self.backgrounds = dynamicNp()
        if self.plotCurve is not None:
            self.plotCurve.clear()
            self.plotCurve = None

    def enabledChanged(self):
        super().enabledChanged()
        self.esibdWindow.outputWidget.globalUpdate(inout = INOUT.OUT)
        if not self.enabled and self.plotCurve is not None:
            self.plotCurve = None

    def getValues(self,subtractBackground = True):
        # overwrite method from super class and replace with dedicated method for output channels
        # note that background subtraction only affects what is displayed,the raw signal and background curves are always retained
        return ((self.values.get() - self.backgrounds.get()) if subtractBackground else self.values.get())

    def appendValue(self):
        super().appendValue()
        self.backgrounds.add(self.background)

class ESIBD_Scan(ESIBD_GUI):
    """ Base class for Scans and other measurement modes
    Acquires arbitrary output channel values vs arbitrary input channel values.
    The dimension of inputs and outputs is dynamic.
    """

    PARAMETER   = 'Parameter'
    VERSION     = 'Version'
    VALUE       = 'Value'
    UNIT        = 'Unit'
    DISPLAY     = 'Display'
    DISPLAYCHANNEL = 'Displaychannel'
    LEFTRIGHT   = 'Left-Right'
    UPDOWN      = 'Up-Down'
    WAITLONG    = 'Wait long'
    LARGESTEP   = 'Large step'
    WAIT        = 'Wait'
    AVERAGE     = 'Average'
    INTERVAL    = 'Interval'
    FROM        = 'From'
    TO          = 'To'
    STEP        = 'Step'
    CHANNEL     = 'Channel'
    INPUTCHANNELS = 'Input Channels'
    OUTPUTCHANNELS = 'Output Channels'
    SCAN            = 'Scan'
    MYBLUE='#1f77b4'
    MYGREEN='#00aa00'
    MYRED='#d62728'

    class SignalCommunicate(QObject):
        scanUpdateSignal       = pyqtSignal(bool)
        resetScanButtonSignal  = pyqtSignal()
        saveScanCompleteSignal  = pyqtSignal()

    def __init__(self,esibdWindow,**kwargs):
        super().__init__(esibdWindow=esibdWindow,**kwargs)
        self.esibdWindow = esibdWindow
        self.loading = True
        self.acquiring = False
        self.finished  = True
        self.displayTab = ESIBD_GUI(name=self.name)
        self.fig = plt.figure(dpi=self.getDPI())
        self.axes = []
        self.canvas,self.toolbar = self.makeFigureCanvasWithToolbar(self.displayTab,self.fig)
        self.displayComboBox = QComboBox()
        self.displayComboBox.setMinimumSize(200,self.displayComboBox.minimumSize().height())
        self.displayTab.provideRow(0).insertWidget(1,self.displayComboBox,1)
        self.esibdWindow.displayTabWidget.addTab(self.displayTab,self.name)
        self.measurementsPerStep = 0
        self.mouseMoving = False
        self.runThread = None
        self.saveThread = None
        self.file = None
        self.mouseActive = False
        self.suffixes.append(f'_{self.name.lower()}.h5')
        self.signalComm = self.SignalCommunicate()
        self.signalComm.scanUpdateSignal.connect(self.scanUpdate)
        self.signalComm.resetScanButtonSignal.connect(self.resetScanButton)
        self.signalComm.saveScanCompleteSignal.connect(self.saveScanComplete)
        settingsTreeWidget = QTreeWidget()
        settingsTreeWidget.setHeaderLabels([self.PARAMETER,self.VALUE])
        self.addContentWidget(settingsTreeWidget)
        self.esibdWindow.mainTabWidget.addTab(self,self.name)
        self.settings = management.SettingsManager(esibdWindow = self.esibdWindow,name = self.name,tree = settingsTreeWidget,
                                        defaultFile = self.esibdWindow.configPath / 'config.h5')
        self.settings.addDefaultSettings(self,self.getDefaultSettings())
        self.settings.init()

        self.addButton(0,0,self.LOAD  ,lambda : self.loadSettings(file=None),'Load Settings.')
        self.addButton(0,1,self.EXPORT,lambda : self.saveSettings(file=None),'Export Settings.')
        self.scanPushButton = self.addButton(0,2,self.SCAN,self.scanToogle,'Start Scan.',checkable = True)
        self.outputChannels = None
        self.inputData = None
        self.init()
        self.loading = False

    def updateFile(self):
        self.esibdWindow.measurementNumber += 1
        self.file = self.esibdWindow.settingsWidget.getMeasurementFileName(self.suffixes[0])

    def updateDisplayChannel(self):
        if not self.esibdWindow.loading and not self.loading and not self.settings.loading:
            self.scanPlot(update=False, done=not self.acquiring) # update labels

    def updateDisplayDefault(self):
        self.loading = True
        i = self.displayComboBox.findText(self.displayDefault)
        if i == -1:
            self.displayComboBox.setCurrentIndex(0)
        else:
            self.displayComboBox.setCurrentIndex(i)
        self.loading = False
        self.updateDisplayChannel()

    def populateDisplayChannel(self):
        self.loading = True
        self.displayComboBox.clear()
        for n in self.outputNames: # use channels form current aquisition or from file.
            self.displayComboBox.insertItem(self.displayComboBox.count(),n)
        self.loading = False
        self.updateDisplayDefault()

    def loadSettings(self, file=None):
        self.settings.loadSettings(file=file)
        self.updateDisplayChannel()

    def saveSettings(self, file=None, default=False):
        self.settings.saveSettings(file=file, default=default)

    def getDefaultSettings(self):
        """ Define device specific settings that will be added to the general settings tab.
        These will be included if the settings file is deleted and automatically regenerated.
        Overwrite as needed."""
        settings = {}
        settings[self.DISPLAYCHANNEL] = parameterDict(value = '',toolTip = 'Select display channel.', widget=self.displayComboBox,
                                         items = '',widgetType = ESIBD_Parameter.WIDGETCOMBO,attr = 'displayChannel',event = self.updateDisplayChannel)
        settings[self.DISPLAY] = parameterDict(value = 'RT_Front-Plate',toolTip = 'Default display channel used when scanning.',
                                         items = 'RT_Front-Plate,RT_Detector,RT_Sample-Center,RT_Sample-End,LALB_Aperture',
                                         widgetType = ESIBD_Parameter.WIDGETCOMBO,attr = 'displayDefault',event = self.updateDisplayDefault)
            # NOTE: alternatively the wait time could be determined proportional to the step.
            # While this would be technically cleaner and more time efficient,
            # the present implementation is easier to understand and should work well as long as the step sizes do not change too often
        settings[self.WAIT]         = parameterDict(value = 500,toolTip = 'Wait time between small steps in ms.',
                                                                        widgetType = ESIBD_Parameter.WIDGETINT,attr = 'wait')
        settings[self.WAITLONG]     = parameterDict(value = 2000,toolTip = f'Wait time between steps larger than {self.LARGESTEP} in ms.',
                                                                        widgetType = ESIBD_Parameter.WIDGETINT,attr = 'waitlong')
        settings[self.LARGESTEP]    = parameterDict(value = 2,toolTip = 'Threshold step size to use longer wait time.',
                                                                        widgetType = ESIBD_Parameter.WIDGETFLOAT,attr = 'largestep')
        settings[self.AVERAGE]      = parameterDict(value = 1000,toolTip = 'Average time in ms.',widgetType = ESIBD_Parameter.WIDGETINT,attr = 'average')
        return settings

    def getOutputIndex(self):
        try:
            i = self.outputNames.index(self.displayChannel)
        except ValueError:
            i = 0
        return i

    def init(self):
        self.outputData = []
        self.outputNames = []
        self.outputUnits = []
        self.inputChannels = []
        self.inputNames = []
        self.inputUnits = []
        self.inputData = []
        self.inputInitial = []
        self.outputChannels = []

    def initScan(self):
        """Initialized all data and metadata.
        Returns True if initialization sucessful and scan is ready to start."""
        self.outputChannels = self.esibdWindow.outputWidget.getInitializedOutputChannels()
        self.measurementsPerStep = int((self.average/self.esibdWindow.outputWidget.interval))-1
        if len(self.outputChannels) > 0:
            lengths = [len(i) for i in self.inputData]
            for o in self.outputChannels:
                if len(self.inputData) == 1: # 1D scan
                    self.outputData.append(np.zeros(len(self.inputData[0]))) # cant reuse same array for all outputs as they would refer to same instance.
                else: # 2D scan,higher dimensions not jet supported
                    self.outputData.append(np.zeros(np.prod(lengths)).reshape(*lengths).transpose())
                self.outputNames.append(o.name)
                self.outputUnits.append(o.parent.unit)
            self.updateFile()
            self.populateDisplayChannel()
            return True
        else:
            self.print(f'{self.name} Scan Warning: No initialized output channel found.')
            return False

    def saveData(self,file):
        """Writes generic scan data to h5 file"""
        with h5py.File(file,'a',track_order = True) as f:
            g = require_group(f,self.name) #,track_order = True

            i = require_group(g,self.INPUTCHANNELS)
            for j,name in enumerate(self.inputNames):
                # print('chrate dataset',name,np.random.rand() )
                d = i.create_dataset(name = name,data = self.getData(j,INOUT.IN),track_order = True)
                d.attrs[self.UNIT] = self.inputUnits[j]

            o = require_group(g,self.OUTPUTCHANNELS)
            for j,name in enumerate(self.outputNames):
                d = o.create_dataset(name = name,data = self.getData(j,INOUT.OUT),track_order = True)
                d.attrs[self.UNIT] = self.outputUnits[j]

    def loadData(self,file):
        """Loads generic scan data from h5 file"""
        self.init()
        self.file = file
        self.loadDataInternal()
        self.populateDisplayChannel() # select default scan channel if available and then calls scanPlot

    def loadDataInternal(self):
        """Loads data from scan file. Data is stored in scan-neutral format of input and output channels.
        Extend to provide support for previous file formats."""
        with h5py.File(self.file,'r') as f:
            g = f[self.name]

            i = g[self.INPUTCHANNELS]
            for name,data in i.items():
                self.inputChannels.append(self.esibdWindow.outputWidget.getChannelbyName(name,inout = INOUT.IN))
                self.inputNames.append(name)
                self.inputData.append(data[:]) # no need for dynamic np as data loaded from file will not change
                self.inputUnits.append(data.attrs[self.UNIT])

            o = g[self.OUTPUTCHANNELS]
            for name,data in o.items():
                self.outputChannels.append(self.esibdWindow.outputWidget.getChannelbyName(name,inout = INOUT.OUT))
                self.outputNames.append(name)
                self.outputData.append(data[:])
                self.outputUnits.append(data.attrs[self.UNIT])

    def addInputChannel(self,channelName,_from,to,step):
        """Converting channel to generic input data.
        Returns True if channel is valid for scanning."""
        self.inputNames.append(channelName)
        c = self.esibdWindow.outputWidget.getChannelbyName(channelName,inout = INOUT.IN)
        if c is None:
            self.print(f'{self.name} Scan: No channel found with name {channelName}.')
            self.inputChannels.append(None)
            self.inputInitial.append(None)
            self.inputUnits.append(None)
            self.inputData.append(None)
            return False
        else:
            self.inputChannels.append(c)
            self.inputInitial.append(c.value) # remember initial values
            self.inputUnits.append(c.parent.unit)
            if _from == to:
                self.print(f'{self.name} Scan: Limits are equal.')
                self.inputData.append(None)
                return False
            self.inputData.append(np.arange(_from,to+step*np.sign(to-_from),step*np.sign(to-_from))) # always step from '_from' to 'to' and include the endpoint
            if any([len(a) < 3 for a in self.inputData]):
                self.print(f'{self.name} Scan: Not enough steps.')
                return False
            elif not self.esibdWindow.outputWidget.acquiring:
                self.print('Acquisition not running.')
                return False
            else:
                return True

    def getData(self,i,inout):
        if inout == INOUT.IN:
            if isinstance(self.inputData[i],dynamicNp):
                return self.inputData[i].get()
            else:
                return self.inputData[i]
        else:
            if isinstance(self.outputData[i],dynamicNp):
                return self.outputData[i].get()
            else:
                return self.outputData[i]

    def scanToogle(self):
        """Handles start and stop of scan."""
        if self.esibdWindow.outputWidget.acquiring:
            if self.scanPushButton.isChecked():
                if self.finished:
                    self.init()
                    if self.initScan():
                        if self.runThread is not None and self.acquiring:
                            self.acquiring=False
                            self.runThread.join()
                        self.acquiring = True
                        self.finished  = False
                        self.scanPlot(done=False,update=False) # init plot without data, some widgets may be able to update data only without redrawing the rest
                        self.runThread = Thread(target = self.run,args =(lambda : self.acquiring,))
                        self.runThread.daemon = True
                        self.runThread.start()
                else:
                    self.scanPushButton.setChecked(False)
                    self.print(f'Wait for {self.name} scan to finish.')
            else:
                self.acquiring = False
        else:
            self.print(f'NOTE: Acquisition is not running. Cannot start {self.name} scan.')
            self.scanPushButton.setChecked(False)

    def mouseEvent(self,event):  # use mouse to move beam # use ctrl key to avoid this while zoomiong
        """Handles dragging beam in 2D scan or setting retarding grid potential in energy scan"""
        if not self.mouseActive:
            return
        if self.mouseMoving and not event.name == 'button_release_event': # dont trigger events until last one has been processed
            return
        else:
            self.mouseMoving = True
            if event.button == MouseButton.LEFT and kb.is_pressed('ctrl') and event.xdata is not None:
                for i,c in enumerate(self.inputChannels):
                    if c is not None:
                        c.value = event.xdata if i == 0 else event.ydata # 3D not supported
                    else:
                        self.print(f'Could not find channel {self.inputNames[i]}.')
                if self.axes[-1].cursor is not None:
                    self.axes[-1].cursor.ondrag(event)
            self.mouseMoving = False

    @pyqtSlot(bool)
    def scanUpdate(self,done=False):
        self.scanPlot(update=not done, done=done)
        if done: # save data
            self.esibdWindow.explorerWidget.activeFileFullPath = self.file
            self.saveThread = Thread(target = self.saveScanParallel,args =(self.file,))
            self.saveThread.daemon = True # Terminate with main app independent of stop condition
            self.saveThread.start()

    def saveScanParallel(self, file):
        """Keeps GUI interactive while saving scan."""
        # only reads data from gui but does not modify it -> can run in parallel thread
        self.settings.saveSettings(file = file) # save settings
        self.saveData(file = file) # save data to same file
        self.esibdWindow.outputWidget.exportConfiguration(file = file) # save corresponding device settings in measurement file
        self.signalComm.saveScanCompleteSignal.emit()

    def saveScanComplete(self):
        self.esibdWindow.explorerWidget.populateTree()
        self.finished = True

    def scanPlot(self, update=False, **kwargs): # pylint: disable = unused-argument # use **kwargs to allow child classed to extend the signature
        """Plot showing a current or final state of the scan."""
        if self.loading:
            return
        if not update: # optional use set_data or similar functions to only update data without expensive redrawing of the entire canvas
            # extend for specific code
            # general postprocessing
            # Trigger the canvas to update and redraw. / .draw() not working for some reason https://stackoverflow.com/questions/32698501/fast-redrawing-with-pyqt-and-matplotlib
            self.toolbar.update()
            self.canvas.get_default_file = lambda : self.file.with_suffix('') # set up save file dialog
            self.fig.tight_layout()
        # labelPlot seems to defer .draw() -> makes timeit unreliale so comment out for timing tests. defering draw might make UI more responsive?
        if len(self.outputNames) > 0:
            self.labelPlot(self.axes[0],f'{self.outputNames[self.getOutputIndex()]} from {self.file.name}')
        else:
            self.labelPlot(self.axes[0],self.file.name)
        self.canvas.draw_idle()
        # self.canvas.draw() # use this instead of draw_idle() to include actual drawing time when measure timing

    def addRightAxis(self,ax):
        """adds additional y labels on the right"""
        # .tick_params(labelright=True) does only add labels
        # .tick_right() removes ticks on left
        # -> link second axis as a workaround
        axr = ax.twinx()
        axr.tick_params(direction="out",right=True)
        axr.get_shared_y_axes().join(ax,axr)

    @pyqtSlot()
    def resetScanButton(self):
        self.scanPushButton.setChecked(False)

    def run(self,acquiring):
        """ steps through scan by setting potentials and triggering plot update """
        steps = list(itertools.product(*self.inputData))
        seconds = 0 # estimate scan time
        for i,step in enumerate(steps):
            waitlong = False
            for j,c in enumerate(self.inputChannels):
                if not waitlong and abs(steps[i-1][j]-steps[i][j]) > self.largestep:
                    waitlong=True
                    break
            seconds += (self.waitlong if waitlong else self.wait) + self.average
        seconds = round((seconds)/1000)
        self.printFromThread(f'Starting {self.name} scan M{self.esibdWindow.measurementNumber:02}. Estimated time: {seconds//60:02d}:{seconds%60:02d}')

        for i,step in enumerate(steps): # scan over all steps
            waitlong = False
            for j,c in enumerate(self.inputChannels):
                if not waitlong and abs(c.value-step[j]) > self.largestep:
                    waitlong=True
                c.signalComm.updateValueSignal.emit(step[j])
            time.sleep(((self.waitlong if waitlong else self.wait)+self.average)/1000) # if step is larger than threashold use longer wait time
            for j,c in enumerate(self.outputChannels):
                if len(self.inputData) == 1: # 1D scan
                    self.outputData[j][i] = np.mean(c.getValues()[-self.measurementsPerStep:])
                else: # 2D scan,higher dimensions not jet supported
                    self.outputData[j][i%len(self.inputData[1]),i//len(self.inputData[1])] = np.mean(c.getValues()[-self.measurementsPerStep:])

            if i == len(steps)-1 or not acquiring(): # last step
                for j,c in enumerate(self.inputChannels):
                    c.signalComm.updateValueSignal.emit(self.inputInitial[j])
                time.sleep(.5) # allow time to reset to initial value before saving
                self.signalComm.scanUpdateSignal.emit(True) # update graph and save data
                self.signalComm.resetScanButtonSignal.emit()
                break # in case this is last step
            else:
                self.signalComm.scanUpdateSignal.emit(False) # update graph

    def close(self):
        self.settings.saveSettings(default=True)
        self.acquiring = False
