"""This module contains classes that contain and manage a list of (extended) UI elements.
In addition it contains classes used to manage data acquisition.
Finally it contains classes for data export,and data import."""

import time
from threading import Thread
from pathlib import Path
from datetime import datetime
import configparser
import timeit
import inspect
from asteval import Interpreter
import h5py
import matplotlib.pyplot as plt
import pyqtgraph as pg
import pyqtgraph.console
from scipy.stats import binned_statistic
from PyQt6.QtWidgets import QTreeWidgetItem,QFileDialog,QTreeWidget,QMenu,QInputDialog,QVBoxLayout,QSlider,QComboBox,QTreeWidgetItemIterator,QHeaderView,QGridLayout,QSizePolicy
from PyQt6.QtCore import Qt,QObject,pyqtSlot,pyqtSignal
from PyQt6.QtGui import QFont
import numpy as np
from ES_IBD_controls import ESIBD_Channel,ESIBD_Input_Device,ESIBD_Output_Device,ESIBD_Scan
import ES_IBD_core as core
from ES_IBD_core import INOUT, ESIBD_Parameter,ESIBD_Setting,parameterDict,require_group,dynamicNp,ESIBD_GUI
aeval = Interpreter()

def makeSettingWrapper(name,settingsMgr,docstring=None):
    """ Neutral setting wrapper for convenient access to the value of a setting.
        If you need to handle events on value change,link these directly to the events of the corresponding control.
    """
    def getter(self): # pylint: disable=[unused-argument] # self will be passed on when used in class
        return settingsMgr.settings[name].value
    def setter(self,value): # pylint: disable=[unused-argument] # self will be passed on when used in class
        settingsMgr.settings[name].value = value
    return property(getter,setter,doc=docstring)

########################## General Settings Manager ###############################################

