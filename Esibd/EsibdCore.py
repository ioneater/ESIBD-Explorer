"""This module contains internally used constants, functions and classes
Generally all objects that are used accross multiple modules should be defined here to avoid circular imports and keep things consistent.
Whenever it is possible to make definitions only locally where they are needed, this is preferred. Keep this file as compact as possible.
This helps to keep things consistent and avoid errors to typos in strings etc.
In principle, different versions of this file could be used for localization
For now, English is the only supported language and use of hard coded error messages etc. in other files is tolerated if they are unique."""

import re
import sys
import traceback
import subprocess
from threading import Timer, Lock, Thread, current_thread, main_thread
from pathlib import Path
from datetime import datetime
from enum import Enum
import configparser
import importlib
import serial
from packaging import version
import numpy as np
import pyqtgraph as pg
import pyqtgraph.console
import keyboard as kb
import matplotlib as mpl
import matplotlib.pyplot as plt # pylint: disable = unused-import # need to import to access mpl.axes.Axes
from matplotlib.widgets import Cursor
from matplotlib.backend_bases import MouseButton, MouseEvent
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (QApplication, QVBoxLayout, QSizePolicy, QWidget, QGridLayout, QTreeWidgetItem, QToolButton, QDockWidget,
                             QMainWindow, QSplashScreen, #QPushButton, # QStyle, QLayout,
                             QComboBox, QDoubleSpinBox, QSpinBox, QLineEdit, QLabel, QCheckBox, QAbstractSpinBox, QTabWidget, QAbstractButton, QCompleter, QPlainTextEdit,
                             QDialog, QHeaderView, QDialogButtonBox, QTreeWidget, QTabBar)
from PyQt6.QtCore import Qt, QSettings, pyqtSignal, QObject, QPointF, pyqtProperty, QRect, QTimer, QThread, QCoreApplication #, QPoint
from PyQt6.QtGui import QIcon, QBrush, QValidator, QColor, QPainter, QPen, QTextCursor, QRadialGradient, QPixmap, QPalette, QAction
# if TYPE_CHECKING:
#     from Esibd.EsibdPlugins import Plugin, Device # only import for type checking. Do not import at runtime to avoid circular import

useWebEngine = True
# if sys.platform == 'win32':
#     if sys.getwindowsversion().major == 6 and sys.getwindowsversion().minor == 3: # win 8.1 not supported by PyQt 6
#         useWebEngine = False

# General field
COMPANY_NAME    = 'ESIBD LAB'
PROGRAM_NAME    = 'ESIBD Explorer'
PROGRAM         = 'Program'
VERSION_MAYOR   = 0
VERSION_MINOR   = 6
VERSION         = 'Version'
ICON_EXPLORER   = 'media/ESIBD_Explorer.png'
SPLASHIMAGE     = 'media/ESIBD_Explorer_Splash'
NAME            = 'Name'
PLUGIN          = 'Plugin'
INFO            = 'Info'
TIMESTAMP       = 'Time'
GENERAL         = 'General'
LOGGING         = 'Logging'
DATAPATH        = 'Data path'
CONFIGPATH      = 'Config path'
PLUGINPATH      = 'Plugin path'
DARKMODE        = 'Dark mode'
DPI             = 'DPI'
TESTMODE        = 'Test mode'
GEOMETRY        = 'GEOMETRY'
ABOUTHTML       = f"""<p>{PROGRAM_NAME} controls all aspects of an ESIBD experiment, including ion beam guiding and steering, beam energy analysis, deposition monitoring, and data analysis.<br>
                    Using the build-in plugin system, it can be extended to support additional hardware as well as custom controls for data acquisition, analysis, and visualization.<br>
                    Read the docs: <a href='TODO read the docs'>here</a> for more details.<br><br>
                    Github: <a href='https://github.com/ioneater/ES-IBD_Explorer'>https://github.com/ioneater/ES-IBD_Explorer</a><br>
                    Rauschenbach Lab: <a href='https://rauschenbach.chem.ox.ac.uk/'>https://rauschenbach.chem.ox.ac.uk/</a><br>
                    Present implementation in Python/PyQt: ioneater <a href='mailto:tim.esser@gmx.de'>tim.esser@gmx.de</a><br>
                    Original implementation in LabView: rauschi2000 <a href='mailto:stephan.rauschenbach@chem.ox.ac.uk'>stephan.rauschenbach@chem.ox.ac.uk</a><br></p>"""

qSet = QSettings(COMPANY_NAME, PROGRAM_NAME)

def getDarkMode():
    return qSet.value(f'{GENERAL}/{DARKMODE}', 'true') == 'true'

def infoDict(name):
    return {PROGRAM : PROGRAM_NAME, VERSION : f'{VERSION_MAYOR}.{VERSION_MINOR}', PLUGIN : name, TIMESTAMP : datetime.now().strftime('%Y-%m-%d %H:%M')}

# file types
FILE_INI = '.ini'
FILE_H5  = '.h5'
FILE_PDF = '.pdf'

# other
UTF8    = 'utf-8'

# class TestAllControls(QObject):
#     """Triggers events of all standard controls to reveal unstable code."""

#     testControlSignal = pyqtSignal(QObject)

#     def __init__(self, mainWindow):
#         super().__init__(mainWindow)
#         self.mainWindow = mainWindow
#         self.tested = 0
#         self.testControlSignal.connect(self.testControl)

#     def test(self):
#         # if testing is called from console, testAll should still be executed independently to make sure stdout does not land in console only
#         Timer(0, self.testAll).start()
#         Timer(150, self.endTest).start()

#     def testAll(self):
#         print('Start testing all controls.')
#         self.mainWindow.pluginManager.loading = True # no need to plot data during this test, this will be tested independently
#         for t in [QAction, QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox, QCheckBox, pg.ColorButton]:
#             for c in self.mainWindow.findChildren(t):
#                 self.testControlSignal.emit(c)
#                 if np.mod(self.tested, 100) == 0:
#                     QApplication.processEvents()

#     def testControl(self, c):
#         if isinstance(c, QAction):
#             c.triggered.emit(c.isChecked())
#         elif isinstance(c, QComboBox):
#             c.currentIndexChanged.emit(c.currentIndex())
#         elif isinstance(c, (QLineEdit)):
#             c.editingFinished.emit()
#         elif isinstance(c, (QSpinBox)):
#             c.valueChanged.emit(c.value())
#             c.editingFinished.emit()
#         elif isinstance(c, (QCheckBox)):
#             c.stateChanged.emit(c.isChecked())
#         elif isinstance(c, (QToolButton)):
#             c.clicked.emit()
#         elif isinstance(c, (pg.ColorButton)):
#             c.sigColorChanged.emit(c)
#         self.tested += 1
#         print(f'Tested {self.tested} controls. Last tested {c.objectName()}.')

#     def endTest(self):
#         self.mainWindow.pluginManager.loading = False
#         print('End testing all controls.')

class Colors():
    """Provides dark mode dependant defaul colors"""

    def getDarkMode(self):
        # qSet.sync()
        return qSet.value(f'{GENERAL}/{DARKMODE}', 'true') == 'true'

    @property
    def fg(self):
        return '#e4e7eb' if getDarkMode() else '#000000'

    @property
    def bg(self):
        return '#202124' if getDarkMode() else '#ffffff'

    @property
    def bgAlt1(self):
        return QColor(self.bg).lighter(160).name() if getDarkMode() else QColor(self.bg).darker(105).name()

    @property
    def bgAlt2(self):
        return QColor(self.bg).lighter(200).name() if getDarkMode() else QColor(self.bg).darker(110).name()

    @property
    def highlight(self):
        return '#8ab4f7' if getDarkMode() else '#0063e6'

colors = Colors()

def makeSettingWrapper(name, settingsMgr, docstring=None):
    """ Neutral setting wrapper for convenient access to the value of a setting.
        If you need to handle events on value change, link these directly to the events of the corresponding control.
    """
    def getter(self): # pylint: disable=[unused-argument] # self will be passed on when used in class
        return settingsMgr.settings[name].value
    def setter(self, value): # pylint: disable=[unused-argument] # self will be passed on when used in class
        settingsMgr.settings[name].value = value
    return property(getter, setter, doc=docstring)

def makeWrapper(name, docstring=None):
    """ Neutral property wrapper for convenient access to the value of a parameter inside a channel.
        If you need to handle events on value change, link these directly to the events of the corresponding control in the finalizeInit method.
    """
    def getter(self):
        return self.getParameterByName(name).value
    def setter(self, value):
        self.getParameterByName(name).value = value
    return property(getter, setter, doc=docstring)

def makeStateWrapper(stateAction, docstring=None):
    """State wrapper for convenient access to the value of a StateAction."""
    def getter(self): # pylint: disable = unused-argument
        return stateAction.state
    def setter(self, state): # pylint: disable = unused-argument
        stateAction.state = state
    return property(getter, setter, doc=docstring)

def dynamicImport(module, path):
    spec = importlib.util.spec_from_file_location(module, path)
    Module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(Module)
    return Module

class INOUT(Enum):
    """Used to specify if a function affects only input, only output, or all channels."""
    IN = 0
    """Input"""
    OUT = 1
    """Output"""
    BOTH = 2
    """Both input and output."""

class PRINT(Enum):
    """Used to specify if a function affects only input, only output, or all channels."""
    MESSAGE = 0
    """A standard message."""
    WARNING = 1
    """Tag message as warning and highlight using color."""
    ERROR = 2
    """Tag message as error and highlight using color."""
    DEBUG = 3
    """Only show if debug flag is enabled."""

class EsibdExplorer(QMainWindow):
    r"""ESIBD Explorer: A comprehensive data acquisition and analysis tool for Electrospray Ion-Beam Deposition experiments and beyond.
    
    Contains minimal code to start, initialize, and close the program.
    All high level logic is provided by :mod:`~Esibd.EsibdCore`, 
    :mod:`~Esibd.EsibdPlugins` and additional
    :class:`plugins<Esibd.EsibdPlugins.Plugin>`.
    """

    loadPluginsSignal = pyqtSignal()

    def __init__(self):
        """Sets up basic user interface and triggers loading of plugins."""
        super().__init__()
        if useWebEngine:
            dummy = QWebEngineView(parent=self) # switch to GL compatibility mode https://stackoverflow.com/questions/77031792/how-to-avoid-white-flash-when-initializing-qwebengineview
            dummy.setHtml('dummy')
            dummy.deleteLater()
        self.restoreUiState()
        self.setWindowIcon(QIcon(ICON_EXPLORER))
        self.setWindowTitle(PROGRAM_NAME)
        self.actionFull_Screen = QAction()
        self.actionFull_Screen.triggered.connect(self.toggleFullscreen)
        self.actionFull_Screen.setShortcut('F11')
        self.addAction(self.actionFull_Screen) # action only works when added to a widget
        self.maximized  = False
        self.loadPluginsSignal.connect(self.loadPlugins)
        QTimer.singleShot(0, self.loadPluginsSignal.emit) # let event loop start before loading plugins

    def loadPlugins(self):
        """Loads :class:`plugins<Esibd.EsibdPlugins.Plugin>` in main thread."""
        self.pluginManager = PluginManager()
        self.pluginManager.loadPlugins()

    def toggleFullscreen(self):
        """Toggles full screen mode."""
        if self.isFullScreen(): # return to previous view
            self.showMaximized() if self.maximized else self.showNormal() # pylint: disable = expression-not-assigned
        else: # goFullscreen
            self.maximized = self.isMaximized() # workaround for bug https://github.com/qutebrowser/qutebrowser/issues/2778
            self.showFullScreen()

    def restoreUiState(self):
        """Restores size and location of main window."""
        try:
            self.restoreGeometry(qSet.value(GEOMETRY, self.saveGeometry()))
            # Note that the state on startup will not include dynamic displays which open only as needed. Thus the state cannot be restored.
            # self.mainWindow.restoreState(qSet.value(self.WINDOWSTATE, self.mainWindow.saveState()))
            # NOTE: need to restore before starting event loop to avoid Unable to set geometry warning
        except TypeError as e:
            print(f'Could not restore window state: {e}')
            self.resize(800, 400)
            self.saveUiState()

    def saveUiState(self):
        """Saves size and location of main window."""
        qSet.setValue(GEOMETRY, self.saveGeometry())
        # qSet.setValue(GEOMETRY, self.mainWindow.geometry())
        # qSet.setValue(self.WINDOWSTATE, self.mainWindow.saveState())

    def closeEvent(self, event):
        """Triggers :class:`~Esibd.EsibdCore.PluginManager` to close all plugins and all related communication."""
        if not self.pluginManager.loading and (not any([ld.recording for ld in self.pluginManager.DeviceManager.getActiveLiveDisplays()])
                or CloseDialog(prompt='Acquisition is still running. Do you really want to close?').exec()):
            self.pluginManager.closePlugins()
            QApplication.instance().quit()
            event.accept() # let the window close
        else:
            event.ignore() # keep running

