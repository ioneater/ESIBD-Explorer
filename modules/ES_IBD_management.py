"""This module contains classes that contain and manage a list of (extended) UI elements.
In addition it contains classes used to manage data acquisition.
Finally it contains classes for data export, and data import."""


import time
from threading import Thread
from datetime import datetime
from pathlib import Path
import configparser
import h5py
from PyQt5.QtWidgets import QTreeWidgetItem, QFileDialog
from PyQt5.QtCore import Qt, QSettings, QObject, pyqtSlot
import numpy as np
import ES_IBD_controls as controls
import ES_IBD_configuration as conf
from GA import GA

########################## General Settings Manager ###############################################

class SettingsManager(dict):
    """Bundles miltiple settings into a single object to handle shared functionality"""
    def __init__(self, esibdWindow, tree = None, mode = None):
        super().__init__()
        self.esibdWindow=esibdWindow
        self.tree   = tree
        self.mode   = mode
        self.hdf5   = self.mode in [conf.S2DSETTINGS,conf.SESETTINGS]
        self.qSet   = QSettings(conf.COMPANY_NAME, conf.PROGRAM_NAME)
        if self.hdf5:
            self.load(conf.configFile(self.qSet))
        else:
            self.load(conf.settingsFile(self.qSet))

    def load(self, file = None): # public method
        if self.hdf5:
            self.loadHDF(file)
        else:
            self.loadINI(file)

    def save(self, file = None, append='w'): # public method
        if self.hdf5:
            self.saveHDF(file, append)
        else:
            self.saveINI(file, append)

    def loadHDF(self, file = None):
        """initiates loading of settings from group corresponding to current mode"""
        if file is None: # get file via dialog
            file = Path(QFileDialog.getOpenFileName(self.esibdWindow,conf.SELECTFILE,filter = conf.FILTER_H5)[0])
        elif not file.exists(): # create default if not exist
            self.hdfGenerateDefaultConfig(file)
        if file != Path('.'):
            self.tree.clear()
            with h5py.File(file, 'r') as f:
                try:
                    item = f[self.mode] # only load from specific group, ignore other settings or data in the file
                except KeyError:
                    self.esibdWindow.esibdPrint(f'Could not load {self.mode} from {file}')
                    return
                if item is not None:
                    self.loadHDFStep(item,self.tree)
        self.esibdWindow.expandTree(self.tree)

    def loadHDFStep(self, obj, parent):
        """recursively loads settings from hdf5 file"""
        treeWidgetItem=None
        if len(list(obj.attrs.items())) > 0: # has attributes -> parameter
            setting = {}
            setting[conf.VALUE] = obj.attrs[conf.VALUE]
            setting[conf.DEFAULT] = obj.attrs[conf.DEFAULT]
            setting[conf.TOOLTIP] = obj.attrs[conf.TOOLTIP]
            setting[conf.ITEMS] = obj.attrs[conf.ITEMS]

            if isinstance(setting[conf.VALUE],np.float64):
                widget = conf.WIDGETFLOAT
            elif isinstance(setting[conf.VALUE], np.int32):
                widget = conf.WIDGETINT
            elif setting[conf.ITEMS] != '':
                widget = conf.WIDGETCOMBO
            else: # if type(setting[conf.VALUE]) is str:
                widget = conf.WIDGETTEXT
            setting[conf.WIDGET] = widget
            # use full path as unique string to find setting but only use last element for display
            self[obj.name] = controls.esibdSetting(self.esibdWindow,self.tree,obj.name,setting, parentItem = parent)
            treeWidgetItem = self[obj.name]
        else: # this is just a group -> category
            treeWidgetItem = QTreeWidgetItem(parent,[Path(obj.name).name])
            treeWidgetItem.fullName = obj.name # tag this to identify corresponding setting later from context menu
        for _, item in obj.items(): # name, item
            if isinstance(item, h5py.Group):
                self.loadHDFStep(item,treeWidgetItem)

    def saveHDF(self, file = None, append='w'):
        if file is None: # get file via dialog
            file = Path(QFileDialog.getSaveFileName(self.esibdWindow,conf.SELECTFILE,filter = conf.FILTER_H5)[0])
        if file != Path('.'):
            with h5py.File(file, append, track_order = True) as f:
                if append !='a': # if append == 'a', version group already exists
                    self.hdfAddSettingTemplate(f.create_group(conf.VERSION) ,f'{conf.VERSION_MAYOR}.{conf.VERSION_MINOR}', default=None, toolTip = self.mode)
                self.saveHDFStep(f,self.tree.findItems(self.mode,Qt.MatchExactly|Qt.MatchRecursive)[0]) # iterate over treewidget items

    def saveHDFStep(self, f, item):
        g=f.create_group(item.text(0), track_order = True)
        setting = None
        try:
            setting = self[item.fullName]
        except KeyError:
            pass
        if setting is not None:  #add attributes
            self.hdfAddSetting(g,setting)
        for i in range(item.childCount()):
            child = item.child(i)
            self.saveHDFStep(g,child)

    def hdfGenerateDefaultConfig(self,file):
        """Generated defaul settings file if file was not found.
        If you delete the default file, this will be used to generate a new one on startup."""
        self.esibdWindow.esibdPrint(f'Generating default config file {file}')
        with h5py.File(file, "w", track_order = True) as f: # track_order -> sort in creation order, rather than alphanumeric
            self.hdfAddSettingTemplate(f.create_group(conf.VERSION), f'{conf.VERSION_MAYOR}.{conf.VERSION_MINOR}', default=None, toolTip = self.mode)
            g=f.create_group(conf.S2DSETTINGS, track_order = True) # always use track_order, using it on file creation is not sufficient.
            self.hdfAddSettingTemplate(g.create_group(conf.DISPLAY),'RT_Front-Plate', toolTip = 'Display current on this electrode',
                                         items = 'RT_Front-Plate,RT_Detector,RT_Sample-Center,RT_Sample-End,Aperture')
            self.hdfAddSettingTemplate(g.create_group(conf.WAITFIRST) ,1000, toolTip = 'wait at start of data column in ms\n(large voltage step -> large pickup -> longer wait)')
            self.hdfAddSettingTemplate(g.create_group(conf.WAIT)      , 300, toolTip = 'wait between datapoints in ms\n(small voltage step -> small pickup -> shorter wait)')
            self.hdfAddSettingTemplate(g.create_group(conf.AVERAGE)  ,1000)

            h=g.create_group(conf.LEFTRIGHT, track_order = True)
            self.hdfAddSettingTemplate(h.create_group(conf.CHANNEL),'LB-S-LR', items = 'LA-S-LR,LB-S-LR,LC-S-LR,LD-S-LR,LE-S-LR')
            self.hdfAddSettingTemplate(h.create_group(conf.FROM),-5.0)
            self.hdfAddSettingTemplate(h.create_group(conf.TO),5.0)
            self.hdfAddSettingTemplate(h.create_group(conf.STEP),.5)
            # self.hdfAddSettingTemplate(h.create_group(conf.OFFSET),0.)

            h=g.create_group(conf.UPDOWN, track_order = True)
            self.hdfAddSettingTemplate(h.create_group(conf.CHANNEL),'LB-S-UD', items = 'LA-S-UD,LB-S-UD,LC-S-UD,LD-S-UD,LE-S-UD')
            self.hdfAddSettingTemplate(h.create_group(conf.FROM),-5.0)
            self.hdfAddSettingTemplate(h.create_group(conf.TO),5.0)
            self.hdfAddSettingTemplate(h.create_group(conf.STEP),.5)
            # self.hdfAddSettingTemplate(h.create_group(conf.OFFSET),0.)

            g=f.create_group(conf.SESETTINGS, track_order = True)
            self.hdfAddSettingTemplate(g.create_group(conf.CHANNEL),'RT_Grid',toolTip = 'Electrode that is swept through', items = 'RT_Grid,Sample-Center,Sample-End')
            self.hdfAddSettingTemplate(g.create_group(conf.DISPLAY),'RT_Detector',toolTip = 'Will be displayed and used for fitting', items = 'RT_Detector,RT_Front-Plate,Aperture')
            self.hdfAddSettingTemplate(g.create_group(conf.WAITFIRST) ,1000, toolTip = 'wait time at start of scan in ms\n(large voltage step -> large pickup -> longer wait)')
            self.hdfAddSettingTemplate(g.create_group(conf.WAIT)      , 300, toolTip = 'wait between datapoints in ms\n(small voltage step -> small pickup -> shorter wait)')
            self.hdfAddSettingTemplate(g.create_group(conf.AVERAGE), 1000)
            self.hdfAddSettingTemplate(g.create_group(conf.FROM),-10.0)
            self.hdfAddSettingTemplate(g.create_group(conf.TO),-5.0)
            self.hdfAddSettingTemplate(g.create_group(conf.STEP),.2)

    def hdfAddSettingTemplate(self,g,value,default = None, toolTip = '', items = ''):
        g.attrs[conf.VALUE]     = value
        g.attrs[conf.DEFAULT]   = default if default is not None else value
        g.attrs[conf.TOOLTIP]   = toolTip
        g.attrs[conf.ITEMS]     = items

    def hdfAddSetting(self,g,setting):
        g.attrs[conf.VALUE]     = setting.value
        g.attrs[conf.DEFAULT]   = setting.default
        g.attrs[conf.TOOLTIP]   = setting.toolTip
        g.attrs[conf.ITEMS]     = ','.join(setting.items)

    def hdfAddSeData(self,scan,notes = ''):
        with h5py.File(scan.filename, 'a', track_order = True) as f:
            f.create_dataset(conf.VOLTAGE, data=scan.voltage, dtype='f')
            g = f.create_group(conf.CURRENT, track_order = True)
            for c in scan.currents:
                g.create_dataset(c.name, data=c.current, dtype='f')
            f.attrs[conf.NOTES] = notes
            # Note: metadata has already been saved as settings in the same file

    def hdfLoadSeData(self,file):
        with h5py.File(file, 'r') as f:
            metadata = SeScanMetaData(
                f[conf.SE_CHANNEL].attrs[conf.VALUE],
                f[conf.SE_FROM].attrs[conf.VALUE],
                f[conf.SE_TO  ].attrs[conf.VALUE],
                f[conf.SE_STEP].attrs[conf.VALUE]
            )
            g = f[conf.CURRENT]
            return [SeScanData(name,f[conf.VOLTAGE][:],current = item[:], md = metadata) for name, item in g.items()]

    def hdfAddS2dData(self,scan,notes = ''):
        with h5py.File(scan.filename, 'a', track_order = True) as f:
            g = f.create_group(conf.CURRENT, track_order = True)
            for c in scan.currents:
                d = g.create_dataset(c.name, data=c.current, dtype='f')
                d.dims[0].label = 'Left-Right'
                d.dims[1].label = 'Up-Down'
            f.attrs[conf.NOTES] = notes
            # Note: metadata has already been saved as settings in the same file

    def hdfLoadS2dData(self,file):
        with h5py.File(file, 'r') as f:
            metadata = S2dScanMetaData(
                f[conf.S2D_LR_CHANNEL].attrs[conf.VALUE],
                f[conf.S2D_UD_CHANNEL].attrs[conf.VALUE],
                f[conf.S2D_LR_FROM].attrs[conf.VALUE],
                f[conf.S2D_LR_TO  ].attrs[conf.VALUE],
                f[conf.S2D_LR_STEP].attrs[conf.VALUE],
                f[conf.S2D_UD_FROM].attrs[conf.VALUE],
                f[conf.S2D_UD_TO  ].attrs[conf.VALUE],
                f[conf.S2D_UD_STEP].attrs[conf.VALUE]
            )
            g = f[conf.CURRENT]
            return [S2dScanData(name, metadata, item[:]) for name, item in g.items()]

    def loadINI(self, file = None):
        """Load settings from INI file"""
        if file is None: # get file via dialog
            file = Path(QFileDialog.getOpenFileName(self.esibdWindow,conf.SELECTFILE,filter = conf.FILTER_INI)[0])
        elif not file.exists(): # create default if not exist
            self.iniGenerateDefaultConfig(file)
        if file != Path('.'):
            self.tree.clear()

            # system specific settings (including path to file with other settings)
            self.qSet.sync()
            self.loadINIinternal()

            # remaining settings from file
            confParser = configparser.ConfigParser()
            try:
                confParser.read(file)
            except KeyError:
                self.esibdWindow.esibdPrint(f'Could not load settings from {file}')
                return

            for name, item in confParser.items():
                if not any(name == key for key in [conf.DEFAULT,conf.VERSION]):
                    self[name]=controls.esibdSetting(self.esibdWindow, self.tree, name, item)

            self.esibdWindow.expandTree(self.tree)

    def loadINIinternal(self):
        self[conf.CONFIGPATH]=controls.esibdSetting(self.esibdWindow,self.tree,conf.CONFIGPATH,{conf.DEFAULT : conf.configPathDefault},internal = True)
        confPath = Path(self.qSet.value(conf.CONFIGPATH,conf.configPathDefault))
        self[conf.CONFIGPATH].value = confPath if confPath.exists() else conf.configPathDefault

        self[conf.DATAPATH]=controls.esibdSetting(self.esibdWindow,self.tree,conf.DATAPATH,{conf.DEFAULT : conf.dataPathDefault},internal = True)
        dataPath = Path(self.qSet.value(conf.DATAPATH,conf.dataPathDefault))
        self[conf.DATAPATH].value = dataPath if dataPath.exists() else conf.dataPathDefault

    def iniGenerateDefaultConfig(self,file):
        """Generates default settings file if file was not found.
        To update files with new parameters, simply delete the old file and the new one will be generated.
        NOTE: This is only true for files that do not contain device specific information. These cannot be autogenerated."""
        self.esibdWindow.esibdPrint(f'Generating default config file {file}')
        self.clear()
        self.loadINIinternal()
        items = []
        items.append(self.settingsDict(conf.VERSION,f'{conf.VERSION_MAYOR}.{conf.VERSION_MINOR}',conf.GENERALSETTINGS,'',conf.WIDGETLABEL,conf.GENERAL))
        items.append(self.settingsDict(conf.MEASUREMENTNUMBER,0,'','',conf.WIDGETINT,conf.SESSION))
        items.append(self.settingsDict(conf.AUTOSAVE,'True','Save all data to session','',conf.WIDGETBOOL,conf.SESSION))
        items.append(self.settingsDict(conf.SUBSTRATE,'HOPG','','HOPG,Graphene,aCarbon',conf.WIDGETCOMBO,conf.SESSION))
        items.append(self.settingsDict(conf.MOLION,'GroEL','','Ferritin,GroEL,ADH,GDH,BSA,DNA,BK',conf.WIDGETCOMBO,conf.SESSION))
        items.append(self.settingsDict(conf.SESSIONTYPE,'MS','','MS,depoHV,depoUHV,depoCryo,opt',conf.WIDGETCOMBO,conf.SESSION))
        items.append(self.settingsDict(conf.SESSIONPATH,'','Where session data will be stored','',conf.WIDGETLABEL,conf.SESSION))
        items.append(self.settingsDict(conf.DATAINTERVAL,100,'Interval for data acquisition in ms','',conf.WIDGETINT,conf.HARDWARE))
        items.append(self.settingsDict(conf.MONITORINTERVAL,1000,'Interval for monitoring in ms','',conf.WIDGETINT,conf.HARDWARE))
        items.append(self.settingsDict(conf.DPI,'100','DPI used in ES-IBD Explorer','100,150,200,300,600',conf.WIDGETCOMBO,conf.GENERAL))
        items.append(self.settingsDict(conf.ISEGIP,'169.254.163.182','IP address of ECH244','',conf.WIDGETTEXT,conf.HARDWARE))
        items.append(self.settingsDict(conf.ISEGPORT,10001,'SCPI port of ECH244','',conf.WIDGETINT,conf.HARDWARE))
        items.append(self.settingsDict(conf.DISPLAYTIME,'2','Length of displayed current history in min','1,2,3,5,10,60,3600',conf.WIDGETCOMBO,conf.GENERAL))
        items.append(self.settingsDict(conf.GACHANNEL,'RT_Detector','GA optimizes on this channel','RT_Detector,RT_Sample-Center,RT_Sample-End,Aperture',conf.WIDGETCOMBO,conf.GENERAL))

        for item in items:
            self[item[conf.NAME]] = controls.esibdSetting(self.esibdWindow, self.tree, item[conf.NAME], item)
        self.saveINI(file)

    def settingsDict(self, name, value, tooltip, items, widget, category):
        return {conf.NAME : name, conf.VALUE : value, conf.DEFAULT : value, conf.TOOLTIP : tooltip, conf.ITEMS : items, conf.WIDGET : widget, conf.CATEGORY : category}

    def saveINI(self, file = None, append='w'):
        """Saves settings to INI file"""
        if file is None: # get file via dialog
            file = Path(QFileDialog.getSaveFileName(self.esibdWindow,conf.SELECTFILE,filter = conf.FILTER_INI)[0])
        if file != Path('.'):
            config = configparser.ConfigParser()
            config[conf.VERSION] = self.settingsDict(conf.VERSION,f'{conf.VERSION_MAYOR}.{conf.VERSION_MINOR}',conf.GENERALSETTINGS,'',conf.WIDGETLABEL,conf.GENERAL)
            for name, setting in self.items():
                if not setting.internal and name != conf.DEFAULT:
                    config[name] = {}
                    config[name][conf.VALUE   ]  = str(setting.value)
                    config[name][conf.DEFAULT ]  = str(setting.default)
                    config[name][conf.TOOLTIP ]  = setting.toolTip
                    config[name][conf.ITEMS   ]  = ','.join(setting.items)
                    config[name][conf.WIDGET  ]  = setting.widget
                    config[name][conf.CATEGORY]  = setting.category
            with open(file, append, encoding = conf.UTF8) as configfile:
                config.write(configfile)

    def getMeasurementFileName(self,extension):
        sessionpath = Path(self[conf.SESSIONPATH].value)
        sessionpath.mkdir(parents=True, exist_ok=True) # create if not already existing
        return sessionpath / f'{sessionpath.name}_M{self[conf.MEASUREMENTNUMBER].value:02d}{extension}'

    def updateSessionPath(self):
        self[conf.SESSIONPATH].value = Path(*[self[conf.DATAPATH].value,self[conf.SUBSTRATE].value,self[conf.MOLION].value,
            datetime.now().strftime(f'%Y-%m-%d_%H-%M_{self[conf.SUBSTRATE].value}_{self[conf.MOLION].value}_{self[conf.SESSIONTYPE].value}')])
        self[conf.MEASUREMENTNUMBER].value = 0