class SettingsManager(ESIBD_GUI):
    """Bundles miltiple settings into a single object to handle shared functionality"""
    def __init__(self,esibdWindow,defaultFile,tree = None,**kwargs):
        super().__init__(esibdWindow=esibdWindow,**kwargs)
        self.esibdWindow = esibdWindow
        self.defaultFile = defaultFile
        self.tree   = tree
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.initSettingsContextMenu)
        self.defaultSettings = {}
        self.settings = {}
        self.loading = True
        #self.init() # call this after creating the instance,as the instance is required during initialization

    def addDefaultSettings(self,parent,defaultSettings):
        self.defaultSettings.update(defaultSettings)
        # generate property for direct access of setting value from parent
        for name,default in defaultSettings.items():
            if default[ESIBD_Parameter.ATTR] is not None:
                setattr(parent.__class__,default[ESIBD_Parameter.ATTR],makeSettingWrapper(name,self))

    def initSettingsContextMenu(self,pos):
        try:
            self.initSettingsContextMenuBase(self.settings[self.tree.itemAt(pos).fullName],self.tree.mapToGlobal(pos))
        except KeyError as e: # setting could not be identified
            self.print(e)

    ADDITEM     = 'Add Item'
    EDITITEM     = 'Edit Item'
    REMOVEITEM     = 'Remove Item'
    SELECTPATH  = 'Select Path'
    SELECTFILE  = 'Select File'

    def initSettingsContextMenuBase(self,setting,pos):
        """General implementation of context a menu.
        The relevent actions will be chosen based on the type and properties of the setting."""
        settingsContextMenu = QMenu(self.tree)
        changePathAction = None
        addItemAction = None
        editItemAction = None
        removeItemAction = None
        setToDefaultAction = None
        makeDefaultAction = None
        if setting.widgetType == ESIBD_Parameter.WIDGETPATH:
            changePathAction = settingsContextMenu.addAction(self.SELECTPATH)
        elif (any(setting.widgetType == wType for wType in [ESIBD_Parameter.WIDGETCOMBO,ESIBD_Parameter.WIDGETINTCOMBO,ESIBD_Parameter.WIDGETFLOATCOMBO])
                and not isinstance(setting.parent,ESIBD_Channel)):
            # ESIBD_Channels are part of ESIBD_Devices which define items centrally
            addItemAction = settingsContextMenu.addAction(self.ADDITEM)
            editItemAction = settingsContextMenu.addAction(self.EDITITEM)
            removeItemAction = settingsContextMenu.addAction(self.REMOVEITEM)
        if not isinstance(setting.parent,ESIBD_Channel):
            setToDefaultAction = settingsContextMenu.addAction(f'Set to Default: {setting.default}')
            makeDefaultAction = settingsContextMenu.addAction('Make Default')
        settingsContextMenuAction = settingsContextMenu.exec(pos)
        if settingsContextMenuAction is not None: # no option selected (NOTE: if it is None this could trigger a non initialized action which is also None if not tested here)
            if settingsContextMenuAction is setToDefaultAction:
                setting.setToDefault()
            if settingsContextMenuAction is makeDefaultAction:
                setting.makeDefault()
            elif settingsContextMenuAction is changePathAction:
                startPath = setting.value
                newPath = Path(QFileDialog.getExistingDirectory(self.esibdWindow,self.SELECTPATH,startPath.as_posix(),QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontResolveSymlinks))
                if newPath != Path('.'): # directory has been selected successfully
                    setting.value = newPath
            elif settingsContextMenuAction is addItemAction:
                text,ok = QInputDialog.getText(self,self.ADDITEM,self.ADDITEM)
                if ok and text != '':
                    setting.addItem(text)
            elif settingsContextMenuAction is editItemAction:
                text,ok = QInputDialog.getText(self,self.EDITITEM,self.EDITITEM,text = str(setting.value))
                if ok and text != '':
                    setting.editCurrentItem(text)
            elif settingsContextMenuAction is removeItemAction:
                setting.removeCurrentItem()

    def init(self): # call after all defaultSettings have been added!
        self.loadSettings(file = self.defaultFile)

    def loadSettings(self,file = None): # public method
        """loading settings from .h5 or ini file"""
        self.loading = True
        if file is None: # get file via dialog
            file = Path(QFileDialog.getOpenFileName(parent = self.esibdWindow,caption = self.SELECTFILE,
                                                    directory = self.esibdWindow.configPath.as_posix(),filter = self.FILTER_INI_H5)[0])
        if file == Path('.'):
            return
        self.settings.clear()
        self.tree.clear() # Remove all previoisly existing widgets. They will be recreated based on settings in file.
        useFile = False
        if file.suffix == core.FILE_INI:
            # Load settings from INI file
            if file != Path('.') and file.exists():
                confParser = configparser.ConfigParser()
                try:
                    confParser.read(file)
                    useFile = True
                except KeyError:
                    pass
            for name,default in self.defaultSettings.items():
                if not default[ESIBD_Parameter.INTERNAL] and useFile and not name in confParser:
                    self.print(f'Using defaults for setting {name}.')
                self.settings[name]=ESIBD_Setting(esibdWindow = self.esibdWindow,parent=self,name = name,
                    value = confParser[name][ESIBD_Parameter.VALUE] if useFile and name in confParser and ESIBD_Parameter.VALUE in confParser[name] else default[ESIBD_Parameter.VALUE],
                    default = confParser[name][ESIBD_Parameter.DEFAULT] if useFile and name in confParser and ESIBD_Parameter.DEFAULT in confParser[name] else default[ESIBD_Parameter.DEFAULT],
                    items = confParser[name][ESIBD_Parameter.ITEMS] if useFile and name in confParser and ESIBD_Parameter.ITEMS in confParser[name] else default[ESIBD_Parameter.ITEMS],
                    _min = default[ESIBD_Parameter.MIN],_max = default[ESIBD_Parameter.MAX],
                    internal = default[ESIBD_Parameter.INTERNAL] if ESIBD_Parameter.INTERNAL in default else False,
                    toolTip = default[ESIBD_Parameter.TOOLTIP],
                    tree = self.tree if default[ESIBD_Parameter.WIDGET] is None else None,
                    widgetType = default[ESIBD_Parameter.WIDGETTYPE],widget = default[ESIBD_Parameter.WIDGET],
                    event = default[ESIBD_Parameter.EVENT],
                    parentItem = self.hdfRequireParentItem(name,self.tree.invisibleRootItem()))
        else:
            with h5py.File(file,'r' if file.exists() else 'w') as f:
                if self.name in f:
                    g = f[self.name]
                    useFile = True
                for name,default in self.defaultSettings.items():
                    if useFile and not name in g:
                        self.print(f'Using defaults for setting {name}.')
                    self.settings[name] = ESIBD_Setting(esibdWindow = self.esibdWindow,parent=self,name = name,
                            value = g[name].attrs[ESIBD_Parameter.VALUE] if useFile and name in g and ESIBD_Parameter.VALUE in g[name].attrs else default[ESIBD_Parameter.VALUE],
                            default = g[name].attrs[ESIBD_Parameter.DEFAULT] if useFile and name in g and ESIBD_Parameter.DEFAULT in g[name].attrs else default[ESIBD_Parameter.DEFAULT],
                            items = g[name].attrs[ESIBD_Parameter.ITEMS] if useFile and name in g and ESIBD_Parameter.ITEMS in g[name].attrs else default[ESIBD_Parameter.ITEMS],
                            _min = default[ESIBD_Parameter.MIN],_max = default[ESIBD_Parameter.MAX],
                            internal = default[ESIBD_Parameter.INTERNAL] if ESIBD_Parameter.INTERNAL in default else False,
                            toolTip = default[ESIBD_Parameter.TOOLTIP],
                            tree = self.tree if default[ESIBD_Parameter.WIDGET] is None else None, # dont use tree if widget is provided independently
                            widgetType = default[ESIBD_Parameter.WIDGETTYPE],widget = default[ESIBD_Parameter.WIDGET],
                            event = default[ESIBD_Parameter.EVENT],
                            parentItem = self.hdfRequireParentItem(name,self.tree.invisibleRootItem()))

        if not useFile: # create default if not exist
            self.print(f'Adding default setting for {self.name} in {file}.')
            self.saveSettings(file)
        self.expandTree(self.tree)
        self.loading = False

    def expandTree(self,tree):
        # expand all categories
        it = QTreeWidgetItemIterator(tree,QTreeWidgetItemIterator.IteratorFlag.HasChildren)
        while it.value():
            it.value().setExpanded(True)
            it +=1
        # size to content
        tree.header().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)

    def hdfRequireParentItem(self,name,parentItem):
        names = name.split('/')
        if len(names) > 1: # only ensure parents are there. last widget will be created as an ESIBD_Setting
            for n in name.split('/')[:-1]:
                children = [parentItem.child(i) for i in range(parentItem.childCount())] # list of existing children
                children_text = [c.text(0) for c in children]
                if n in children_text: # reuse existing
                    parentItem = parentItem.child(children_text.index(n))
                else:
                    parentItem = QTreeWidgetItem(parentItem,[n])
        return parentItem

    def saveSettings(self, file=None, default=False): # public method
        """saving settings to .h5 or ini file"""
        if default:
            file = self.defaultFile
        if file is None: # get file via dialog
            file = Path(QFileDialog.getSaveFileName(parent = self.esibdWindow,caption = self.SELECTFILE,
                                                    directory = self.esibdWindow.configPath.as_posix(),filter = self.FILTER_INI_H5)[0])
        if file == Path('.'):
            return
        if file.suffix == core.FILE_INI:
            config = configparser.ConfigParser()
            config[core.INFO] = core.infoDict(self.name)
            for name,default in self.defaultSettings.items():
                if not name in [ESIBD_Parameter.DEFAULT.upper(),core.VERSION] and not self.settings[name].internal:
                    config[name] = {}
                    config[name][ESIBD_Parameter.VALUE]     = str(self.settings[name].value)
                    config[name][ESIBD_Parameter.DEFAULT]   = str(self.settings[name].default)
                    if default[ESIBD_Parameter.WIDGETTYPE] == ESIBD_Parameter.WIDGETCOMBO:
                        config[name][ESIBD_Parameter.ITEMS] = ','.join(self.settings[name].items)
            with open(file,'w',encoding = self.UTF8) as configfile:
                config.write(configfile)
        else:
            with h5py.File(file,'a',track_order = True) as f: # will update if exist,otherwise create
                h5py.get_config().track_order = True
                self.hdfUpdateVersion(f)
                g = require_group(f,self.name) #,track_order = True
                for name,default in self.defaultSettings.items():
                    self.hdfSaveSettig(g,name,default)

    def hdfSaveSettig(self,g,name,default):
        for n in name.split('/'):
            g = require_group(g,n) #,track_order = True
        g.attrs[ESIBD_Parameter.VALUE]     = self.settings[name].value
        g.attrs[ESIBD_Parameter.DEFAULT]     = self.settings[name].default
        if default[ESIBD_Parameter.WIDGETTYPE] == ESIBD_Parameter.WIDGETCOMBO:
            g.attrs[ESIBD_Parameter.ITEMS]     = ','.join(self.settings[name].items)

    def hdfUpdateVersion(self,f):
        # if core.INFO in f:
        #     v = f[core.INFO]  # update existing entry
        # else:
        v = require_group(f,core.INFO) #,track_order = True
        for key,value in core.infoDict(self.name).items():
            v.attrs[key] = value