class PluginManager():
    """The :class:`~Esibd.EsibdCore.PluginManager` is responsible for loading all internal and external
        Plugins. It catches errors or incompatibilities while loading,
        initializing, and closing plugins. Users will only see the plugin selection
        interface accessed from the :ref:`sec:settings` plugin.
        The :class:`~Esibd.EsibdCore.PluginManager` can be accessed from the :ref:`sec:console` as `PluginManager`.
        It allows plugins to interact by using unique plugin names as attributes, e.g.
        `self.pluginManager.ISEG` or `self.pluginManager.DeviceManager`."""

    class SignalCommunicate(QObject):
        finalizeSignal = pyqtSignal()
        toggleTitleBarSignal = pyqtSignal()

    class TYPE(Enum):
        """Each plugin must be of one of the following types to define its location and behavior."""
        CONSOLE       = 'Console'
        """The internal Console."""
        CONTROL       = 'Generic Control'
        """Any control plugin, will be placed next to Settings, Explorer, Devices, and Scans."""
        INPUTDEVICE   = 'Input Device'
        """Device plugin sending user input to hardware."""
        OUTPUTDEVICE  = 'Output Device'
        """Device plugin sending hardware output to user."""
        DISPLAY       = 'Display'
        """Any display plugin, will be places next to scan displays and static displays."""
        LIVEDISPLAY   = 'LiveDisplay'
        """Live display associated with a device."""
        SCAN          = 'Scan'
        """Scan plugin, will be placed with other controls."""
        DEVICEMGR     = 'DeviceManager'
        """Device manager, will be placed below live displays."""
        INTERNAL      = 'Internal'
        """A plugin without user interface."""

    VERSION             = 'Version'
    ENABLED             = 'Enabled'
    PREVIEWFILETYPES    = 'PREVIEWFILETYPES'
    DESCRIPTION         = 'DESCRIPTION'
    OPTIONAL            = 'OPTIONAL'
    PLUGINTYPE          = 'PLUGINTYPE'
    # WINDOWSTATE = 'WINDOWSTATE'
    plugins = [] # Plugin avoid circular import
    """A central plugin list that allows plugins to interact with each other."""

    def __init__(self):
        self.mainWindow = QApplication.instance().mainWindow
        self.logger = Logger(pluginManager=self)
        self.logger.print('Loading.')
        # self.debug = True # set to True to print debug messages
        self.debug = False # set to True to print debug messages
        self.userPluginPath     = None
        self.pluginFile         = None
        self.internalPluginPath = Path('plugins')
        self.mainWindow.setTabPosition(Qt.DockWidgetArea.LeftDockWidgetArea, QTabWidget.TabPosition.North)
        self.mainWindow.setTabPosition(Qt.DockWidgetArea.RightDockWidgetArea, QTabWidget.TabPosition.North)
        self.mainWindow.setTabPosition(Qt.DockWidgetArea.TopDockWidgetArea, QTabWidget.TabPosition.North)
        self.mainWindow.setTabPosition(Qt.DockWidgetArea.BottomDockWidgetArea, QTabWidget.TabPosition.North)
        self.mainWindow.setDockOptions(QMainWindow.DockOption.AllowTabbedDocks | QMainWindow.DockOption.AllowNestedDocks
                                     | QMainWindow.DockOption.GroupedDragging | QMainWindow.DockOption.AnimatedDocks)
        self.signalComm = self.SignalCommunicate()
        self.signalComm.finalizeSignal.connect(self.finalizeUiState)
        self.signalComm.toggleTitleBarSignal.connect(self.toggleTitleBar)
        self.plugins = []
        self.pluginNames = []
        self.firstControl = None
        self.firstDisplay = None
        self._loading = 0
        self.closing = False

    @property
    def loading(self):
        """Flag that can be used to suppress events while plugins are loading, initializing, or closing."""
        return self._loading != 0

    @loading.setter
    def loading(self, loading):
        if loading:
            self._loading +=1
        else:
            self._loading -= 1
        # print('pluginManager', self._loading)

    def loadPlugins(self, reload=False):
        """Loads all enabled plugins."""

        self.updateTheme()
        if not reload:
            self.splash = SplashScreen()
            self.splash.show()
            QApplication.processEvents()

        self.mainWindow.setUpdatesEnabled(False)
        self.loading = True # some events should not be triggered until after the UI is completely initialized
        self.closing = False

        self.userPluginPath     = Path(qSet.value(f'{GENERAL}/{PLUGINPATH}',(Path.home() / PROGRAM_NAME / 'plugins/').as_posix()))
        # self.mainWindow.configPath not yet be available -> use directly from qSet
        self.pluginFile         = Path(qSet.value(f'{GENERAL}/{CONFIGPATH}',(Path.home() / PROGRAM_NAME / 'conf/').as_posix())) / 'plugins.ini'
        self.plugins = []
        self.pluginNames = []
        self.firstControl = None
        self.firstDisplay = None

        self.confParser = configparser.ConfigParser()
        self.pluginFile.parent.mkdir(parents=True, exist_ok=True)
        if self.pluginFile.exists():
            self.confParser.read(self.pluginFile)

        import Esibd.EsibdPlugins # pylint: disable = import-outside-toplevel # avoid circular import
        self.loadPluginsFromModule(Module=Esibd.EsibdPlugins, dependencyPath=Path('media'))
        self.loadPluginsFromPath(self.internalPluginPath)
        self.userPluginPath.mkdir(parents=True, exist_ok=True)
        if self.userPluginPath == self.internalPluginPath:
            self.logger.print('Ignoring user plugin path as it equals internal plugin path.', flag=PRINT.WARNING)
        else:
            self.loadPluginsFromPath(self.userPluginPath)

        obsoletePluginNames = []
        for name in self.confParser.keys():
            if not name == Parameter.DEFAULT.upper() and not name in self.pluginNames:
                obsoletePluginNames.append(name)
        if len(obsoletePluginNames) > 0:
            self.logger.print(f"Removing obsolete plugin data: {', '.join(obsoletePluginNames)}", flag=PRINT.WARNING)
            for o in obsoletePluginNames:
                self.confParser.pop(o)
        with open(self.pluginFile,'w', encoding = UTF8) as configfile:
            self.confParser.write(configfile)

        if hasattr(self, 'Settings'):
            self.Settings.init()  # init internal settings and settings of devices and scans which have been added in the meantime
        self.provideDocks() # add plugin docks before loading = False

        if hasattr(self, 'Tree'):
            self.plugins.append(self.plugins.pop(self.plugins.index(self.Tree))) # move Tree to end to have lowest priority to handle files
        if hasattr(self, 'Text'):
            self.plugins.append(self.plugins.pop(self.plugins.index(self.Text))) # move Text to end to have lowest priority to handle files
        self.loading = False
        self.finalizeInit()
        self.mainWindow.setUpdatesEnabled(True)
        QTimer.singleShot(0, self.signalComm.finalizeSignal.emit) # add delay to make sure application is ready to process updates, but make sure it is done in main thread
        self.splash.close() # close as soon as mainWindow is ready
        self.logger.print('Ready.')

    def loadPluginsFromPath(self, path):
        for _dir in [_dir for _dir in path.iterdir() if _dir.is_dir()]:
            for file in [file for file in _dir.iterdir() if file.name.endswith('.py')]:
                try:
                    Module = dynamicImport(file.stem, file)
                except Exception as e: # pylint: disable = broad-except # we have no control about the exeption a plugin can possibly throw
                    # No unpredicatble Exeption in a single plugin should break the whole application
                    self.logger.print(f'Could not import module {file.stem}: {e}', flag=PRINT.ERROR)
                else:
                    if hasattr(Module,'providePlugins'):
                        self.loadPluginsFromModule(Module=Module, dependencyPath=file.parent)
                    # silently ignore dependencies which do not define providePlugins

    def loadPluginsFromModule(self, Module, dependencyPath):
        """Loads plugins from a module."""
        for Plugin in Module.providePlugins():
            # requires loading all dependencies, no matter if plugin is used or not
            # if a dependency of an unused plugin causes issues, report it and remove the corresponding file from the plugin folder until fixed.
            # might consider different import mechanism which does not require import unless plugins are enabled.
            self.pluginNames.append(Plugin.name)
            if Plugin.name not in self.confParser: #add
                self.confParser[Plugin.name] = {self.ENABLED : not Plugin.optional, self.VERSION : Plugin.version, self.PLUGINTYPE : str(Plugin.pluginType.value),
                                            self.PREVIEWFILETYPES : ', '.join(Plugin.previewFileTypes), self.DESCRIPTION : Plugin.__doc__, self.OPTIONAL : str(Plugin.optional)}
            else: # update
                self.confParser[Plugin.name][self.VERSION] = Plugin.version
                self.confParser[Plugin.name][self.PLUGINTYPE] = str(Plugin.pluginType.value)
                self.confParser[Plugin.name][self.PREVIEWFILETYPES] = ', '.join(Plugin.previewFileTypes)
                self.confParser[Plugin.name][self.DESCRIPTION] = Plugin.__doc__
                self.confParser[Plugin.name][self.OPTIONAL] = str(Plugin.optional)
            if self.confParser[Plugin.name][self.ENABLED] == 'True':
                p=self.loadPlugin(Plugin, dependencyPath=dependencyPath)
                if p is not None:
                    self.confParser[Plugin.name][self.PREVIEWFILETYPES] = ', '.join(p.getSupportedFiles()) # requires instance

    def loadPlugin(self, Plugin, dependencyPath=None):
        """Load a single plugin.
        Plugins must have a static name and pluginType.
        'mainWindow' is passed to enable flexible integration, but should only be used at your own risk.
        Enabled state is saved and restored from an independent file and can also be edited using the plugins dialog."""
        QApplication.processEvents() # break down expensive initialization to allow update splash screens while loading
        self.logger.print(f'loadPlugin {Plugin.name}', flag=PRINT.DEBUG)
        if version.parse(Plugin.supportedVersion) != version.parse(f'{VERSION_MAYOR}.{VERSION_MINOR}'):
            self.logger.print(f'Plugin {Plugin.name} supports {PROGRAM_NAME} {Plugin.supportedVersion}. It is not compatible with {PROGRAM_NAME} {VERSION_MAYOR}.{VERSION_MINOR}.', flag=PRINT.WARNING)
            return
        if Plugin.name in [p.name for p in self.plugins]:
            self.logger.print(f'Ignoring duplicate plugin {Plugin.name}.', flag=PRINT.WARNING)
        else:
            try:
                p=Plugin(pluginManager=self, dependencyPath=dependencyPath)
                setattr(self.__class__, p.name, p) # use attributes to access for communication between plugins
            except Exception as e: # pylint: disable = broad-except # we have no control about the exeption a plugin can possibly throw
                # No unpredicatble Exeption in a single plugin should break the whole application
                self.logger.print(f'Could not load plugin {Plugin.name}: {e}', flag=PRINT.ERROR)
            else:
                self.plugins.append(p)
                return p
        return None

    def provideDocks(self):
        """creates docks and positions them as defined by plugintype"""
        if not hasattr(self, 'topDock'): # reuse old
            self.topDock = QDockWidget() # dummy to align other docks to
            self.topDock.setObjectName('topDock') # required to restore state
            QApplication.processEvents()
            self.topDock.hide()
        # NOTE: when using TopDockWidgetArea there is a superfluous separator on top of the statusbar
        self.mainWindow.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.topDock)
        for p in self.plugins:
            self.logger.print(f'provideDocks {p.name}', flag=PRINT.DEBUG)
            if not p.pluginType in [self.TYPE.INTERNAL, self.TYPE.DISPLAY] or p.name == 'Browser':
                # display plugins will be initialized when needed, internal plugins do not need GUI
                try:
                    p.provideDock()
                except Exception:
                    self.logger.print(f'Could not load GUI of plugin {p.name}: {traceback.format_exc()}', flag=PRINT.ERROR)
                    self.plugins.pop(self.plugins.index(p)) # avoid any further undefined interaction
                self.splash.raise_() # some operations (likely tabifyDockWidget) will cause the main window to get on top of the splash screen
        tabBars = self.mainWindow.findChildren(QTabBar)
        if tabBars: #might be null if there are no tabbed docks
            for t in tabBars:
                t.setElideMode(Qt.TextElideMode.ElideNone) # do not elide tab names

    def finalizeInit(self):
        """Finalize initalization after all other plugins have been initialized."""
        for p in self.plugins:
            QApplication.processEvents()
            if p.initializedDock:
                try:
                    p.finalizeInit()
                except Exception:
                    self.logger.print(f'Could not finalize plugin {p.name}: {traceback.format_exc()}', flag=PRINT.ERROR)
                    p.closeGUI()
                    self.plugins.pop(self.plugins.index(p)) # avoid any further undefined interaction

    def test(self):
        """ Calls :meth:`~Esibd.EsibdCore.PluginManager.runTestParallel` to test most features of for all plugins."""
        Timer(0, self.runTestParallel).start()

    def runTestParallel(self):
        """Runs test of all plugins from parallel thread."""
        for p in self.plugins:
            p.runTestParallel()

    def managePlugins(self):
        """A dialog to select which plugins should be enabled"""
        if self.DeviceManager.recording:
            if CloseDialog(title='Stop Acquisition?', ok='Stop Acquisition', prompt='Acquisition is still running. Stop acquisition before changin plugins!').exec():
                self.DeviceManager.stopAcquisition()
            else:
                return
        dlg = QDialog(self.mainWindow)
        dlg.resize(800, 400)
        dlg.setWindowTitle('Select Plugins')
        dlg.setWindowIcon(BetterIcon('media/block--pencil.png'))
        lay = QGridLayout()
        tree = QTreeWidget()
        tree.setHeaderLabels(['Name','Enabled','Version','Type','Preview File Types','Description'])
        tree.setColumnCount(6)
        tree.setRootIsDecorated(False)
        tree.header().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        tree.header().setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        tree.setColumnWidth(1, 50)
        tree.setColumnWidth(2, 50)
        tree.setColumnWidth(4, 150)
        root = tree.invisibleRootItem()
        lay.addWidget(tree)
        buttonBox = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttonBox.button(QDialogButtonBox.StandardButton.Ok).setText("Confirm and Reload Plugins")
        buttonBox.accepted.connect(dlg.accept)
        buttonBox.rejected.connect(dlg.reject)
        lay.addWidget(buttonBox)
        confParser = configparser.ConfigParser()
        if self.pluginFile.exists():
            confParser.read(self.pluginFile)
        for name, item in confParser.items():
            if name != Parameter.DEFAULT.upper():
                self.addPluginTreeWidgetItem(tree=tree, name=name, enabled=item[self.ENABLED] == 'True', version_=item[self.VERSION],
                                                pluginType=item[self.PLUGINTYPE], previewFileTypes=item[self.PREVIEWFILETYPES],
                                                description=item[self.DESCRIPTION], optional=item[self.OPTIONAL] == 'True')
        dlg.setLayout(lay)
        if dlg.exec():
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            children = [root.child(i) for i in range(root.childCount())] # list of existing children
            for name, enabled, internal in [(c.text(0),(tree.itemWidget(c, 1)).isChecked(), not (tree.itemWidget(c, 1)).isEnabled()) for c in children]:
                if not internal:
                    confParser[name][self.ENABLED] = str(enabled)
            with open(self.pluginFile,'w', encoding=UTF8) as configfile:
                confParser.write(configfile)
            self.closePlugins(reload=True)
            QApplication.restoreOverrideCursor()

    def addPluginTreeWidgetItem(self, tree, name, enabled, version_, pluginType, previewFileTypes, description, optional=True):
        """Adds a row for given plugin. If not a core plugin it can be enabled or disabled using the checkbox."""
        p = QTreeWidgetItem(tree.invisibleRootItem(),[name])
        c = CheckBox()
        c.setChecked(enabled)
        c.setEnabled(optional)
        tree.setItemWidget(p, 1, c)
        versionLabel = QLabel()
        versionLabel.setText(version_)
        tree.setItemWidget(p, 2, versionLabel)
        typeLabel = QLabel()
        typeLabel.setText(pluginType)
        tree.setItemWidget(p, 3, typeLabel)
        previewFileTypesLabel = QLabel()
        previewFileTypesLabel.setText(previewFileTypes)
        previewFileTypesLabel.setToolTip(previewFileTypes)
        tree.setItemWidget(p, 4, previewFileTypesLabel)
        descriptionLabel = QLabel()
        if description is not None:
            descriptionLabel.setText(description.splitlines()[0][:100] )
            descriptionLabel.setToolTip(description)
        tree.setItemWidget(p, 5, descriptionLabel)

    def closePlugins(self, reload=False):
        """ close all open connections and leave hardware in save state (voltage off)"""
        self.logger.print('Closing.')
        if reload:
            self.splash = SplashScreen()
            self.splash.show()
            QApplication.processEvents()
        qSet.sync()
        self.loading = True # skip UI updates
        self.mainWindow.saveUiState()
        self.closing = not reload
        for p in self.plugins:
            try:
                p.closeGUI()
            except Exception: # pylint: disable = broad-except # we have no control about the exeption a plugin can possibly throw
                # No unpredicatble Exeption in a single plugin should break the whole application
                self.logger.print(f'Could not close plugin {p.name}: {traceback.format_exc()}',PRINT.ERROR)
        if reload:
            self.Explorer.print('Reloading Plugins')
            self.loadPlugins(reload=True) # restore fails if plugins have been added or removed
            self.loading = False
        else:
            self.logger.close()

    def finalizeUiState(self):
        self.Settings.raiseDock() # make sure settings tab visible after start
        QApplication.processEvents()
        self.Explorer.raiseDock() # only works if given at least .3 ms delay after loadPlugins completed
        if hasattr(self, 'Browser'):
            self.Browser.raiseDock()
        self.Console.toggleVisible()

    def getMainPlugins(self):
        """Returns all plugins found in the control section, including devices, controls, and scans."""
        return self.getPluginsByType([self.TYPE.INPUTDEVICE, self.TYPE.OUTPUTDEVICE, self.TYPE.CONTROL, self.TYPE.SCAN])

    def getPluginsByType(self, pluginTypes):
        """Returns all plugins of the specified type.

        :param pluginTypes: A single type or list of types.
        :type pluginTypes: :meth:`~Esibd.EsibdCore.PluginManager.TYPE`
        :return: _description_
        :rtype: _type_
        """
        if isinstance(pluginTypes, list):
            return [p for p in self.plugins if p.pluginType in pluginTypes]
        else:
            return [p for p in self.plugins if p.pluginType == pluginTypes]

    def toggleTitleBarDelayed(self):
        QTimer.singleShot(500, self.signalComm.toggleTitleBarSignal.emit)

    def toggleTitleBar(self):
        for p in self.plugins:
            if p.initializedDock:
                p.toggleTitleBar()

    def updateTheme(self):
        """Updates application theme while showing a splash screen if necessary."""
        if not self.loading:
            splash = SplashScreen()
            splash.show()
            QApplication.processEvents()
            self.mainWindow.setUpdatesEnabled(False)
        pal = QApplication.style().standardPalette()
        pal.setColor(QPalette.ColorRole.Base, QColor(colors.bg))
        pal.setColor(QPalette.ColorRole.AlternateBase, QColor(colors.bg))
        pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(colors.bg))
        pal.setColor(QPalette.ColorRole.Window, QColor(colors.bg))
        pal.setColor(QPalette.ColorRole.Button, QColor(colors.bgAlt2)) # also comboboxes
        pal.setColor(QPalette.ColorRole.Text, QColor(colors.fg))
        pal.setColor(QPalette.ColorRole.ToolTipText, QColor(colors.fg))
        pal.setColor(QPalette.ColorRole.WindowText, QColor(colors.fg))
        pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(colors.fg))
        pal.setColor(QPalette.ColorRole.ButtonText, QColor(colors.fg))
        pal.setColor(QPalette.ColorRole.BrightText, QColor(colors.highlight))
        pal.setColor(QPalette.ColorRole.HighlightedText, QColor(colors.highlight))
        self.styleSheet = f"""
        QTreeView::item {{border: none; outline: 0;}}
        QLineEdit     {{background-color:{colors.bgAlt2};}}
        QPlainTextEdit{{background-color:{colors.bgAlt2};}}
        QSpinBox      {{background-color:{colors.bgAlt2}; color:{colors.fg}; border-style:none;}}
        QDoubleSpinBox{{background-color:{colors.bgAlt2}; color:{colors.fg}; border-style:none;}}
        QMainWindow::separator      {{background-color:{colors.bgAlt2};    width:4px; height:4px;}}
        QMainWindow::separator:hover{{background-color:{colors.highlight}; width:4px; height:4px;}}
        QWidget::separator      {{background-color:{colors.bgAlt2};    width:4px; height:4px;}}
        QWidget::separator:hover{{background-color:{colors.highlight}; width:4px; height:4px;}}
        QToolBar{{background-color:{colors.bgAlt1}; margin:0px 0px 0px 0px;}}
        QToolBarExtension {{qproperty-icon: url({'media/chevron_double_dark.png' if getDarkMode() else 'media/chevron_double_light.png'});}}
        QToolTip{{background-color: {colors.bg}; color: {colors.fg}; border: black solid 1px}}
        QCheckBox::indicator         {{border:1px solid {colors.fg}; width: 12px;height: 12px;}}
        QCheckBox::indicator:checked {{border:1px solid {colors.fg}; width: 12px;height: 12px; image: url({'media/check_dark.png' if getDarkMode() else 'media/check.png'})}}
        QTabBar::tab         {{margin:0px 0px 2px 0px; padding:4px; border-width:0px; }}
        QTabBar::tab:selected{{margin:0px 0px 0px 0px; padding:4px; border-bottom-width:2px; color:{colors.highlight}; border-bottom-color:{colors.highlight}; border-style:solid;}}"""
        # QMainWindow::separator Warning: The style sheet has no effect when the QDockWidget is undocked as Qt uses native top level windows when undocked.
        # QLineEdit     {{border-color:{fg}; border-width:1px; border-style:solid;}}
        # QPlainTextEdit{{border-color:{fg}; border-width:1px; border-style:solid;}}
        # QStatusBar::item {{border: 1px solid red;}}
        # QCheckBox::indicator{{border:1px solid {fg};}}
        QApplication.setPalette(pal)
        self.mainWindow.setStyleSheet(self.styleSheet)
        plt.style.use('dark_background' if getDarkMode() else 'default')
        for p in self.plugins:
            if p.initializedDock:
                try:
                    p.updateTheme()
                except Exception:
                    self.logger.print(f'Error while updating plugin {p.name} theme: {traceback.format_exc()}')
        if not self.loading:
            self.mainWindow.setUpdatesEnabled(True)
            # dialog.close()
            splash.close()