########################## Instrument Manager #################################################

class InstrumentManager(QObject):
    """Top-level manager that controls data aquisition from all instruments.
    While the instruments run independently in separate threads, this class manages parallel collection of data for display and analysis"""
    def __init__(self, esibdWindow = None):
        super().__init__()
        self.esibdWindow = esibdWindow
        self.dataThread = None
        self.time = None
        self.clearHistory()
        self.acquiring = False
        self.esibdWindow.signalComm.appendDataSignal.connect(self.appendData)

    @pyqtSlot(float)
    def appendData(self,datainterval):
        # NOTE: add all new entries including time in one step to avoid any chance of unequal array sizes
        self.esibdWindow.currentConfig.updateCurrent() # use equations if needed
        for device in self.esibdWindow.currentConfig.getInitializedDevices():
            device.appendCurrent(datainterval)
        for channel in self.esibdWindow.voltageConfig.channels:
            channel.appendVoltage()
        self.time.add(time.time()) # add time in seconds
        self.esibdWindow.signalComm.plotDataSignal.emit() # use signal instead of calling updateCurrent directly to trigger graph update asynchronously

    def clearHistory(self):
        for device in self.esibdWindow.currentConfig.devices:
            device.clearHistory()
        for channel in self.esibdWindow.voltageConfig.channels:
            channel.clearHistory()
        self.time = self.esibdWindow.dynamicNp()

    def startAcquisition(self):
        if len(self.esibdWindow.currentConfig.getInitializedDevices()) > 0:
            self.dataThread = Thread(target = self.runDataThread, args =(lambda : self.acquiring,))
            self.dataThread.daemon = True # Terminate with main app independent of stop condition
            self.acquiring = True
            self.dataThread.start()
        else:
            self.esibdWindow.esibdPrint("No device ready. Can't start aquisition")
            self.esibdWindow.sampleCurrentPushButton.setChecked(False)

    def stopAcquisition(self):
        if self.dataThread is not None:
            self.acquiring = False # stop thread
            self.dataThread.join()

    def getTime(self, cutoff):
        return self.time.get()[self.time.get()>cutoff] if self.time.size > 0 else None

    def runDataThread(self,acquiring):
        while acquiring():
            datainterval = int(self.esibdWindow.settingsMgr[conf.DATAINTERVAL].value)/1000 # in seconds
            time.sleep(datainterval)
            self.esibdWindow.signalComm.appendDataSignal.emit(datainterval)

