"""This is the main ES-IBD_Explorer module that loads all other dependecies"""

import sys
import os
import ctypes
from functools import partial
import inspect
from datetime import datetime
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas, NavigationToolbar2QT as NavigationToolbar
from qt_material import apply_stylesheet
import pyqtgraph as pg
from pyqtgraph.dockarea import *
import pyqtgraph.console
from PyQt5 import uic, QtWebEngineWidgets, sip # pylint: disable=[unused-import] # note QtWebEngineWidgets is required to loadUi, despite the fact that it is marked as "not accessed" by pylint
from PyQt5.QtWidgets import QApplication, QMainWindow, QComboBox, QGridLayout, QSizePolicy, QWidget, QVBoxLayout
from PyQt5.QtGui import QGuiApplication, QIcon, QFont
from PyQt5.QtCore import QSettings, Qt, pyqtSlot
import ES_IBD_configuration as conf
import ES_IBD_management as management
import ES_IBD_functions
import ES_IBD_controls as controls
# from ES_IBD_Explorer_UI import Ui_MainWindow
matplotlib.use('Qt5Agg')

class ES_IBDWindow(QMainWindow,ES_IBD_functions.func_mixin): # ,Ui_MainWindow
    """Contains minimal code to start, initialize, and close the program.
    More detailed but still general functions that directly link to UI envents are added as a mixin from ES_IBD_functions.func_mixin.
    All high level logic is provided in separate modules."""
    def __init__(self):
        super(ES_IBDWindow, self).__init__()
        print(f'Starting ES-IBD Control version: {conf.VERSION_MAYOR}.{conf.VERSION_MINOR}')

        self.activeFile = None
        self.maximized = False
        self.testMode = False # set true from console if needed, this mode should not concern normal users
        self.loading = True # some events should not be triggered until after the UI is completely initialized
        self.mouseMoving = False
        #init UI
        uic.loadUi('ES_IBD_Explorer.ui', self) # using .ui directly
        # self.setupUi(self) # using python file generated with pyuic5 ES_IBD_Explorer.ui -o ES_IBD_Explorer_UI.py
        self.mainConsole    = pyqtgraph.console.ConsoleWidget(parent=self,namespace= {'self': self,'conf': conf,'management': management,'np': np,'inspect': inspect,'sip':sip})
        self.qSet           = QSettings(conf.COMPANY_NAME, conf.PROGRAM_NAME)
        self.signalComm     = self.SignalCommunicate()
        self.settingsMgr    = management.SettingsManager(self, tree = self.settingsTreeWidget, mode = conf.GENERALSETTINGS)
        self.voltageConfig  = controls.VoltageConfig(esibdWindow = self)
        self.currentConfig  = controls.CurrentConfig(esibdWindow = self)
        self.instMgr        = management.InstrumentManager(esibdWindow=self)

        self.initUi()
        self.initDepoUi()
        self.initVoltageUi()
        self.initCurrentUi()

        self.initLine()
        self.initS2D()
        self.initSE()

        self.updateRoot(self.settingsMgr[conf.DATAPATH].value)
        self.populateTree()

        self.mainTabWidget.setCurrentIndex(conf.indexSettings)
        self.mainTabWidget.currentChanged.connect(self.mainTabChanged)
        self.displayTabWidget.setCurrentIndex(conf.indexHtml)
        self.loading = False
        self.xChannelChanged() # requires full initialization

