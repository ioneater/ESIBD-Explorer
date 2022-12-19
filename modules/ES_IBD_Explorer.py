"""This is the main ES-IBD_Explorer module that loads all other dependecies"""

import sys
import os
import ctypes
import platform
import importlib
from datetime import datetime
from pathlib import Path
import matplotlib as mpl
from PyQt6 import uic, QtWebEngineWidgets # pylint: disable = unused-import # (need to import at top level here in case a plugin needs it later)
from PyQt6.QtWidgets import QApplication,QMainWindow
from PyQt6.QtGui import QGuiApplication,QIcon,QAction
from PyQt6.QtCore import QSettings, pyqtSignal,QObject
import ES_IBD_core as core
import ES_IBD_management as management
import ES_IBD_controls as controls
sys.path.append('../modules')

mpl.use('Qt5Agg')
mpl.rcParams['savefig.format']  = 'pdf' # make pdf default export format
mpl.rcParams['savefig.bbox']  = 'tight' # trim white space by default (also when saving from toolbar)

class ESIBD_Window(QMainWindow): #,Ui_MainWindow
    """Contains minimal code to start,restore,initialize,and close the program.
    All high level logic is provided in separate modules."""

    ICON_DIRECTION = 'media/direction.png'

    class SignalCommunicate(QObject): # signals that can be emitted by external threads
        printFromThreadSignal   = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        print(f'{core.PROGRAM_NAME} {core.VERSION_MAYOR}.{core.VERSION_MINOR} starting.')
        self.setUpdatesEnabled(False)
        uic.loadUi('modules/ES_IBD_Explorer.ui',self) # init UI
        self.setWindowIcon(QIcon(self.ICON_DIRECTION))
        # General Events
        self.actionFull_Screen = QAction()
        self.actionFull_Screen.triggered.connect(self.toogleFullscreen)
        self.actionFull_Screen.setShortcut('F11')
        self.mainSplitter.addAction(self.actionFull_Screen) # action only works when added to a widget
        self.maximized = False
        self.loading = True # some events should not be triggered until after the UI is completely initialized
        self.outputWidget = None # has to be defined in case it is accessed before it is initialized
        self.mainTabWidget.currentChanged.connect(self.mainTabChanged)
        self.qSet           = QSettings(core.COMPANY_NAME,core.PROGRAM_NAME)
        self.qSet.sync() # load QSettings from registry
        self.signalComm     = self.SignalCommunicate()
        self.signalComm.printFromThreadSignal.connect(self.esibdPrint)

        self.consoleWidget = management.ESIBD_CONSOLE_GUI(esibdWindow=self)
        self.settingsWidget = management.ESIBD_SETTINGS_GUI(esibdWindow=self)
        self.outputWidget   = management.ESIBD_OUTPUT_GUI(esibdWindow=self)
        self.loadPlugins()

        self.settingsWidget.init()  # init internal settings and settings of devices and scans which have been added in the meantime
        self.restoreUiState()
        self.loading = False
        self.setUpdatesEnabled(True)
        self.outputWidget.init() # requires full initialization
        self.esibdPrint(f'{core.PROGRAM_NAME} {core.VERSION_MAYOR}.{core.VERSION_MINOR} ready.') # writes to statusbar for user

    def loadPlugins(self):
        # with plugins -> dict file, name, enabled -> update based on availbale, GUI with live update
        for file in Path('plugins').iterdir():
            if file.name.endswith('.py'):
                print(file.stem)
                importlib.import_module(f'plugins.{file.stem}','.').initialize(esibdWindow = self)

    def toogleFullscreen(self):
        if self.isFullScreen(): # return to previous view
            if self.maximized:
                self.showMaximized()
            else:
                self.showNormal()
        else: # goFullscreen
            self.maximized = self.isMaximized() # workaround for bug https://github.com/qutebrowser/qutebrowser/issues/2778
            self.showFullScreen()

    def esibdPrint(self,*string):
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S: ')
        flatString=' '.join(string)
        self.statusbar.showMessage(datetime.now().strftime(timestamp + flatString)) # writes to statusbar for user
        if 'Error' in flatString:
            self.statusbar.setStyleSheet('color : red;')
        elif 'Warning' in flatString:
            self.statusbar.setStyleSheet('color : indianred;')
        else:
            self.statusbar.setStyleSheet('color : black;')
        for s in string: # writes to integrated console to keep track of message history
            self.consoleWidget.mainConsole.write(timestamp + s if isinstance(s,str) else repr(s)) # repr(s) does not use \n
        self.consoleWidget.mainConsole.write('\r\n')
        print(*string) # writes to terminal for developer

    def addGUIWidget(self,tabWidget,widget):
        tabWidget.addTab(widget,widget.name)
        return widget

    def getMainWidgets(self):
        return [self.mainTabWidget.widget(i) for i in range(self.mainTabWidget.count()) if isinstance(self.mainTabWidget.widget(i),core.ESIBD_GUI)]

    def getScanWidgets(self):
        return [self.mainTabWidget.widget(i) for i in range(self.mainTabWidget.count()) if isinstance(self.mainTabWidget.widget(i),controls.ESIBD_Scan)]

    def getDisplayWidgets(self):
        return [self.displayTabWidget.widget(i) for i in range(self.displayTabWidget.count()) if isinstance(self.displayTabWidget.widget(i),core.ESIBD_GUI)]

    def getAllWidgets(self):
        return self.getMainWidgets() + self.getDisplayWidgets() + [self.outputWidget]

    def mainTabChanged(self):
        if self.mainTabWidget.currentWidget() in self.getMainWidgets() and self.mainTabWidget.currentWidget().displayTab is not None:
            self.displayTabWidget.setCurrentWidget(self.mainTabWidget.currentWidget().displayTab)

    GEOMETRY            = 'GEOMETRY'
    WINDOWSTATE         = 'WINDOWSTATE'
    WINDOWSIZE          = 'WINDOWSIZE'
    MAINSPLTTERSIZE     = 'MAINSPLTTERSIZE'
    CONTENTSPLTTERSIZE  = 'CONTENTSPLTTERSIZE'

    def restoreUiState(self):
        size = QGuiApplication.primaryScreen().size()
        self.restoreGeometry(self.qSet.value(self.GEOMETRY,self.saveGeometry()))
        self.restoreState(self.qSet.value(self.WINDOWSTATE,self.saveState()))
        self.mainSplitter.setSizes     ([int(x) for x in self.qSet.value(self.MAINSPLTTERSIZE,[size.height()/2,size.height()/2,0])])
        self.contentSplitter.setSizes  ([int(x) for x in self.qSet.value(self.CONTENTSPLTTERSIZE,[300,size.width()])])
        for w in self.getAllWidgets():
            try:
                w.dockArea.restoreState(self.qSet.value(w.name + 'DOCK',w.dockArea.saveState())) #,extra='left'
            except Exception: # pylint: disable=broad-except # restoreState does not throw more specific exception
                self.esibdPrint(f'Warning: Could not restore Dock {w.name}. Dock state should be availbale on next start.')

    def saveUiState(self):
        self.qSet.setValue(self.GEOMETRY,self.saveGeometry())
        self.qSet.setValue(self.WINDOWSTATE,self.saveState())
        mainSplittersizes = self.mainSplitter.sizes()
        if self.testmode: # restore console while testing
            self.qSet.setValue(self.MAINSPLTTERSIZE,self.mainSplitter.sizes())
        else: # ignore console which shall always be hidden on start and only found by those who know
            self.qSet.setValue(self.MAINSPLTTERSIZE,[mainSplittersizes[0],mainSplittersizes[1]+mainSplittersizes[2],0])
        self.qSet.setValue(self.CONTENTSPLTTERSIZE,self.contentSplitter.sizes())
        for w in self.getAllWidgets():
            self.qSet.setValue(w.name + 'DOCK',w.dockArea.saveState())

    def closeEvent(self,event):
        """ close all open connections and leave hardware in save state (voltage off)"""
        self.loading = True # skip UI updates as we are about to close
        self.outputWidget.close() # covers all devices
        self.settingsWidget.saveSettings(default = True) # general and device settings
        for i,w in enumerate(self.getScanWidgets()): # scan settings
            if i == 0:
                w.settings.defaultFile.unlink() # delete and recreate file as HDF cannot overwrite but only append data.
            if isinstance(w, controls.ESIBD_Scan): # save scan settings
                w.close()
        #self.notesWidget.rootChanging(self.explorerWidget.root,None) # TOOD
        self.saveUiState()
        app.quit()
        event.accept() # let the window close

if __name__ == '__main__':
    app = QApplication(sys.argv)
    #app.setStyle('QtCurve') # default
    if '11' in platform.release():
        app.setStyle('Fusion') # otherwise button statis is not clearly displayed on windows 11
    #app.setStyle('Windows') # very ugly
    # os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-logging"
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--enable-logging --log-level=1"
    # make task bar item work https://stackoverflow.com/questions/1551605/how-to-set-applications-taskbar-icon-in-windows-7/1552105#1552105
    myappid = 'mycompany.myproduct.subproduct.version' # arbitrary string
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

    mainWindow = ESIBD_Window()

    mainWindow.show()
    sys.exit(app.exec())