###################################### Energy Scan ################################################

class SeScanData():

    def __init__(self, name, voltage, current = None, md =  None):
        if md is None:
            self.current = current # needs to be supplied if there is no metadata
            self.md = SeScanMetaData(channel = conf.VOLTAGE, _from = min(self.current), to = max(self.current))
            self.md.steps = self.current.shape[0]
        else:
            self.md = md
            self.current = np.zeros([self.md.steps]) if current is None else current
        self.voltage = voltage
        self.name = name

    def addPoint(self,i,value):
        self.current[i] = value

class SeScanMetaData():
    """Bundles energy scan data in hardware and UI independent format to allow use of same methods for data aquired with different software versions (Labview / PyQt)"""
    def __init__(self, channel, _from = 0, to = 1, step = .1):
        self.channel = channel
        self._from   = _from
        self.to      = to
        self.step    = step * (1 if self.to - self._from > 0 else -1)
        self.steps   = int(abs(self._from-self.to)/abs(self.step))+1

class SeScan():
    """manages erergy scan"""

    def __init__(self, esibdWindow):
        self.esibdWindow = esibdWindow
        self.acquiring=False
        self.seScanThread = Thread(target = self.runScanThread, args =(lambda : self.acquiring,))
        self.seScanThread.daemon = True
        name = self.esibdWindow.seMgr[conf.SE_CHANNEL].value
        self.channel = self.esibdWindow.voltageConfig.getChannelbyName(name)
        self.esibdWindow.settingsMgr[conf.MEASUREMENTNUMBER].value += 1
        self.filename = self.esibdWindow.settingsMgr.getMeasurementFileName(conf.FILE_SE)

        if self.channel is None:
            self.esibdWindow.esibdPrint(f'Energy Scan: Voltage channel {name} not found.')
            self.esibdWindow.seScanPushButton.setChecked(False)
            return
        else:
            self.initial = self.channel.voltage # remember initial value
        self.md = SeScanMetaData(
            self.esibdWindow.seMgr[conf.SE_CHANNEL].value,
            self.esibdWindow.seMgr[conf.SE_FROM].value,
            self.esibdWindow.seMgr[conf.SE_TO  ].value,
            self.esibdWindow.seMgr[conf.SE_STEP].value
        )
        self.waitfirst = int(self.esibdWindow.seMgr[conf.SE_WAITFIRST].value)/1000 # wait time in seconds
        self.wait = int(self.esibdWindow.seMgr[conf.SE_WAIT].value)/1000 # wait time in seconds
        self.average = int(self.esibdWindow.seMgr[conf.SE_AVERAGE].value)/1000 # wait time in seconds
        # skip last point to account for possible timing issues # self.wait
        self.measurementsPerStep = int((self.esibdWindow.seMgr[conf.SE_AVERAGE].value/esibdWindow.settingsMgr[conf.DATAINTERVAL].value))-1
        self.voltage = [self.md._from + i * self.md.step for i in range(self.md.steps)]
        self.devices = self.esibdWindow.currentConfig.getInitializedDevices()
        self.currents = [SeScanData(d.lens,self.voltage,md=self.md) for d in self.devices]

    def start(self):
        error = ''
        if self.channel is None:
            error = 'Energy Scan: Voltage channel not found.'
        elif len(self.currents) == 0:
            error = 'Energy Scan: No picoammeter initialized.'
        elif self.md.steps < 2:
            error = 'Energy Scan: Not enough steps.'

        if error != '':
            self.esibdWindow.esibdPrint(error)
            self.esibdWindow.seScanPushButton.setChecked(False)
        else:
            self.acquiring=True
            self.seScanThread.start()

    def runScanThread(self,acquiring):
        for i in range(self.md.steps):
            if not acquiring():
                break
            self.esibdWindow.signalComm.updateVoltageSignal.emit(self.channel,self.md._from + i * self.md.step)
            time.sleep((self.waitfirst if i == 0 else self.wait)+self.average)
            for c,d in zip(self.currents,self.devices):
                c.addPoint(i,np.mean(d.getCurrents(subtractBackground = True)[-self.measurementsPerStep:]))
            self.esibdWindow.signalComm.seScanUpdateSignal.emit((i == self.md.steps-1) or not acquiring()) # update graph

        self.esibdWindow.signalComm.updateVoltageSignal.emit(self.channel, self.initial) # restore initial value
        self.esibdWindow.signalComm.resetScanButtonsSignal.emit()