class Logger(QObject):
    """Redicrects stderr and stdout to logfile while still sending them to :ref:`sec:console` as well.
    Also shows messages on Status bar.
    Use :meth:`~Esibd.EsibdPlugins.Plugin.print` of :class:`~Esibd.EsibdPlugins.Plugin` to send messages to the logger."""

    printFromThreadSignal = pyqtSignal(str, str, PRINT)

    def __init__(self, pluginManager):
        """
        :param pluginManager: The central pluginManager
        :type pluginManager: :class:`~Esibd.EsibdCore.PluginManager`
        """
        super().__init__()
        self.pluginManager = pluginManager
        self.logFileName = Path(qSet.value(f'{GENERAL}/{CONFIGPATH}',(Path.home() / PROGRAM_NAME / 'conf/').as_posix())) / f'{PROGRAM_NAME.lower()}.log'
        self.active = False
        self.lock = Lock()
        self.printFromThreadSignal.connect(self.print)
        if qSet.value(LOGGING, 'false') == 'true':
            self.open()

    def open(self):
        """Activates logging of Plugin.print statements, stdout, and stderr to the log file."""
        if not self.active:
            self.terminalOut = sys.stdout
            self.terminalErr = sys.stderr
            sys.stderr = sys.stdout = self # redirect all calls to stdout and stderr to the write function of our logger
            self.log = open(self.logFileName, 'w', encoding=UTF8) # pylint: disable=consider-using-with # keep file open instead of reopening for every new line
            self.active = True

    def openLog(self):
        """Opens the log file in an external program."""
        if self.logFileName.exists():
            subprocess.Popen(f'explorer {self.logFileName}')
        else:
            self.print('Start logging to create log file.')

    def write(self, message):
        """Directs messages to terminal, log file, and :ref:`sec:console`.
        Called directly from stdout or stderr or indirectly via Plugin.print."""
        if self.active:
            if self.terminalOut is not None: # after packaging with pyinstaller the programm will not be connected to a terminal
                self.terminalOut.write(message) # write to original stdout
            with self.lock:
                self.log.write(message) # write to log file
                self.log.flush()
        if current_thread() is main_thread() and hasattr(self.pluginManager, 'Console') and self.pluginManager.Console.initializedDock:
            # handles new lines in system error messages better than Console.write
            # needs to run in main_thread
            self.pluginManager.Console.mainConsole.output.insertPlainText(message)

    def print(self, message, sender=f'{PROGRAM_NAME} {VERSION_MAYOR}.{VERSION_MINOR}', flag=PRINT.MESSAGE): # only used for program messages
        """Augments messages and redirects to log file, console, statusbar, and console.

        :param message: A short and descriptive message.
        :type message: str
        :param sender: The name of the sending plugin, defaults to f'{PROGRAM_NAME} {VERSION_MAYOR}.{VERSION_MINOR}'
        :type sender: str, optional
        :param flag: Signals the status of the message, defaults to PRINT.MESSAGE
        :type flag: :meth:`~Esibd.EsibdCore.PRINT`, optional
        """
        if current_thread() is not main_thread():
            # redirect to main thread if needed to avoid chanign GUI from parallel thread.
            self.printFromThreadSignal.emit(message, sender, flag)
            return
        if flag == PRINT.DEBUG and not self.pluginManager.debug:
            return
        if flag == PRINT.WARNING:
            flagstring = ' warning'
            styleSheet = 'color : orange;' if getDarkMode() else 'color : orangered;'
        elif flag == PRINT.ERROR:
            flagstring = ' error'
            styleSheet = 'color : red;'
        else:
            flagstring = ''
            styleSheet = 'color : white;' if getDarkMode() else 'color : black;'
        message = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {sender}{flagstring}: {message}"
        if self.active:
            print(message) # redirects to write if active
        else:
            print(message) # only to stdout if not active
            self.write(f'\n{message}') # call explicitly otherwise
        self.pluginManager.mainWindow.statusBar().showMessage(message)
        self.pluginManager.mainWindow.statusBar().setStyleSheet(styleSheet)

    def flush(self):
        """Flushes content to log file"""
        self.log.flush()

    def close(self):
        """Disables logging and restores stdout and stderr"""
        if self.active:
            self.log.close()
            self.active = False
            sys.stdout = self.terminalOut # restore previous
            sys.stderr = self.terminalErr # restore previous

class CloseDialog(QDialog):
    """ Dialog to confirm closing the program."""
    def __init__(self, parent=None, title=f'Close {PROGRAM_NAME}?', ok='Close', prompt='Do you really want to close?'):
        super().__init__(parent)

        self.setWindowTitle(title)
        self.setModal(True)
        buttonBox = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttonBox.button(QDialogButtonBox.StandardButton.Ok).setText(ok)
        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)
        self.layout = QVBoxLayout()
        self.layout.addWidget(QLabel(prompt))
        self.layout.addWidget(buttonBox)
        self.setLayout(self.layout)
        buttonBox.button(QDialogButtonBox.StandardButton.Cancel).setFocus()

class InfoDialog(QDialog):
    """ Dialog to confirm closing the program."""
    def __init__(self, parent=None, title='Information.', info='This is Information.'):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.layout = QVBoxLayout()
        self.layout.addWidget(QLabel(info))
        self.setLayout(self.layout)

class DynamicNp():
    """ A numpy.array that dynamically increases its size in increments to prevent frequent memory allocation while growing."""
    # based on https://stackoverflow.com/questions/7133885/fastest-way-to-grow-a-numpy-numeric-array
    def __init__(self, initialData=None, max_size=None, dtype=np.float32):
        # use float64 for time data
        self.init(initialData, max_size, dtype)

    def init(self, initialData=None, max_size=None, dtype=np.float32):
        self.data = np.zeros((2000,),dtype=dtype) if initialData is None or initialData.shape[0] == 0 else initialData
        self.capacity = self.data.shape[0]
        self.size = 0 if initialData is None else initialData.shape[0]
        self.max_size = max_size

    def add(self, x, lenT=None):
        """Adds the new data point and adjusts the data array as required."""
        if lenT is not None:
            if self.size < lenT:
                # if length does not match length of time, e.g. becuase channel was enabled later then others or temporarily disabled,
                # padd data with NaN to ensure data is alligned with time axis
                pad = np.zeros(lenT-self.size)
                pad[:] = np.nan
                self.init(np.hstack([self.get(), pad, x]), max_size=self.max_size) # append padding after existing data to account for time without data collection
            if self.size > lenT:
                self.init(self.get()[-lenT:], max_size=self.max_size) # remove data older than time axis
        if self.size == self.capacity:
            self.capacity *= 4
            newdata = np.zeros((self.capacity,))
            newdata[:self.size] = self.data
            self.data = newdata
        if self.max_size is not None and self.size >= self.max_size:
            # thin out old data. use only every second value for first half of array to limit RAM use
            a, b = np.array_split(self.get(), 2) # pylint: disable=[unbalanced-tuple-unpacking] # balance not relevant, as long as it is consistent
            self.size = a[::2].shape[0]+b.shape[0]
            self.data[:self.size] = np.hstack([a[::2], b])
            self.data[self.size] = x
            self.size += 1
            # remove old data as new data is coming in. while this implementation is simpler it limits the length of stored history
            # self.data = np.roll(self.data,-1)
            # self.data[self.size-1] = x
        else:
            self.data[self.size] = x
            self.size += 1

    def get(self, length=None, _min=None, _max=None, n=1):
        """Returns actual values.

        :param length: will return last 'length' values.
        :type length: int
        :param _min: Index of lower limit.
        :type _min: int
        :param _max: Index of upper limit.
        :type _max: int
        :param n: Will only return every nth value, defaults to 1
        :type n: int, optional
        :return: Values in specified range.
        :rtype: numpy.array
        """
        if length is not None:
            _min = self.size - length

        # NOTE: n cannot be determined internally as it has to match for multiple instances that may have different size (e.g. if one device is initialized later)
        # Solution A
        # perfect indices for smooth update but not very efficient
        # return self.data[np.concatenate((np.arange(x0, x0+2*n-np.remainder(x0+2*n, n)), np.arange(x0+2*n-np.remainder(x0+2*n, n), self.size-n, n), np.arange(self.size-n, self.size)))]
        # Solution B
        # length: typically lenght of array to return, relative to end of array. E.g. lenght relative to a certain point in time.
        # n: use every nth data point
        # simple and works but causes slow update when n is large
        # display update can be jumpy when large n is combined with short time period. This is very rare and can be avoided by slightly higher number of points
        if _min is not None and _max is not None:
            return self.data[_min:_max][::n]
        if _min is not None:
            return self.data[_min-np.remainder(_min, n):self.size][::n]
        return self.data[:self.size][::n] # returns everything
        # Solution C
        # pyqtgraph has build in downsampling, however in automatic mode it does not save as much performance.
        # if n is increased to get similar performance than the code above, the curves are flickering as the displayed points can change (roll) while new data comes in.

def parameterDict(name=None, value=None, default=None, _min=None, _max=None, toolTip=None, items=None, tree=None, widgetType=None, advanced=False, header=None,
                    widget=None, event=None, internal=False, attr=None, indicator=False, instantUpdate=True):
    """Provides default values for all properties of a parameter.
    See :class:`~Esibd.EsibdCore.Parameter` for definitions.
    """
    return {Parameter.NAME : name, Parameter.VALUE : value, Parameter.DEFAULT : default if default is not None else value, Parameter.MIN : _min, Parameter.MAX : _max, Parameter.ADVANCED : advanced,
            Parameter.HEADER : header, Parameter.TOOLTIP : toolTip, Parameter.ITEMS : items, Parameter.TREE : tree, Parameter.WIDGETTYPE : widgetType,
            Parameter.WIDGET : widget, Parameter.EVENT : event, Parameter.INTERNAL : internal, Parameter.ATTR : attr, Parameter.INDICATOR : indicator, Parameter.INSTANTUPDATE : instantUpdate}