class ESIBD_SETTINGS_GUI(SettingsManager):
    """Displays settings defined by other widgets"""

    SETTINGS    = 'Settings'
    LOAD_GS     = 'Load General Settings'
    GS_FILE     = 'settings.ini'
    DATAPATH  = 'Data Path'
    CONFIGPATH  = 'Config Path'
    defaultConfigPath = Path('conf/').resolve()

    def __init__(self,esibdWindow,**kwargs):
        self.tree = QTreeWidget()
        super().__init__(esibdWindow=esibdWindow,name=self.SETTINGS,tree=self.tree,defaultFile=Path(esibdWindow.qSet.value(self.CONFIGPATH,self.defaultConfigPath)) / self.GS_FILE,**kwargs)
        self.tree.setHeaderLabels(['Parameter','Value'])
        self.addContentWidget(self.tree)

        self.addButton(0,0,self.LOAD,lambda : self.loadSettings(None),'Load Settings.')
        self.addButton(0,1,self.EXPORT,lambda : self.saveSettings(None),'Export Settings.')
        self.esibdWindow.mainTabWidget.addTab(self,self.name)

        s = {}
        s[self.DATAPATH]=parameterDict(value = Path('data/').resolve(),
                                        widgetType = ESIBD_Parameter.WIDGETPATH,internal = True,event = self.updateDataPath,attr = 'dataPath')
        s[self.CONFIGPATH]=parameterDict(value = self.defaultConfigPath,
                                        widgetType = ESIBD_Parameter.WIDGETPATH,internal = True,event = self.updateConfigPath,attr = 'configPath')
        # validate config path before loading settings from file
        path = Path(self.esibdWindow.qSet.value(self.CONFIGPATH,self.defaultConfigPath)) # validate path and use default if not exists
        if not path.exists():
            Path(self.defaultConfigPath).mkdir(parents=True,exist_ok=True)
            self.esibdWindow.qSet.setValue(self.CONFIGPATH,self.defaultConfigPath)
            self.defaultFile = Path(esibdWindow.qSet.value(self.CONFIGPATH,self.defaultConfigPath)) / self.GS_FILE
            self.print(f'Warning: Could not find path {path.as_posix()}. Defaulting to {self.defaultFile.parent.as_posix()}.')
        # attributes for DPI and Testmode are optional. To reduce passing reference to esibdWindow, access using getDPI() and getTestmode() inherited from ESIBD_GUI
        s['DPI']                    = parameterDict(value = '100',toolTip = 'DPI used in ES-IBD Explorer',internal=True, attr='dpi', event=self.updateDPI,
                                                                items = '100,150,200,300',widgetType = ESIBD_Parameter.WIDGETINTCOMBO)
        s['Testmode']               = parameterDict(value = False,toolTip = 'Devices will fake communication in Testmode!', widgetType = ESIBD_Parameter.WIDGETBOOL,
                                    event = lambda : self.esibdWindow.outputWidget.initDevices(restart = self.esibdWindow.outputWidget.acquiring),internal=True,attr='testmode')
        s['Session/Measurement Number'] = parameterDict(value = 0,toolTip = 'Self incrementing measurement number. Set to 0 to start a new session.',
                                                                widgetType = ESIBD_Parameter.WIDGETINT,event = self.updateSessionPath,attr = 'measurementNumber')
        s['Session/Substrate']      = parameterDict(value = 'None',toolTip = 'Choose substrate',
                                                                items = 'None,HOPG,aCarbon,Graphene,Silicon,Gold,Copper',widgetType = ESIBD_Parameter.WIDGETCOMBO,
                                                                event = self.updateSessionPath,attr = 'substrate')
        s['Session/Ion']            = parameterDict(value = 'GroEL',toolTip = 'Choose ion',
                                                                items = 'Betagal,Ferritin,GroEL,ADH,GDH,BSA,DNA,BK',widgetType = ESIBD_Parameter.WIDGETCOMBO,
                                                                event = self.updateSessionPath,attr = 'molion')
        s['Session/Session Type']   = parameterDict(value = 'MS',toolTip = 'Choose session type',
                                                                items = 'MS,depoHV,depoUHV,depoCryo,opt',widgetType = ESIBD_Parameter.WIDGETCOMBO,
                                                                event = self.updateSessionPath,attr = 'sessionType')
        s['Session/Session Path']   = parameterDict(value = '',toolTip = 'Where session data will be stored',
                                                                widgetType = ESIBD_Parameter.WIDGETLABEL,attr = 'sessionPath')
        self.addDefaultSettings(self.esibdWindow,s) # make settings available via self.esibdWindow.attr
        self.init() # will only init basic settings, settings from scans, widgets and other plugins will be added later
        self.settings[self.DATAPATH]._changedEvent() # validate path before first use
        self.loading = True # set flag to indicate settings are not fully initialized.

    def updateDataPath(self):
        if not self.esibdWindow.loading:
            self.updateSessionPath()
            self.esibdWindow.explorerWidget.updateRoot(self.esibdWindow.dataPath)

    def updateConfigPath(self): # load settings from new conf path
        self.defaultFile = self.esibdWindow.configPath / self.GS_FILE
        if not self.esibdWindow.loading:
            self.loadSettings(self.defaultFile)

    def updateSessionPath(self):
        if not self.esibdWindow.loading:
            self.esibdWindow.sessionPath = Path(*[self.esibdWindow.dataPath,self.esibdWindow.substrate,self.esibdWindow.molion,
                datetime.now().strftime(f'%Y-%m-%d_%H-%M_{self.esibdWindow.substrate}_{self.esibdWindow.molion}_{self.esibdWindow.sessionType}')])
            self.esibdWindow.measurementNumber = 0

    def updateDPI(self):
        for w in self.esibdWindow.getScanWidgets():
            w.fig.set_dpi(self.esibdWindow.dpi)

    def getMeasurementFileName(self,extension):
        sessionPath = Path(self.esibdWindow.sessionPath)
        sessionPath.mkdir(parents=True,exist_ok=True) # create if not already existing
        return sessionPath / f'{sessionPath.name}_{self.esibdWindow.measurementNumber:02d}{extension}'