###################################### 2D Scan ################################################

class S2dScanData():

    def __init__(self, name, md = None, current = None):
        self.name = name
        self.current = np.zeros([md.LR_steps,md.UD_steps]) if current is None else current
        if md is None:
            self.md = S2dScanMetaData(conf.LEFTRIGHT,conf.UPDOWN)
            self.md.LR_steps=self.current.shape[0] # generate based on data dimensions
            self.md.UD_steps=self.current.shape[1]
        else:
            self.md = md

    def addPoint(self,i,j,value):
        self.current[i,j] = value

class S2dScanMetaData():
    """Bundles 2D scan data in hardware and UI independent format to allow use of same methods for data aquired with different software versions (Labview / PyQt)"""
    def __init__(self, LR_channel, UD_channel, LR_from = 0, LR_to = 1, LR_step = .1, UD_from = 0, UD_to = 1, UD_step = .1):
        self.LR_from    = LR_from
        self.LR_to      = LR_to
        self.LR_step    = LR_step * (1 if self.LR_to - self.LR_from > 0 else -1)
        self.LR_steps   = int(abs(self.LR_from-self.LR_to)/abs(self.LR_step))+1
        self.LR_channel = LR_channel

        self.UD_from    = UD_from
        self.UD_to      = UD_to
        self.UD_step    = UD_step * (1 if self.UD_to - self.UD_from > 0 else -1)
        self.UD_steps   = int(abs(self.UD_from-self.UD_to)/abs(self.UD_step))+1
        self.UD_channel = UD_channel

    def getMgrid(self,scaling=1):
        return np.mgrid[self.LR_from:self.LR_to:self.LR_steps*scaling*1j, self.UD_from:self.UD_to:self.UD_steps*scaling*1j]