############################# UI Initialization and Connection ####################################

    def initUi(self):
        """init al general UI elements"""
        self.setWindowIcon(QIcon(conf.ICON_DIRECTION))
        self.statusbar.showMessage('ES-IBD Explorer') # writes to statusbar for user

        # General Events
        self.actionExit.triggered.connect(self.close)
        self.actionFull_Screen.triggered.connect(self.goFullscreen)
        self.actionCopy_to_Clipboard.triggered.connect(self.copyClipboard)
        self.actionAbout.triggered.connect(self.aboutDialog)
        self.signalComm.printFromThreadSignal.connect(self.printFromThread)
        self.signalComm.resetScanButtonsSignal.connect(self.resetScanButtons)

        # init settings
        self.settingsMgr[conf.DPI].changedEvent = self.dpiChanged
        self.settingsMgr[conf.SESSIONTYPE].changedEvent = self.settingsMgr.updateSessionPath
        self.settingsMgr[conf.MOLION].changedEvent = self.settingsMgr.updateSessionPath
        self.settingsMgr[conf.SUBSTRATE].changedEvent = self.settingsMgr.updateSessionPath
        self.settingsMgr.updateSessionPath()
        self.settingsTreeWidget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.settingsTreeWidget.customContextMenuRequested.connect(partial(self.initSettingsContextMenu,self.settingsMgr))
        self.saveSettingsPushButton.clicked.connect(lambda : self.settingsMgr.save(None))
        self.loadSettingsPushButton.clicked.connect(lambda : self.settingsMgr.load(None))

        # init explorer
        self.root = None
        self.notes = None
        self.rootTreeWidget.currentItemChanged.connect(self.treeItemClicked)
        self.rootTreeWidget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.rootTreeWidget.customContextMenuRequested.connect(self.initExplorerContextMenu)
        self.rootTreeWidget.itemDoubleClicked.connect(self.treeItemDoubleClicked)
        self.filterLineEdit.textChanged.connect(self.populateTree)
        self.filterLineEdit.setPlaceholderText("Search")
        self.refreshFileTreeButton.setIcon(QIcon(conf.ICON_REFRESH))
        self.refreshFileTreeButton.clicked.connect(self.populateTree)
        self.goToCurrentSessionButton.clicked.connect(self.goToCurrentSession)
        self.goToCurrentSessionButton.setIcon(QIcon(conf.ICON_FOLDER))
        self.currentDirLineEdit.returnPressed.connect(self.updateCurDirFromLineEdit)

        # webEngineView for websites and pdf
        self.webEngineView.settings().setAttribute(QtWebEngineWidgets.QWebEngineSettings.PluginsEnabled, True)
        self.webEngineView.settings().setAttribute(QtWebEngineWidgets.QWebEngineSettings.PdfViewerEnabled, True)
        self.PDFJS = 'file:///pdfjs/web/viewer.html'

        # auto scaling with fixed aspect ratio
        #self.imgImageWidget =  controls.SaneDefaultsImageLabel()
        self.imgImageWidget =  controls.ImageWidget()
        self.imgVerticalLayout.addWidget(self.imgImageWidget)

        # Vector graphic display
        self.svgWidget = controls.SvgWidget() # QtSvg.QSvgWidget()
        self.vectorVerticalLayout.addWidget(self.svgWidget)

        # PDB 3D scatter plot
        self.pdbFig=plt.figure(dpi=int(self.settingsMgr[conf.DPI].value))
        self.pdbCanvas = FigureCanvas(self.pdbFig)
        self.pdbFig.add_subplot(111, projection='3d')

        pdbToolbar = NavigationToolbar(self.pdbCanvas, self)
        self.pdbVerticalLayout.addWidget(pdbToolbar)
        self.pdbVerticalLayout.addWidget(self.pdbCanvas)

        # col = QColor('#00a500')
        # self.setStyleSheet(f'background:rgb(r:{col.red()},g:{col.green()},b:{col.blue()})')


        #self.mainConsole.runCmd('self.testMode = True') # uncomment for development only
        self.mainConsole.write(('All features implemented in the user interface and more can be accessed directly from this console.\n'
                                'It is mainly intended for debugging. Use at your own Risk! You can select some commonly used commands fireclty from the combobox below.\n'
                                'Status messages will also be logged here\n'))
        self.consoleDockVerticalLayout.addWidget(self.mainConsole,1) # https://github.com/pyqtgraph/pyqtgraph/issues/404 # add before hintsTextEdit

        self.commonCommandsLayout = QGridLayout()
        self.commonCommandsLayout.setContentsMargins(11,0,11,0)
        self.commonCommandsComboBox = QComboBox()
        self.commonCommandsComboBox.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Fixed)
        self.commonCommandsComboBox.addItems([
            "select command",
            "self.instMgr.clearHistory(); self.testMode = True; self.initCurrent() # activate test mode to autogenerate data for development when devices are not available",
            "self.currentConfig.close() # close ports",
            "self.voltageConfig.close() # close ports",
            "rbd.channel.port.write(bytes('&'+ 'S' + '\n','utf-8'))",
            "rbd.channel.port.readline().decode('utf-8').rstrip()",
            "self.instMgr.acquiring",
            "volt = self.voltageConfig.channels[0] # get first voltage channel",
            "volt.real = True",
            "xChannel = self.voltageConfig.getChannelbyName(self.settingsMgr[conf.XCHANNEL].value)",
            "self.qSet.clear() # only use when resetting to default e.g. for testing fresh deployment on new computer",
            "sip.delete() # add to the widget you want to remove (testing layout)",
            "[print(m[0],m[1].__doc__) for m in inspect.getmembers(self, inspect.ismethod) if m[1].__module__ == '__main__'] # quick documented module overview",
"[print(m[1].__module__,m[0],m[1].__doc__) for m in inspect.getmembers(management, lambda x: inspect.isfunction(x) or inspect.ismethod(x) or inspect.isclass(x)) if m[1].__module__ == 'ES_IBD_management'] # quick documentation",
            "rbd = self.currentConfig.getInitializedDevices()[0] # get first initialized picoammeter",
            "self.settingsMgr.hdfGenerateDefaultConfig(conf.settingsFile(self.qSet)) # save autogenerated settings to default"
        ])
        self.commonCommandsComboBox.currentIndexChanged.connect(self.commandChanged)
        self.commonCommandsLayout.setSpacing(0)
        self.commonCommandsLayout.addWidget(self.commonCommandsComboBox)
        self.consoleDockVerticalLayout.setContentsMargins(0, 0, 0, 0)
        self.consoleDockVerticalLayout.addLayout(self.commonCommandsLayout,0)
        self.restoreUiState()

    def commandChanged(self, _):
        self.mainConsole.runCmd(self.commonCommandsComboBox.currentText())

    def initDepoUi(self):
        """ Init all elements related to display of currents"""
        self.currentDockArea = DockArea()
        self.currentDisplayLayout.addWidget(self.currentDockArea)
        self.currentDock = Dock("CurrentDock", size=(100, 100))
        self.currentDockArea.addDock(self.currentDock,'left')
        self.currentDock.addWidget(self.currentPlotWidget)

        container = QWidget()
        self.xSliderVBoxLayout = QVBoxLayout(container)
        self.xSliderVBoxLayout.setContentsMargins(50,0,30,0)
        self.xSliderVBoxLayout.addWidget(self.xSlider)
        self.currentDock.addWidget(container) # can only add QWidgets, not QLayouts

        self.plotWidgetFont=QFont()
        self.plotWidgetFont.setPixelSize(15)
        self.currentPlotWidget.showGrid(x=True, y=True)
        self.currentPlotWidget.setMouseEnabled(x=False, y=True) # keep auto pan in x running, use settings to zoom in x
        self.currentPlotWidget.setAxisItems({'right': pg.AxisItem('right')}) # , size=5
        self.currentPlotWidget.setLabel('left','<font size="5">Current (pA)</font>')
        self.currentPlotWidget.getAxis('left').setTickFont(self.plotWidgetFont)
        self.currentPlotWidget.getAxis('right').setTickFont(self.plotWidgetFont)
        self.xSlider.valueChanged.connect(self.updateX)

    def initVoltageUi(self):
        self.voltageChannelsVerticalLayout.addWidget(self.voltageConfig)
        self.saveVoltagePushButton.clicked.connect(lambda : self.voltageConfig.save(None))
        self.loadVoltagePushButton.clicked.connect(lambda : self.voltageConfig.load(None))
        self.initVoltagePushButton.clicked.connect(lambda : self.voltageConfig.init(restart = self.voltageOnPushButton.isChecked()))
        self.advancedVoltagePushButton.clicked.connect(lambda : self.voltageConfig.setAdvanced(self.advancedVoltagePushButton.isChecked()))
        self.voltageOnPushButton.clicked.connect(self.voltageON)
        self.signalComm.updateVoltageSignal.connect(self.updateVoltage)
        self.optimizeVoltagePushButton.clicked.connect(self.toogleGA)
        self.plotVoltagePushButton.clicked.connect(self.voltagePlot)
        self.signalComm.gaUpdateSignal.connect(self.gaUpdate)

    def initCurrentUi(self):
        self.currentDevicesVerticalLayout.addWidget(self.currentConfig)
        self.initCurrentPushButton.clicked.connect(self.initCurrent)
        self.sampleCurrentPushButton.clicked.connect(self.sampleCurrent)
        self.clearCurrentPushButton.clicked.connect(self.instMgr.clearHistory)
        self.resetChargePushButton.clicked.connect(self.currentConfig.resetCharge)
        self.saveCurrentPushButton.clicked.connect(lambda : self.currentConfig.save(None))
        self.loadCurrentPushButton.clicked.connect(lambda : self.currentConfig.load(None))
        self.exportCurrentPushButton.clicked.connect(self.hdfSaveCurrentData)
        self.advancedCurrentPushButton.clicked.connect(lambda : self.currentConfig.setAdvanced(self.advancedCurrentPushButton.isChecked()))
        self.setBackgroundCurrentPushButton.clicked.connect(self.currentConfig.setBackground)
        self.signalComm.plotDataSignal.connect(self.plotData)

    def initLine(self): # init plot for single line data, typically mass spectra
        # matplotlib
        self.lineFig=plt.figure(dpi=int(self.settingsMgr[conf.DPI].value))
        self.lineCanvas = FigureCanvas(self.lineFig)
        self.lineCanvas.mpl_connect('button_press_event', self.lineOnClick)
        self.mz = np.array([])
        self.intensity = np.array([])
        self.lineFig.add_subplot(111)
        self.lineAx=self.lineFig.axes[0]
        self.lineToolbar = NavigationToolbar(self.lineCanvas, self)
        self.lineVerticalLayout.addWidget(self.lineToolbar,0)
        self.lineVerticalLayout.addWidget(self.lineCanvas,1)
        # pyqt
        # widget already in UI, no initialization needed

    def initS2D(self):
        """initialize all UI elements related to 2D scan"""
        self.s2dMgr = management.SettingsManager(self, tree = self.s2dTreeWidget, mode = conf.S2DSETTINGS)
        self.s2dMgr[conf.S2D_DISPLAY].changedEvent = self.updateS2dContent
        self.s2dTreeWidget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.s2dTreeWidget.customContextMenuRequested.connect(partial(self.initSettingsContextMenu,self.s2dMgr))
        self.s2dLoadPushButton.clicked.connect(lambda : self.s2dMgr.load(None))
        self.s2dSavePushButton.clicked.connect(lambda : self.s2dMgr.save(None))
        self.s2dScanPushButton.clicked.connect(self.s2dScanToogle)
        self.s2dLimitsPushButton.clicked.connect(self.s2dLimits)
        self.s2dLimitsPushButton.setToolTip('Adopts limits from display')
        self.signalComm.s2dScanUpdateSignal.connect(self.s2dScanUpdate)

        # matplotlib
        self.s2dFig=plt.figure(dpi=int(self.settingsMgr[conf.DPI].value))
        self.s2dCanvas = FigureCanvas(self.s2dFig)
        self.s2dCanvas.mpl_connect('motion_notify_event', self.s2dMouseEvent)
        self.s2dCanvas.mpl_connect('button_press_event', self.s2dMouseEvent)
        self.s2dCanvas.mpl_connect('button_release_event', self.s2dMouseEvent)
        self.s2dFig.add_subplot(111)
        self.s2dToolbar = NavigationToolbar(self.s2dCanvas, self)
        self.s2dVerticalLayout.addWidget(self.s2dToolbar,0)
        self.s2dVerticalLayout.addWidget(self.s2dCanvas,1)
        self.s2dCont = None
        self.s2dScat = None
        self.s2dCbar = None
        self.s2dAnn  = None

        # pyqt image view for S2D
        self.s2dImv = pg.ImageView()
        self.s2dQtVerticalLayout.addWidget(self.s2dImv)

    def initSE(self):
        """initialize all UI element related to energy scan"""
        self.seMgr = management.SettingsManager(self, tree = self.seTreeWidget, mode = conf.SESETTINGS)
        self.seMgr[conf.SE_DISPLAY].changedEvent = self.updateSeContent
        self.seTreeWidget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.seTreeWidget.customContextMenuRequested.connect(partial(self.initSettingsContextMenu,self.seMgr))
        self.seLoadPushButton.clicked.connect(lambda : self.seMgr.load(None))
        self.seSavePushButton.clicked.connect(lambda : self.seMgr.save(None))
        self.seScanPushButton.clicked.connect(self.seScanToogle)
        self.signalComm.seScanUpdateSignal.connect(self.seScanUpdate)

        # init matplotlib for Energy Scan display
        self.seFig=plt.figure(dpi=int(self.settingsMgr[conf.DPI].value))
        self.seCanvas = FigureCanvas(self.seFig)
        self.seFig.add_subplot(111)
        self.seFig.axes[0].twinx() # creating twin axis
        self.seToolbar = NavigationToolbar(self.seCanvas, self)
        self.seVerticalLayout.addWidget(self.seToolbar)
        self.seVerticalLayout.addWidget(self.seCanvas)

        #self.seFig.axes[0].set_ylim([0,112])
        self.seFig.axes[0].yaxis.label.set_color(conf.MYBLUE)
        self.seFig.axes[0].tick_params(axis='y', colors=conf.MYBLUE)
        self.seFig.axes[1].set_ylabel('-dI/dV (%)')
        self.seFig.axes[1].set_ylim([0,112])
        self.seFig.axes[1].yaxis.label.set_color(conf.MYRED)
        self.seFig.axes[1].tick_params(axis='y', colors=conf.MYRED)

        self.seRaw = self.seFig.axes[0].plot([], [],marker='.',linestyle = 'None', color=conf.MYBLUE,label='.')[0] # dummy plot
        self.seGrad = self.seFig.axes[1].plot([], [],marker='.',linestyle = 'None', color=conf.MYRED)[0] # dummy plot
        self.seFit = self.seFig.axes[1].plot([], [],color=conf.MYRED)[0] # dummy plot
        self.seAnnArrow = None
        self.seAnnFile = None
        self.seAnnFWHM = None

        # pyqt implementation not needed for comparably small amount of data

    def goFullscreen(self):
        if self.isFullScreen(): # return to previous view
            if self.maximized:
                self.showMaximized()
            else:
                self.showNormal()
        else: # goFullscreen
            self.maximized = self.isMaximized() # workaround for bug https://github.com/qutebrowser/qutebrowser/issues/2778
            self.showFullScreen()

    @pyqtSlot(str)
    def printFromThread(self, string):
        self.esibdPrint(string)

    def esibdPrint(self, *string):
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S: ')
        self.statusbar.showMessage(datetime.now().strftime(timestamp + ' '.join(string))) # writes to statusbar for user
        for s in string: # writes to integrated console to keep track of message history
            self.mainConsole.write(timestamp + s if isinstance(s,str) else repr(s)) # repr(s) does not use \n
        self.mainConsole.write('\r\n')
        print(*string) # writes to terminal for developer

    def restoreUiState(self):
        size = QGuiApplication.primaryScreen().size()
        self.restoreGeometry(self.qSet.value(conf.GEOMETRY,self.saveGeometry()))
        self.restoreState(self.qSet.value(conf.WINDOWSTATE,self.saveState()))
        self.mainSplitter.setSizes      ([int(x) for x in self.qSet.value(conf.MAINSPLTTERSIZE      ,[size.height()/2,size.height()/2,0])])
        self.contentSplitter.setSizes  ([int(x) for x in self.qSet.value(conf.CONTENTSPLTTERSIZE  ,[300,size.width()])])

    def saveUiState(self):
        self.qSet.setValue(conf.GEOMETRY, self.saveGeometry())
        self.qSet.setValue(conf.WINDOWSTATE, self.saveState())
        mainSplittersizes = self.mainSplitter.sizes()
        # ignore console which shall always be hidden on start and only found by those who know
        self.qSet.setValue(conf.MAINSPLTTERSIZE     ,[mainSplittersizes[0],mainSplittersizes[1]+mainSplittersizes[2],0])
        self.qSet.setValue(conf.CONTENTSPLTTERSIZE       ,self.contentSplitter.sizes())

    def closeEvent(self, event):
        # close all open connections and leave hardware in save state (voltage off)
        self.instMgr.stopAcquisition()
        self.settingsMgr.save(conf.settingsFile(self.qSet))
        self.currentConfig.save(conf.currentConfigFile(self.qSet))
        self.voltageConfig.save(conf.voltageConfigFile(self.qSet))
        self.s2dMgr.save(conf.configFile(self.qSet),'w') # writes new file
        self.seMgr.save(conf.configFile(self.qSet),'a') # appends to file
        self.saveNotes()
        self.saveUiState()
        self.currentConfig.close()
        self.voltageConfig.voltageON(False)
        self.voltageConfig.close()
        app.quit()
        event.accept() # let the window close

###################################################################################################
# import ctypes
if __name__ == '__main__':
    # ctypes.windll.shcore.SetProcessDpiAwareness(2)
    # QApplication.setAttribute(Qt.AA_DisableHighDpiScaling) # correct scaling based on resolution
    #QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True) # correct scaling based on resolution
    app = QApplication(sys.argv)
    #app.setStyle('QtCurve')
    #app.setStyle('Windows')
    app.setStyle('Material') # requires pyqt > 5.15.8
    #apply_stylesheet(app, theme='dark_teal.xml') # from Qt-Material package
    #apply_stylesheet(app, theme='light_teal.xml', invert_secondary=True)


    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--enable-logging --log-level=3" # supress pdfjs warnings https://www.pythonfixing.com/2022/02/fixed-how-to-suppress-console-output.html
    # make task bar item work https://stackoverflow.com/questions/1551605/how-to-set-applications-taskbar-icon-in-windows-7/1552105#1552105
    myappid = 'mycompany.myproduct.subproduct.version' # arbitrary string
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

    mainWindow = ES_IBDWindow()

    mainWindow.show()
    sys.exit(app.exec_())
    