class Parameter():
    """Parameters are used by settings and channels. They take care
    of providing consistent user controls, linking events, input validation,
    context menus, and restoring values.
    Typically they are not initialized directly but via a :meth:`~Esibd.EsibdCore.parameterDict`
    from which settings and channels take the relevant information.

    name : str
        The parameter name.
    value : var
        The default value of the parameter in any supported type.
    min : float
        Minimum limit for numerical properties.
    max : float
        Maximum limit for numerical properties.
    toolTip : str
        Tooltip used to describe the parameter.
    items : [str]
        List of options for parameters with a combobox.
    widgetType : :meth:`~Esibd.EsibdCore.Parameter.TYPE`
        They type determines which widget is used to represent the parameter in the user interface.
    advanced : bool
        If True, parameter will only be visible in advanced mode.
        Only applies to channel parameters.
    header : str
        Header used for the corresponding column in list of channels.
        The parameter name is used if not specified.
        Only applies to channel parameters.
    widget : QWidget
        A custom widget that will be used instead of the automatically provided one.
    event : method
        A function that will be triggered when the parameter value changes.
    internal : bool
        Set to True to save parameter value in the registry (using QSetting)
        instead of configuration files. This can help to reduce clutter in
        configuration files and restore essential parameters even if
        configuration files get moved or lost.
    attr : str
        Allows direct access to the parameter. Only applies to channel and settings parameters.
            E.g. The *color* parameter of a channel specifies *attr=’color’*
            and can thus be accessed via *channel.color*.

            E.g. The *Session path* parameter in :class:`~Esibd.EsibdPlugins.Settings` specifies
            *attr=’sessionPath’* and can thus be accessed via
            *Settings.sessionPath*.

            E.g. The *interval* parameter of a device specifies
            *attr=’interval’* and can thus be accessed via *device.interval*.

            E.g. The *notes* parameter of a scan specifies *attr=’notes’* and
            can thus be accessed via *scan.notes*.
    indicator : bool
        Indicators cannot be edited by the user.
    instantUpdate : bool
        By default, events are triggered as soon as the value changes. If set
        to False, certain events will only be triggered if editing is
        finished by the *enter* key or if the widget loses focus.
    print : method
        Reference to :meth:`~Esibd.EsibdPlugins.Plugin.print`.
    """

    # general keys
    NAME        = 'Name'
    ATTR        = 'Attribute'
    ADVANCED    = 'Advanced'
    HEADER      = 'Header'
    VALUE       = 'Value'
    MIN         = 'Min'
    MAX         = 'Max'
    DEFAULT     = 'Default'
    ITEMS       = 'Items'
    TREE        = 'Tree'
    TOOLTIP     = 'Tooltip'
    EVENT       = 'Event'
    INTERNAL    = 'Internal'
    INDICATOR   = 'Indicator'
    INSTANTUPDATE = 'InstantUpdate'
    WIDGETTYPE  = 'WIDGETTYPE'
    WIDGET      = 'WIDGET'

    class TYPE(Enum):
        """Specifies what type of widget should be used to represent the parameter in the user interface."""

        LABEL = 'LABEL'
        """A label that displays information."""
        PATH  = 'PATH'
        """A path to a file or directory."""
        COMBO = 'COMBO'
        """A combobox providing text options."""
        INTCOMBO = 'INTCOMBO'
        """A combobox providing integer options."""
        FLOATCOMBO = 'FLOATCOMBO'
        """A combobox providing floating point options."""
        TEXT  = 'TEXT'
        """An editable text field."""
        COLOR = 'COLOR'
        """A ColorButton that allows to select a color."""
        BOOL  = 'BOOL'
        """A boolean flag, represented by a checkbox."""
        INT   = 'INT'
        """An integer spinbox."""
        FLOAT = 'FLOAT'
        """An floating point spinbox."""
        EXP   = 'EXP'
        """An spinbox with scientific format."""

    def __init__(self, name, _parent=None, default=None, widgetType=None, index=1, items=None, widget=None, internal=False,
                    tree=None, itemWidget=None, toolTip=None, event=None, _min=None, _max=None, indicator=False, instantUpdate=True):
        self._parent = _parent
        self.widgetType = widgetType if widgetType is not None else self.TYPE.LABEL
        self.index = index
        self.print = _parent.print
        self.fullName = name # will contain path of setting in HDF5 file if applicable
        self.name = Path(name).name # only use last element in case its a path
        self.toolTip = toolTip
        self._items = items.split(',') if items is not None else None
        self.tree = tree # None unless the parameter is used for settings
        self.itemWidget = itemWidget # if this is not None, parameter is part of a device channel
        self.widget = widget # None unless widget provided -> can be used to place an interface to a settings anywhere
        self._changedEvent = None
        self._valueChanged = False
        self.event = event # None unless widget provided -> can be used to place an interface to a settings anywhere
        self.extendedEvent = event # allows to add internal events on top of the explicitly assigned ones
        self.internal = internal # internal settings will not be exported to file but saved using QSetting
        self.indicator = indicator
        self.instantUpdate = instantUpdate
        self.rowHeight = QLineEdit().sizeHint().height() - 4
        self.check = None
        self.min = _min
        self.max = _max
        self.button = None
        self.spin = None
        self._default = None
        if default is not None:
            self.default = default
        if self.tree is None: # if this is part of a QTreeWidget, applyWidget() should be called after this parameter is added to the tree
            self.applyWidget() # call after everything else is initialized but before setting value

    @property
    def value(self):
        """returns value in correct format, based on widgetType"""
        # use widget even for internal settings, should always be synchronized to allow access via both attribute and qSet
        if self.widgetType == self.TYPE.COMBO:
            return self.combo.currentText()
        if self.widgetType == self.TYPE.INTCOMBO:
            return int(self.combo.currentText())
        if self.widgetType == self.TYPE.FLOATCOMBO:
            return float(self.combo.currentText())
        elif self.widgetType == self.TYPE.TEXT:
            return self.line.text()
        elif self.widgetType in [self.TYPE.INT, self.TYPE.FLOAT, self.TYPE.EXP]:
            return self.spin.value()
        elif self.widgetType == self.TYPE.BOOL:
            if self.check is not None:
                return self.check.isChecked()
            else:
                return self.button.isChecked()
        elif self.widgetType == self.TYPE.COLOR:
            return self.colBtn.color().name()
        elif self.widgetType == self.TYPE.LABEL:
            return self.label.text()
        elif self.widgetType == self.TYPE.PATH:
            return Path(self.label.text())

    @value.setter
    def value(self, value):
        if self.internal:
            qSet.setValue(self.fullName, value)
            if self._items is not None:
                qSet.setValue(self.fullName+self.ITEMS, ','.join(self.items))
        if self.widgetType == self.TYPE.BOOL:
            value = value if isinstance(value,(bool, np.bool_)) else value in ['True','true'] # accepts strings (from ini file or qset) and bools
            if self.check is not None:
                self.check.setChecked(value)
            else:
                self.button.setChecked(value)
        elif self.widgetType == self.TYPE.INT:
            self.spin.setValue(int(float(value)))
        elif self.widgetType in [self.TYPE.FLOAT, self.TYPE.EXP]:
            self.spin.setValue(float(value))
        elif self.widgetType == self.TYPE.COLOR:
            self.colBtn.setColor(value, True)
        elif self.widgetType in [self.TYPE.COMBO, self.TYPE.INTCOMBO, self.TYPE.FLOATCOMBO]:
            if value is None:
                i = 0
            else:
                i = self.combo.findText(str(value))
                if i == -1 and self.widgetType is self.TYPE.FLOATCOMBO:
                    i = self.combo.findText(str(int(float(value)))) # try to find int version if float version not found. e.g. 1 instead of 1.0
            if i == -1:
                self.print(f'Value {value} not found for {self.fullName}. Defaulting to {self.combo.itemText(0)}.', PRINT.WARNING)
                self.combo.setCurrentIndex(0)
            else:
                self.combo.setCurrentIndex(i)
        elif self.widgetType == self.TYPE.TEXT:
            self.line.setText(str(value)) # input may be of type Path from pathlib -> needs to be converted to str for display in lineedit
        elif self.widgetType in [self.TYPE.LABEL, self.TYPE.PATH]:
            self.label.setText(str(value))
            self.label.setToolTip(str(value))
            if self._changedEvent is not None:
                self._changedEvent() # emit here as it is not emitted by the label

    @property
    def default(self):
        return self._default
    @default.setter
    def default(self, default): # casting does not change anything if the value is already supplied in the right type, but will convert strings to correct value if needed
        if self.widgetType == self.TYPE.BOOL:
            self._default = default
        elif self.widgetType == self.TYPE.INT:
            self._default = int(default)
        elif self.widgetType in [self.TYPE.FLOAT, self.TYPE.EXP]:
            self._default = float(default)
        else:
            self._default = str(default)

    @property
    def items(self):
        if self.widgetType in [self.TYPE.COMBO, self.TYPE.INTCOMBO, self.TYPE.FLOATCOMBO]:
            return [self.combo.itemText(i) for i in range(self.combo.count())]
        else:
            return ''

    @property
    def changedEvent(self):
        return self._changedEvent
    @changedEvent.setter
    def changedEvent(self, changedEvent):
        self._changedEvent=changedEvent
        if self.widgetType in [self.TYPE.COMBO, self.TYPE.INTCOMBO, self.TYPE.FLOATCOMBO]:
            self.combo.currentIndexChanged.connect(self._changedEvent)
        elif self.widgetType == self.TYPE.TEXT:
            self.line.editingFinished.connect(self._changedEvent)
        elif self.widgetType in [self.TYPE.INT, self.TYPE.FLOAT, self.TYPE.EXP]:
            if self.instantUpdate:
                self.spin.valueChanged.connect(self._changedEvent) # by default trigger events on every change, not matter if through user interface or software
            else:
                self.spin.valueChanged.connect(self.setValueChanged)
                self.spin.editingFinished.connect(self._changedEvent) # trigger events only when changed via user interface
        elif self.widgetType == self.TYPE.BOOL:
            if isinstance(self.check, QCheckBox):
                self.check.stateChanged.connect(self._changedEvent)
            elif isinstance(self.check, QAction):
                self.check.toggled.connect(self._changedEvent)
            else: #isinstance(self.check, QToolButton)
                self.check.clicked.connect(self._changedEvent)
        elif self.widgetType == self.TYPE.COLOR:
            self.colBtn.sigColorChanged.connect(self._changedEvent)
        elif self.widgetType in [self.TYPE.LABEL, self.TYPE.PATH]:
            pass # self.label.changeEvent.connect(self._changedEvent) # no change events for labels

    def setValueChanged(self):
        self._valueChanged = True

    def setToDefault(self):
        if self.widgetType in [self.TYPE.COMBO, self.TYPE.INTCOMBO, self.TYPE.FLOATCOMBO]:
            i = self.combo.findText(str(self.default))
            if i == -1: # add default entry in case it has been deleted
                self.print(f'Adding Default value {self.default} for {self.fullName}.', PRINT.WARNING)
                self.addItem(self.default)
        self.value = self.default

    def makeDefault(self):
        self.default = self.value

    def applyWidget(self):
        """create UI widget depending on widget type
        Linking dedicated widget if provided
        """
        if self.widgetType in [self.TYPE.COMBO, self.TYPE.INTCOMBO, self.TYPE.FLOATCOMBO]:
            self.combo = QComboBox() if self.widget is None else self.widget
            if self.widget is not None: # potentially reuse widget with old data!
                self.combo.clear()
            self.combo.wheelEvent = lambda event: None # disable wheel event to avoid accidental change of setting
            for i in [x.strip(' ') for x in self._items]:
                self.combo.insertItem(self.combo.count(), i)
            self.combo.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self.combo.customContextMenuRequested.connect(self.initComboContextMenu)
        elif self.widgetType == self.TYPE.TEXT:
            self.line = self.widget if self.widget is not None else QLineEdit()
            self.line.setFrame(False)
        elif self.widgetType in [self.TYPE.INT, self.TYPE.FLOAT, self.TYPE.EXP]:
            if self.widget is None:
                if self.widgetType == self.TYPE.INT:
                    self.spin = QLabviewSpinBox(indicator=self.indicator)
                elif self.widgetType == self.TYPE.FLOAT:
                    self.spin = QLabviewDoubleSpinBox(indicator=self.indicator)
                else: # self.TYPE.EXP
                    self.spin = QLabviewSciSpinBox(indicator=self.indicator)
                self.spin.lineEdit().setObjectName(self.fullName)
            else:
                self.spin = self.widget
        elif self.widgetType == self.TYPE.BOOL:
            if self.widget is None:
                if self.indicator:
                    self.check = LedIndicator()
                    self.check.setMinimumSize(self.rowHeight-10, self.rowHeight-10)
                    self.check.setMaximumSize(self.rowHeight-10, self.rowHeight-10)
                else:
                    self.check = CheckBox()
            else:
                self.check = self.widget
            self.setEnabled(not self.indicator)
        elif self.widgetType == self.TYPE.COLOR:
            self.colBtn = pg.ColorButton() if self.widget is None else self.widget
        elif self.widgetType in [self.TYPE.LABEL, self.TYPE.PATH]:
            self.label = QLabel() if self.widget is None else self.widget

        if self.spin is not None: # apply limits # no limits by default to avoid unpredictable behaviour.
            if self.min is not None:
                self.spin.setMinimum(self.min)
            if self.max is not None:
                self.spin.setMaximum(self.max)

        if self.tree is not None:
            if self.itemWidget is None:
                if self.widget is None: # widget has already been provided and added to the GUI independently
                    self.tree.setItemWidget(self, 1, self.getWidget())
            else:
                self.tree.setItemWidget(self.itemWidget, self.index, self.containerize(self.getWidget())) # container required to hide widgets reliable
        if self.extendedEvent is not None:
            self.changedEvent = self.extendedEvent
        elif self.event is not None:
            self.changedEvent = self.event

        self.getWidget().setToolTip(self.toolTip)
        self.getWidget().setMinimumHeight(self.rowHeight) # always keep entire row at consistent height
        self.getWidget().setMaximumHeight(self.rowHeight)
        self.getWidget().setObjectName(self.fullName)

    def containerize(self, widget):
        # just hiding widget using setVisible(False) is not reliable due to bug https://bugreports.qt.io/browse/QTBUG-13522
        # use a wrapping container as a workaround https://stackoverflow.com/questions/71707347/how-to-keep-qwidgets-in-qtreewidget-hidden-during-resize?noredirect=1#comment126731693_71707347
        container = QWidget()
        containerLayout = QGridLayout(container)
        containerLayout.setContentsMargins(0, 0, 0, 0)
        widget.setSizePolicy(QSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.MinimumExpanding))
        widget.container = container # used to have proper backgound color independent of widget visibility
        containerLayout.addWidget(widget)
        return container

    def getWidget(self):
        if self.widgetType in [self.TYPE.COMBO, self.TYPE.INTCOMBO, self.TYPE.FLOATCOMBO]:
            return self.combo
        elif self.widgetType == self.TYPE.TEXT:
            return self.line
        elif self.widgetType in [self.TYPE.INT, self.TYPE.FLOAT, self.TYPE.EXP]:
            return self.spin
        elif self.widgetType == self.TYPE.BOOL:
            return self.check if self.check is not None else self.button
        elif self.widgetType == self.TYPE.COLOR:
            return self.colBtn
        elif self.widgetType in [self.TYPE.LABEL, self.TYPE.PATH]:
            return self.label

    def setEnabled(self, enabled):
        if hasattr(self.getWidget(), 'setReadOnly'):
            self.getWidget().setReadOnly(not enabled)
        else:
            self.getWidget().setEnabled(enabled)

    def addItem(self, value):
        # should only be called for WIDGETCOMBO settings
        if self.validateComboInput(value):
            if self.combo.findText(str(value)) == -1: # only add item if not already in list
                self.combo.insertItem(self.combo.count(), str(value))
                self.value = value

    def removeCurrentItem(self):
        if len(self.items) > 1:
            self.combo.removeItem(self.combo.currentIndex())
        else:
            self.print('List cannot be empty.', PRINT.WARNING)

    def editCurrentItem(self, value):
        if self.validateComboInput(value):
            self.combo.setItemText(self.combo.currentIndex(), str(value))

    def validateComboInput(self, value):
        """Validates input for comboboxes"""
        if self.widgetType == self.TYPE.COMBO:
            return True
        elif self.widgetType == self.TYPE.INTCOMBO:
            try:
                int(value)
                return True
            except ValueError:
                self.print(f'{value} is not an integer!', PRINT.ERROR)
        elif self.widgetType == self.TYPE.FLOATCOMBO:
            try:
                float(value)
                return True
            except ValueError:
                self.print(f'{value} is not a float!', PRINT.ERROR)
        return False

    def equals(self, value):
        """Returns True if a representation of value matches the value of the parameter"""
        # if self.internal:
        #     return self.value == value
        if self.widgetType == self.TYPE.BOOL:
            return self.value == value if isinstance(value,(bool, np.bool_)) else self.value == (value in ['True','true']) # accepts strings (from ini file or qset) and bools
        elif self.widgetType in [self.TYPE.INT, self.TYPE.INTCOMBO]:
            return self.value == int(value)
        elif self.widgetType in [self.TYPE.FLOAT, self.TYPE.FLOATCOMBO]:
            return self.value == float(value)
        elif self.widgetType == self.TYPE.EXP:
            return f'{self.value:.2e}' == f'{value:.2e}'
        elif self.widgetType == self.TYPE.COLOR:
            return self.value == value.name() if isinstance(value, QColor) else self.value == value
        elif self.widgetType in [self.TYPE.TEXT, self.TYPE.LABEL, self.TYPE.PATH]:
            return self.value == str(value)# input may be of type Path from pathlib -> needs to be converted to str for display in lineedit
        else:
            return self.value == value

    def initComboContextMenu(self, pos):
        self._parent.initSettingsContextMenuBase(self, self.combo.mapToGlobal(pos))

#################################### Settings Item ################################################

class Setting(QTreeWidgetItem, Parameter):
    """Parameter to be used as general settings with dedicated UI controls instead of being embedded in a device channel."""
    def __init__(self, value=None, parentItem=None,**kwargs):
        # use keyword arguments rather than positional to avoid issues with multiple inheritace
        # https://stackoverflow.com/questions/9575409/calling-parent-class-init-with-multiple-inheritance-whats-the-right-way
        super().__init__(**kwargs)
        if self.tree is not None: # some settings may be attached to dedicated controls
            self.parentItem = parentItem
            self.parentItem.addChild(self) # has to be added to parent before widgets can be added!
            self.setData(0, Qt.ItemDataRole.DisplayRole, self.name)
            self.setToolTip(0, self.toolTip)
            self.extendedEvent = self.settingEvent # assign before applyWidget()
            self.applyWidget()
        if self.internal:
            if self.widget is not None:
                self.extendedEvent = self.settingEvent # assign before applyWidget()
                if self._items is not None:
                    self._items = qSet.value(self.fullName+self.ITEMS).split(',') if qSet.value(self.fullName+self.ITEMS) is not None else self._items
                self.applyWidget()
            self.value = qSet.value(self.fullName, self.default) # trigger assignment to widget
        else:
            self.value = value # use setter to distinguish data types based on other fields

    def setWidget(self, widget):
        """Allows to change to custom widget after initialization. E.g. to move a setting to a more logical position outside the Settings tree."""
        v = self.value
        self.widget = widget
        self.applyWidget() # will overwrite ToolTip -> restore if value specific
        self._parent.loading = True # only change widget, do not trigger event when value is restored
        self.value = v
        self._parent.loading = False
        self.parentItem.removeChild(self) # remove old entry from tree

    def resetWidget(self):
        """Returns widget back to the Settigs tree."""
        v = self.value
        self.widget = None
        self.parentItem.addChild(self)
        self.applyWidget()
        self._parent.loading = True # only change widget, do not trigger event when value is restored
        self.value = v
        self._parent.loading = False

    def settingEvent(self):
        """Executes internal validation based on setting type.
        Saves parameters to file or qSet to make sure they can be restored even after a crash.
        Finally executes setting specific event if applicable."""
        if not self._parent.loading:
            if self.widgetType == self.TYPE.PATH:
                path = Path(self.value) # validate path and use default if not exists
                if not path.exists():
                    default = Path(self.default)
                    if path == default:
                        self.print(f'Creating {default.as_posix()}.')
                    else:
                        self.print(f'Could not find path {path.as_posix()}. Defaulting to {default.as_posix()}.', PRINT.WARNING)
                    default.mkdir(parents=True, exist_ok=True)
                    self.value = default
            elif not self.instantUpdate and self.widgetType in [self.TYPE.INT, self.TYPE.FLOAT, self.TYPE.EXP]:
                if self._valueChanged:
                    self._valueChanged = False # reset and continue event loop
                else:
                    return # ignore editingFinished if content has not changed
            if self.internal:
                qSet.setValue(self.fullName, self.value)
                if self._items is not None:
                    qSet.setValue(self.fullName+self.ITEMS, ','.join(self.items))
            else: # save non internal parameters to file
                self._parent.saveSettings(default=True)
            if self.event is not None: # call explicitly assigned event if applicable without causing recursion issue
                self.event()