class S2dScan():
    """Manages 2D scan acquisition"""
    def __init__(self, esibdWindow):
        self.esibdWindow = esibdWindow
        self.esibdWindow.settingsMgr[conf.MEASUREMENTNUMBER].value += 1
        self.filename = self.esibdWindow.settingsMgr.getMeasurementFileName(conf.FILE_S2D)
        self.acquiring=False
        self.s2dScanThread = Thread(target = self.runScanThread, args =(lambda : self.acquiring,))
        self.s2dScanThread.daemon = True
        self.waitfirst = int(self.esibdWindow.s2dMgr[conf.S2D_WAITFIRST].value)/1000 # wait time in seconds
        self.wait = int(self.esibdWindow.s2dMgr[conf.S2D_WAIT].value)/1000 # wait time in seconds
        self.average = int(self.esibdWindow.s2dMgr[conf.S2D_AVERAGE].value)/1000 # wait time in seconds
        self.md = S2dScanMetaData(
            self.esibdWindow.s2dMgr[conf.S2D_LR_CHANNEL].value,
            self.esibdWindow.s2dMgr[conf.S2D_UD_CHANNEL].value,
            self.esibdWindow.s2dMgr[conf.S2D_LR_FROM].value,
            self.esibdWindow.s2dMgr[conf.S2D_LR_TO  ].value,
            self.esibdWindow.s2dMgr[conf.S2D_LR_STEP].value,
            self.esibdWindow.s2dMgr[conf.S2D_UD_FROM].value,
            self.esibdWindow.s2dMgr[conf.S2D_UD_TO  ].value,
            self.esibdWindow.s2dMgr[conf.S2D_UD_STEP].value
        )
        LR_name = self.esibdWindow.s2dMgr[conf.S2D_LR_CHANNEL].value
        UD_name = self.esibdWindow.s2dMgr[conf.S2D_UD_CHANNEL].value
        self.LR_channel = self.esibdWindow.voltageConfig.getChannelbyName(LR_name)
        self.UD_channel = self.esibdWindow.voltageConfig.getChannelbyName(UD_name)
        if self.LR_channel is None or self.UD_channel is None:
            self.esibdWindow.esibdPrint(f'2D Scan: No voltage channel found with name {LR_name} or {UD_name}.')
            self.esibdWindow.s2dScanPushButton.setChecked(False)
            return
        else:
            self.LR_initial = self.LR_channel.voltage # remember initial values
            self.UD_initial = self.UD_channel.voltage # remember initial values
        # skip last point to account for possible timing issues # self.wait
        self.measurementsPerStep = int ((self.esibdWindow.s2dMgr[conf.S2D_AVERAGE].value/esibdWindow.settingsMgr[conf.DATAINTERVAL].value))-1
        # self.voltage = []
        self.devices = self.esibdWindow.currentConfig.getInitializedDevices()
        self.currents = [S2dScanData(d.lens, self.md) for d in self.devices]

    def start(self):
        error = ''
        if self.LR_channel is None or self.UD_channel is None:
            error = '2D Scan: Voltage channel not found.'
        elif len(self.currents) == 0:
            error = '2D Scan: No picoammeter initialized.'
        elif self.md.LR_steps < 2 or self.md.UD_steps < 2:
            error = '2D Scan: Not enough steps.'
        if error != '':
            self.esibdWindow.esibdPrint(error)
            self.esibdWindow.s2dScanPushButton.setChecked(False)
        else:
            self.acquiring=True
            self.s2dScanThread.start()

    def runScanThread(self, acquiring):
        for i in range(self.md.LR_steps):
            for j in range(self.md.UD_steps):
                if not acquiring():
                    break
                self.esibdWindow.signalComm.updateVoltageSignal.emit(self.LR_channel,self.md.LR_from + i * self.md.LR_step)
                self.esibdWindow.signalComm.updateVoltageSignal.emit(self.UD_channel,self.md.UD_from + j * self.md.UD_step)
                time.sleep((self.waitfirst if j==0 else self.wait)+self.average)
                for c,d in zip(self.currents,self.devices):
                    c.addPoint(i,j,np.mean(d.getCurrents(subtractBackground = True)[-self.measurementsPerStep:]))
                self.esibdWindow.signalComm.s2dScanUpdateSignal.emit((i == self.md.LR_steps-1 and j == self.md.UD_steps-1) or not acquiring()) # update graph

        self.esibdWindow.signalComm.updateVoltageSignal.emit(self.LR_channel,self.LR_initial)
        self.esibdWindow.signalComm.updateVoltageSignal.emit(self.UD_channel,self.UD_initial)
        self.esibdWindow.signalComm.resetScanButtonsSignal.emit()