class InstrumentManager(ESIBD_GUI):
    """Top-level manager that controls data aquisition from all instruments.
    While the instruments run independently in separate threads,this class manages parallel collection of data for display and analysis"""

    class SignalCommunicate(QObject): # signals that can be emitted by external threads
        appendDataSignal    = pyqtSignal()
        displayOutputSignal = pyqtSignal()

    def __init__(self,esibdWindow,**kwargs):
        super().__init__(esibdWindow=esibdWindow,**kwargs)
        self.esibdWindow = esibdWindow
        self.dataThread = None
        self.updating = False
        self.time = None
        self.inputs = []    # inputs are tabwidgets that implement user interface and communication for an input device
        self.outputs = []   # outputs are tabwidgets that implement user interface and communication for an output device
        self.acquiring = False
        self.signalComm = self.SignalCommunicate()
        self.signalComm.appendDataSignal.connect(self.appendData)

    ########################## Inout Output Access #################################################

    def channels(self,inout = INOUT.BOTH): # flat list of all channels
        # 15% slower than using cached channels but avoids need to maintain cashed lists when removing and adding channels
        return [y for x in [device.channels for device in self.getDevices(inout)] for y in x]

    def getChannelbyName(self,name,inout = INOUT.BOTH):
        return next((c for c in self.channels(inout) if c.name.strip().lower() == name.strip().lower()),None)

    def getInitializedOutputChannels(self):
        return [y for x in [device.getInitializedChannels() for device in self.outputs] for y in x]

    def getSelectedInputChannel(self):
        return next((c for c in self.channels(inout = INOUT.IN) if c.select),None)

    def getDevices(self,inout = INOUT.BOTH):
        if inout == INOUT.BOTH:
            return self.inputs + self.outputs
        elif inout == INOUT.IN:
            return self.inputs
        else: # inout == INOUT.OUT:
            return self.outputs

    ########################## Inout Output Wrappers #################################################

    def getDefaultSettings(self):
        settings = {}
        settings['Acquisition/Interval'] = parameterDict(value = 100,toolTip = 'Interval for data acquisition in ms',
                                                                widgetType = ESIBD_Parameter.WIDGETINT,_min = 10,_max = 10000,attr = 'interval')
        return settings

    def exportConfiguration(self,file = None,default=False,inout = INOUT.BOTH):
        for d in self.getDevices(inout):
            d.exportConfiguration(file = file,default=default)

    def close(self,inout = INOUT.BOTH):
        self.stopAcquisition()
        for d in self.getDevices(inout):
            d.close()

    def initDevices(self,restart,inout = INOUT.BOTH):
        for d in self.getDevices(inout):
            d.init(restart)

    def initialized(self,inout = INOUT.OUT):
        return any([d.initialized for d in self.getDevices(inout)])

    def setBackground(self,inout = INOUT.OUT):
        for d in self.getDevices(inout):
            d.setBackground()

    def startSampling(self,inout = INOUT.OUT):
        for d in self.getDevices(inout):
            d.startSampling()

    def stopSampling(self,inout = INOUT.OUT):
        for d in self.getDevices(inout):
            d.stopSampling()

    def globalUpdate(self,apply = False,inout = INOUT.BOTH):
        # wait until all channels are complete before applying logic. will be called again when loading completed
        if any([device.loading for device in self.getDevices(inout)]) or self.esibdWindow.loading:
            return
        if inout in [INOUT.BOTH,INOUT.IN]:
            self.updateValues(self.channels(inout = INOUT.IN))
            for c in self.inputs:
                c.apply(apply)
        if inout in [INOUT.BOTH,INOUT.OUT]:
            self.updateValues(self.channels(inout = INOUT.OUT))

    def updateValues(self,channels,N = 2):
        """this minimal implementation will not give a warning about circular definitions
        it will also fail if expressions are nested on more than N levels (N can be increased as needed)
        it should however be sufficient for day to day ESIBD work
        more complex algorithms should only be implemented if they are required to solve a practical problem"""
        self.updating = True # prevent recursive call caused by changing values from here
        # print('updateValues rand:',np.random.rand())
        for _ in range(N): # go through parsing N times,in case the dependencies are not ordered
            for channel in [c for c in channels if not c.active and c.equation != '']: # ignore if no equation defined
                equ = channel.equation
                error = False
                for name in [n for n in channel.equation.split(' ') if len(n) > 1]: # ignore mathematical operators
                    c = next((c for c in channels if c.name == name),None)
                    if c is None:
                        self.print(f'Warning: Could not find channel {name} in equation of channel {channel.name}.')
                        error = True
                    else:
                        equ = equ.replace(c.name,f'{c.value}')
                if error:
                    self.print(f'Warning: Could not resolve equation of channel {channel.name}.')
                else:
                    channel.value = aeval(equ) or 0 # evaluate
        self.updating = False
    ########################## Aquisition ############################################################

    @pyqtSlot()
    def appendData(self):
        # NOTE: add all new entries including time in one step to avoid any chance of unequal array sizes
        self.globalUpdate(inout = INOUT.OUT)
        for c in self.channels():
            c.appendValue()
        self.time.add(time.time()) # add time in seconds
        self.signalComm.displayOutputSignal.emit() # use signal instead of direct call to trigger graph update asynchronously

    def clearHistory(self):
        for c in self.channels():
            c.clearHistory()
        self.time = dynamicNp()

    def startAcquisition(self):
        self.dataThread = Thread(target = self.runDataThread,args =(lambda : self.acquiring,))
        self.dataThread.daemon = True # Terminate with main app independent of stop condition
        self.acquiring = True
        self.dataThread.start()

    def stopAcquisition(self):
        if self.dataThread is not None:
            self.acquiring = False # stop thread
            self.dataThread.join()
        self.sampleOutputPushButton.setChecked(False)

    def getTime(self,cutoff):
        """gets time data corresponding to the intervall that should be displayed
        may need to look for more efficient implementation if there are issues with long acquisitions"""
        return self.time.get()[self.time.get()>cutoff] if self.time.size > 0 else None

    def initOutput(self):
        self.initDevices(self.sampleOutputPushButton.isChecked()) # will start sampling when initialization is complete
        self.outputPlotWidget.clear()
        self.outputPlotWidget.addLegend() # before adding plots
        for c in self.channels(inout = INOUT.OUT): # getInitializedChannels() don't know yet which will be initialized -> create all
            c.plotCurve = None

    def sampleOutput(self):
        if self.sampleOutputPushButton.isChecked():
            if not self.initialized():
                self.initOutput()
            else:
                self.startSampling()
            self.startAcquisition()
        else:
            self.stopSampling()
            self.stopAcquisition()
            for s in self.esibdWindow.getScanWidgets():
                s.acquiring = False # stop all running scans

    def runDataThread(self,acquiring):
        while acquiring():
            time.sleep(self.interval/1000) # in seconds
            # self.printFromThread(f'appenddata {np.random.rand()}') # TODO gets slowed down by plotting in main thread, consider using process instead and updating UI later?!
            self.signalComm.appendDataSignal.emit()