########################## Generic channel ########################################################

class MetaChannel():
    """Manages metadata associated with a channel by a :class:`~Esibd.EsibdPlugins.Scan` or :class:`~Esibd.EsibdPlugins.LiveDisplay`.
    Allows to restore data even if corresponding channels do not exist anymore.

    name : str
        The scan channel name is usualy the same as the name of the corresponding
        :class:`~Esibd.EsibdCore.Channel`.
    data : numpy.array
        Scan data is saved and restored automatically.
        Each scan is free to define its data with arbitrary dimensions.
    initial : var
        Initial value. Used to restore all conditions after scan has completed.
    background : numpy.array
        If used, has to be of same dimension as data.
    unit : str
        The channel unit.
    channel: :class:`~Esibd.EsibdCore.PluginManager`
        The actual channel, if it exists.
    """

    def __init__(self, name, data, initial=None, background=None, unit='', channel=None):
        """

        """
        self.name = name
        self.data = data
        self.initial = initial
        self.background = background
        self.unit = unit
        self.channel = channel # use getChannelByName(name, inout=INOUT.OUT) as argument if applicable

class Channel(QTreeWidgetItem):
    """A :class:`~Esibd.EsibdCore.Channel` represents a virtual or real parameter and manages all data and
    metadata related to that parameter. Each :class:`~Esibd.EsibdPlugins.Device` can only have one
    type of :class:`~Esibd.EsibdCore.Channel`, but channels have dynamic interfaces that allow to
    account for differences in the physical backend."""

    class SignalCommunicate(QObject):
        updateValueSignal = pyqtSignal(float)

    device : any # Device, avoid circular import
    """The :class:`~Esibd.EsibdPlugins.Device` containing this channel."""
    print : callable
    """Reference to :meth:`~Esibd.EsibdPlugins.Plugin.print`."""
    tree : QTreeWidget
    """TreeWidget containing the channel widgets."""
    inout : INOUT
    """Reference to :meth:`~Esibd.EsibdPlugins.Device.inout`."""
    plotCurve : pyqtgraph.PlotCurveItem
    """The plotCurve in the corresponding :class:`~Esibd.EsibdPlugins.LiveDisplay`."""
    lastAppliedValue : any
    """Reference to last value. Allows to decide if hardware update is required."""
    parameters : Parameter
    """List of channel parameters."""
    displayedParameters : [str]
    """List of parameters that determines which parameters are shown in the
       user interface and in what order. Compare :meth:`~Esibd.EsibdCore.Channel.insertDisplayedParameter`.
       If your custom parameter is not in this list it will not be visible in the user interface."""
    values : DynamicNp
    """The history of values shown in the :class:`~Esibd.EsibdPlugins.LiveDisplay`.
       Use :meth:`~Esibd.EsibdCore.Channel.getValues` to get a plain numpy.array."""
    backgrounds : DynamicNp
    """List of backgrounds. Only defined if corresponding device uses backgrounds."""

    def __init__(self, device, tree):
        super().__init__() # need to init without tree, otherwise channels will always appended to the end when trying to change order using insertTopLevelItem
        self.device = device
        self.print = device.print
        self.tree = tree # may be None for internal default channels
        self.inout = device.inout
        self.plotCurve = None
        self.signalComm = self.SignalCommunicate()
        self.signalComm.updateValueSignal.connect(self.updateValueParallel)
        self.lastAppliedValue = None # keep track of last value to identify what has changed
        self.parameters = []
        self.displayedParameters = []
        self.values = DynamicNp(max_size=self.device.maxDataPoints)
        if self.device.useBackgrounds:
            self.backgrounds = DynamicNp(max_size=self.device.maxDataPoints) # array of background history. managed by instrument manager to keep timing synchronous

        # self.value = None # will be replaced by wrapper
        # generate property for direct access of parameter values
        # note: this assigns properties directly to class and only works as it uses a method that is specific to the current instance
        for name, default in self.getSortedDefaultChannel().items():
            if Parameter.ATTR in default and default[Parameter.ATTR] is not None:
                setattr(self.__class__, default[Parameter.ATTR], makeWrapper(name))

        for i, (name, default) in enumerate(self.getSortedDefaultChannel().items()):
            self.parameters.append(Parameter(_parent=self, name=name, widgetType=default[Parameter.WIDGETTYPE],
                                                    items=default[Parameter.ITEMS] if Parameter.ITEMS in default else None,
                                                    _min=default[Parameter.MIN] if Parameter.MIN in default else None,
                                                    _max=default[Parameter.MAX] if Parameter.MAX in default else None,
                                                    toolTip=default[Parameter.TOOLTIP] if Parameter.TOOLTIP in default else None,
                                                    internal=default[Parameter.INTERNAL] if Parameter.INTERNAL in default else False,
                                                    indicator=default[Parameter.INDICATOR] if Parameter.INDICATOR in default else False,
                                                    instantUpdate=default[Parameter.INSTANTUPDATE] if Parameter.INSTANTUPDATE in default else True,
                                                    itemWidget=self, index=i, tree=self.tree,
                                                    event=default[Parameter.EVENT] if Parameter.EVENT in default else None))
    HEADER      = 'HEADER'
    SELECT      = 'Select'
    ENABLED     = 'Enabled'
    NAME        = 'Name'
    VALUE       = 'Value'
    BACKGROUND  = 'Background'
    EQUATION    = 'Equation'
    DISPLAY     = 'Display'
    ACTIVE      = 'Active'
    REAL        = 'Real'
    LINEWIDTH   = 'Linewidth'
    COLOR       = 'Color'
    MIN         = 'Min'
    MAX         = 'Max'
    OPTIMIZE    = 'Optimize'

    def getDefaultChannel(self):
        """ Defines parameter(s) of the default channel.
        This is also use to assign widgetTypes and if settings are visible outside of advanced mode.
        See :meth:`~Esibd.EsibdCore.parameterDict`.
        If parameters do not exist in the settings file, the default parameter will be added.
        Overwrite in dependent classes as needed.
        """
        channel = {}
        channel[self.SELECT  ] = parameterDict(value=False, widgetType=Parameter.TYPE.BOOL, advanced=True,
                                    toolTip='Plots data as a function of selected channel.', event=lambda : self.device.channelSelection(channel = self) , attr='select')
        channel[self.ENABLED] = parameterDict(value=True, widgetType=Parameter.TYPE.BOOL, advanced=False,
                                    header= 'E', toolTip='If enabled, channel will communicate with the device.',
                                    event=self.enabledChanged, attr='enabled')
        channel[self.NAME    ] = parameterDict(value=f'{self.device.name}_parameter', widgetType=Parameter.TYPE.TEXT, advanced=False, attr='name')
        channel[self.VALUE   ] = parameterDict(value=0, widgetType=Parameter.TYPE.FLOAT, advanced=False,
                                    header='Unit', attr='value')
        if self.inout == INOUT.IN:
            channel[self.VALUE][Parameter.EVENT] = lambda : self.device.pluginManager.DeviceManager.globalUpdate(inout=self.inout)
        channel[self.EQUATION] = parameterDict(value='', widgetType=Parameter.TYPE.TEXT, advanced=True, attr='equation',
                                    event=self.equationChanged)
        channel[self.DISPLAY   ] = parameterDict(value=True, widgetType=Parameter.TYPE.BOOL, advanced=False,
                                    header='D', toolTip='Display channel history.',
                                    event=self.updateDisplay, attr='display')
        channel[self.ACTIVE  ] = parameterDict(value=True, widgetType=Parameter.TYPE.BOOL, advanced=True,
                                    header='A', toolTip='If not active, value will be determined from equation.',
                                    event=self.activeChanged, attr='active')
        channel[self.REAL    ] = parameterDict(value=True, widgetType=Parameter.TYPE.BOOL, advanced=True,
                                    header='R', toolTip='Set to real for physically exiting channels.',
                                    event=self.realChanged, attr='real')
        channel[self.LINEWIDTH  ] = parameterDict(value='4', widgetType=Parameter.TYPE.INTCOMBO, advanced=True,
                                        items='2, 4, 6, 8, 10', attr='linewidth', event=self.updateDisplay)
        # NOTE: avoid using middle gray colors, as the bitwise NOT which is used for the caret color has very poor contrast
        # https://stackoverflow.com/questions/55877769/qt-5-8-qtextedit-text-cursor-color-wont-change
        channel[self.COLOR   ] = parameterDict(value='#ffffff', widgetType=Parameter.TYPE.COLOR, advanced=True,
                                    event=self.updateColor, attr='color')
        if self.inout == INOUT.IN:
            channel[self.MIN     ] = parameterDict(value=-50, widgetType=Parameter.TYPE.FLOAT, advanced=True,
                                    event=self.updateMin, attr='min')
            channel[self.MAX     ] = parameterDict(value=+50, widgetType=Parameter.TYPE.FLOAT, advanced=True,
                                    event= self.updateMax, attr='max')
            channel[self.OPTIMIZE] = parameterDict(value=False, widgetType=Parameter.TYPE.BOOL, advanced=False,
                                    header='O', toolTip='Selected channels will be optimized using GA', attr='optimize')
        else:
            channel[self.VALUE][Parameter.INDICATOR] = True
            channel[self.NAME][Parameter.EVENT] = self.updateDisplay
            # channel[self.ENABLED][Parameter.EVENT] = self.enabledChanged
            if self.device.useBackgrounds:
                channel[self.BACKGROUND] = parameterDict(value=0, widgetType=Parameter.TYPE.FLOAT, advanced=False,
                                    header='BG    ', attr='background')
        return channel

    def getSortedDefaultChannel(self):
        """Returns default channel sorted in the order defined by :attr:`~Esibd.EsibdCore.Channel.displayedParameters`."""
        self.setDisplayedParameters()
        return {k: self.getDefaultChannel()[k] for k in self.displayedParameters}

    def insertDisplayedParameter(self, parameter, before):
        """Inserts your custom parameter before an existing parameter in :attr:`~Esibd.EsibdCore.Channel.displayedParameters`.

        :param parameter: The new parameter to insert.
        :type parameter: :class:`~Esibd.EsibdCore.Parameter`
        :param before: The existing parameter before which the new one will be placed.
        :type before: :class:`~Esibd.EsibdCore.Parameter`
        """
        self.displayedParameters.insert(self.displayedParameters.index(before), parameter)

    def setDisplayedParameters(self):
        """Used to determine which parameters to use and in what order.
        Extend using insertParameter to add more parameters"""
        self.displayedParameters = [self.SELECT, self.ENABLED, self.NAME, self.VALUE, self.EQUATION, self.DISPLAY, self.ACTIVE, self.REAL, self.LINEWIDTH, self.COLOR]
        if self.inout == INOUT.IN:
            self.insertDisplayedParameter(self.MIN, before=self.EQUATION)
            self.insertDisplayedParameter(self.MAX, before=self.EQUATION)
            self.insertDisplayedParameter(self.OPTIMIZE, before=self.DISPLAY)
        if self.device.useBackgrounds:
            self.insertDisplayedParameter(self.BACKGROUND, before=self.DISPLAY)

    def tempParameters(self):
        """List of parameters, such as live signal or status, that will not be saved and restored."""
        if self.inout == INOUT.OUT:
            if self.device.useBackgrounds:
                return [self.VALUE, self.BACKGROUND]
            else:
                return [self.VALUE]
        else:
            return []

    def getParameterByName(self, name):
        p = next((p for p in self.parameters if p.name.strip().lower() == name.strip().lower()), None)
        if p is None:
            self.print(f'Could not find parameter {name}.', PRINT.WARNING)
        return p

    def asDict(self):
        """Returns a dictionary containing all channel parameters and their values."""
        d = {}
        for p in self.parameters:
            if p.name not in self.tempParameters():
                d[p.name] = p.value
        return d

    def updateValueParallel(self, value): # used to update from external threads
        self.value = value # pylint: disable=[attribute-defined-outside-init] # attribute defined by makeWrapper

    def activeChanged(self):
        self.updateColor()
        if not self.device.loading:
            self.device.pluginManager.DeviceManager.globalUpdate(inout=self.inout)

    def equationChanged(self):
        if not self.device.loading:
            self.device.pluginManager.DeviceManager.globalUpdate(inout=self.inout)

    def appendValue(self, lenT):
        self.values.add(x=self.value, lenT=lenT)
        if self.device.useBackgrounds:
            self.backgrounds.add(self.background, lenT)

    def getValues(self, length=None, _min=None, _max=None, n=1, subtractBackground=None): # pylint: disable = unused-argument # use consistent arguments for all versions of getValues
        """Returns plain Numpy array of values.
        Note that background subtraction only affects what is displayed, the raw signal and background curves are always retained."""
        if self.device.useBackgrounds and subtractBackground:
            return self.values.get(length=length, _min=_min, _max=_max, n=n) - self.backgrounds.get(_min=_min, _max=_max, n=n)
        else:
            return self.values.get(length=length, _min=_min, _max=_max, n=n)

    def clearHistory(self, max_size=None): # overwrite as needed, e.g. when keeping history of more than one parametrer
        if self.device.pluginManager.DeviceManager is not None and (self.device.pluginManager.Settings is not None and not self.device.pluginManager.Settings.loading):
            self.values = DynamicNp(max_size=max_size if max_size is not None else 600000/int(self.device.interval)) # 600000 -> only keep last 10 min to save ram unless otherwise specified
        self.clearPlotCurve()
        if self.device.useBackgrounds:
            self.backgrounds = DynamicNp(max_size=max_size)

    def clearPlotCurve(self):
        if self.plotCurve is not None:
            self.plotCurve.clear()
            self.plotCurve = None

    def updateColor(self):
        """Apply new color to all controls."""
        if getDarkMode():
            color = QColor(self.color).darker(150) if self.active else QColor(self.color).darker(200) # indicate passive channels by darker color
        else:
            color = QColor(self.color) if self.active else QColor(self.color).darker(115) # indicate passive channels by darker color
        qb = QBrush(color)
        for i in range(len(self.parameters)+1): # use highest index
            self.setBackground(i, qb) # use correct color even when widgets are hidden
        for p in self.parameters:
            w = p.getWidget()
            w.container.setStyleSheet(f'background-color: {color.name()};')
            if isinstance(w, QToolButton):
                w.setStyleSheet(f'''QToolButton {{background-color: {color.name()}}}
                                QToolButton:checked {{background-color: {color.darker(150 if getDarkMode() else 120).name()};
                                border-style: inset; border-width: 2px; border-color: 'gray';}}''')
            elif isinstance(w, QComboBox):
                pass
            else:
                w.setStyleSheet(f'background-color: {color.name()}; color:{colors.fg}; margin:0px')
        self.updateDisplay()
        return color

    def realChanged(self):
        self.getParameterByName(self.ENABLED).getWidget().setVisible(self.real)
        if not self.device.loading:
            self.device.pluginManager.DeviceManager.globalUpdate(inout=self.inout)

    def enabledChanged(self):
        """Extend as needed. Already linked to enabled checkbox."""
        if not self.device.loading:
            self.device.pluginManager.DeviceManager.globalUpdate(inout=self.inout)
        if not self.enabled and self.plotCurve is not None:
            self.plotCurve = None

    def updateDisplay(self):
        if not self.device.loading:
            self.device.pluginManager.DeviceManager.resetPlot()
            self.device.pluginManager.DeviceManager.updateLivePlot()
            self.device.pluginManager.DeviceManager.updateStaticPlot()

    def initGUI(self, item):
        """call after itemWidget has been added to treeWidget
            itemWidget needs parent for all graphics operations
        """
        for p in self.parameters:
            p.applyWidget()
        for name, default in self.getSortedDefaultChannel().items():
            # add default value if not found in file. Will be saved to file later.
            if name in item and not name in self.tempParameters():
                self.getParameterByName(name).value = item[name]
            else:
                self.getParameterByName(name).value = default[self.VALUE]
                if not name in self.tempParameters() and not item == {}: # item == {} -> generating default file
                    self.print(f'Added missing parameter {name} to channel {self.name} using default value {default[self.VALUE]}.')

        line = self.getParameterByName(self.EQUATION).line
        line.setMinimumWidth(200)
        f = line.font()
        f.setPointSize(8)
        line.setFont(f)

        select = self.getParameterByName(self.SELECT)
        v = select.value
        select.widget = ToolButton() # hard to spot checked QCheckBox. QPushButton is too wide -> overwrite internal widget to QToolButton
        select.applyWidget()
        select.check.setMaximumHeight(select.rowHeight) # default too high
        select.check.setText(self.SELECT.title())
        select.check.setMinimumWidth(5)
        select.check.setCheckable(True)
        select.value = v

        self.updateColor()
        self.realChanged()
        if self.inout == INOUT.IN:
            self.updateMin()
            self.updateMax()

    def updateMin(self):
        self.getParameterByName(self.VALUE).spin.setMinimum(self.min)

    def updateMax(self):
        self.getParameterByName(self.VALUE).spin.setMaximum(self.max)