###################################### 2D Scan ################################################

class GAManager(GA):
    """Manages optimization using genetic algorithm (GA)"""
    def __init__(self, esibdWindow):
        super().__init__()
        self.esibdWindow = esibdWindow
        self.optimizing = False
        self.gaChannel = None
        self.gaThread = None
        self.maximize(True)
        self.wait = int(self.esibdWindow.seMgr[conf.SE_WAIT].value)/1000 # wait time in seconds
        self.average = int(self.esibdWindow.seMgr[conf.SE_AVERAGE].value)/1000 # average time in seconds
        self.measurementsPerStep = int((self.esibdWindow.seMgr[conf.SE_AVERAGE].value/esibdWindow.settingsMgr[conf.DATAINTERVAL].value))-1
        # self.restore(True)
        self.esibdWindow.settingsMgr[conf.MEASUREMENTNUMBER].value += 1
        measFileName = self.esibdWindow.settingsMgr.getMeasurementFileName('')
        self.file_path(measFileName.parent.as_posix())
        self.file_name(measFileName.name)

    def start(self):
        self.gaChannel = self.esibdWindow.currentConfig.getDevicebyLens(self.esibdWindow.settingsMgr[conf.GACHANNEL].value)
        if self.gaChannel is None:
            self.esibdWindow.esibdPrint(f'Channel {self.esibdWindow.settingsMgr[conf.GACHANNEL].value} not found. Cannot start Optimization')
            return
        for c in self.esibdWindow.voltageConfig.channels:
            if c.optimize:
                self.optimize(c.voltage,c.min,c.max,.2,abs(c.max-c.min)/10,c.name)
            else:
                self.optimize(c.voltage,c.min,c.max,0,abs(c.max-c.min)/10,c.name) # add entry but set rate to 0 to prevent value change. Can be activated later.
        self.genesis()
        self.gaThread = Thread(target = self.runGA, args =(lambda : self.optimizing,))
        self.gaThread.daemon=True
        self.optimizing = True
        self.gaThread.start() # init in background

    def runGA(self,optimizing):
        while optimizing():
            for c in [c for c in self.esibdWindow.voltageConfig.channels if c.optimize]:
                self.esibdWindow.signalComm.updateVoltageSignal.emit(c,self.GAget(c.name,c.voltage))
            time.sleep(self.wait+self.average)
            self.fitness(np.mean(self.gaChannel.getCurrents(subtractBackground = True)[-self.measurementsPerStep:]))
            self.print_step()
            self.check_restart()
        self.check_restart(True) # sort population
        for c in [c for c in self.esibdWindow.voltageConfig.channels if c.optimize]:
            self.esibdWindow.signalComm.updateVoltageSignal.emit(c,self.GAget(c.name,c.voltage,0)) # apply best settings when done
        self.esibdWindow.signalComm.gaUpdateSignal.emit()