class ESIBD_OUTPUT_GUI(InstrumentManager):
    """Records output data over time"""
    def __init__(self,**kwargs):
        super().__init__(name = 'Output',**kwargs)

        self.outputPlotWidget = pg.PlotWidget()
        self.outputLayout = QVBoxLayout()
        self.outputLayout.addWidget(self.outputPlotWidget)
        self.xSlider = QSlider(Qt.Orientation.Horizontal)
        self.outputLayout.addWidget(self.xSlider)
        self.addContentLayout(self.outputLayout)
        self.esibdWindow.outputDisplayLayout.addWidget(self)

        self.plotWidgetFont = QFont()
        self.plotWidgetFont.setPixelSize(15)
        self.outputPlotWidget.showGrid(x=True,y=True)
        self.outputPlotWidget.setMouseEnabled(x=False,y=True) # keep auto pan in x running,use settings to zoom in x
        self.outputPlotWidget.setAxisItems({'right': pg.AxisItem('right')}) #,size=5
        #self.outputPlotWidget.setLabel('left','<font size="5">Current (pA)</font>') # no label needed as output channels can have various different units -> use plot labels instead
        self.outputPlotWidget.getAxis('left').setTickFont(self.plotWidgetFont)
        self.outputPlotWidget.getAxis('right').setTickFont(self.plotWidgetFont)
        self.xSlider.valueChanged.connect(self.updateX)

        self.displayTimeComboBox = QComboBox()
        self.displayTimeComboBox.setToolTip('Length of displayed current history in min')
        self.provideRow(0).insertWidget(0,self.displayTimeComboBox)

        self.signalComm.displayOutputSignal.connect(self.displayOutputData)

        self.addButton(0,1,'Close', func=lambda : self.close(inout = INOUT.BOTH),toolTip='Close communication.')
        self.addButton(0,2,'Init',  func=self.initOutput,toolTip='Initialize communication.')
        self.addButton(0,3,'Clear', func=self.clearHistory,toolTip='Clear history.')
        self.addButton(0,4,'Set BG',func=self.setBackground,toolTip='Set background.')
        self.addButton(0,5,self.SAVE,  func=self.exportOutputData,toolTip='Save to current session.')
        self.sampleOutputPushButton = self.addButton(0,6,'Sample',func=self.sampleOutput,toolTip='Toogle data acquisition.',checkable=True)

        self.initData()
        self.esibdWindow.settingsWidget.addDefaultSettings(self,self.getDefaultSettings())

    def init(self):
        for w in self.esibdWindow.getMainWidgets():
            #print(w.name,type(w),type(w).__bases__)
            if isinstance(w,ESIBD_Input_Device):
                self.inputs.append(w)
            elif isinstance(w,ESIBD_Output_Device):
                self.outputs.append(w)
        self.clearHistory() # Init all inputs and outputs
        self.globalUpdate(True)
        if self.esibdWindow.sessionPath == '': # keep existing session path when restarting
            self.esibdWindow.settingsWidget.updateSessionPath()
        self.xChannelChanged()

    def getDefaultSettings(self):
        ds = super().getDefaultSettings()
        ds['Display Time'    ] = parameterDict(value = '2',toolTip = 'Length of displayed history in min.',
                                                                items = '0.2,1,2,3,5,10,60,600',widgetType = ESIBD_Parameter.WIDGETFLOATCOMBO,
                                                                 widget = self.displayTimeComboBox,_min = .2,_max = 3600,
                                                                event = self.displayOutputData,attr = 'displaytime')
        ds['Acquisition/Subtract Background'] = parameterDict(value = True,toolTip = 'Subtract background.',widgetType = ESIBD_Parameter.WIDGETBOOL,
                                                                attr = 'subtractBackground')
        return ds

    def clearHistory(self):
        self.outputPlotWidget.clear()
        return super().clearHistory()

    def supportsFile(self, file):
        return any(file.name.endswith(suffix) for suffix in [self.FILE_OUT,'.cur.rec','.cur.h5'])

    def loadData(self,file):
        """Plots one dimensional data for multiple file types."""
        # using linewidget to display
        axes = self.esibdWindow.lineWidget.axes
        fig = self.esibdWindow.lineWidget.fig
        canvas = self.esibdWindow.lineWidget.canvas
        toolbar = self.esibdWindow.lineWidget.toolbar
        axes[0].clear()
        axes[0].set_xlabel('Time')
        fig.autofmt_xdate() # does not affect other plots if axis is cleared
        self.loadDataInternal(file)
        if len(self.outputData) > 0:
            #axes[0].set_ylabel('Current (pA)') # no y label needed, output channels may have various different units -> use plot lable instead
            _time = [datetime.fromtimestamp(float(t)) for t in self.inputData[0]] # convert timestamp to datetime
            for i, (data,name,unit) in enumerate(zip(self.outputData,self.outputNames,self.outputUnits)):
                if '_BG' in name:
                    continue
                else:
                    axes[0].plot(_time, data-self.outputData[i+1] if self.subtractBackground else data, label=f'{name} ({unit})')
            axes[0].legend(loc = 'best',prop={'size': 7},frameon=False)

        fig.tight_layout()
        canvas.draw_idle()
        toolbar.update() # reset history for zooming and home view
        canvas.get_default_filename = lambda: file.with_suffix('') # set up save file dialog
        self.labelPlot(axes[0],file.name)
        self.esibdWindow.displayTabWidget.setCurrentWidget(self.esibdWindow.lineWidget)

    def initData(self):
        self.outputData = []
        self.outputNames = []
        self.outputUnits = []
        self.inputChannels = []
        self.inputNames = []
        self.inputUnits = []
        self.inputData = []
        self.inputInitial = []
        self.outputChannels = []

    def loadDataInternal(self,file):
        """Loads data from various files into generic format for plotting."""
        self.initData()
        if file.name.endswith('.cur.rec'):  # legacy ES-IBD Control file
            with open(file,'r',encoding = self.UTF8) as f:
                f.readline()
                headers = f.readline().split(',') # read names from second line
            try:
                data = np.loadtxt(file,skiprows=4,delimiter=',',unpack=True)
            except ValueError as e:
                self.print(f'Warning: Error when loading from {file.name}: {e}')
                return
            if data.shape[0] == 0:
                self.print(f'Warning: no data found in file {file.name}')
                return
            for d,n in zip(data,headers):
                self.outputChannels.append(None)
                self.outputNames.append(n.strip())
                self.outputData.append(d)
                self.outputUnits.append('pA')
                self.outputChannels.append(None)
                self.outputNames.append(n.strip()+'_BG') # backgrounds were not saved at the time
                self.outputData.append(np.zeros(d.shape[0]))
                self.outputUnits.append('pA')
            if len(self.outputData) > 0: # might be empty
                self.inputChannels.append(None)
                self.inputNames.append(self.TIME)
                self.inputData.append([100*i for i in range(self.outputData[0].shape[0])]) # need to fake time axis as it was not implemented
                self.inputUnits.append('')
        elif file.name.endswith('.cur.h5'):
            with h5py.File(file, 'r') as f:
                self.inputNames.append(self.TIME)
                self.inputChannels.append(None)
                self.inputData.append(f[self.TIME][:])
                self.inputUnits.append('')
                g = f['Current']
                for name,item in g.items():
                    self.outputNames.append(name)
                    self.outputChannels.append(None)
                    self.outputData.append(item[:])
                    self.outputUnits.append('pA')
        else:
            with h5py.File(file,'r') as f:
                self.inputNames.append(self.TIME)
                self.inputChannels.append(None)
                self.inputData.append(f[ESIBD_Scan.INPUTCHANNELS][self.TIME][:])
                self.inputUnits.append('')
                g = f[ESIBD_Scan.OUTPUTCHANNELS]
                for name,item in g.items():
                    self.outputNames.append(name)
                    self.outputChannels.append(None)
                    self.outputData.append(item[:])
                    self.outputUnits.append(item.attrs[ESIBD_Scan.UNIT] if ESIBD_Scan.UNIT in item.attrs else '')

    @pyqtSlot()
    def displayOutputData(self):
        """Plots the enabled and initialized channels in the main output plot
            The x axis is either time or a selected channel"""
        if self.esibdWindow.loading or self.esibdWindow.settingsWidget.loading:
            return
        xChannel = self.getSelectedInputChannel()
        displaytime = self.getTime(time.time() - float(self.displaytime)*60)
        if displaytime is None: # values not yet available
            return
        for channel in self.getInitializedOutputChannels()[::-1]: # [::-1] -> reverse list to plot top channels last and thus display them on top of others.
            if channel.plotCurve is None:
                channel.plotCurve = self.outputPlotWidget.plot(pen=pg.mkPen((channel.color),width=channel.linewidth),name = f'{channel.name} ({channel.parent.unit})') # initialize empty plots
            if channel.display:
                if xChannel is not None:
                    x = xChannel.getValues()[-min(len(displaytime),xChannel.getValues().shape[0]):] # match length to displaytime
                    y = channel.getValues(subtractBackground = self.subtractBackground)
                    length = min(x.shape[0],y.shape[0]) # plot minimal available history
                    mean,bin_edges,_ = binned_statistic(x[-length:],y[-length:],bins=abs(xChannel.max-xChannel.min)*2,range=(xChannel.min,xChannel.max))
                    channel.plotCurve.setData((bin_edges[:-1] + bin_edges[1:]) / 2,mean)
                else:
                    y = channel.getValues(subtractBackground = self.subtractBackground)
                    length = min(displaytime.shape[0],y.shape[0]) # plot minimal available history
                    # ratio = max(1,length // 200) # limit number of shown datapoints to prevent performance issues with long history
                    # channel.plotCurve.setDownsampling(auto=False,ds=ratio) # display gets less responsive than without this even after 1000 data points
                    if length > 1: # need at least 2 datapoints to plot connecting line segement
                        channel.plotCurve.setData(displaytime[-length:],y[-length:])
            else:
                channel.plotCurve.clear()

    def xChannelChanged(self):
        """Adjust user intercaface for given x axis,either time or specific channel.
        If a channel is selected,a slider will be displayed to control the value corresponding to the x axis of the graph."""
        if not self.esibdWindow.loading:
            xChannel = self.getSelectedInputChannel()
            if xChannel is not None:
                self.xSlider.setVisible(True)
                self.xSlider.setValue((xChannel.value - xChannel.min)*self.xSlider.maximum()/(xChannel.max - xChannel.min)) # map voltage range onto slider range
                self.outputPlotWidget.setAxisItems({'bottom': pg.AxisItem('bottom')}) #,size=5
                self.outputPlotWidget.setLabel('bottom',f'<font size="5">{xChannel.name} ({xChannel.parent.unit})</font>') # has to be after setAxisItems
                self.outputPlotWidget.enableAutoRange(self.outputPlotWidget.getViewBox().XAxis,False)
                # setXRange definition changing all time  # QRectF(-1,0,0,0) bug: XRange is set from 0 to 1 if called with the same parameters -> calling with -1 0 to trigger update
                self.outputPlotWidget.setXRange(-1,0,padding=0) #  pylint: disable = redundant-keyword-arg
                self.outputPlotWidget.setXRange(xChannel.min,xChannel.max,padding=0) # pylint: disable = redundant-keyword-arg #QRectF(xChannel.min,0,xChannel.max-xChannel.min,0)
            else: # default to time
                self.xSlider.setVisible(False)
                self.outputPlotWidget.setAxisItems({'bottom': pg.DateAxisItem()}) #,size=5
                self.outputPlotWidget.setLabel('bottom','<font size="5">Time</font>') # has to be after setAxisItems
                self.outputPlotWidget.enableAutoRange(self.outputPlotWidget.getViewBox().XAxis,True)
            self.outputPlotWidget.getAxis('bottom').setTickFont(self.plotWidgetFont)
            if self.acquiring:
                self.displayOutputData()

    def updateX(self,value):
        xChannel = self.getSelectedInputChannel()
        if xChannel is not None:
            xChannel.value = xChannel.min + value/self.xSlider.maximum()*(xChannel.max - xChannel.min) # map slider range onto range

    FILE_OUT    = '_OUT.h5'
    TIME        = 'Time'

    def exportOutputData(self):
        self.esibdWindow.measurementNumber += 1
        with h5py.File(name = self.esibdWindow.settingsWidget.getMeasurementFileName(self.FILE_OUT),mode = 'a',track_order = True) as f:
            self.esibdWindow.settingsWidget.hdfUpdateVersion(f)
            g = f.create_group(ESIBD_Scan.INPUTCHANNELS,track_order = True)
            g.create_dataset(self.TIME,data=self.time.get(),dtype=np.float64,track_order = True) # need double precision to keep all decimal places
            g = f.create_group(ESIBD_Scan.OUTPUTCHANNELS,track_order = True)
            for channel in self.getInitializedOutputChannels():
                h = g.create_dataset(channel.name,data=channel.values.get(),dtype='f')
                h.attrs[ESIBD_Scan.UNIT] = channel.parent.unit
                h = g.create_dataset(channel.name + '_BG',data=channel.backgrounds.get(),dtype='f')
                h.attrs[ESIBD_Scan.UNIT] = channel.parent.unit
        self.exportConfiguration(file = self.esibdWindow.settingsWidget.getMeasurementFileName(self.FILE_OUT)) # save corresponding device settings in measurement file
        self.esibdWindow.explorerWidget.populateTree()