#################################### Other Custom Widgets #########################################

class QLabviewSpinBox(QSpinBox):
    """Implements handling of arrow key events based on curser position as in LabView"""
    def __init__(self, parent=None, indicator=False):
        super().__init__(parent)
        self.indicator = indicator
        self.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.setRange(np.iinfo(np.int32).min, np.iinfo(np.int32).max) # limit explicitly if needed, this seems more useful than the [0, 100] default range
        if indicator:
            self.setReadOnly(True)
            self.preciseValue = 0

    def contextMenuEvent(self, event):
        if self.indicator:
            event.ignore()
        else:
            return super().contextMenuEvent(event)

    def wheelEvent(self, event):
        event.ignore()

    def stepBy(self, step):
        """Handles stepping value depending con caret position."""
        text=self.lineEdit().text()
        cur = self.lineEdit().cursorPosition()
        pos = len(text)-cur
        if cur==0 and not '-' in text: # left of number
            pos= len(text)-1
        if cur<=1 and '-' in text: # left of number
            pos= len(text)-2
        val=self.value()+10**pos*step # use step for sign
        self.setValue(val)
        # keep cursor position fixed relative to .
        newText = self.lineEdit().text()
        if len(newText) > len(text):
            if cur == 0 and not '-' in text:
                self.lineEdit().setCursorPosition(2)
            elif cur <= 1 and '-' in text:
                self.lineEdit().setCursorPosition(3)
            else:
                self.lineEdit().setCursorPosition(cur + 1)
        elif len(newText) < len(text):
            self.lineEdit().setCursorPosition(max(cur - 1,0))

class QLabviewDoubleSpinBox(QDoubleSpinBox):
    """Implements handling of arrow key events based on curser position as in LabView"""
    def __init__(self, parent=None, indicator=False):
        super().__init__(parent)
        self.indicator = indicator
        self.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.setRange(-np.inf, np.inf) # limit explicitly if needed, this seems more useful than the [0, 100] default range
        if indicator:
            self.setReadOnly(True)
            self.preciseValue = 0

    def contextMenuEvent(self, event):
        if self.indicator:
            event.ignore()
        else:
            return super().contextMenuEvent(event)

    def wheelEvent(self, event):
        event.ignore()

    def stepBy(self, step):
        """Handles stepping value depending con caret position. This implementation works with negative numbers and of number of digets before the dot."""
        text = self.lineEdit().text()
        cur = self.lineEdit().cursorPosition()
        dig = len(text.strip('-').split('.')[0])
        if cur <= 1 or cur <= 2 and '-' in text:
            pos = dig - 1
        elif cur < dig and not '-' in text:
            pos = dig - cur
        elif cur < dig + 1 and '-' in text:
            pos = dig - cur + 1
        elif cur == dig and not '-' in text or cur == dig + 1 and '-' in text:
            pos = 0
        elif cur == dig + 1 and not '-' in text or cur == dig + 2 and '-' in text:
            pos = -1
        else:
            pos = dig-cur + 2 if '-' in text else dig-cur + 1
        val=self.value()+10**pos*step # use step for sign
        self.setValue(val)
        # keep cursor position fixed relative to .
        newText = self.lineEdit().text()
        if len(newText) > len(text):
            if cur == 0 and not '-' in text:
                self.lineEdit().setCursorPosition(2)
            elif cur <= 1 and '-' in text:
                self.lineEdit().setCursorPosition(3)
            else:
                self.lineEdit().setCursorPosition(cur + 1)
        elif len(newText) < len(text):
            self.lineEdit().setCursorPosition(max(cur - 1,0))

class QLabviewSciSpinBox(QLabviewDoubleSpinBox):
    """Spinbox for scientific notation"""
    # inspired by https://gist.github.com/jdreaver/0be2e44981159d0854f5
    # Regular expression to find floats. Match groups are the whole string, the
    # whole coefficient, the decimal part of the coefficient, and the exponent part.

    class FloatValidator(QValidator):
        """Validates input for correct scientific notation."""
        _float_re = re.compile(r'(([+-]?\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?)')

        def valid_float_string(self, string):
            match = self._float_re.search(string)
            # print(string, match.groups()[0], match.groups()[0] == string, match)
            return match.groups()[0] == string if match else False

        def validate(self, string, position): # -> typing.Tuple[State, str, int]:
            if self.valid_float_string(string):
                return self.State.Acceptable, string, position
            if string == '' or string[position-1] in 'e.-+':
                return self.State.Intermediate, string, position
            return self.State.Invalid, string, position

        def fixup(self, text):
            match = self._float_re.search(text)
            return match.groups()[0] if match else ''

    def __init__(self, parent=None, indicator=False):
        super().__init__(parent, indicator)
        self.validator = self.FloatValidator()
        self.setDecimals(1000) # need this to allow internal handling of data as floats 1E-20 = 0.0000000000000000001

    def validate(self, text, position):
        return self.validator.validate(text, position)

    def fixup(self, text):
        return self.validator.fixup(text)

    def valueFromText(self, text):
        return float(text)

    def textFromValue(self, value):
        return f'{value:.2E}'.replace('E-0', 'E-')

    def stepBy(self, step):
        text = self.lineEdit().text()
        cur = self.lineEdit().cursorPosition()
        v, p = text.split('E')
        sign = '-' if p[0] == '-' else ''
        pot = ''.join([pp for pp in p[1:].lstrip('0')])
        pot = '0' if pot == '' else pot
        if cur <= 2 and not '-' in v or cur <= 3 and '-' in v:
            pos = 0
        else: # right of dot
            pos = 3-cur if '-' in v else 2-cur
        self.setValue(float(str(float(v)+10**pos*step) + 'E' + sign + pot))
        # keep cursor position fixed relative to .
        newText = self.lineEdit().text()
        if len(newText) > len(text):
            if cur == 0 and not '-' in v:
                self.lineEdit().setCursorPosition(2)
            elif cur <= 1 and '-' in v:
                self.lineEdit().setCursorPosition(3)
            else:
                self.lineEdit().setCursorPosition(cur + 1)
        elif len(newText) < len(text):
            self.lineEdit().setCursorPosition(max(cur - 1,0))

############################ Third Party Widgets ##################################################

class ControlCursor(Cursor):
    """Extending implementation given here
    https://matplotlib.org/3.5.0/gallery/misc/cursor_demo.html
    cursor only moves when dragged
    """
    def __init__(self, ax, color, **kwargs):
        self.ax = ax
        super().__init__(ax,**kwargs)
        self.lineh.set_color(color)
        self.linev.set_color(color)

    def onmove(self, event):
        pass

    def ondrag(self, event):
        if event.button == MouseButton.LEFT and kb.is_pressed('ctrl') and event.xdata is not None:
            # dir(event)
            super().onmove(event)

    def setPosition(self, x, y):
        """emulated mouse event to set position"""
        [xpix, ypix]=self.ax.transData.transform((x, y))
        event = MouseEvent(name='', canvas=self.ax.figure.canvas, x=xpix, y=ypix, button=MouseButton.LEFT)
        super().onmove(event)

    def getPosition(self):
        return self.linev.get_data()[0][0], self.lineh.get_data()[1][1]

    def updatePosition(self):
        self.setPosition(*self.getPosition())

class RestoreFloatComboBox(QComboBox):

    def __init__(self, parentPlugin, default, items, attr, **kwargs):
        super().__init__(parent=parentPlugin)
        self.parentPlugin = parentPlugin
        self.attr = attr
        self.fullName = f'{self.parentPlugin.name}/{self.attr}'
        self.parentPlugin.pluginManager.Settings.loading = True
        self.setting = Setting(_parent=self.parentPlugin.pluginManager.Settings, name=self.fullName, widgetType=Parameter.TYPE.FLOATCOMBO,
                               value=qSet.value(self.fullName, default), default=default,
                                items=items, widget=self, internal=True, **kwargs)
        self.parentPlugin.pluginManager.Settings.loading = False
        # use keyword rather than positional arguments to avoid issues with multiple inheritace!
        # cannot assign property to istance, only class -> use control directly https://stackoverflow.com/questions/1325673/how-to-add-property-to-a-class-dynamically
        # setattr(self.parentPlugin.__class__, self.attr, makeSettingWrapper(self.setting.fullName, self.parentPlugin.pluginManager.Settings)) # unconsistent results, overlap between instances

class CheckBox(QCheckBox):

    class SignalCommunicate(QObject):
        setValueFromThreadSignal = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self.signalComm = self.SignalCommunicate()
        self.signalComm.setValueFromThreadSignal.connect(self.setValue)

    def setValue(self, value):
        self.setChecked(value)

class ToolButton(QToolButton):

    class SignalCommunicate(QObject):
        setValueFromThreadSignal = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self.signalComm = self.SignalCommunicate()
        self.signalComm.setValueFromThreadSignal.connect(self.setValue)

    def setValue(self, value):
        self.setChecked(value)

class Action(QAction):

    class SignalCommunicate(QObject):
        setValueFromThreadSignal = pyqtSignal(bool)

    def __init__(self, icon, toolTip, parent):
        super().__init__(icon, toolTip, parent)
        self.signalComm = self.SignalCommunicate()
        self.signalComm.setValueFromThreadSignal.connect(self.setValue)

    def setValue(self, value):
        self.setChecked(value)

class StateAction(Action):
    """Extends QActions to show different icons depending on a state.
    Values are restored using QSettings if name is provided."""

    def __init__(self, parentPlugin, toolTipFalse='', iconFalse=None, toolTipTrue='', iconTrue=None, func=None, before=None, attr=None, restore=True):
        super().__init__(iconFalse, toolTipFalse, parentPlugin)
        self.parentPlugin = parentPlugin
        self.iconFalse = iconFalse
        self.toolTipFalse = toolTipFalse
        self.iconTrue = iconTrue if iconTrue is not None else iconFalse
        self.toolTipTrue = toolTipTrue if toolTipTrue != '' else toolTipFalse
        self.setCheckable(True)
        self.toggled.connect(self.updateIcon)
        self.setToolTip(self.toolTipFalse)
        self.attr = attr
        self.fullName = None
        if self.attr is None:
            self.setObjectName(f'{self.parentPlugin.name}/{self.toolTipFalse}')
        else:
            self.fullName = f'{self.parentPlugin.name}/{self.attr}'
            self.setObjectName(self.fullName)
            setattr(self.parentPlugin.__class__, self.attr, makeStateWrapper(self)) # allows to acces state by using attribute from parentPlugin
        if func is not None:
            self.triggered.connect(func) # see comments above about "checked"
        if restore and self.fullName is not None:
            self.state = qSet.value(self.fullName,'false') == 'true'
        else:
            self.state = False # init
        if before is None:
            self.parentPlugin.titleBar.addAction(self)
        else:
            self.parentPlugin.titleBar.insertAction(before, self)

    def toggle(self):
        self.state = not self.state
        return self.state

    @property
    def state(self):
        return self.isChecked()

    @state.setter
    def state(self, state):
        self.setChecked(state)

    def updateIcon(self, checked):
        if self.fullName is not None:
            qSet.setValue(self.fullName, self.state)
        self.setIcon(self.iconTrue if checked else self.iconFalse)
        self.setToolTip(self.toolTipTrue if checked else self.toolTipFalse)

    def setValue(self, value):
        self.state = value

class CompactComboBox(QComboBox):
    """Combobox that stays small while showing full content in dropdown"""
    # from JonB at https://forum.qt.io/post/542594
    def showPopup(self):
        # we like the popup to always show the full contents
        # we only need to do work for this when the combo has had a maximum width specified
        maxWidth = self.maximumWidth()
        # see https://doc.qt.io/qt-5/qwidget.html#maximumWidth-prop for the 16777215 value
        if maxWidth and maxWidth < 16777215:
            self.setPopupMinimumWidthForItems()

        # call the base method now to display the popup
        super().showPopup()

    def setPopupMinimumWidthForItems(self):
        # we like the popup to always show the full contents
        # under Linux/GNOME popups always do this
        # but under Windows they get truncated/ellipsised
        # here we calculate the maximum width among the items
        # and set QComboBox.view() to accomodate this
        # which makes items show full width under Windows
        view = self.view()
        fm = self.fontMetrics()
        maxWidth = max([fm.size(Qt.TextFlag.TextSingleLine, self.itemText(i)).width() for i in range(self.count())]) + 50 # account for scrollbar and margins
        if maxWidth:
            view.setMinimumWidth(maxWidth)

class BetterDockWidget(QDockWidget):
    """Allows to intercept the closeEvent and update title when floating or tabbing."""
    # future desired features:
    # - floating docks should have icons, be able to be maximized/minimized and appear as separate windows of the same software in task bar
    # - float and close buttons should be shown in tab if widget is tabifyed -> hide redundant title bar
    # - some of these are possibe with pyqtgraph but this introduces other limitations and bugs
    # TODO Open bug: https://bugreports.qt.io/browse/QTBUG-118223 see also  https://stackoverflow.com/questions/77340981/how-to-prevent-crash-with-qdockwidget-and-custom-titlebar

    class SignalCommunicate(QObject):
        dockClosingSignal = pyqtSignal()

    def __init__(self, plugin):
        super().__init__(plugin.name)
        self.plugin = plugin
        self.signalComm = self.SignalCommunicate()
        self.signalComm.dockClosingSignal.connect(self.plugin.closeGUI)
        self.setObjectName(f'{self.plugin.pluginType}_{self.plugin.name}') # essential to make restoreState work!
        self.setTitleBarWidget(plugin.titleBar)
        self.topLevelChanged.connect(self.plugin.pluginManager.toggleTitleBarDelayed)
        QTimer.singleShot(500, self.toggleTitleBar) # not sure why needed but needed
        self.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable | QDockWidget.DockWidgetFeature.DockWidgetFloatable) # | QDockWidget.DockWidgetFeature.DockWidgetClosable)
        self.setWidget(self.plugin.mainDisplayWidget)

    def toggleTitleBar(self):
        """Updates titlebar as dock is changing from floating to docked states."""
        # print('toggleTitleBar', self.plugin.name, self.isFloating())
        if self.isFloating(): # dock is floating on its own
            # self.setWindowFlags(Qt.WindowType.Window)
            # self.setTitleBarWidget(None) # restore original to have something to drag dock around / not needed if titlebar passes mouse events correctly
            self.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable | QDockWidget.DockWidgetFeature.DockWidgetFloatable)
            if self.plugin.titleBarLabel is not None:
                self.plugin.titleBarLabel.setText(self.plugin.name)
            if hasattr(self.plugin, 'floatAction'):
                self.plugin.floatAction.state = True
                # self.plugin.floatAction.setVisible(False)
        else: # dock is inside the mainwindow or an external window
            # self.setTitleBarWidget(QWidget()) # hide titlebar by using empty widget # stays hidden no need to call again after initialization
            # self.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
            self.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable | QDockWidget.DockWidgetFeature.DockWidgetFloatable)
            if hasattr(self.plugin, 'floatAction'):
                self.plugin.floatAction.state = False
                # do not allow to float from external windows as this causes GUI instabilities (empty external windows, crash without error, ...)
                # need to allow float to leave external window -> need to make safe / dragging using standard titlebar works but not using custom titlebar
                # self.plugin.floatAction.setVisible(isinstance(self.parent(), QMainWindow))
            if hasattr(self.plugin, 'titleBarLabel') and self.plugin.titleBarLabel is not None:
                self.plugin.titleBarLabel.setText(self.plugin.name if not isinstance(self.parent(), QMainWindow) or len(self.parent().tabifiedDockWidgets(self)) == 0 else '')
            if not isinstance(self.parent(), QMainWindow):
                self.parent().setStyleSheet(self.plugin.pluginManager.styleSheet) # use same separators as in main window
            #     # close button will not be functional as QDockWidget.DockWidgetFeature.DockWidgetClosable is not set -> remove superfluous button
            #     closeButton = self.parent().findChild(QAbstractButton, "qt_dockwidget_closebutton")
            #     if closeButton is not None:
            #         closeButton.hide()

    def closeEvent(self, event):
        self.signalComm.dockClosingSignal.emit()
        return super().closeEvent(event)

class BetterIcon(QIcon):
    """QIcon that allows to save the icon file name. Allows to reuse icon elsewhere, e.g., for html about dialog."""

    def __init__(self, fileName):
        super().__init__(fileName)
        self.fileName = fileName # remember for later access

class LedIndicator(QAbstractButton):
    """Simple custom LED indicator"""
    # inspired by https://github.com/nlamprian/pyqt5-led-indicator-widget/blob/master/LedIndicatorWidget.py
    scaledSize = 1000.0

    def __init__(self, parent=None):
        QAbstractButton.__init__(self, parent)

        self.setMinimumSize(20, 20)
        self.setMaximumSize(20, 20)
        self.setCheckable(True)
        self.setEnabled(False) # indicator

        # Green
        self.on_color = QColor(0, 220, 0)
        self.off_color = QColor(0, 60, 0)

    def resizeEvent(self, QResizeEvent):  # pylint: disable = unused-argument # matching standard signature
        self.update()

    def paintEvent(self, QPaintEvent):  # pylint: disable = unused-argument # matching standard signature
        "an event that paints"
        realSize = min(self.width(), self.height())

        painter = QPainter(self)
        pen = QPen(Qt.GlobalColor.black)
        pen.setWidth(4)

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.translate(self.width() / 2, self.height() / 2)
        painter.scale(realSize / self.scaledSize, realSize / self.scaledSize)

        # paint outer ring
        gradient = QRadialGradient(QPointF(-500, -500), 1500, QPointF(-500, -500))
        gradient.setColorAt(0, QColor(224, 224, 224))
        gradient.setColorAt(1, QColor(28, 28, 28))
        painter.setPen(pen)
        painter.setBrush(QBrush(gradient))
        painter.drawEllipse(QPointF(0, 0), 500, 500)

        # paint inner ring
        gradient = QRadialGradient(QPointF(500, 500), 1500, QPointF(500, 500))
        gradient.setColorAt(0, QColor(224, 224, 224))
        gradient.setColorAt(1, QColor(28, 28, 28))
        painter.setPen(pen)
        painter.setBrush(QBrush(gradient))
        painter.drawEllipse(QPointF(0, 0), 450, 450)

        # paint center
        painter.setPen(pen)
        if self.isChecked():
            painter.setBrush(self.on_color)
        else:
            painter.setBrush(self.off_color)
        painter.drawEllipse(QPointF(0, 0), 400, 400)

    @pyqtProperty(QColor)
    def onColor(self):
        return self.on_color

    @onColor.setter
    def onColor(self, color):
        self.on_color = color

    @pyqtProperty(QColor)
    def offColor(self):
        return self.off_color

    @offColor.setter
    def offColor(self, color):
        self.off_color = color

    @pyqtProperty(QColor)
    def onColor1(self):
        return self.on_color_1

    @onColor1.setter
    def onColor1(self, color):
        self.on_color_1 = color

    @pyqtProperty(QColor)
    def onColor2(self):
        return self.on_color_2

    @onColor2.setter
    def onColor2(self, color):
        self.on_color_2 = color

    @pyqtProperty(QColor)
    def offColor1(self):
        return self.off_color_1

    @offColor1.setter
    def offColor1(self, color):
        self.off_color_1 = color

    @pyqtProperty(QColor)
    def offColor2(self):
        return self.off_color_2

    @offColor2.setter
    def offColor2(self, color):
        self.off_color_2 = color

class TextEdit(QPlainTextEdit):
    """from https://gist.github.com/Axel-Erfurt/8c84b5e70a1faf894879cd2ab99118c2"""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.installEventFilter(self)
        self._completer = None

    def setCompleter(self, c):
        if self._completer is not None:
            self._completer.activated.disconnect()

        self._completer = c
#        c.popup().verticalScrollBar().hide()
        c.popup().setStyleSheet("background-color: #555753; color: #eeeeec; font-size: 8pt; selection-background-color: #4e9a06;")

        c.setWidget(self)
        c.setCompletionMode(QCompleter.PopupCompletion)
        c.activated.connect(self.insertCompletion)

    def completer(self):
        return self._completer

    def insertCompletion(self, completion):
        if self._completer.widget() is not self:
            return

        tc = self.textCursor()
        extra = len(completion) - len(self._completer.completionPrefix())
        tc.movePosition(QTextCursor.Left)
        tc.movePosition(QTextCursor.EndOfWord)
        tc.insertText(completion[-extra:])
        self.setTextCursor(tc)

    def textUnderCursor(self):
        tc = self.textCursor()
        tc.select(QTextCursor.WordUnderCursor)

        return tc.selectedText()

    def focusInEvent(self, e):
        if self._completer is not None:
            self._completer.setWidget(self)

        super(TextEdit, self).focusInEvent(e)

    def keyPressEvent(self, e):
        """keyPressEvent"""
        if e.key() == Qt.Key.Key_Tab:
            self.textCursor().insertText("    ")
            return
        if self._completer is not None and self._completer.popup().isVisible():
            # The following keys are forwarded by the completer to the widget.
            if e.key() in (Qt.Key.Key_Enter, Qt.Key.Key_Return):
                e.ignore()
                # Let the completer do default behavior.
                return

        isShortcut = ((e.modifiers() & Qt.KeyboardModifier.ControlModifier) != 0 and e.key() == Qt.Key.Key_Escape)
        if self._completer is None or not isShortcut:
            # Do not process the shortcut when we have a completer.
            super(TextEdit, self).keyPressEvent(e)

        ctrlOrShift = e.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
        if self._completer is None or (ctrlOrShift and len(e.text()) == 0):
            return

        eow = "~!@#$%^&*()_+{}|:\"<>?,./;'[]\\-="
        hasModifier = (e.modifiers() != Qt.KeyboardModifier.NoModifier) and not ctrlOrShift
        completionPrefix = self.textUnderCursor()

        if not isShortcut and (hasModifier or len(e.text()) == 0 or len(completionPrefix) < 2 or e.text()[-1] in eow):
            self._completer.popup().hide()
            return

        if completionPrefix != self._completer.completionPrefix():
            self._completer.setCompletionPrefix(completionPrefix)
            self._completer.popup().setCurrentIndex(
                    self._completer.completionModel().index(0, 0))

        cr = self.cursorRect()
        cr.setWidth(self._completer.popup().sizeHintForColumn(0) + self._completer.popup().verticalScrollBar().sizeHint().width())
        self._completer.complete(cr)
    ####################################################################

class NumberBar(QWidget):
    """based on https://gist.github.com/Axel-Erfurt/8c84b5e70a1faf894879cd2ab99118c2"""

    def __init__(self, parent = None):
        super(NumberBar, self).__init__(parent)
        self.editor = parent
        self.editor.blockCountChanged.connect(self.update_width)
        self.editor.updateRequest.connect(self.update_on_scroll)
        self.update_width('1')
        self.lineBarColor = Qt.GlobalColor.black

    def updateTheme(self):
        self.lineBarColor = QColor(colors.bg)

    def update_on_scroll(self, rect, scroll): # pylint: disable = unused-argument # keeping consitent signature
        if self.isVisible():
            if scroll:
                self.scroll(0, scroll)
            else:
                self.update()

    def update_width(self, string):
        width = self.fontMetrics().horizontalAdvance(str(string)) + 8 # changed from width to horizontalAdvance
        if self.width() != width:
            self.setFixedWidth(width)

    def paintEvent(self, event):
        """paintEvent"""
        if self.isVisible():
            block = self.editor.firstVisibleBlock()
            height = self.fontMetrics().height()
            number = block.blockNumber()
            painter = QPainter(self)
            painter.fillRect(event.rect(), self.lineBarColor)
            painter.drawRect(0, 0, event.rect().width() - 1, event.rect().height() - 1)
            font = painter.font()

            current_block = self.editor.textCursor().block().blockNumber() + 1

            condition = True
            while block.isValid() and condition:
                block_geometry = self.editor.blockBoundingGeometry(block)
                offset = self.editor.contentOffset()
                block_top = block_geometry.translated(offset).top()
                number += 1

                rect = QRect(0, int(block_top + 2), self.width() - 5, height) # added conversion to int

                if number == current_block:
                    font.setBold(True)
                else:
                    font.setBold(False)

                painter.setFont(font)
                painter.drawText(rect, Qt.AlignmentFlag.AlignRight, f'{number:d}') # added .AlignmentFlag

                if block_top > event.rect().bottom():
                    condition = False

                block = block.next()

            painter.end()

class ThemedConsole(pyqtgraph.console.ConsoleWidget):
    """pyqtgraph.console.ConsoleWidget with colors adjusting to theme"""

    def __init__(self, parent=None, namespace=None, historyFile=None, text=None, editor=None):
        super().__init__(parent, namespace, historyFile, text, editor)
        self.updateTheme()

    def updateTheme(self):
        self.fgColor = '#ffffff' if getDarkMode() else '#000000' # foregound
        self.bgColor = '#000000' if getDarkMode() else '#ffffff' # background
        self.hlColor = '#51537e' if getDarkMode() else '#ccccff' # highlight
        self.output.setStyleSheet(f'QPlainTextEdit{{background-color:{colors.bg};}}')

    def runCmd(self, cmd):
        #cmd = str(self.input.lastCmd)

        orig_stdout = sys.stdout
        orig_stderr = sys.stderr
        encCmd = re.sub(r'>', '&gt;', re.sub(r'<', '&lt;', cmd))
        encCmd = re.sub(r' ', '&nbsp;', encCmd)

        self.ui.historyList.addItem(cmd)
        self.saveHistory(self.input.history[1:100])

        try:
            sys.stdout = self
            sys.stderr = self
            if self.multiline is not None:
                self.write("<br><b>%s</b>\n"%encCmd, html=True, scrollToBottom=True) # pylint: disable = consider-using-f-string # do not modify original source
                self.execMulti(cmd)
            else:
                self.write(f"<br><div style='background-color: {self.hlColor}; color: {self.fgColor}'><b>%s</b>\n"%encCmd, html=True, scrollToBottom=True)
                self.inCmd = True
                self.execSingle(cmd)

            if not self.inCmd:
                self.write("</div>\n", html=True, scrollToBottom=True)

        finally:
            sys.stdout = orig_stdout
            sys.stderr = orig_stderr

            sb = self.ui.historyList.verticalScrollBar()
            sb.setValue(sb.maximum())

    def write(self, strn, html=False, scrollToBottom='auto'):
        """Write a string into the console.

        If scrollToBottom is 'auto', then the console is automatically scrolled
        to fit the new text only if it was already at the bottom.
        """
        isGuiThread = QThread.currentThread() == QCoreApplication.instance().thread()
        if not isGuiThread:
            sys.__stdout__.write(strn)
            return

        sb = self.output.verticalScrollBar()
        scroll = sb.value()
        if scrollToBottom == 'auto':
            atBottom = scroll == sb.maximum()
            scrollToBottom = atBottom

        self.output.moveCursor(QTextCursor.MoveOperation.End)
        if html:
            self.output.textCursor().insertHtml(strn)
        else:
            if self.inCmd:
                self.inCmd = False
                self.output.textCursor().insertHtml(f"</div><br><div style='font-weight: normal; background-color: {self.bgColor}; color: {self.fgColor}'>")
            self.output.insertPlainText(strn)

        if scrollToBottom:
            sb.setValue(sb.maximum())
        else:
            sb.setValue(scroll)

    def setStack(self, frame=None, tb=None):
        """Display a call stack and exception traceback.

        This allows the user to probe the contents of any frame in the given stack.

        *frame* may either be a Frame instance or None, in which case the current
        frame is retrieved from ``sys._getframe()``.

        If *tb* is provided then the frames in the traceback will be appended to
        the end of the stack list. If *tb* is None, then sys.exc_info() will
        be checked instead.
        """
        self.ui.clearExceptionBtn.setEnabled(True)

        if frame is None:
            frame = sys._getframe().f_back

        if tb is None:
            tb = sys.exc_info()[2]

        self.ui.exceptionStackList.clear()
        self.frames = []

        # Build stack up to this point
        for index, line in enumerate(traceback.extract_stack(frame)): # pylint: disable = unused-variable # do not modify original source
            # extract_stack return value changed in python 3.5
            if 'FrameSummary' in str(type(line)):
                line = (line.filename, line.lineno, line.name, line._line)

            self.ui.exceptionStackList.addItem('File "%s", line %s, in %s()\n  %s' % line) # pylint: disable = consider-using-f-string # do not modify original source
        while frame is not None:
            self.frames.insert(0, frame)
            frame = frame.f_back

        if tb is None:
            return

        self.ui.exceptionStackList.addItem('-- exception caught here: --')
        item = self.ui.exceptionStackList.item(self.ui.exceptionStackList.count()-1)
        item.setBackground(QBrush(QColor(self.bgColor)))
        item.setForeground(QBrush(QColor(self.fgColor)))
        self.frames.append(None)

        # And finish the rest of the stack up to the exception
        for index, line in enumerate(traceback.extract_tb(tb)):
            # extract_stack return value changed in python 3.5
            if 'FrameSummary' in str(type(line)):
                line = (line.filename, line.lineno, line.name, line._line)

            self.ui.exceptionStackList.addItem('File "%s", line %s, in %s()\n  %s' % line) # pylint: disable = consider-using-f-string # do not modify original source
        while tb is not None:
            self.frames.append(tb.tb_frame)
            tb = tb.tb_next