class ESIBD_CONSOLE_GUI(ESIBD_GUI):
    """Initializes the hidden console."""
    def __init__(self,esibdWindow):
        super().__init__(name='Console')
        self.mainConsole    = pyqtgraph.console.ConsoleWidget(parent=esibdWindow,namespace= {'self': esibdWindow,'timeit': timeit,
                                                                'np': np,'plt': plt,'inspect': inspect,'INOUT':INOUT,'ESIBD_Parameter':ESIBD_Parameter})
        self.mainConsole.write(('All features implemented in the user interface and more can be accessed directly from this console.\n'
                                'It is mainly intended for debugging. Use at your own Risk! You can select some commonly used commands directly from the combobox below.\n'
                                'Status messages will also be logged here.\n'))
        self.vertLayout.addWidget(self.mainConsole,1) # https://github.com/pyqtgraph/pyqtgraph/issues/404 # add before hintsTextEdit

        self.commonCommandsLayout = QGridLayout()
        self.commonCommandsLayout.setContentsMargins(11,0,11,0)
        self.commonCommandsComboBox = QComboBox()
        self.commonCommandsComboBox.wheelEvent = lambda event: None
        self.commonCommandsComboBox.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed)
        self.commonCommandsComboBox.addItems([
            "select command",
            "w=self.mainTabWidget.widget(6)",
            "w=self.displayTabWidget.widget(0)",
            "timeit.timeit('w.scanPlot(update=True,done=False)',number=100,globals=globals())",
            "from custom import CustomControl; CustomControl(self.mainTabWidget) # add custom control from custom.py",
            "timeit.timeit('self.outputWidget.globalUpdate()',number=10,globals=globals())",
            "self.testTiming()",
            "c = self.outputWidget.getChannelbyName('RT_Frontplate',inout = INOUT.IN)",
            "c = self.outputWidget.getChannelbyName('RT_Detector',inout = INOUT.OUT)",
            "vm = c.parent.voltageMgr",
            "p = c.getParameterByName(core.ENABLED)",
            "print(p.widgetType,p.value,p.getWidget())",
            "self.qSet.clear() # reset settings saved in registry. Only use when testing fresh deployment on new computer"
        ])
        self.commonCommandsComboBox.currentIndexChanged.connect(self.commandChanged)
        self.commonCommandsLayout.setSpacing(0)
        self.commonCommandsLayout.addWidget(self.commonCommandsComboBox)
        self.vertLayout.addLayout(self.commonCommandsLayout,0)
        esibdWindow.consoleDockVerticalLayout.addWidget(self)

    def commandChanged(self,_):
        if self.commonCommandsComboBox.currentIndex() != 0:
            self.mainConsole.ui.input.setText(self.commonCommandsComboBox.currentText())
            self.mainConsole.ui.input.execCmd()
            self.commonCommandsComboBox.setCurrentIndex(0)