class ThemedNavigationToolbar(NavigationToolbar2QT):
    """Provides controls to interact with the figure.
    Adds light and dark theme support to NavigationToolbar2QT."""

    def __init__(self, canvas, parentPlugin=None, coordinates=True, dark=False):
        super().__init__(canvas, parentPlugin, coordinates)
        self.parentPlugin = parentPlugin
        self.updateNavToolbarTheme(dark=dark)

    def updateNavToolbarTheme(self, dark):
        """Changes color of icons in matplotlib navigation toolBar to match theme."""
        for a in self.actions()[:-1]:
            match a.text():
                case 'Home':
                    a.setIcon(self.parentPlugin.makeCoreIcon('home_large_dark.png' if dark else 'home_large.png'))
                case 'Back':
                    a.setIcon(self.parentPlugin.makeCoreIcon('back_large_dark.png' if dark else 'back_large.png'))
                case 'Forward':
                    a.setIcon(self.parentPlugin.makeCoreIcon('forward_large_dark.png' if dark else 'forward_large.png'))
                case 'Pan':
                    a.setIcon(self.parentPlugin.makeCoreIcon('move_large_dark.png' if dark else 'move_large.png'))
                case 'Zoom':
                    a.setIcon(self.parentPlugin.makeCoreIcon('zoom_to_rect_large_dark.png' if dark else 'zoom_to_rect_large.png'))
                case 'Subplots':
                    a.setIcon(self.parentPlugin.makeCoreIcon('subplots_large_dark.png' if dark else 'subplots_large.png'))
                case 'Customize':
                    a.setIcon(self.parentPlugin.makeCoreIcon('qt4_editor_options_large_dark.png' if dark else 'qt4_editor_options_large.png'))
                case 'Save':
                    a.setIcon(self.parentPlugin.makeCoreIcon('filesave_large_dark.png' if dark else 'filesave_large.png'))

    def save_figure(self, *args):
        super().save_figure(*args)
        self.parentPlugin.pluginManager.Explorer.populateTree() # show saved file in Explorer

class MZCaculator():
    """
    Add to a class derived from Scan.
    Allows to mark mz locations within a chargestate distrubution, calculates absolute mass, and displays it on the axis.
    Use Ctrl + Left Mouse to mark and Ctrl + Right Mouse to reset"""
    def __init__(self, parentPlugin, ax=None):
        self.parentPlugin = parentPlugin
        if ax:
            self.ax = ax
            self.canvas = ax.figure.canvas
        self.mz = np.array([]) # array with selected m/z values
        self.cs = None
        self.charges=np.array([]) # for charge state up to 100
        self.maxChargeState = 100 # maximal value for lowest charge state
        self.STD = np.array([]) # array with standard deviations for each charge state
        self.c1 = 0 # charge state of lowest m/z value
        self.intensity = np.array([]) # y value for selected m/z values (for plotting only)
        # Note: Events should be implemented outside of this class to allow Scan to trigger multiple functions based on the event
        # self.canvas.mpl_connect('button_press_event', self.msOnClick) -> self.canvas.mpl_connect('button_press_event', self.mzCalc.msOnClick)

    def setAxis(self, ax):
        self.ax = ax
        self.canvas = ax.figure.canvas

    def msOnClick(self, event):
        if event.button == MouseButton.RIGHT: # reset m/z analysis
            self.clear()
        elif event.button == MouseButton.LEFT and kb.is_pressed('ctrl'): # add new value and analyze m/z
            self.addMZ(event.xdata, event.ydata)

    def addMZ(self, x, y):
        self.mz = np.append(self.mz, x)
        self.intensity = np.append(self.intensity, y)
        self.determine_mass_to_charge()

    def clear(self):
        self.mz = np.array([])
        self.intensity = np.array([])
        self.update_mass_to_charge()

    def determine_mass_to_charge(self):
        """estimates charge states based on m/z values provided by user by minimizing standard deviation of absolute mass within a charge state series.
        Provides standard deviation for neightbouring series to allow for validation of the result."""
        if len(self.mz) > 1: # not enough information for analysis
            sort_indices = self.mz.argsort()
            self.mz = self.mz[sort_indices] # increasing m/z match decreasing charge states
            self.intensity = self.intensity[sort_indices]
            self.charges=np.arange(self.maxChargeState+len(self.mz)) # for charge state up to self.maxChargeState
            self.STD=np.zeros(self.maxChargeState) # initialize standard deviation
            for i in np.arange(self.maxChargeState):
                self.STD[i] = np.std(self.mz*np.flip(self.charges[i:i+len(self.mz)]))
            self.c1 = self.STD.argmin()
            self.cs = np.flip(self.charges[self.c1:self.c1+len(self.mz)]) # charge states
            self.update_mass_to_charge()

    def mass_string(self, offset, label):
        return f'{label} mass (Da): {np.average(self.mz*self.charges[self.c1+offset:self.c1+offset+len(self.mz)]):.2f}, std: {self.STD[self.c1+offset]:.2f}'

    def update_mass_to_charge(self):
        for ann in [child for child in self.ax.get_children() if isinstance(child, mpl.text.Annotation)]:#[self.seAnnArrow, self.seAnnFile, self.seAnnFWHM]:
            ann.remove()
        if len(self.mz) > 1:
            for x, y, c in zip(self.mz, self.intensity, self.cs):
                self.ax.annotate(text=f'{c}', xy=(x, y), xycoords='data', ha='center')
            self.ax.annotate(text=f"{self.mass_string(-1,'lower  ')}\n{self.mass_string( 0,'likely  ')}\n{self.mass_string(+1,'higher')}\n"
                                    + '\n'.join([f'mz:{m:10.2f} z:{c:4}' for m, c in zip(self.mz, self.cs)]),
                                xy=(0.02, 0.98), xycoords='axes fraction', fontsize=8, ha='left', va='top')
        self.parentPlugin.labelPlot(self.ax, self.parentPlugin.file.name)

class BetterPlotWidget(pg.PlotWidget):
    """PlotWidget providing xyLabel."""

    def __init__(self, parent=None, background='default', plotItem=None, **kargs):
        super().__init__(parent, background, plotItem, **kargs)
        self.parent = parent
        self.xyLabel = pg.TextItem(anchor=(0, 0))
        self.xyLabel.setParentItem(self.getPlotItem().getViewBox())

    def mouseMoveEvent(self, ev):
        pos = QPointF(ev.pos())
        if self.getPlotItem().getViewBox().geometry().contains(pos): # add offset
            # print(ev.pos(), self.getPlotItem().getViewBox().mapSceneToView(pos))
            pos = self.getPlotItem().getViewBox().mapSceneToView(pos)
            try:
                if self.getPlotItem().ctrl.logYCheck.isChecked():
                    self.xyLabel.setText(f"t = {datetime.fromtimestamp(pos.x()).strftime('%Y-%m-%d %H:%M:%S')}, y = {10**pos.y():.2e}")
                else:
                    self.xyLabel.setText(f"t = {datetime.fromtimestamp(pos.x()).strftime('%Y-%m-%d %H:%M:%S')}, y = {pos.y():.2f}")
                g = self.getPlotItem().getViewBox().geometry()
                self.xyLabel.setPos(g.width()-self.xyLabel.boundingRect().width()-4, 2)
            except (OSError, ValueError, OverflowError):
                pass # ignore label before time axis is initialized
        else:
            self.xyLabel.setText('')
        return super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        if self.parent is not None:
            self.parent.plot()
        return super().mouseReleaseEvent(ev)


class SciAxisItem(pg.AxisItem):
    """Based on original logTickStrings from https://pyqtgraph.readthedocs.io/en/latest/_modules/pyqtgraph/graphicsItems/AxisItem.html
    Only difference to source code is 0.1g -> .0e and consistend use of 1 = 10⁰"""

    # no ticks when zooming in too much: https://github.com/pyqtgraph/pyqtgraph/issues/1505

    def logTickStrings(self, values, scale, spacing):
        estrings = [f'{x:.0e}' for x in 10 ** np.array(values).astype(float) * np.array(scale)]
        # print(estrings, values, scale)
        convdict = {"0": "⁰",
                    "1": "¹",
                    "2": "²",
                    "3": "³",
                    "4": "⁴",
                    "5": "⁵",
                    "6": "⁶",
                    "7": "⁷",
                    "8": "⁸",
                    "9": "⁹",
                    }
        dstrings = []
        for e in estrings:
            if e.count("e"):
                v, p = e.split("e")
                sign = "⁻" if p[0] == "-" else ""
                pot = "".join([convdict[pp] for pp in p[1:].lstrip("0")])
                if pot == '': # added to account for 1=10⁰
                    pot='⁰'
                # if v == "1": # removed -> not needed?
                #     v = ""
                # else:
                    # v = v + '·'
                dstrings.append(v + '·'+ '10' + sign + pot)
            else:
                dstrings.append(e)
        return dstrings

class DeviceController(QObject):
    """Each :class:`~Esibd.EsibdPlugins.Device` or :class:`~Esibd.EsibdCore.Channel` comes with a :class:`~Esibd.EsibdCore.DeviceController`. The
    :class:`~Esibd.EsibdCore.DeviceController` is not itself a :class:`~Esibd.EsibdPlugins.Plugin`. It only abstracts the direct
    hardware communication from :class:`plugins<Esibd.EsibdPlugins.Plugin>` allowing them to use minimal and
    consistent code that can be adjusted and reused independently of the
    hardware. It should do all resource or time intensive communication work
    in parallel threads to not slow down the main software. Following the
    producer consumer logic, the :class:`~Esibd.EsibdCore.DeviceController` reads values and assigns
    them to the corresponding :class:`~Esibd.EsibdCore.Channel`. The :class:`devices<Esibd.EsibdPlugins.Device>` will collect data from
    the :class:`~Esibd.EsibdCore.Channel` independently. In case you work with time sensitive
    experiments this concept will need to be adapted. Feel free to use the
    basic functionality provided by :class:`~Esibd.EsibdCore.DeviceController` or implement
    your own from scratch. As the :class:`~Esibd.EsibdCore.DeviceController` only interacts with your
    custom :class:`~Esibd.EsibdCore.Channel` or :class:`~Esibd.EsibdPlugins.Device`, there are no general requirements for
    its implementation."""

    class SignalCommunicate(QObject): # signals called from external thread and run in main thread
        """Object that bundles pyqtSignals for the :class:`~Esibd.EsibdCore.DeviceController`. Extend to add additional events."""
        initCompleteSignal = pyqtSignal()
        """Signal that is emitted after successful initialization of device communication."""
        stopSignal = pyqtSignal()
        """Signal that triggers the acquisition to stop after communication errors."""
        updateValueSignal = pyqtSignal()
        """Signal that transfers new data from the :attr:`~Esibd.EsibdCore.DeviceController.acquisitionThread` to the corresponding channels."""

    parent : any # Device or Channel, cannot specify without causing circular import
    """Reference to the associated class."""
    print : callable
    """Reference to :meth:`~Esibd.EsibdPlugins.Plugin.print`."""
    port : serial.Serial = None
    """Port for serial communication."""
    initThread : Thread = None
    """A parallel thread used to initialize communication."""
    acquisitionThread : Thread = None
    """A parallel thread that regularly reads values from the device."""
    lock : Lock = Lock()
    """Lock used to avoid race conditions when communicating with the hardware."""
    acquiring : bool = False
    """True, while *acquisitionThread* is running. *AcquisitionThread* terminates if set to False."""
    initialized : bool = False
    """Indicates if communications has been initialized successfully and not yet terminated."""

    def __init__(self, parent):
        super().__init__()
        self.channel = None # overwrite with parent if applicable
        self.device = parent # overwrite with channel.device if applicable
        self.print = parent.print
        self.signalComm = self.SignalCommunicate()
        self.signalComm.initCompleteSignal.connect(self.initComplete)
        self.signalComm.updateValueSignal.connect(self.updateValue)
        self.signalComm.stopSignal.connect(self.stop)

    def init(self):
        """Starts the :meth:`~Esibd.EsibdCore.DeviceController.initThread`."""
        self.close() # terminate old thread before starting new one
        # threads cannot be restarted -> make new thread every time. possibly there are cleaner solutions
        self.initThread = Thread(target=self.runInitialization)
        self.initThread.daemon = True
        self.initThread.start() # initialize in separate thread

    def runInitialization(self):
        """Hardware specific initialization of communication. Executed in initThread."""

    def initComplete(self):
        """Called after successful initialization to start acquisition."""
        self.initialized = True
        self.startAcquisition()

    def startAcquisition(self):
        """Starts data acquisition from physical device."""
        if self.acquisitionThread is not None and self.acquisitionThread.is_alive():
            if self.device.log:
                self.device.print('Wait for data reading thread to complete before restarting acquisition.', PRINT.WARNING)
            self.acquiring = False
            self.acquisitionThread.join(timeout=5)
            if self.acquisitionThread.is_alive():
                self.print('Data reading thread did not complete. Reset connection manually.', PRINT.ERROR)
                return
        self.acquisitionThread = Thread(target=self.runAcquisition, args =(lambda : self.acquiring,))
        self.acquisitionThread.daemon = True
        self.acquiring = True # terminate old thread before starting new one
        self.acquisitionThread.start()

    def runAcquisition(self, acquiring):
        """Runs acquisitoin loop. Executed in acquisitionThread.
        Overwrite with hardware specific acquisition code."""

    def updateValue(self):
        """Called from acquisitionThread to update the
        value of the channel(s) in the main thread.
        Overwrite with specific update code."""

    def serialWrite(self, port, message, encoding='utf-8'):
        """Writes a string to a serial port. Takes care of decoding messages to
        bytes and catches common exceptions.

        :param port: Serial port.
        :type port: serial.Serial
        :param message: Message.
        :type message: str
        :param encoding: Encoding used for sending and receiving messages, defaults to 'utf-8'
        :type encoding: str, optional
        """
        try:
            port.write(bytes(message, encoding))
        except serial.SerialTimeoutException as e:
            self.print(f'Timeout while writing message, try to reinitialize communication: {e}', PRINT.ERROR)
        except serial.PortNotOpenError as e:
            self.print(f'Port not open, try to reinitialize communication: {e}', PRINT.ERROR)
            self.stopDelayed()
        except serial.SerialException as e:
            self.print(f'Serial error, try to reinitialize communication: {e}', PRINT.ERROR)
            self.stopDelayed()
        except AttributeError as e:
            self.print(f'Attribute error, try to reinitialize communication: {e}', PRINT.ERROR)
            self.stopDelayed()

    def serialRead(self, port, encoding='utf-8'):
        """Reads a string from a serial port. Takes care of decoding messages
        from bytes and catches common exceptions.

        :param port: Serial port.
        :type port: serial.Serial
        :param encoding: Encoding used for sending and receiving messages, defaults to 'utf-8'
        :type encoding: str, optional
        :return: message
        :rtype: str
        """
        try:
            return port.readline().decode(encoding).rstrip()
        except UnicodeDecodeError as e:
            self.print(f'Error while decoding message: {e}', PRINT.ERROR)
        except serial.SerialTimeoutException as e:
            self.print(f'Timeout while reading message, try to reinitialize communication: {e}', PRINT.ERROR)
            self.stopDelayed()
        except serial.SerialException as e:
            self.print(f'Serial error, try to reinitialize communication: {e}', PRINT.ERROR)
            self.stopDelayed()
        except AttributeError as e:
            self.print(f'Attribute error, try to reinitialize communication: {e}', PRINT.ERROR)
            self.stopDelayed()
        return ''

    def stopDelayed(self):
        # stopAcquisition has to run after the lock has been released as it acquires lock to close communication.
        Timer(0, self.signalComm.stopSignal.emit).start()

    def stop(self):
        """Overwrite to stop recording and acquisition in case a communication error occured.
        This should free up all resources and allow for clean reinitialization."""
        # depending on the hardware this may be self.device.stopAcquisition() or self.channel.device.stopAcquisition() or something else

    def close(self):
        """Terminates acquisition and closes all open ports.
        Extend to add hardware specific code.
        """
        self.stopAcquisition()

    def stopAcquisition(self):
        """Terminates acquisition but leaves communication initialized by default."""
        if self.acquisitionThread is not None:
            self.acquiring = False
            return True
        return False

class SplashScreen(QSplashScreen):
    """Program splash screen indicates start process before main window is ready."""

    def __init__(self):
        super().__init__()
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint | Qt.WindowType.SplashScreen | Qt.WindowType.WindowStaysOnTopHint)
        self.lay = QVBoxLayout(self)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        currentDesktopsCenter = QApplication.instance().mainWindow.geometry().center()
        self.move(currentDesktopsCenter.x()-100, currentDesktopsCenter.y()-100) # move to center
        self.labels = []
        self.index = 3
        self.label = QLabel()
        self.label.setMaximumSize(200, 200)
        self.label.setScaledContents(True)
        self.lay.addWidget(self.label)
        self.timer = QTimer()
        self.timer.timeout.connect(self.animate)
        self.timer.setInterval(1000)
        self.timer.start()
        self.closed = False

    def animate(self):
        self.index = np.mod(self.index + 1, 4)
        self.label.setPixmap(QPixmap(f'{SPLASHIMAGE}{self.index+1}.png'))

    def close(self):
        self.closed=True
        self.timer.stop()
        return super().close()
