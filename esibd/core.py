"""This module contains internally used functions and classes.
Generally all objects that are used across multiple modules should be defined here to avoid circular imports and keep things consistent.
Whenever it is possible to make definitions only locally where they are needed, this is preferred.
For now, English is the only supported language and use of hard coded error messages etc. in other files is tolerated if they are unique."""

import re
import sys
import traceback
from threading import Timer, Thread, current_thread, main_thread
import threading
import time
from typing import Any, List
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime
from enum import Enum
import configparser
import serial
import numpy as np
import pyqtgraph as pg
import pyqtgraph.console
import keyboard as kb
import matplotlib as mpl
import cv2
import matplotlib.pyplot as plt # pylint: disable = unused-import # need to import to access mpl.axes.Axes
from matplotlib.widgets import Cursor
from matplotlib.backend_bases import MouseButton, MouseEvent
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT
from PIL import Image
from PIL.ImageQt import ImageQt
from PyQt6.QtWebEngineWidgets import QWebEngineView # pylint: disable = unused-import # QtWebEngineWidgets must be imported or Qt.AA_ShareOpenGLContexts must be set before a QCoreApplication instance is created
from PyQt6.QtWidgets import (QApplication, QVBoxLayout, QSizePolicy, QWidget, QGridLayout, QTreeWidgetItem, QToolButton, QDockWidget,
                             QMainWindow, QSplashScreen, QCompleter, QPlainTextEdit, QPushButton, QStatusBar, QStackedLayout, # QStyle, QLayout, QInputDialog,
                             QComboBox, QDoubleSpinBox, QSpinBox, QLineEdit, QLabel, QCheckBox, QAbstractSpinBox, QTabWidget, QAbstractButton,
                             QDialog, QHeaderView, QDialogButtonBox, QTreeWidget, QTabBar, QMessageBox, QMenu, QTextEdit)
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QPointF, pyqtProperty, QRect, QTimer, QSize, QPoint #, QEvent #
from PyQt6.QtGui import (QIcon, QBrush, QGuiApplication, QValidator, QColor, QPainter, QCursor, QPen, QTextCursor, QRadialGradient, QPixmap,
                          QPalette, QAction, QFont, QMouseEvent, QFontMetrics, QImage) #
from esibd.const import * # pylint: disable = wildcard-import, unused-wildcard-import  # noqa: F403

class EsibdExplorer(QMainWindow):
    r"""ESIBD Explorer: A comprehensive data acquisition and analysis tool for Electrospray Ion-Beam Deposition experiments and beyond.

    Contains minimal code to start, initialize, and close the program.
    All high level logic is provided by :mod:`~esibd.core`,
    :mod:`~esibd.plugins` and additional
    :class:`plugins<esibd.plugins.Plugin>`.
    """

    loadPluginsSignal = pyqtSignal()

    def __init__(self):
        """Sets up basic user interface and triggers loading of plugins."""
        super().__init__()
        # switch to GL compatibility mode here to avoid UI glitches later https://stackoverflow.com/questions/77031792/how-to-avoid-white-flash-when-initializing-qwebengineview
        dummy = QWebEngineView(parent=self)
        dummy.setHtml('dummy')
        dummy.deleteLater()
        self.restoreUiState()
        self.setWindowIcon(QIcon(PROGRAM_ICON.as_posix()))
        self.setWindowTitle(PROGRAM_NAME)
        self.actionFull_Screen = QAction()
        self.actionFull_Screen.triggered.connect(self.toggleFullscreen)
        self.actionFull_Screen.setShortcut('F11')
        self.addAction(self.actionFull_Screen) # action only works when added to a widget
        self.maximized  = False
        self.loadPluginsSignal.connect(self.loadPlugins)
        self.setStatusBar(IconStatusBar())
        QTimer.singleShot(0, self.loadPluginsSignal.emit) # let event loop start before loading plugins
        self.installEventFilter(self)

    def loadPlugins(self):
        """Loads :class:`plugins<esibd.plugins.Plugin>` in main thread."""
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
            # * need to restore before starting event loop to avoid Unable to set geometry warning
        except TypeError as e:
            print(f'Could not restore window state: {e}')
            self.resize(800, 400)
            self.saveUiState()

    def saveUiState(self):
        """Saves size and location of main window."""
        qSet.setValue(GEOMETRY, self.saveGeometry())
        self.pluginManager.Settings.raiseDock(True) # need to be visible to give right dimensions
        QApplication.processEvents()
        qSet.setValue(SETTINGSWIDTH, self.pluginManager.Settings.mainDisplayWidget.width()) # store width
        qSet.setValue(SETTINGSHEIGHT, self.pluginManager.Settings.mainDisplayWidget.height()) # store height
        qSet.setValue(CONSOLEHEIGHT, self.pluginManager.Console.mainDisplayWidget.height()) # store height
        # qSet.setValue(GEOMETRY, self.mainWindow.geometry())
        # qSet.setValue(self.WINDOWSTATE, self.mainWindow.saveState())

    def closeEvent(self, event):
        """Triggers :class:`~esibd.core.PluginManager` to close all plugins and all related communication."""
        if not self.pluginManager.loading:
            if self.pluginManager.DeviceManager.initialized():
                if CloseDialog(prompt='Acquisition is still running. Do you really want to close?').exec():
                    self.pluginManager.DeviceManager.closeCommunication(closing=True)
                else:
                    event.ignore() # keep running
                    return
            self.pluginManager.closePlugins()
            QApplication.instance().quit()
            event.accept() # let the window close
        else:
            event.ignore() # keep running

class PluginManager():
    """The :class:`~esibd.core.PluginManager` is responsible for loading all internal and external
        Plugins. It catches errors or incompatibilities while loading,
        initializing, and closing plugins. Users will only see the plugin selection
        interface accessed from the :ref:`sec:settings` plugin.
        The :class:`~esibd.core.PluginManager` can be accessed from the :ref:`sec:console` as `PluginManager`.
        It allows plugins to interact by using unique plugin names as attributes, e.g.
        `self.pluginManager.ISEG` or `self.pluginManager.DeviceManager`."""

    class SignalCommunicate(QObject):
        finalizeSignal = pyqtSignal()

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
        CHANNELMANAGER  = 'Channel Manager'
        """A plugin that manages channels which are neither inputs or outputs."""
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
    SUPPORTEDVERSION    = 'Supported Version'
    ENABLED             = 'Enabled'
    PREVIEWFILETYPES    = 'PREVIEWFILETYPES'
    DESCRIPTION         = 'DESCRIPTION'
    OPTIONAL            = 'OPTIONAL'
    PLUGINTYPE          = 'PLUGINTYPE'
    DEPENDENCYPATH      = 'dependencyPath'
    ICONFILE            = 'iconFile'
    ICONFILEDARK        = 'iconFileDark'
    # WINDOWSTATE = 'WINDOWSTATE'
    plugins = [] # Plugin avoid circular import
    """A central plugin list that allows plugins to interact with each other."""

    def __init__(self):
        self.mainWindow = QApplication.instance().mainWindow
        self._testing = False # has to be defined before logger
        self.logger = Logger(pluginManager=self)
        self.logger.print('Loading.', flag=PRINT.EXPLORER)
        self.userPluginPath = None
        self.pluginFile     = None
        self.plotting = False
        self.mainWindow.setTabPosition(Qt.DockWidgetArea.LeftDockWidgetArea, QTabWidget.TabPosition.North)
        self.mainWindow.setTabPosition(Qt.DockWidgetArea.RightDockWidgetArea, QTabWidget.TabPosition.North)
        self.mainWindow.setTabPosition(Qt.DockWidgetArea.TopDockWidgetArea, QTabWidget.TabPosition.North)
        self.mainWindow.setTabPosition(Qt.DockWidgetArea.BottomDockWidgetArea, QTabWidget.TabPosition.North)
        self.mainWindow.setDockOptions(QMainWindow.DockOption.AllowTabbedDocks | QMainWindow.DockOption.AllowNestedDocks
                                     | QMainWindow.DockOption.GroupedDragging | QMainWindow.DockOption.AnimatedDocks)
        self.signalComm = self.SignalCommunicate()
        self.signalComm.finalizeSignal.connect(self.finalizeUiState)
        self.plugins = []
        self.pluginNames = []
        self.firstControl = None
        self.firstDisplay = None
        self.tabBars = None
        self._loading = 0
        self.finalizing = False
        self.closing = False
        self.qm = QMessageBox(QMessageBox.Icon.Information, 'Warning!', 'v!', buttons=QMessageBox.StandardButton.Ok)

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

    def loadPlugins(self, reload=False):
        """Loads all enabled plugins."""

        self.updateTheme()
        if not reload:
            self.splash = SplashScreen()
            self.splash.show()

        self.mainWindow.setUpdatesEnabled(False)
        self.loading = True # some events should not be triggered until after the UI is completely initialized
        self.closing = False

        self.userPluginPath = validatePath(qSet.value(f'{GENERAL}/{PLUGINPATH}', defaultPluginPath), defaultPluginPath)[0]
        # self.mainWindow.configPath not yet be available -> use directly from qSet
        self.pluginFile     = validatePath(qSet.value(f'{GENERAL}/{CONFIGPATH}', defaultConfigPath), defaultConfigPath)[0] / 'plugins.ini'
        self.plugins = []
        self.pluginNames = []
        self.firstControl = None
        self.firstDisplay = None

        self.confParser = configparser.ConfigParser()
        self.pluginFile.parent.mkdir(parents=True, exist_ok=True)
        if self.pluginFile.exists():
            self.confParser.read(self.pluginFile)
        self.confParser[INFO] = infoDict('PluginManager')

        import esibd.providePlugins # pylint: disable = import-outside-toplevel # avoid circular import
        self.loadPluginsFromModule(Module=esibd.providePlugins, dependencyPath=internalMediaPath)
        self.loadPluginsFromPath(internalPluginPath)
        self.userPluginPath.mkdir(parents=True, exist_ok=True)
        if self.userPluginPath == internalPluginPath:
            self.logger.print('Ignoring user plugin path as it equals internal plugin path.', flag=PRINT.WARNING)
        else:
            self.loadPluginsFromPath(self.userPluginPath)

        obsoletePluginNames = []
        for name in self.confParser.keys():
            if not name == Parameter.DEFAULT.upper() and not name == INFO and name not in self.pluginNames:
                obsoletePluginNames.append(name)
        if len(obsoletePluginNames) > 0:
            self.logger.print(f"Removing obsolete plugin data: {', '.join(obsoletePluginNames)}", flag=PRINT.WARNING)
            for obsoletePluginName in obsoletePluginNames:
                self.confParser.pop(obsoletePluginName)
        with open(self.pluginFile, 'w', encoding = UTF8) as configFile:
            self.confParser.write(configFile)

        if hasattr(self, 'Settings'):
            self.Settings.init()  # init internal settings and settings of devices and scans which have been added in the meantime
        self.provideDocks() # add plugin docks before loading = False

        if hasattr(self, 'Tree'):
            self.plugins.append(self.plugins.pop(self.plugins.index(self.Tree))) # move Tree to end to have lowest priority to handle files
        if hasattr(self, 'Text'):
            self.plugins.append(self.plugins.pop(self.plugins.index(self.Text))) # move Text to end to have lowest priority to handle files
        if hasattr(self, 'PID'):
            if self.PID in self.plugins:
                self.plugins.append(self.plugins.pop(self.plugins.index(self.PID))) # move PID to end to connectAllSources after all devices are initialized
        if hasattr(self, 'UCM'):
            if self.UCM in self.plugins:
                self.plugins.append(self.plugins.pop(self.plugins.index(self.UCM))) # move UCM to end to connectAllSources after all devices and PID are initialized
        self.loading = False
        self.finalizing = True
        self.finalizeInit()
        self.afterFinalizeInit()
        self.toggleVideoRecorder()
        self.mainWindow.setUpdatesEnabled(True)
        self.finalizing = False
        self.toggleTitleBarDelayed(update=True, delay=1000)
        QTimer.singleShot(0, self.signalComm.finalizeSignal.emit) # add delay to make sure application is ready to process updates, but make sure it is done in main thread
        self.splash.close() # close as soon as mainWindow is ready
        self.logger.print('Ready.', flag=PRINT.EXPLORER)

    def loadPluginsFromPath(self, path):
        for _dir in [_dir for _dir in path.iterdir() if _dir.is_dir()]:
            for file in [file for file in _dir.iterdir() if file.name.endswith('.py')]:
                try:
                    Module = dynamicImport(file.stem, file)
                except Exception as e: # pylint: disable = broad-except # we have no control about the exception a plugin can possibly throw here
                    # No unpredictable Exception in a single plugin should break the whole application
                    self.logger.print(f'Could not import module {file.stem}: {e}', flag=PRINT.ERROR)
                    # Note, this will not show in the Console Plugin which is not yet fully initialized. -> show in separate dialog window:
                    self.qm.setText(f'Could not import module {file.stem}: {e}')
                    self.qm.setIcon(QMessageBox.Icon.Warning)
                    # self.qm.setWindowIcon(QMessageBox.icon)
                    self.qm.open()
                    self.qm.raise_()
                else:
                    if hasattr(Module, 'providePlugins'):
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
                self.confParser[Plugin.name] = {self.ENABLED : not Plugin.optional, self.VERSION : Plugin.version, self.SUPPORTEDVERSION : Plugin.supportedVersion,
                                                self.DEPENDENCYPATH : dependencyPath, self.ICONFILE : Plugin.iconFile, self.ICONFILEDARK : Plugin.iconFileDark,
                                                self.PLUGINTYPE : str(Plugin.pluginType.value),
                                            self.PREVIEWFILETYPES : ', '.join(Plugin.previewFileTypes), # getSupportedFiles() not available without instantiation
                                            self.DESCRIPTION : Plugin.documentation if Plugin.documentation is not None else Plugin.__doc__, self.OPTIONAL : str(Plugin.optional)}
            else: # update
                self.confParser[Plugin.name][self.VERSION] = Plugin.version
                self.confParser[Plugin.name][self.SUPPORTEDVERSION] = Plugin.supportedVersion
                self.confParser[Plugin.name][self.DEPENDENCYPATH] = dependencyPath.as_posix()
                self.confParser[Plugin.name][self.ICONFILE] = Plugin.iconFile
                self.confParser[Plugin.name][self.ICONFILEDARK] = Plugin.iconFileDark
                self.confParser[Plugin.name][self.PLUGINTYPE] = str(Plugin.pluginType.value)
                self.confParser[Plugin.name][self.PREVIEWFILETYPES] = ', '.join(Plugin.previewFileTypes) # getSupportedFiles() not available without instantiation
                self.confParser[Plugin.name][self.DESCRIPTION] = Plugin.documentation if Plugin.documentation is not None else Plugin.__doc__
                self.confParser[Plugin.name][self.OPTIONAL] = str(Plugin.optional)
            if self.confParser[Plugin.name][self.ENABLED] == 'True':
                plugin=self.loadPlugin(Plugin, dependencyPath=dependencyPath)
                if plugin is not None:
                    self.confParser[Plugin.name][self.PREVIEWFILETYPES] = ', '.join(plugin.getSupportedFiles()) # requires instance

    def loadPlugin(self, Plugin, dependencyPath=None):
        """Load a single plugin.
        Plugins must have a static name and pluginType.
        'mainWindow' is passed to enable flexible integration, but should only be used at your own risk.
        Enabled state is saved and restored from an independent file and can also be edited using the plugins dialog."""
        QApplication.processEvents() # break down expensive initialization to allow update splash screens while loading
        self.logger.print(f'loadPlugin {Plugin.name}', flag=PRINT.DEBUG)
        if not pluginSupported(Plugin.supportedVersion):
            # * we ignore micro (packaging.version name for patch)
            self.logger.print(f'Plugin {Plugin.name} supports {PROGRAM_NAME} {Plugin.supportedVersion}. It is not compatible with {PROGRAM_NAME} {PROGRAM_VERSION}.', flag=PRINT.WARNING)
            return
        if Plugin.name in [plugin.name for plugin in self.plugins]:
            self.logger.print(f'Ignoring duplicate plugin {Plugin.name}.', flag=PRINT.WARNING)
        else:
            try:
                plugin = Plugin(pluginManager=self, dependencyPath=dependencyPath)
                setattr(self.__class__, plugin.name, plugin) # use attributes to access for communication between plugins
            except Exception: # pylint: disable = broad-except # we have no control about the exception a plugin can possibly throw
                # No unpredictable exception in a single plugin should break the whole application
                self.logger.print(f'Could not load plugin {Plugin.name} {Plugin.version}: {traceback.format_exc()}', flag=PRINT.ERROR)
            else:
                self.plugins.append(plugin)
                return plugin
        return None

    def provideDocks(self):
        """Creates docks and positions them as defined by :attr:`~esibd.core.PluginManager.pluginType`"""
        if not hasattr(self, 'topDock'): # else reuse old
            self.topDock = QDockWidget() # dummy to align other docks to
            self.topDock.setObjectName('topDock') # required to restore state
            QApplication.processEvents()
            self.topDock.hide()
        # * when using TopDockWidgetArea there is a superfluous separator on top of the statusbar -> use BottomDockWidgetArea
        # first 4 plugins define layout
        self.mainWindow.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.topDock)
        self.DeviceManager.provideDock()
        self.Settings.provideDock()
        self.Console.provideDock()
        self.Browser.provideDock()
        pluginTypeOrder = [self.TYPE.DEVICEMGR, self.TYPE.CONTROL, self.TYPE.CONSOLE, self.TYPE.CHANNELMANAGER, self.TYPE.INPUTDEVICE, self.TYPE.OUTPUTDEVICE, self.TYPE.SCAN]
        for plugin in sorted((plugin for plugin in self.plugins if plugin.pluginType in pluginTypeOrder),
            key=lambda x: pluginTypeOrder.index(x.pluginType)):
            # Note: self.TYPE.INTERNAL, self.TYPE.DISPLAY will be loaded by their parent items later if needed
            # self.logger.print(f'provideDocks {plugin.name} {plugin.version}', flag=PRINT.DEBUG)
            # display plugins will be initialized when needed, internal plugins do not need GUI
            try:
                plugin.provideDock()
            except Exception:
                self.logger.print(f'Could not load GUI of plugin {plugin.name} {plugin.version}: {traceback.format_exc()}', flag=PRINT.ERROR)
                delattr(self.__class__, plugin.name) # remove attribute
                self.plugins.pop(self.plugins.index(plugin)) # avoid any further undefined interaction
            self.splash.raise_() # some operations (likely tabifyDockWidget) will cause the main window to get on top of the splash screen

    def finalizeInit(self):
        """Finalize initialization after all other plugins have been initialized."""
        for plugin in self.plugins:
            QApplication.processEvents()
            if plugin.initializedDock:
                try:
                    plugin.finalizeInit()
                except Exception:
                    self.logger.print(f'Could not finalize plugin {plugin.name} {plugin.version}: {traceback.format_exc()}', flag=PRINT.ERROR)
                    plugin.closeGUI()
                    self.plugins.pop(self.plugins.index(plugin)) # avoid any further undefined interaction

    def afterFinalizeInit(self):
        """Finalize initialization after all other plugins have been initialized."""
        for plugin in self.plugins:
            QApplication.processEvents()
            if plugin.initializedDock:
                try:
                    plugin.afterFinalizeInit()
                except Exception:
                    self.logger.print(f'Could not complete finalization of plugin {plugin.name} {plugin.version}: {traceback.format_exc()}', flag=PRINT.ERROR)
                    plugin.closeGUI()
                    self.plugins.pop(self.plugins.index(plugin)) # avoid any further undefined interaction

    @property
    def testing(self):
        return self._testing or any([plugin._testing for plugin in self.plugins])
    @testing.setter
    def testing(self, state):
        # self.print(f'testing {state}', PRINT.DEBUG)
        self._testing = state

    def test(self):
        """ Calls :meth:`~esibd.core.PluginManager.runTestParallel` to test most features of for all plugins."""
        self.testing = True
        self.Settings.updateSessionPath() # avoid interference with undefined files from previous test run
        self.logger.print('Start testing.')
        time.sleep(1)
        timer = Timer(0, self.runTestParallel)
        timer.start()
        timer.name = 'TestingThread'
        self.Console.mainConsole.input.setText('PluginManager.stopTest()') # prepare to stop

    def stopTest(self):
        self.logger.print('Stopping test.')
        self.testing = False
        for plugin in self.plugins:
            plugin.signalComm.testCompleteSignal.emit()

    def runTestParallel(self):
        """Runs test of all plugins from parallel thread."""
        self.logger.print('Start testing all plugins.')
        # this will record the entire test session, consider compressing the file with third party software before publication
        self.DeviceManager.testControl(self.DeviceManager.videoRecorderAction, True)
        for plugin in self.plugins:
            self.logger.print(f'Starting testing for {plugin.name} {plugin.version}.')
            plugin.testing = True
            plugin.raiseDock(True)
            plugin.waitForCondition(condition=lambda: hasattr(plugin, 'videoRecorderAction'), timeoutMessage=f'dock of {plugin.name}')
            # if plugin is not self.DeviceManager:
            #     plugin.testControl(plugin.videoRecorderAction, True) # record manually -> more suitable for website
            plugin.runTestParallel()
            if not plugin.waitForCondition(condition=lambda: not plugin._testing, timeout=60, timeoutMessage=f'testing {plugin.name}'):
                plugin.signalComm.testCompleteSignal.emit()
            # if plugin is not self.DeviceManager:
            #     plugin.testControl(plugin.videoRecorderAction, False)
            if not self.testing:
                break
        self.DeviceManager.testControl(self.DeviceManager.videoRecorderAction, False)
        self.Console.testControl(self.Console.openLogAction, True, 1)
        self.testing = False

    def showThreads(self):
        self.Text.setText('\n'.join([thread.name for thread in threading.enumerate()]), True)

    def managePlugins(self):
        """A dialog to select which plugins should be enabled."""
        dlg = QDialog(self.mainWindow, Qt.WindowType.WindowStaysOnTopHint)
        dlg.resize(800, 400)
        dlg.setWindowTitle('Select Plugins')
        dlg.setWindowIcon(Icon(internalMediaPath / 'block--pencil.png'))
        lay = QGridLayout()
        tree = QTreeWidget()
        tree.setHeaderLabels(['', 'Name', 'Enabled', 'Version', 'Supported Version', 'Type', 'Preview File Types', 'Description (See tooltips!)'])
        tree.setColumnCount(8)
        tree.setRootIsDecorated(False)
        tree.header().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        tree.setColumnWidth(2, 50)
        tree.setColumnWidth(3, 50)
        tree.setColumnWidth(4, 50)
        tree.header().setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        tree.setColumnWidth(6, 150)
        root = tree.invisibleRootItem()
        lay.addWidget(tree)
        buttonBox = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttonBox.button(QDialogButtonBox.StandardButton.Ok).setText('Stop communication and reload plugins' if self.DeviceManager.initialized() else 'Reload plugins')
        buttonBox.accepted.connect(dlg.accept)
        buttonBox.rejected.connect(dlg.reject)
        lay.addWidget(buttonBox)
        confParser = configparser.ConfigParser()
        if self.pluginFile.exists():
            confParser.read(self.pluginFile)
        confParser[INFO] = infoDict('PluginManager')
        for name, item in confParser.items():
            if name != Parameter.DEFAULT.upper() and name != INFO:
                self.addPluginTreeWidgetItem(tree=tree, item=item, name=name)

        dlg.setLayout(lay)
        if dlg.exec():
            self.DeviceManager.closeCommunication(closing=True, message='Stopping communication before reloading plugins.')
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            for child in [root.child(i) for i in range(root.childCount())]:
                name = child.text(1)
                enabled = True
                internal = True
                if tree.itemWidget(child, 2) is not None:
                    enabled = (tree.itemWidget(child, 2)).isChecked()
                    internal = False
                if not internal:
                    confParser[name][self.ENABLED] = str(enabled)
            with open(self.pluginFile, 'w', encoding=UTF8) as configFile:
                confParser.write(configFile)
            self.closePlugins(reload=True)
            QApplication.restoreOverrideCursor()

    def addPluginTreeWidgetItem(self, tree, item, name):
        """Adds a row for given plugin. If not a core plugin it can be enabled or disabled using the checkbox."""
        pluginTreeWidget = QTreeWidgetItem(tree.invisibleRootItem())
        if item[self.ICONFILE] != '':
            pluginTreeWidget.setIcon(0, Icon(Path(item[self.DEPENDENCYPATH]) / (item[self.ICONFILEDARK] if getDarkMode() and item[self.ICONFILEDARK] != '' else item[self.ICONFILE])))
        else:
            pluginTreeWidget.setIcon(0, Icon(Path(item[self.DEPENDENCYPATH]) / ('help_large_dark.png' if getDarkMode() else 'help_large.png')))
        pluginTreeWidget.setText(1, name)
        if item[self.OPTIONAL] == 'True':
            checkbox = CheckBox()
            checkbox.setChecked(item[self.ENABLED] == 'True')
            tree.setItemWidget(pluginTreeWidget, 2, checkbox)
        versionLabel = QLabel()
        versionLabel.setText(item[self.VERSION])
        tree.setItemWidget(pluginTreeWidget, 3, versionLabel)
        supportedVersionLabel = QLabel()
        supportedVersionLabel.setText(item[self.SUPPORTEDVERSION])
        supportedVersionLabel.setStyleSheet(f"color: {'red' if not pluginSupported(item[self.SUPPORTEDVERSION]) else 'green'}")
        tree.setItemWidget(pluginTreeWidget, 4, supportedVersionLabel)
        typeLabel = QLabel()
        typeLabel.setText(item[self.PLUGINTYPE])
        tree.setItemWidget(pluginTreeWidget, 5, typeLabel)
        previewFileTypesLabel = QLabel()
        previewFileTypesLabel.setText(item[self.PREVIEWFILETYPES])
        previewFileTypesLabel.setToolTip(item[self.PREVIEWFILETYPES])
        tree.setItemWidget(pluginTreeWidget, 6, previewFileTypesLabel)
        descriptionLabel = QLabel()
        description = item[self.DESCRIPTION]
        if description is not None:
            descriptionLabel.setText(description.splitlines()[0][:100] )
            descriptionLabel.setToolTip(description)
        tree.setItemWidget(pluginTreeWidget, 7, descriptionLabel)

    def closePlugins(self, reload=False):
        """Closes all open connections and leave hardware in save state (e.g. voltage off)."""
        if reload:
            self.logger.print('Reloading Plugins.', flag=PRINT.EXPLORER)
            self.splash = SplashScreen()
            self.splash.show()
        else:
            self.logger.print('Closing Plugins.', flag=PRINT.EXPLORER)
        qSet.sync()
        self.loading = True # skip UI updates
        self.mainWindow.saveUiState()
        self.closing = not reload
        for plugin in self.plugins:
            try:
                plugin.closeGUI()
            except Exception: # pylint: disable = broad-except # we have no control about the exception a plugin can possibly throw
                # No unpredictable exception in a single plugin should break the whole application
                self.logger.print(f'Could not close plugin {plugin.name} {plugin.version}: {traceback.format_exc()}', PRINT.ERROR)
        if reload:
            # self.Explorer.print('Reloading Plugins.')
            self.loadPlugins(reload=True) # restore fails if plugins have been added or removed
            self.loading = False
        else:
            self.logger.close()

    def finalizeUiState(self):
        """Restores dimensions of core plugins."""
        self.Settings.raiseDock() # make sure settings tab visible after start
        # if len(self.DeviceManager.getActiveLiveDisplays()) > 1: UCM is last livedisplay
        #     self.DeviceManager.getActiveLiveDisplays()[0].raiseDock(True)
        self.Console.toggleVisible()
        QApplication.processEvents()

        width = qSet.value(SETTINGSWIDTH, self.Settings.mainDisplayWidget.width())
        if width is not None:
            self.Settings.mainDisplayWidget.setMinimumWidth(width)
            self.Settings.mainDisplayWidget.setMaximumWidth(width)
        height = qSet.value(SETTINGSHEIGHT, self.Settings.mainDisplayWidget.height())
        if height is not None:
            self.Settings.mainDisplayWidget.setMinimumHeight(height)
            self.Settings.mainDisplayWidget.setMaximumHeight(height)
        height = qSet.value(CONSOLEHEIGHT, self.Console.mainDisplayWidget.height())
        if height is not None and self.Settings.showConsoleAction.state:
            self.Console.mainDisplayWidget.setMinimumHeight(height)
            self.Console.mainDisplayWidget.setMaximumHeight(height)
        QTimer.singleShot(1000, self.resetMainDisplayWidgetLimits)
        self.Explorer.raiseDock() # only works if given at least .3 ms delay after loadPlugins completed
        self.Browser.raiseDock()

    def resetMainDisplayWidgetLimits(self):
        """Resets limits to allow for user scaling of plugin sizes."""
        # Needs to be called after releasing event loop or changes will not be applied.
        # QApplication.processEvents() is not sufficient
        self.Settings.mainDisplayWidget.setMinimumWidth(100)
        self.Settings.mainDisplayWidget.setMaximumWidth(10000)
        self.Settings.mainDisplayWidget.setMinimumHeight(50)
        self.Settings.mainDisplayWidget.setMaximumHeight(10000)
        self.Console.mainDisplayWidget.setMinimumHeight(50)
        self.Console.mainDisplayWidget.setMaximumHeight(10000)

    def getMainPlugins(self):
        """Returns all plugins found in the control section, including devices, controls, and scans."""
        return self.getPluginsByType([self.TYPE.INPUTDEVICE, self.TYPE.OUTPUTDEVICE, self.TYPE.CONTROL, self.TYPE.SCAN])

    def getPluginsByType(self, pluginTypes):
        """Returns all plugins of the specified type.

        :param pluginTypes: A single type or list of types.
        :type pluginTypes: :meth:`~esibd.core.PluginManager.TYPE`
        :return: List of matching plugins.
        :rtype: [:class:`~esibd.plugins.Plugin`]
        """
        if isinstance(pluginTypes, list):
            return [plugin for plugin in self.plugins if plugin.pluginType in pluginTypes]
        else:
            return [plugin for plugin in self.plugins if plugin.pluginType == pluginTypes]

    def getPluginsByClass(self, parentClasses):
        """Returns all plugins of the specified type.

        :param parentClasses: A single class or list of classes.
        :type parentClasses: class
        :return: List of matching plugins.
        :rtype: [:class:`~esibd.plugins.Plugin`]
        """
        return [plugin for plugin in self.plugins if isinstance(plugin, parentClasses)]

    def toggleTitleBarDelayed(self, update=False, delay=500):
        QTimer.singleShot(delay, lambda: self.toggleTitleBar(update=update))

    def toggleTitleBar(self, update=False):
        if not self.tabBars or update:
            # this is very expensive as it traverses the entire QObject hierarchy, but this is the only way to find a new tabbar that is created by moving docks around
            # keep reference to tabBars. this should only need update if dock topLevelChanged
            self.tabBars = self.mainWindow.findChildren(QTabBar)
        if self.tabBars:
            for tabBar in self.tabBars:
                # has to be called in main thread!
                tabBar.setStyleSheet(
        f'QTabBar::tab {{font-size: 1px; margin-right: -18px; color: transparent}}QTabBar::tab:selected {{font-size: 12px;margin-right: 0px; color: {colors.highlight}}}'
                        if getIconMode() == 'Icons' else '')
        if not self.loading:
            for plugin in self.plugins:
                if plugin.initializedDock:
                    plugin.toggleTitleBar()

    def updateTheme(self):
        """Updates application theme while showing a splash screen if necessary."""
        if not self.loading:
            splash = SplashScreen()
            splash.show()
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
        QWidget::separator          {{background-color:{colors.bgAlt2};    width:4px; height:4px;}}
        QToolBar{{background-color:{colors.bgAlt1}; margin:0px 0px 0px 0px;}}
        QToolBarExtension {{qproperty-icon: url({(internalMediaPath / 'chevron_double_dark.png').as_posix()
                                                 if getDarkMode() else (internalMediaPath / 'chevron_double_light.png').as_posix()});}}
        QToolTip{{background-color: {colors.bg}; color: {colors.fg}; border: black solid 1px}}
        QCheckBox::indicator         {{border:1px solid {colors.fg}; width: 12px;height: 12px;}}
        QCheckBox::indicator:checked {{border:1px solid {colors.fg}; width: 12px;height: 12px; image: url({(internalMediaPath / 'check_dark.png').as_posix()
                                                                                                           if getDarkMode() else (internalMediaPath / 'check.png').as_posix()})}}
        QTabBar::tab         {{margin:0px 0px 2px 0px; padding:4px; border-width:0px; }}
        QTabBar::tab:selected{{margin:0px 0px 0px 0px; padding:4px; border-bottom-width:2px; color:{colors.highlight}; border-bottom-color:{colors.highlight}; border-style:solid;}}"""
        # QMainWindow::separator Warning: The style sheet has no effect when the QDockWidget is undocked as Qt uses native top level windows when undocked.
        # QLineEdit     {{border-color:{fg}; border-width:1px; border-style:solid;}}
        # QPlainTextEdit{{border-color:{fg}; border-width:1px; border-style:solid;}}
        # QStatusBar::item {{border: 1px solid red;}}
        # QCheckBox::indicator{{border:1px solid {fg};}}
        # QWidget::separator:hover{{background-color:{colors.highlight}; width:4px; height:4px;}} # causes focus on hover -> other widgets loose focus -> no side effect when leaving out
        QApplication.setPalette(pal)
        self.mainWindow.setStyleSheet(self.styleSheet)
        plt.style.use('dark_background' if getDarkMode() else 'default')
        plt.rcParams['figure.facecolor']  = colors.bg
        plt.rcParams['axes.facecolor']  = colors.bg
        for plugin in self.plugins:
            if plugin.initializedDock:
                try:
                    plugin.updateTheme()
                except Exception:
                    self.logger.print(f'Error while updating plugin {plugin.name} theme: {traceback.format_exc()}')
        if not (self.loading or self.finalizing):
            self.mainWindow.setUpdatesEnabled(True)
            splash.close()
        self.toggleTitleBarDelayed(update=True)

    def reconnectSource(self, channel):
        if hasattr(self, 'PID'):
            self.PID.reconnectSource(channel.name)
        if hasattr(self, 'UCM'):
            self.UCM.reconnectSource(channel.name)

    def connectAllSources(self):
        if hasattr(self, 'PID'):
            self.PID.connectAllSources(update=True)
        if hasattr(self, 'UCM'):
            self.UCM.connectAllSources(update=True)

    def toggleVideoRecorder(self):
        show = self.Settings.showVideoRecorders
        for plugin in self.plugins:
            if plugin.initializedDock and hasattr(plugin, 'videoRecorderAction'):
                plugin.videoRecorderAction.setVisible(show)
                if hasattr(plugin, 'liveDisplay') and plugin.liveDisplayActive():
                    plugin.liveDisplay.videoRecorderAction.setVisible(show)
                if hasattr(plugin, 'staticDisplay') and plugin.staticDisplayActive():
                    plugin.staticDisplay.videoRecorderAction.setVisible(show)
                if hasattr(plugin, 'channelPlot') and plugin.channelPlotActive():
                    plugin.channelPlot.videoRecorderAction.setVisible(show)
                if hasattr(plugin, 'display') and plugin.displayActive():
                    plugin.display.videoRecorderAction.setVisible(show)

class Logger(QObject):
    """Redirects stderr and stdout to logfile while still sending them to :ref:`sec:console` as well.
    Also shows messages on Status bar.
    Use :meth:`~esibd.plugins.Plugin.print` to send messages to the logger."""

    printFromThreadSignal = pyqtSignal(str, str, PRINT)

    def __init__(self, pluginManager):
        """
        :param pluginManager: The central pluginManager
        :type pluginManager: :class:`~esibd.core.PluginManager`
        """
        super().__init__()
        self.pluginManager = pluginManager
        self.active = False
        self.lock = TimeoutLock(_parent=self)
        self.purgeTo = 10000
        self.purgeLimit = 30000
        self.lastCallTime = None
        self.errorCount = 0
        self.timer = QTimer()
        self.timer.timeout.connect(self.purge)
        self.timer.setInterval(3600000) # every 1 hour
        self.printFromThreadSignal.connect(self.print)
        self.backLog = [] # stores messages to be displayed later if console is not initialized
        if qSet.value(LOGGING, defaultValue='true', type=bool):
            self.open()

    def open(self):
        """Activates logging of Plugin.print statements, stdout, and stderr to the log file."""
        if not self.active:
            self.logFileName = validatePath(qSet.value(f'{GENERAL}/{CONFIGPATH}', defaultConfigPath), defaultConfigPath)[0] / f'{PROGRAM_NAME.lower()}.log'
            self.terminalOut = sys.stdout
            self.terminalErr = sys.stderr
            sys.stderr = sys.stdout = self # redirect all calls to stdout and stderr to the write function of our logger
            self.log = open(self.logFileName, 'a', encoding="utf-8-sig") # pylint: disable=consider-using-with # keep file open instead of reopening for every new line
            self.active = True
            self.timer.start()

    def openLog(self):
        """Opens the log file in an external program."""
        if self.logFileName.exists():
            openInDefaultApplication(self.logFileName)
        else:
            self.print('Start logging to create log file.')

    def write(self, message, flag=PRINT.MESSAGE):
        """Directs messages to terminal, log file, and :ref:`sec:console`.
        Called directly from stdout or stderr or indirectly via :meth:`~esibd.plugins.Plugin.print`."""
        if self.active:
            if self.terminalOut is not None: # after packaging with pyinstaller the program will not be connected to a terminal
                self.terminalOut.write(message) # write to original stdout
            with self.lock.acquire_timeout(1) as lock_acquired:
                if lock_acquired:
                    self.log.write(message) # write to log file
                    self.log.flush()
                # else:
                    # cannot print without using recursion

        if hasattr(self.pluginManager, 'Console') and self.pluginManager.Console.initializedGUI:
            # handles new lines in system error messages better than Console.repl.write()
            # needs to run in main_thread
            self.pluginManager.Console.write(message)
        else:
            self.backLog.append(message)

    def purge(self):
        # ca. 12 ms, only call once per hour. lock makes sure there is not race conditions with open reference
        with self.lock.acquire_timeout(1) as lock_acquired:
            if lock_acquired:
                with open(self.logFileName, 'r', encoding=UTF8) as original:
                    lines = original.readlines()
                if len(lines) > self.purgeLimit:
                    with open(self.logFileName, 'w', encoding="utf-8-sig") as purged:
                        for line in lines[-self.purgeTo:]:
                            purged.write(line)

    def print(self, message, sender=f'{PROGRAM_NAME} {PROGRAM_VERSION}', flag=PRINT.MESSAGE): # only used for program messages
        """Augments messages and redirects to log file, statusbar, and console.

        :param message: A short and descriptive message.
        :type message: str
        :param sender: The name of the sending plugin'
        :type sender: str, optional
        :param flag: Signals the status of the message, defaults to :attr:`~esibd.const.PRINT.MESSAGE`
        :type flag: :class:`~esibd.const.PRINT`, optional
        """
        if current_thread() is not main_thread():
            # redirect to main thread if needed to avoid changing GUI from parallel thread.
            self.printFromThreadSignal.emit(message, sender, flag)
            return
        match flag:
            case PRINT.DEBUG:
                if not getShowDebug():
                    return
                flagString = '🪲'
                # message = message + ' Stack: ' + ', '.join([trace.split('\n')[1].strip() for trace in traceback.format_stack(limit=8)[:-3] if trace.split('\n')[1].strip() != ''])
            case PRINT.WARNING:
                flagString = '⚠️'
            case PRINT.ERROR:
                flagString = '❌'
            case PRINT.EXPLORER:
                flagString = ' ❖'
            case _: # PRINT.MESSAGE
                flagString = 'ℹ️'
        timerString = ''
        if getShowDebug():
            ms = ((datetime.now()-self.lastCallTime).total_seconds() * 1000) if self.lastCallTime is not None else 0
            timerString = f'🕐 {ms:4.0f} ms '
            self.lastCallTime = datetime.now()
        first_line = message.split('\n')[0]
        message_status = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {sender}: {first_line}"
        message        = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {timerString}{flagString} {sender}: {message}"
        if self.active:
            print(message) # redirects to write if active
        else:
            print(message) # only to stdout if not active
            self.write(f'\n{message}') # call explicitly
        self.pluginManager.mainWindow.statusBar().showMessage(message_status)
        self.pluginManager.mainWindow.statusBar().setFlag(flag)

    def flush(self):
        """Flushes content to log file."""
        if self.active:
            self.log.flush()

    def close(self):
        """Disables logging and restores stdout and stderr."""
        if self.active:
            self.log.close()
            self.active = False
            sys.stdout = self.terminalOut # restore previous
            sys.stderr = self.terminalErr # restore previous
        self.timer.stop()

class CloseDialog(QDialog):
    """ Dialog to confirm closing the program."""
    def __init__(self, parent=None, title=f'Close {PROGRAM_NAME}?', ok='Close', prompt='Do you really want to close?'):
        super().__init__(parent)

        self.setWindowTitle(title)
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint)
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

class DynamicNp():
    """ A numpy.array that dynamically increases its size in increments to prevent frequent memory allocation while growing."""
    # based on https://stackoverflow.com/questions/7133885/fastest-way-to-grow-a-numpy-numeric-array
    def __init__(self, initialData=None, max_size=None, dtype=np.float32):
        # use float64 for time data
        self.init(initialData, max_size, dtype)

    def init(self, initialData=None, max_size=None, dtype=np.float32):
        self.data = np.zeros((2000,), dtype=dtype) if initialData is None or initialData.shape[0] == 0 else initialData
        self.capacity = self.data.shape[0]
        self.size = 0 if initialData is None else initialData.shape[0]
        self.max_size = max_size

    def add(self, x, lenT=None):
        """Adds the new data point and adjusts the data array as required.

        :param x: Datapoint to be added
        :type x: float
        :param lenT: length of corresponding time array, defaults to None
        :type lenT: int, optional
        """
        if lenT is not None:
            if self.size < lenT:
                # if length does not match length of time, e.g. because channel was enabled later then others or temporarily disabled,
                # pad data with NaN to ensure new data is aligned with time axis
                pad = np.zeros(lenT-self.size)
                pad[:] = np.nan
                self.init(np.hstack([self.get(), pad]), max_size=self.max_size) # append padding after existing data to account for time without data collection
            if self.size > lenT:
                self.init(self.get()[-lenT:], max_size=self.max_size) # remove data older than time axis
        if self.size == self.capacity:
            self.capacity *= 4
            newData = np.zeros((self.capacity,))
            newData[:self.size] = self.data
            self.data = newData
        if self.max_size is not None and self.size >= self.max_size:
            # Tested performance via console using
            # a = [EsibdCore.DynamicNp(initialData=np.ones(500000), max_size=90) for _ in range(1000)]
            # a[0].get().shape
            # timeit.timeit('[d.add(1) for d in a]', number=1, globals=globals())
            # resulting time 2.5 s -> negligible for all relevant use cases
            # thin out old data. use only every second value for first half of array to limit RAM use
            a, b = np.array_split(self.get(), 2) # split array in two halves # pylint: disable=[unbalanced-tuple-unpacking] # balance not relevant, as long as it is consistent
            self.size = a[1::2].shape[0]+b.shape[0] # only thin out older half, take every second item (starting with the second one to avoid keeping the first for every!)
            self.data[:self.size] = np.hstack([a[1::2], b]) # recombine
            # remove old data as new data is coming in. while this implementation is simpler it limits the length of stored history
            # self.data = np.roll(self.data,-1)
            # self.data[self.size-1] = x
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

        # * n cannot be determined internally as it has to match for multiple instances that may have different size (e.g. if one device is initialized later)
        # Solution A
        # perfect indices for smooth update but not very efficient
        # return self.data[np.concatenate((np.arange(x0, x0+2*n-np.remainder(x0+2*n, n)), np.arange(x0+2*n-np.remainder(x0+2*n, n), self.size-n, n), np.arange(self.size-n, self.size)))]
        # Solution B
        # length: typically length of array to return, relative to end of array. E.g. length relative to a certain point in time.
        # n: use every nth data point
        # simple and works but causes slow update when n is large
        # display update can be jumpy when large n is combined with short time period. This is very rare and can be avoided by slightly higher number of points
        if _min is not None and _max is not None:
            return self.data[_min:_max][::n]
        if _min is not None:
            return self.data[_min-np.remainder(_min, n):self.size][::n]
        return self.data[:self.size][::n] # returns everything
        # Solution C
        # pyqtgraph has build in down sampling, however in automatic mode it does not save as much performance.
        # if n is increased to get similar performance than the code above, the curves are flickering as the displayed points can change (roll) while new data comes in.

def parameterDict(name=None, value=None, default=None, _min=None, _max=None, toolTip=None, items=None, fixedItems=False, tree=None, widgetType=None, advanced=False, header=None,
                    widget=None, event=None, internal=False, attr=None, indicator=False, instantUpdate=True, displayDecimals=2):
    """Provides default values for all properties of a parameter.
    See :class:`~esibd.core.Parameter` for definitions.
    """
    return {Parameter.NAME : name, Parameter.VALUE : value, Parameter.DEFAULT : default if default is not None else value, Parameter.MIN : _min, Parameter.MAX : _max, Parameter.ADVANCED : advanced,
            Parameter.HEADER : header, Parameter.TOOLTIP : toolTip, Parameter.ITEMS : items, Parameter.FIXEDITEMS : fixedItems, Parameter.TREE : tree, Parameter.WIDGETTYPE : widgetType,
            Parameter.WIDGET : widget, Parameter.EVENT : event, Parameter.INTERNAL : internal, Parameter.ATTR : attr, Parameter.INDICATOR : indicator, Parameter.INSTANTUPDATE : instantUpdate,
            Parameter.DISPLAYDECIMALS : displayDecimals}

class Parameter():
    """Parameters are used by settings and channels. They take care
    of providing consistent user controls, linking events, input validation,
    context menus, and restoring values.
    Typically they are not initialized directly but via a :meth:`~esibd.core.parameterDict`
    from which settings and channels take the relevant information."""

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
    FIXEDITEMS  = 'FixedItems'
    TREE        = 'Tree'
    TOOLTIP     = 'Tooltip'
    EVENT       = 'Event'
    INTERNAL    = 'Internal'
    INDICATOR   = 'Indicator'
    INSTANTUPDATE = 'InstantUpdate'
    WIDGETTYPE  = 'WIDGETTYPE'
    DISPLAYDECIMALS  = 'DISPLAYDECIMALS'
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
        """A boolean, represented by a checkbox."""
        INT   = 'INT'
        """An integer spinbox."""
        FLOAT = 'FLOAT'
        """A floating point spinbox."""
        EXP   = 'EXP'
        """A spinbox with scientific format."""

    name : str
    """The parameter name. Only use last element of :attr:`~esibd.core.Parameter.fullName` in case its a path."""
    value : Any
    """The default value of the parameter in any supported type."""
    min : float
    """Minimum limit for numerical properties."""
    max : float
    """Maximum limit for numerical properties."""
    toolTip : str
    """Tooltip used to describe the parameter."""
    items : List[str]
    """List of options for parameters with a combobox."""
    fixedItems : bool
    """Indicates if list of items can be edited by the user or should remain fixed."""
    widgetType : TYPE
    """They type determines which widget is used to represent the parameter in the user interface."""
    advanced : bool
    """If True, parameter will only be visible in advanced mode."""
    header : str
    """Header used for the corresponding column in list of channels.
    The parameter name is used if not specified.
    Only applies to channel parameters."""
    widget : QWidget
    """A custom widget that will be used instead of the automatically provided one."""
    event : callable
    """A function that will be triggered when the parameter value changes."""
    internal : bool
    """Set to True to save parameter value in the registry (using QSetting)
    instead of configuration files. This can help to reduce clutter in
    configuration files and restore essential parameters even if
    configuration files get moved or lost."""
    attr : str
    """Allows direct access to the parameter. Only applies to channel and settings parameters.

    E.g. The *color* parameter of a channel specifies *attr=’color’*
    and can thus be accessed via *channel.color*.

    E.g. The *Session path* parameter in :class:`~esibd.plugins.Settings` specifies
    *attr=’sessionPath’* and can thus be accessed via
    *Settings.sessionPath*.

    E.g. The *interval* parameter of a device specifies
    *attr=’interval’* and can thus be accessed via *device.interval*.

    E.g. The *notes* parameter of a scan specifies *attr=’notes’* and
    can thus be accessed via *scan.notes*."""
    indicator : bool
    """Indicators cannot be edited by the user."""
    instantUpdate : bool
    """By default, events are triggered as soon as the value changes. If set
    to False, certain events will only be triggered if editing is
    finished by the *enter* key or if the widget loses focus."""
    displayDecimals : int
    """Number of decimal places to display if applicable."""
    print : callable
    """Reference to :meth:`~esibd.plugins.Plugin.print`."""
    fullName : str
    """Will contain path of setting in HDF5 file if applicable."""
    tree : QTreeWidget
    """None, unless the parameter is used for settings."""
    itemWidget : QTreeWidgetItem
    """None if parameter is part of a channel, otherwise it is part of a setting."""
    extraEvents : List[callable]
    """Used to add internal events on top of the user assigned ones."""

    def __init__(self, name, _parent=None, default=None, widgetType=None, index=1, items=None, fixedItems=False, widget=None, internal=False,
                    tree=None, itemWidget=None, toolTip=None, event=None, _min=None, _max=None, indicator=False, instantUpdate=True, displayDecimals=2):
        self._parent = _parent
        self.widgetType = widgetType if widgetType is not None else self.TYPE.LABEL
        self.index = index
        self.print = _parent.print
        self.fullName = name
        self.name = Path(name).name
        self.toolTip = toolTip
        self._items = items.split(',') if items is not None else None
        self.fixedItems = fixedItems
        self.tree = tree
        self.itemWidget = itemWidget
        self.widget = widget
        self.extraEvents = []
        self._valueChanged = False
        self.event = event
        self.internal = internal
        self.indicator = indicator
        self.instantUpdate = instantUpdate
        self.displayDecimals = displayDecimals
        self.rowHeight = self._parent.rowHeight if hasattr(self._parent, 'rowHeight') else QLineEdit().sizeHint().height() - 4
        self.check = None
        self.min = _min
        self.max = _max
        self.button = None
        self.spin = None
        self.loading = False
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
            return self.colorButton.color().name()
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
            value = value if isinstance(value,(bool, np.bool_)) else value in ['True', 'true'] # accepts strings (from ini file or qSet) and bools
            if self.check is not None:
                self.check.setChecked(value)
            else:
                self.button.setChecked(value)
        elif self.widgetType == self.TYPE.INT:
            self.spin.setValue(int(float(value)))
        elif self.widgetType in [self.TYPE.FLOAT, self.TYPE.EXP]:
            self.spin.setValue(float(value))
        elif self.widgetType == self.TYPE.COLOR:
            self.colorButton.setColor(value, True)
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
            self.line.setText(str(value)) # input may be of type Path from pathlib -> needs to be converted to str for display in lineEdit
        elif self.widgetType in [self.TYPE.LABEL, self.TYPE.PATH]:
            self.label.setText(str(value))
            self.label.setToolTip(str(value))
            if not self.indicator:
                self.changedEvent() # emit here as it is not emitted by the label

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

    def settingEvent(self):
        """Extend to manage changes to settings"""
        pass

    def changedEvent(self):
        if not (self.loading or self._parent.loading):
            self.settingEvent() # always save changes even when event is not triggered
            if not self.instantUpdate and self.widgetType in [self.TYPE.INT, self.TYPE.FLOAT, self.TYPE.EXP]:
                if self._valueChanged:
                    self._valueChanged = False # reset and continue event loop
                else:
                    return # ignore editingFinished if content has not changed
            # ! Settings event has to be triggered before main event to make sure internal parameters are updated and available right away
            # if self.event is not None or self.extraEvents:
            #     self.print(f'changeEvent for parameter {self._parent.name}.{self.fullName}', flag=PRINT.DEBUG)
            # ! if you have 100 channels which update at 10 Hz, changedEvent can be called 1000 times per second.
            # ! adding a print statement to the terminal, console plugin, and statusbar at that rate might make the application unresponsive.
            # ! only uncomment for specific tests. Note that the print statement is always ignored if debug mode is not active.
            for event in self.extraEvents:
                if event is not None:
                    event()
            if self.event is not None:
                self.event()

    def applyChangedEvent(self):
        """Assign events to the corresponding controls.
        Even indicators should be able to trigger events, e.g. to update dependent channels."""
        if self.widgetType in [self.TYPE.COMBO, self.TYPE.INTCOMBO, self.TYPE.FLOATCOMBO]:
            self.safeConnect(self.combo, self.combo.currentIndexChanged, self.changedEvent)
        elif self.widgetType == self.TYPE.TEXT:
            self.safeConnect(self.line, self.line.userEditingFinished , self.changedEvent)
        elif self.widgetType in [self.TYPE.INT, self.TYPE.FLOAT, self.TYPE.EXP]:
            if self.instantUpdate:
                # by default trigger events on every change, not matter if through user interface or software
                self.safeConnect(self.spin, self.spin.valueChanged, self.changedEvent)
            else:
                self.safeConnect(self.spin, self.spin.valueChanged, self.setValueChanged)
                self.safeConnect(self.spin, self.spin.editingFinished, self.changedEvent)
        elif self.widgetType == self.TYPE.BOOL:
            if isinstance(self.check, QCheckBox):
                self.safeConnect(self.check, self.check.stateChanged, self.changedEvent)
            elif isinstance(self.check, QAction):
                self.safeConnect(self.check, self.check.toggled, self.changedEvent)
            else: #isinstance(self.check, QToolButton, QPushButton)
                self.safeConnect(self.check, self.check.clicked, self.changedEvent)
        elif self.widgetType == self.TYPE.COLOR:
            self.safeConnect(self.colorButton, self.colorButton.sigColorChanged, self.changedEvent)
        elif self.widgetType in [self.TYPE.LABEL, self.TYPE.PATH]:
            pass # self.label.changeEvent.connect(self.changedEvent) # no change events for labels

    def safeConnect(self, control, signal, event):
        # make sure there is never more than one event assigned to a signal
        if control.receivers(signal) > 0:
            signal.disconnect()
        if event is not None:
            signal.connect(event)

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
        """Creates UI widget depending on :attr:`~esibd.core.Parameter.widgetType`.
        Links dedicated :attr:`~esibd.core.Parameter.widget` if provided.
        """
        # self.print(f'applyWidget {self.fullName} {self.widgetType}', flag=PRINT.DEBUG) # only uncomment for specific debugging
        if self.widgetType in [self.TYPE.COMBO, self.TYPE.INTCOMBO, self.TYPE.FLOATCOMBO]:
            self.combo = CompactComboBox() if self.widget is None else self.widget
            self.combo.setMaximumWidth(100)
            if self.widget is not None: # potentially reuse widget with old data!
                self.combo.clear()
            self.combo.wheelEvent = lambda event: None # disable wheel event to avoid accidental change of setting
            for item in [item.strip(' ') for item in self._items]:
                self.combo.insertItem(self.combo.count(), item)
            # self.combo.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            # self.combo.customContextMenuRequested.connect(self.initComboContextMenu)
        elif self.widgetType == self.TYPE.TEXT:
            self.line = self.widget if self.widget is not None else LineEdit(tree=self.tree)
            self.line.setFrame(False)
            if self.indicator:
                self.line.setEnabled(False)
        elif self.widgetType in [self.TYPE.INT, self.TYPE.FLOAT, self.TYPE.EXP]:
            if self.widget is None:
                if self.widgetType == self.TYPE.INT:
                    self.spin = QLabviewSpinBox(indicator=self.indicator)
                elif self.widgetType == self.TYPE.FLOAT:
                    self.spin = QLabviewDoubleSpinBox(indicator=self.indicator, displayDecimals=self.displayDecimals)
                else: # self.TYPE.EXP
                    self.spin = QLabviewSciSpinBox(indicator=self.indicator, displayDecimals=self.displayDecimals)
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
            if self.widget is None:
                self.colorButton = pg.ColorButton()
                self.colorButton.padding = (2, 2, -3, -3)
            else:
                self.colorButton = self.widget

        elif self.widgetType in [self.TYPE.LABEL, self.TYPE.PATH]:
            self.label = QLabel() if self.widget is None else self.widget

        if self.spin is not None: # apply limits # no limits by default to avoid unpredictable behavior.
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
        self.applyChangedEvent()

        self.getWidget().setToolTip(self.toolTip)
        self.getWidget().setMinimumHeight(self.rowHeight) # always keep entire row at consistent height
        self.getWidget().setMaximumHeight(self.rowHeight)
        self.getWidget().setObjectName(self.fullName)
        self.getWidget().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.getWidget().customContextMenuRequested.connect(self.initContextMenu)

    def containerize(self, widget):
        # just hiding widget using setVisible(False) is not reliable due to bug https://bugreports.qt.io/browse/QTBUG-13522
        # use a wrapping container as a workaround https://stackoverflow.com/questions/71707347/how-to-keep-qwidgets-in-qtreewidget-hidden-during-resize?noredirect=1#comment126731693_71707347
        container = QWidget()
        containerLayout = QGridLayout(container)
        containerLayout.setContentsMargins(0, 0, 0, 0)
        widget.setSizePolicy(QSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.MinimumExpanding))
        widget.container = container # used to have proper background color independent of widget visibility
        containerLayout.addWidget(widget)
        return container

    def setHeight(self, height=None):
        if self.widgetType not in [self.TYPE.COMBO, self.TYPE.INTCOMBO, self.TYPE.BOOL, self.TYPE.COLOR, self.TYPE.FLOATCOMBO, self.TYPE.TEXT,self.TYPE.INT, self.TYPE.FLOAT, self.TYPE.EXP, self.TYPE.LABEL, self.TYPE.PATH]:
            return
        if height is None:
            height = self.rowHeight
        scaling = height / (QLineEdit().sizeHint().height() - 4)
        self.rowHeight = height
        self.getWidget().setMinimumHeight(self.rowHeight)
        self.getWidget().setMaximumHeight(self.rowHeight)
        font = self.getWidget().font()
        font.setPointSize(int(height/2))
        if self.widgetType in [self.TYPE.COMBO, self.TYPE.INTCOMBO, self.TYPE.FLOATCOMBO]:
            self.combo.setFont(font)
        elif self.widgetType == self.TYPE.TEXT:
            self.line.setFont(font)
        elif self.widgetType in [self.TYPE.INT, self.TYPE.FLOAT, self.TYPE.EXP]:
            self.spin.setMinimumWidth(int(scaling*50)+10) # empirical fixed width
            self.spin.lineEdit().setFont(font)
        elif self.widgetType == self.TYPE.BOOL:
            if isinstance(self.check, QCheckBox):
                checkBoxHeight = min(self.rowHeight-4, QCheckBox().sizeHint().height()-2)
                self.check.checkBoxHeight = checkBoxHeight # remember for updateColor
                self.check.setStyleSheet(f'QCheckBox::indicator {{ width: {checkBoxHeight}; height: {checkBoxHeight};}}')
            else: #isinstance(self.check, QToolButton, QPushButton)
                iconHeight = min(self.rowHeight, QCheckBox().sizeHint().height())
                self.check.setFont(font)
                self.check.setIconSize(QSize(iconHeight, iconHeight))
        # elif self.widgetType == self.TYPE.COLOR:
        #     self.colorButton
        elif self.widgetType in [self.TYPE.LABEL, self.TYPE.PATH]:
            self.label.setFont(font)

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
            return self.colorButton
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
            self.changedEvent() # is not triggered by setItemText

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
        if self.widgetType == self.TYPE.BOOL:
            return self.value == value if isinstance(value,(bool, np.bool_)) else self.value == (value in ['True', 'true']) # accepts strings (from ini file or qSet) and bools
        elif self.widgetType in [self.TYPE.INT, self.TYPE.INTCOMBO]:
            return self.value == int(value)
        elif self.widgetType in [self.TYPE.FLOAT, self.TYPE.FLOATCOMBO]:
            return f'{self.value:.{self.displayDecimals}f}' == f'{float(value):.{self.displayDecimals}f}'
        elif self.widgetType == self.TYPE.EXP:
            return f'{self.value:.{self.displayDecimals}e}' == f'{float(value):.{self.displayDecimals}e}'
        elif self.widgetType == self.TYPE.COLOR:
            return self.value == value.name() if isinstance(value, QColor) else self.value == value
        elif self.widgetType in [self.TYPE.TEXT, self.TYPE.LABEL, self.TYPE.PATH]:
            return self.value == str(value) # input may be of type Path from pathlib -> needs to be converted to str for display in lineEdit
        else:
            return self.value == value

    def formatValue(self, value=None):
        value = value if value is not None else self.value
        if value is None:
            return str(value)
        if self.widgetType in [self.TYPE.INT, self.TYPE.INTCOMBO]:
            return f'{int(value)}'
        elif self.widgetType in [self.TYPE.FLOAT, self.TYPE.FLOATCOMBO, self.TYPE.EXP]:
            if self.widgetType == self.TYPE.EXP:
                return f'{float(value):.{self.displayDecimals}e}'
            else:
                return f'{float(value):.{self.displayDecimals}f}'
        else:
            return str(value)

    def initContextMenu(self, pos):
        self._parent.initSettingsContextMenuBase(self, self.getWidget().mapToGlobal(pos))

class Setting(QTreeWidgetItem, Parameter):
    """Parameter to be used as general settings with dedicated UI controls instead of being embedded in a channel."""
    def __init__(self, value=None, parentItem=None, advanced=False, **kwargs):
        # use keyword arguments rather than positional to avoid issues with multiple inheritance
        # https://stackoverflow.com/questions/9575409/calling-parent-class-init-with-multiple-inheritance-whats-the-right-way
        super().__init__(**kwargs)
        self.advanced = advanced # only display this parameter in advanced mode
        if self.tree is not None: # some settings may be attached to dedicated controls
            self.parentItem = parentItem
            self.parentItem.addChild(self) # has to be added to parent before widgets can be added!
            self.setData(0, Qt.ItemDataRole.DisplayRole, self.name)
            self.setToolTip(0, self.toolTip)
            self.applyWidget()
        self.loading = True
        if self.internal:
            if self.widget is not None:
                if self._items is not None:
                    self._items = qSet.value(self.fullName+self.ITEMS).split(',') if qSet.value(self.fullName+self.ITEMS) is not None else self._items
                self.applyWidget()
            self.value = qSet.value(self.fullName, self.default) # trigger assignment to widget
        else:
            self.value = value # use setter to distinguish data types based on other fields
        self.loading = False

    def setWidget(self, widget):
        """Allows to change to custom widget after initialization. E.g. to move a setting to a more logical position outside the Settings tree."""
        initialValue = self.value
        self.widget = widget
        self.applyWidget() # will overwrite ToolTip -> restore if value specific
        self.loading = True # only change widget, do not trigger event when value is restored
        self.value = initialValue
        self.loading = False
        self.parentItem.removeChild(self) # remove old entry from tree

    def resetWidget(self):
        """Returns widget back to the Settings tree."""
        initialValue = self.value
        self.widget = None
        self.parentItem.addChild(self)
        self.applyWidget()
        self.loading = True # only change widget, do not trigger event when value is restored
        self.value = initialValue
        self.loading = False

    def settingEvent(self):
        """Executes internal validation based on setting type.
        Saves parameters to file or qSet to make sure they can be restored even after a crash.
        Finally executes setting specific event if applicable."""
        if not self.indicator: # setting indicators should never need to trigger events
            if self.widgetType == self.TYPE.PATH:
                path, changed = validatePath(self.value, self.default)
                if changed:
                    self.value = path
            if self.internal:
                qSet.setValue(self.fullName, self.value)
                if self._items is not None:
                    qSet.setValue(self.fullName+self.ITEMS, ','.join(self.items))
            else: # save non internal parameters to file
                self._parent.saveSettings(default=True)

class RelayChannel():

    def getRecordingData(self):
        return self.recordingData.get() if isinstance(self.recordingData, DynamicNp) else self.recordingData

    def getDevice(self):
        return self.sourceChannel.getDevice() if self.sourceChannel is not None else self.device

    def subtractBackgroundActive(self):
        return self.sourceChannel.getDevice().subtractBackgroundActive() if self.sourceChannel is not None else False

    @property
    def recording(self):
        return self.sourceChannel.getDevice().recording if self.sourceChannel is not None else False

    def getValues(self, length=None, _min=None, _max=None, n=1, subtractBackground=None):
        return self.sourceChannel.getValues(length, _min, _max, n, subtractBackground) if self.sourceChannel is not None else None

    @property
    def value(self):
        if self.sourceChannel is not None:
            return self.sourceChannel.value
            # leave decision to subtract background to be handled explicitly at higher level.
            # return self.sourceChannel.value - self.sourceChannel.background if self.subtractBackgroundActive() else self.sourceChannel.value
        # elif len(self.getRecordingData()) > 0: # no valid use case so far
        #     return self.getRecordingData()[-1]
        else:
            return None
    @value.setter
    def value(self, value):
        if self.sourceChannel is not None:
            self.sourceChannel.value = value

    @property
    def enabled(self):
        return self.sourceChannel.enabled if self.sourceChannel is not None else False

    @property
    def active(self):
        return self.sourceChannel.active if self.sourceChannel is not None else True

    @property
    def real(self):
        return self.sourceChannel.real if self.sourceChannel is not None else False

    @property
    def acquiring(self):
        return self.sourceChannel.acquiring if self.sourceChannel is not None else False

    @property
    def min(self):
        return self.sourceChannel.min if self.sourceChannel is not None else None

    @property
    def max(self):
        return self.sourceChannel.max if self.sourceChannel is not None else None

    # @property # implement channel specific, some may prefer to use their internal display!
    # def display(self):
    #     if hasattr(self, 'display'):
    #         return self.display
    #     return self.sourceChannel.display if self.sourceChannel is not None else True

    @property
    def smooth(self):
        return self.sourceChannel.smooth if self.sourceChannel is not None else 0

    # @property # implement channel specific,
    # def unit(self):
    #     return self.sourceChannel.unit if self.sourceChannel is not None else self._unit

    @property
    def color(self):
        return self.sourceChannel.color if self.sourceChannel is not None else '#ffffff'

    @property
    def linewidth(self):
        return self.sourceChannel.linewidth if self.sourceChannel is not None else 4

    @property
    def linestyle(self):
        return self.sourceChannel.linestyle if self.sourceChannel is not None else 'solid'

    def getQtLineStyle(self):
        return self.sourceChannel.getQtLineStyle() if self.sourceChannel is not None else Qt.PenStyle.DotLine

    @property
    def logY(self):
        if self.sourceChannel is not None:
            return self.sourceChannel.logY
        elif self.unit in ['mbar', 'Pa']:
            return True
        else:
            return False

class MetaChannel(RelayChannel):
    """Manages metadata associated with a channel by a :class:`~esibd.plugins.Scan` or :class:`~esibd.plugins.LiveDisplay`.
    Allows to restore data even if corresponding channels do not exist anymore.

    name : str
        The scan channel name is usually the same as the name of the corresponding
        :class:`~esibd.core.Channel`.
    data : numpy.array
        Scan data is saved and restored automatically.
        Each scan is free to define its data with arbitrary dimensions.
    initial : var
        Initial value. Used to restore all conditions after scan has completed.
    background : numpy.array
        If used, has to be of same dimension as data.
    unit : str
        The channel unit.
    channel: :class:`~esibd.core.PluginManager`
        The actual channel, if it exists.
    """

    def __init__(self, parentPlugin=None, name=None, unit='', recordingData=None, initialValue=None, recordingBackground=None, inout=None):
        self.parentPlugin = parentPlugin
        self.name = name
        self.recordingData = recordingData
        self.initialValue = initialValue
        self.recordingBackground = recordingBackground
        self.unit = unit
        self.sourceChannel = None
        self.inout = inout
        self.updateValueSignal = None
        self.connectSource()

    def connectSource(self):
        # Will only be called when using MetaChannel directly. ScanChannel will implements its own version.
        if self.name == 'Time':
            return
        if self.inout is None:
            self.sourceChannel = self.parentPlugin.pluginManager.DeviceManager.getChannelByName(self.name, inout=INOUT.OUT)
            if self.sourceChannel is None:
                self.sourceChannel = self.parentPlugin.pluginManager.DeviceManager.getChannelByName(self.name, inout=INOUT.IN)
        else:
            self.sourceChannel = self.parentPlugin.pluginManager.DeviceManager.getChannelByName(self.name, inout=self.inout)
        if self.sourceChannel is not None:
            self.initialValue = self.sourceChannel.value
            self.unit = self.sourceChannel.unit
            self.updateValueSignal = self.sourceChannel.signalComm.updateValueSignal

    def display(self):
        return self.sourceChannel.display if self.sourceChannel is not None else True

class Channel(QTreeWidgetItem):
    """A :class:`channel<esibd.core.Channel>` represents a virtual or real parameter and manages all data and
    metadata related to that parameter. Each :ref:`device<sec:devices>` can only have one
    type of channel, but channels have dynamic interfaces that allow to
    account for differences in the physical backend.

    Channels provide a consistent and structured interface to inputs and
    outputs. In the advanced mode, channels can be duplicated, moved, or
    deleted. You may also edit channels directly in the corresponding .ini
    file in the config path (import after edit or changes will be lost).

    Channels are accessible from any plugin using :meth:`~esibd.plugins.DeviceManager.getChannelByName`.
    This, and other features like linking channels by equations, depends on the usage of unique and descriptive channel names.
    """

    class SignalCommunicate(QObject):
        updateValueSignal = pyqtSignal(float)

    device : any # Device, avoid circular import
    """The :class:`~esibd.plugins.Device` containing this channel."""
    print : callable
    """Reference to :meth:`~esibd.plugins.Plugin.print`."""
    tree : QTreeWidget
    """TreeWidget containing the channel widgets."""
    inout : INOUT
    """Reference to :class:`~esibd.plugins.Device.inout`."""
    plotCurve : pyqtgraph.PlotCurveItem
    """The plotCurve in the corresponding :class:`~esibd.plugins.LiveDisplay`."""
    lastAppliedValue : any
    """Reference to last value. Allows to decide if hardware update is required."""
    parameters : Parameter
    """List of channel parameters."""
    displayedParameters : List[str]
    """List of parameters that determines which parameters are shown in the
       user interface and in what order. Compare :meth:`~esibd.core.Channel.insertDisplayedParameter`.
       If your custom parameter is not in this list it will not be visible in the user interface."""
    values : DynamicNp
    """The history of values shown in the :class:`~esibd.plugins.LiveDisplay`.
       Use :meth:`~esibd.core.Channel.getValues` to get a plain numpy.array."""
    backgrounds : DynamicNp
    """List of backgrounds. Only defined if corresponding device uses backgrounds."""

    def __init__(self, device=None, tree=None):
        super().__init__() # need to init without tree, otherwise channels will always appended to the end when trying to change order using insertTopLevelItem
        self.device = device
        self.parentPlugin = device # name may be more appropriate for some use cases
        self.print = self.device.print
        self.convertDataDisplay = self.device.convertDataDisplay if hasattr(self.device, 'convertDataDisplay') else None
        self.useDisplays = self.device.useDisplays if hasattr(self.device, 'useDisplays') else False
        self.useBackgrounds = self.device.useBackgrounds if hasattr(self.device, 'useBackgrounds') else False
        self.useMonitors = self.device.useMonitors if hasattr(self.device, 'useMonitors') else False
        if hasattr(self.device, 'logY'):
            self.logY = self.device.logY
        self.tree = tree # may be None for internal default channels
        self.plotCurve = None
        self.rowHeight = QLineEdit().sizeHint().height() - 4
        self.signalComm = self.SignalCommunicate()
        self.signalComm.updateValueSignal.connect(self.updateValueParallel)
        self.lastAppliedValue = None # keep track of last value to identify what has changed
        self.parameters = []
        self.displayedParameters = []
        self.values = DynamicNp(max_size=self.device.maxDataPoints if hasattr(self.device, 'maxDataPoints') else None)
        self.inout = self.device.inout if hasattr(self.device, 'inout') else INOUT.NONE
        self.controller = None
        self.defaultStyleSheet = None # will be initialized when color is set
        self.warningStyleSheet = 'background: rgb(255,0,0)'
        self.warningState = False

        if self.inout != INOUT.NONE and self.useBackgrounds:
                # array of background history. managed by instrument manager to keep timing synchronous
                self.backgrounds = DynamicNp(max_size=self.device.maxDataPoints if hasattr(self.device, 'maxDataPoints') else None)

        # self.value = None # will be replaced by wrapper
        # generate property for direct access of parameter values
        # note: this assigns properties directly to class and only works as it uses a method that is specific to the current instance
        for name, default in self.getSortedDefaultChannel().items():
            if Parameter.ATTR in default and default[Parameter.ATTR] is not None:
                setattr(self.__class__, default[Parameter.ATTR], makeWrapper(name))

        for i, (name, default) in enumerate(self.getSortedDefaultChannel().items()):
            self.parameters.append(Parameter(_parent=self, name=name, widgetType=default[Parameter.WIDGETTYPE],
                                                    items=default[Parameter.ITEMS] if Parameter.ITEMS in default else None,
                                                    fixedItems=default[Parameter.FIXEDITEMS] if Parameter.FIXEDITEMS in default else False,
                                                    _min=default[Parameter.MIN] if Parameter.MIN in default else None,
                                                    _max=default[Parameter.MAX] if Parameter.MAX in default else None,
                                                    toolTip=default[Parameter.TOOLTIP] if Parameter.TOOLTIP in default else None,
                                                    internal=default[Parameter.INTERNAL] if Parameter.INTERNAL in default else False,
                                                    indicator=default[Parameter.INDICATOR] if Parameter.INDICATOR in default else False,
                                                    instantUpdate=default[Parameter.INSTANTUPDATE] if Parameter.INSTANTUPDATE in default else True,
                                                    displayDecimals=default[Parameter.DISPLAYDECIMALS] if Parameter.DISPLAYDECIMALS in default else 2,
                                                    itemWidget=self, index=i, tree=self.tree,
                                                    event=default[Parameter.EVENT] if Parameter.EVENT in default else None))
    HEADER      = 'HEADER'
    SELECT      = 'Select'
    COLLAPSE    = 'Collapse'
    ENABLED     = 'Enabled'
    NAME        = 'Name'
    VALUE       = 'Value'
    BACKGROUND  = 'Background'
    EQUATION    = 'Equation'
    DISPLAY     = 'Display'
    ACTIVE      = 'Active'
    REAL        = 'Real'
    SMOOTH      = 'Smooth'
    LINEWIDTH   = 'Linewidth'
    LINESTYLE   = 'Linestyle'
    DISPLAYGROUP= 'Group'
    SCALING     = 'Scaling'
    COLOR       = 'Color'
    MIN         = 'Min'
    MAX         = 'Max'
    OPTIMIZE    = 'Optimize'
    MONITOR     = 'Monitor'
    UNIT        = 'Unit'
    ADDITEM     = 'Add Item'
    EDITITEM    = 'Edit Item'
    REMOVEITEM  = 'Remove Item'
    ADDPARTOCONSOLE  = 'Add Parameter to Console'
    ADDCHANTOCONSOLE  = 'Add Channel to Console'
    NOTES        = 'Notes'

    @property
    def loading(self):
        return self.getDevice().loading

    @property
    def unit(self):
        return self.getDevice().unit

    @property
    def time(self):
        return self.getDevice().time

    @property
    def acquiring(self):
        if self.controller is not None:
            return self.controller.acquiring
        elif self.getDevice().controller is not None:
            return self.getDevice().controller.acquiring
        else:
            return False

    def getDefaultChannel(self):
        """ Defines parameter(s) of the default channel.
        This is also use to assign widgetTypes and if settings are visible outside of advanced mode.
        See :meth:`~esibd.core.parameterDict`.
        If parameters do not exist in the settings file, the default parameter will be added.
        Overwrite in dependent classes as needed.
        """
        channel = {}
        channel[self.COLLAPSE] = parameterDict(value=False, widgetType=Parameter.TYPE.BOOL,
                                    toolTip='Collapses all channels of same color below.', event=lambda: self.collapseChanged(toggle=True), attr='collapse', header= '',)
        channel[self.SELECT  ] = parameterDict(value=False, widgetType=Parameter.TYPE.BOOL, advanced=True,
                                    toolTip='Select channel for deleting, moving, or duplicating.', event=lambda: self.device.channelSelection(selectedChannel = self), attr='select')
        channel[self.ENABLED ] = parameterDict(value=True, widgetType=Parameter.TYPE.BOOL, advanced=True,
                                    header= 'E', toolTip='If enabled, channel will communicate with the device.',
                                    event=lambda: self.enabledChanged(), attr='enabled')
        channel[self.NAME    ] = parameterDict(value=f'{self.device.name}_parameter', widgetType=Parameter.TYPE.TEXT, advanced=False, attr='name',
                                               event=lambda: self.nameChanged())
        channel[self.VALUE   ] = parameterDict(value=np.nan if self.inout == INOUT.OUT else 0,
                                               widgetType=Parameter.TYPE.EXP if hasattr(self.device, 'logY') and self.device.logY else Parameter.TYPE.FLOAT,
                                               advanced=False, header='Unit', attr='value',
                                               event=lambda: self.device.pluginManager.DeviceManager.globalUpdate(inout=self.inout) if self.inout == INOUT.IN else None,
                                               indicator=self.inout == INOUT.OUT)
        channel[self.EQUATION] = parameterDict(value='', widgetType=Parameter.TYPE.TEXT, advanced=True, attr='equation',
                                    event=lambda: self.equationChanged())
        channel[self.ACTIVE  ] = parameterDict(value=True, widgetType=Parameter.TYPE.BOOL, advanced=True,
                                    header='A', toolTip='If not active, value will be determined from equation.',
                                    event=lambda: self.activeChanged(), attr='active')
        channel[self.REAL    ] = parameterDict(value=True, widgetType=Parameter.TYPE.BOOL, advanced=True,
                                    header='R', toolTip='Check for physically exiting channels.',
                                    event=lambda: self.realChanged(), attr='real')
        channel[self.SCALING ] = parameterDict(value='normal', default='normal', widgetType=Parameter.TYPE.COMBO, advanced=True, attr='scaling', event=lambda: self.scalingChanged(),
                                                       items='small, normal, large, larger, huge', toolTip='Scaling used to display channels.')
        # * avoid using middle gray colors, as the bitwise NOT which is used for the caret color has very poor contrast
        # https://stackoverflow.com/questions/55877769/qt-5-8-qtextedit-text-cursor-color-wont-change
        channel[self.COLOR   ] = parameterDict(value='#e8e8e8', widgetType=Parameter.TYPE.COLOR, advanced=True,
                                    event=lambda: self.updateColor(), attr='color')
        if self.useMonitors:
            channel[self.MONITOR] = parameterDict(value=np.nan, widgetType=Parameter.TYPE.FLOAT, advanced=False,
                                                  event=lambda: self.monitorChanged(), attr='monitor', indicator=True)
        if self.useDisplays:
            channel[self.DISPLAY   ] = parameterDict(value=True, widgetType=Parameter.TYPE.BOOL, advanced=False,
                                        header='D', toolTip='Display channel history.',
                                        event=lambda: self.updateDisplay(), attr='display')
            channel[self.SMOOTH  ] = parameterDict(value='0', widgetType=Parameter.TYPE.INTCOMBO, advanced=True,
                                            items='0, 2, 4, 8, 16, 32', attr='smooth',
                                            # event=lambda: self.updateDisplay(), # update display causes distracting rescaling ->
                                            # should only be relevant for live data anyways, but if needed updateDisplay can be triggered by any of the other parameters like linewidth or displaytime
                                            toolTip='Smooth using running average with selected window.')
            channel[self.LINEWIDTH  ] = parameterDict(value='4', widgetType=Parameter.TYPE.INTCOMBO, advanced=True,
                                            items='2, 4, 6, 8, 10, 12, 14, 16', attr='linewidth', event=lambda: self.updateDisplay(), toolTip='Line width used in plots.')
            channel[self.LINESTYLE  ] = parameterDict(value='solid', widgetType=Parameter.TYPE.COMBO, advanced=True,
                                            items='solid, dotted, dashed, dashdot', attr='linestyle', event=lambda: self.updateDisplay(), toolTip='Line style used in plots.')
            channel[self.DISPLAYGROUP] = parameterDict(value='1', default='1', widgetType=Parameter.TYPE.COMBO, advanced=True, attr='displayGroup', event=lambda: self.updateDisplay(),
                                                           items='0, 1, 2, 3, 4, 5', fixedItems=False, toolTip='Used to group channels in the live display.')
        if self.inout == INOUT.IN:
            channel[self.MIN     ] = parameterDict(value=-50, widgetType=Parameter.TYPE.FLOAT, advanced=True,
                                    event=lambda: self.updateMin(), attr='min', header='Min       ')
            channel[self.MAX     ] = parameterDict(value=+50, widgetType=Parameter.TYPE.FLOAT, advanced=True,
                                    event=lambda: self.updateMax(), attr='max', header='Max       ')
            channel[self.OPTIMIZE] = parameterDict(value=False, widgetType=Parameter.TYPE.BOOL, advanced=False,
                                    header='O', toolTip='Selected channels will be optimized using GA.', attr='optimize')
        if self.useBackgrounds:
            channel[self.BACKGROUND] = parameterDict(value=0, widgetType=Parameter.TYPE.FLOAT, advanced=False,
                                header='BG      ', attr='background')
        return channel

    def getSortedDefaultChannel(self):
        """Returns default channel sorted in the order defined by :attr:`~esibd.core.Channel.displayedParameters`."""
        self.setDisplayedParameters()
        return {k: self.getDefaultChannel()[k] for k in self.displayedParameters}

    def insertDisplayedParameter(self, parameter, before):
        """Inserts your custom parameter before an existing parameter in :attr:`~esibd.core.Channel.displayedParameters`.

        :param parameter: The new parameter to insert.
        :type parameter: :class:`~esibd.core.Parameter`
        :param before: The existing parameter before which the new one will be placed.
        :type before: :class:`~esibd.core.Parameter`
        """
        self.displayedParameters.insert(self.displayedParameters.index(before), parameter)

    def setDisplayedParameters(self):
        """Used to determine which parameters to use and in what order.
        Extend using :meth:`~esibd.core.Channel.insertDisplayedParameter` to add more parameters."""
        if self.useDisplays:
            self.displayedParameters = [self.COLLAPSE, self.SELECT, self.ENABLED, self.NAME, self.VALUE, self.EQUATION, self.DISPLAY,
                                    self.ACTIVE, self.REAL, self.SMOOTH, self.LINEWIDTH, self.LINESTYLE, self.DISPLAYGROUP, self.SCALING, self.COLOR]
        else:
            self.displayedParameters = [self.COLLAPSE, self.SELECT, self.ENABLED, self.NAME, self.VALUE, self.EQUATION,
                                    self.ACTIVE, self.REAL, self.SCALING, self.COLOR]
        if self.useMonitors:
            self.displayedParameters.insert(self.displayedParameters.index(self.VALUE)+1, self.MONITOR)
        if self.inout == INOUT.IN:
            self.insertDisplayedParameter(self.MIN, before=self.EQUATION)
            self.insertDisplayedParameter(self.MAX, before=self.EQUATION)
            self.insertDisplayedParameter(self.OPTIMIZE, before=self.DISPLAY)
        if self.inout != INOUT.NONE and self.useBackgrounds:
            self.insertDisplayedParameter(self.BACKGROUND, before=self.DISPLAY)

    def tempParameters(self):
        """List of parameters, such as live signal or status, that will not be saved and restored."""
        tempParameters = []
        if self.inout == INOUT.OUT:
            tempParameters.append(self.VALUE)
        if self.useBackgrounds:
            tempParameters.append(self.BACKGROUND)
        if self.useMonitors:
            tempParameters.append(self.MONITOR)
        return tempParameters

    def getParameterByName(self, name):
        parameter = next((parameter for parameter in self.parameters if parameter.name.strip().lower() == name.strip().lower()), None)
        if parameter is None:
            self.print(f'Could not find parameter {name}.', PRINT.WARNING)
        return parameter

    def asDict(self, temp=False, formatValue=False):
        """Returns a dictionary containing all channel parameters and their values.

        :param temp: If true, dict will contain temporary parameters
        :type temp: bool, optional
        """
        _dict = {}
        for parameter in self.parameters:
            if temp or parameter.name not in self.tempParameters():
                _dict[parameter.name] = parameter.formatValue() if formatValue else parameter.value
        return _dict

    def updateValueParallel(self, value): # used to update from external threads
        self.value = value # pylint: disable=[attribute-defined-outside-init] # attribute defined by makeWrapper

    def activeChanged(self):
        self.toggleBackgroundVisible()
        self.updateColor()
        if not self.device.loading:
            self.device.pluginManager.DeviceManager.globalUpdate(inout=self.inout)

    def equationChanged(self):
        if not self.device.loading:
            self.device.pluginManager.DeviceManager.globalUpdate(inout=self.inout)

    def collapseChanged(self, toggle=True):
        self.getParameterByName(self.COLLAPSE).getWidget().setIcon(self.device.makeCoreIcon('toggle-expand.png' if self.collapse else 'toggle.png'))
        if toggle and not self.device.loading: # otherwise only update icon
            self.device.toggleAdvanced()

    def appendValue(self, lenT, nan=False):
        """Appends a datapoint to the recorded values.

        :param lenT: length of corresponding time array, defaults to None
        :type lenT: int, optional
        :param nan: If true, np.nan is used instead of current value. This should mark a new collection and prevent interpolation in regions without data.
        :type nan: bool
        """
        if nan:
            if self.inout == INOUT.OUT:
                self.value=np.nan # keep user defined value for input devices, leave undefined until output device provides value
            if self.useMonitors:
                self.monitor = np.nan
            self.values.add(x=np.nan, lenT=lenT)
        else:
            self.values.add(x=self.monitor if (self.useMonitors and self.enabled and self.real) else self.value, lenT=lenT)
        if self.useBackgrounds:
            self.backgrounds.add(x=self.background, lenT=lenT)

    def getValues(self, length=None, _min=None, _max=None, n=1, subtractBackground=None): # pylint: disable = unused-argument # use consistent arguments for all versions of getValues
        """Returns plain Numpy array of values.
        Note that background subtraction only affects what is displayed, the raw signal and background curves are always retained."""
        if self.useBackgrounds and subtractBackground:
            return self.values.get(length=length, _min=_min, _max=_max, n=n) - self.backgrounds.get(length=length, _min=_min, _max=_max, n=n)
        else:
            return self.values.get(length=length, _min=_min, _max=_max, n=n)

    def clearHistory(self, max_size=None): # overwrite as needed, e.g. when keeping history of more than one parameter
        if self.device.pluginManager.DeviceManager is not None and (self.device.pluginManager.Settings is not None and not self.device.pluginManager.Settings.loading):
            self.values = DynamicNp(max_size=max_size if max_size is not None else 600000/int(self.device.interval)) # 600000 -> only keep last 10 min to save ram unless otherwise specified
        self.clearPlotCurve()
        if self.useBackgrounds:
            self.backgrounds = DynamicNp(max_size=max_size)

    def clearPlotCurve(self):
        if self.plotCurve is not None:
            #if hasattr(self.plotCurve, '_parent'):  # all plot curves need to have a _parent so they can be removed gracefully
            self.plotCurve._parent.removeItem(self.plotCurve) # plotWidget still tries to access this even if deleted -> need to explicitly remove!
            if isinstance(self.plotCurve._parent, pg.ViewBox):
                self.plotCurve._legend.removeItem(self.plotCurve)
            self.plotCurve.clear()
            self.plotCurve.deleteLater()
            self.plotCurve = None
            self.getDevice().liveDisplay._updateLegend = True

    def getDevice(self):
        return self.device

    def getQtLineStyle(self):
        match self.linestyle:
            case 'dotted':
                return Qt.PenStyle.DotLine
            case 'dashed':
                return Qt.PenStyle.DashLine
            case 'dashdot':
                return Qt.PenStyle.DashDotLine
            case _: # solid
                return Qt.PenStyle.SolidLine

    def updateColor(self):
        """Apply new color to all controls."""
        if getDarkMode():
            color = QColor(self.color).darker(150) if self.active else QColor(self.color).darker(200) # indicate passive channels by darker color
        else:
            color = QColor(self.color) if self.active else QColor(self.color).darker(115) # indicate passive channels by darker color
        qb = QBrush(color)
        for i in range(len(self.parameters)+1): # use highest index
            self.setBackground(i, qb) # use correct color even when widgets are hidden
        for parameter in self.parameters:
            widget = parameter.getWidget()
            widget.container.setStyleSheet(f'background-color: {color.name()};')
            if isinstance(widget, QToolButton):
                widget.setStyleSheet(f'''QToolButton {{background-color: {color.name()}}}
                                QToolButton:checked {{background-color: {color.darker(150 if getDarkMode() else 120).name()};
                                border-style: inset; border-width: 2px; border-color: 'gray';}}''')
            elif isinstance(widget, QComboBox):
                pass
            elif isinstance(widget, QCheckBox):
                checkBoxHeight = widget.checkBoxHeight if hasattr(widget, 'checkBoxHeight') else min(self.rowHeight-4, QCheckBox().sizeHint().height()-2)
                widget.setStyleSheet(f'QCheckBox{{background-color: {color.name()}; color:{colors.fg}}} QCheckBox::indicator {{ width: {checkBoxHeight}; height: {checkBoxHeight};}}')
            elif isinstance(widget, QPushButton):
                widget.setStyleSheet(f'background-color: {color.name()}; color:{colors.fg}; margin:0px; border:none;')
            else:
                widget.setStyleSheet(f'background-color: {color.name()}; color:{colors.fg}; margin:0px;')
        self.updateDisplay()
        self.defaultStyleSheet = f'background-color: {color.name()}'
        return color

    def scalingChanged(self):
        normalHeight = QLineEdit().sizeHint().height() - 4
        match self.scaling:
            case 'small':
                self.rowHeight = int(normalHeight*.6)
            case 'normal':
                self.rowHeight = normalHeight
            case 'large':
                self.rowHeight = normalHeight*2
            case 'larger':
                self.rowHeight = normalHeight*4
            case 'huge':
                self.rowHeight = normalHeight*6
        for parameter in self.parameters:
            parameter.setHeight(self.rowHeight)
        if not self.loading:
            self.tree.scheduleDelayedItemsLayout()

    def sizeHint(self, option, index):
        # Provide a custom size hint based on the item's content
        return QSize(100, self.rowHeight)  # Width is not relevant; height is set to 50
        # return super().sizeHint(option, index)

    def realChanged(self):
        """Extend as needed. Already linked to real checkbox."""
        self.getParameterByName(self.ENABLED).getWidget().setVisible(self.real)
        self.toggleBackgroundVisible()
        if self.useMonitors:
            self.getParameterByName(self.MONITOR).getWidget().setVisible(self.real)
        if not self.device.loading:
            self.device.pluginManager.DeviceManager.globalUpdate(inout=self.inout)

    def enabledChanged(self):
        """Extend as needed. Already linked to enabled checkbox."""
        if not self.device.loading:
            self.toggleBackgroundVisible()
            self.device.pluginManager.DeviceManager.globalUpdate(inout=self.inout)
            self.clearPlotCurve()
            if self.enabled:
                self.device.appendData(nan=True) # prevent interpolation to old data
            if not self.device.recording and self.device.liveDisplay is not None:
                self.device.liveDisplay.plot(apply=True)

    def toggleBackgroundVisible(self):
        if self.useBackgrounds:
            backgroundVisible = self.enabled and self.active and self.real
            self.getParameterByName(self.BACKGROUND).getWidget().setVisible(backgroundVisible)
            if not backgroundVisible:
                self.background = 0

    def nameChanged(self):
        if self.inout == INOUT.OUT:
            self.updateDisplay()
        self.device.pluginManager.connectAllSources()

    def updateDisplay(self):
        if not self.device.loading and self.useDisplays:
            self.clearPlotCurve()
            if not self.device.recording and self.device.liveDisplay is not None:
                self.device.liveDisplay.plot(apply=True)
            self.device.pluginManager.DeviceManager.updateStaticPlot()

    def monitorChanged(self):
        """Highlights monitors if they deviate to far from set point. Extend for custom monitor logic if applicable."""
        self.updateWarningState(self.enabled and (hasattr(self.device, 'controller') and self.device.controller is not None and self.device.controller.acquiring) and self.getDevice().isOn() and abs(self.monitor - self.value) > 1)

    def updateWarningState(self, warn):
        if warn != self.warningState:
            self.warningState = warn
            self.getParameterByName(self.MONITOR).getWidget().setStyleSheet(self.warningStyleSheet if warn else self.defaultStyleSheet)

    def initGUI(self, item):
        """Call after item has been added to tree.
        Item needs parent for all graphics operations.
        """
        for parameter in self.parameters:
            parameter.applyWidget()
        for name, default in self.getSortedDefaultChannel().items():
            # add default value if not found in file. Will be saved to file later.
            if name in item and name not in self.tempParameters():
                self.getParameterByName(name).value = item[name]
            else:
                self.getParameterByName(name).value = default[self.VALUE]
                if name not in self.tempParameters() and not len(item) < 2: # len(item) < 2 -> generating default file
                    self.print(f'Added missing parameter {name} to channel {item[self.NAME]} using default value {default[self.VALUE]}.')
                    self.device.channelsChanged = True
        if self.inout != INOUT.NONE and self.EQUATION in self.displayedParameters:
            line = self.getParameterByName(self.EQUATION).line
            line.setMinimumWidth(200)
            font = line.font()
            font.setPointSize(8)
            line.setFont(font)
        if self.SELECT in self.displayedParameters:
            select = self.getParameterByName(self.SELECT)
            initialValue= select.value
            select.widget = ToolButton() # hard to spot checked QCheckBox. QPushButton is too wide -> overwrite internal widget to QToolButton
            select.applyWidget()
            select.check.setMaximumHeight(select.rowHeight) # default too high
            select.check.setText(self.SELECT.title())
            select.check.setMinimumWidth(5)
            select.check.setCheckable(True)
            select.value = initialValue
        if self.COLLAPSE in self.displayedParameters:
            collapse = self.getParameterByName(self.COLLAPSE)
            initialValue = collapse.value
            collapse.widget = QPushButton()
            collapse.widget.setCheckable(True)
            collapse.widget.setStyleSheet('QPushButton{border:none;}')
            collapse.applyWidget()
            collapse.value = initialValue
            collapse.getWidget().setIcon(self.device.makeCoreIcon('toggle-small-expand.png' if self.collapse else 'toggle-small.png'))
        if self.inout != INOUT.NONE:
            self.updateColor()
            self.realChanged()
            if self.inout == INOUT.IN:
                self.updateMin()
                self.updateMax()
        self.scalingChanged()

    def updateMin(self):
        self.getParameterByName(self.VALUE).spin.setMinimum(self.min)

    def updateMax(self):
        self.getParameterByName(self.VALUE).spin.setMaximum(self.max)

    def onDelete(self):
        """Extend to handle events on deleting. E.g. handle references that should remain available."""
        self.clearPlotCurve()

    def initSettingsContextMenuBase(self, parameter, pos):
        """General implementation of a context menu.
        The relevant actions will be chosen based on the type and properties of the :class:`~esibd.core.Parameter`."""
        settingsContextMenu = QMenu(self.tree)
        addParameterToConsoleAction = None
        addChannelToConsoleAction = None
        if getShowDebug():
            addParameterToConsoleAction = settingsContextMenu.addAction(self.ADDPARTOCONSOLE)
            addChannelToConsoleAction = settingsContextMenu.addAction(self.ADDCHANTOCONSOLE)
        # addItemAction = None
        # editItemAction = None
        # removeItemAction = None
        # setToDefaultAction= None
        # if parameter.widgetType in [Parameter.TYPE.COMBO, Parameter.TYPE.INTCOMBO, Parameter.TYPE.FLOATCOMBO]:
        #     NOTE channels do only save current value but not the items -> thus editing items is currently not supported
        #     # Channels are part of Devices which define items centrally
        #     addItemAction = settingsContextMenu.addAction(self.ADDITEM)
        #     editItemAction = settingsContextMenu.addAction(self.EDITITEM)
        #     removeItemAction = settingsContextMenu.addAction(self.REMOVEITEM)
        #     setToDefaultAction = settingsContextMenu.addAction(f'Set to Default: {parameter.default}')
        if not settingsContextMenu.actions():
            return
        settingsContextMenuAction = settingsContextMenu.exec(pos)
        if settingsContextMenuAction is not None: # no option selected (NOTE: if it is None this could trigger a non initialized action which is also None if not tested here)
            if settingsContextMenuAction is addParameterToConsoleAction:
                self.device.pluginManager.Console.addToNamespace('parameter', parameter)
                self.device.pluginManager.Console.execute('parameter')
            if settingsContextMenuAction is addChannelToConsoleAction:
                self.device.pluginManager.Console.addToNamespace('channel', parameter._parent)
                self.device.pluginManager.Console.execute('channel')
        #     if settingsContextMenuAction is setToDefaultAction:
        #         parameter.setToDefault()
        #     elif settingsContextMenuAction is addItemAction:
        #         text, ok = QInputDialog.getText(self.device, self.ADDITEM, self.ADDITEM)
        #         if ok and text != '':
        #             parameter.addItem(text)
        #     elif settingsContextMenuAction is editItemAction:
        #         text, ok = QInputDialog.getText(self.device, self.EDITITEM, self.EDITITEM, text=str(parameter.value))
        #         if ok and text != '':
        #             parameter.editCurrentItem(text)
        #     elif settingsContextMenuAction is removeItemAction:
        #         parameter.removeCurrentItem()

class ScanChannel(RelayChannel, Channel):
    """Minimal UI for abstract PID channel."""

    def __init__(self, device, **kwargs):
        self.scan = device
        Channel.__init__(self, device=device, **kwargs)
        self.sourceChannel = None
        self.recordingData = None

    def onDelete(self):
        super().onDelete()
        self.removeEvents()

    DEVICE   = 'Device'

    def getDefaultChannel(self):
        channel = super().getDefaultChannel()
        channel.pop(Channel.SELECT)
        channel.pop(Channel.ACTIVE)
        channel.pop(Channel.EQUATION)
        channel.pop(Channel.REAL)
        channel.pop(Channel.COLOR)
        channel.pop(Channel.COLLAPSE)
        channel[self.VALUE][Parameter.INDICATOR] = True
        channel[self.NAME][Parameter.INDICATOR] = True
        if self.scan.useDisplayParameter:
            channel[self.DISPLAY   ] = parameterDict(value=True, widgetType=Parameter.TYPE.BOOL, advanced=False,
                                        header='D', toolTip='Display channel history.',
                                        event=lambda: self.updateDisplay(), attr='display')
        channel[self.DEVICE] = parameterDict(value=False, widgetType=Parameter.TYPE.BOOL, advanced=False,
                                                 toolTip='Source: Unknown.', header='')
        channel[self.UNIT] = parameterDict(value='', widgetType=Parameter.TYPE.TEXT, attr='unit', header='Unit   ', indicator=True)
        channel[self.NOTES] = parameterDict(value='', widgetType=Parameter.TYPE.LABEL, advanced=True, attr='notes', indicator=True)
        return channel

    def tempParameters(self):
        """This channel is not restored from file, this every parameter is a tempParameter."""
        tempParameters = super().tempParameters() + [self.VALUE, self.DEVICE, self.NOTES, self.SCALING]
        if self.scan.useDisplayParameter:
            tempParameters = tempParameters + [self.DISPLAY]
        return tempParameters

    def setDisplayedParameters(self):
        super().setDisplayedParameters()
        self.displayedParameters.remove(self.COLLAPSE)
        self.displayedParameters.remove(self.ENABLED)
        self.displayedParameters.remove(self.ACTIVE)
        self.displayedParameters.remove(self.EQUATION)
        self.displayedParameters.remove(self.REAL)
        self.displayedParameters.remove(self.COLOR)
        self.displayedParameters.remove(self.SELECT)
        self.insertDisplayedParameter(self.DEVICE, self.NAME)
        self.insertDisplayedParameter(self.UNIT, before=self.SCALING)
        if self.scan.useDisplayParameter:
            self.insertDisplayedParameter(self.DISPLAY, before=self.SCALING)
        self.insertDisplayedParameter(self.NOTES, before=self.SCALING)

    def initGUI(self, item):
        super().initGUI(item)
        device = self.getParameterByName(self.DEVICE)
        device.widget = QPushButton()
        device.widget.setStyleSheet('QPushButton{border:none;}')
        device.applyWidget()
        if self.scan.useDisplayParameter:
            self.display = True

    def connectSource(self):
        self.sourceChannel = self.scan.pluginManager.DeviceManager.getChannelByName(self.name, inout=INOUT.OUT)
        if self.sourceChannel is None:
            self.sourceChannel = self.scan.pluginManager.DeviceManager.getChannelByName(self.name, inout=INOUT.IN)
        # if self.unit != '' and self.sourceChannel is not None and self.unit != self.sourceChannel.unit:
        #     Found a channel that has the same name but likely belongs to another device.
        #     In most cases the only consequence is using the wrong color.
        #     Handle in specific scan if other channel specific properties are relevant
        #     self.sourceChannel = None
        if self.sourceChannel is not None:
            self.getParameterByName(self.DEVICE).getWidget().setIcon(
                self.sourceChannel.getDevice().getIcon(desaturate=(not self.sourceChannel.acquiring and not self.sourceChannel.getDevice().recording)))
            self.getParameterByName(self.DEVICE).getWidget().setToolTip(f'Source: {self.sourceChannel.getDevice().name}')
            if self.sourceChannel.useMonitors:
                self.getParameterByName(self.VALUE).widgetType = self.sourceChannel.getParameterByName(self.MONITOR).widgetType
                self.getParameterByName(self.VALUE).applyWidget()
                self.value = self.sourceChannel.monitor
                self.sourceChannel.getParameterByName(self.MONITOR).extraEvents.append(self.relayValueEvent)
            else:
                self.getParameterByName(self.VALUE).widgetType = self.sourceChannel.getParameterByName(self.VALUE).widgetType
                self.getParameterByName(self.VALUE).applyWidget()
                self.value = self.sourceChannel.value
                self.sourceChannel.getParameterByName(self.VALUE).extraEvents.append(self.relayValueEvent)
            if self.unit == '': # do not overwrite unit if set explicitly
                self.unit = self.sourceChannel.unit
            self.notes = f'Source: {self.sourceChannel.getDevice().name}.{self.sourceChannel.name}'
        else:
            self.getParameterByName(self.DEVICE).getWidget().setIcon(self.scan.makeCoreIcon('help_large_dark.png' if getDarkMode() else 'help_large.png'))
            self.getParameterByName(self.DEVICE).getWidget().setToolTip('Source: Unknown')
            self.notes = f'Could not find {self.name}'
        self.getParameterByName(self.DEVICE).setHeight()
        self.updateColor()
        self.scalingChanged()

    def relayValueEvent(self):
        if self.sourceChannel is not None:
            # Note self.value should only be used as a display. it should show the background corrected value if applicable
            # the uncorrected value should be accessed using self.sourceChannel.value or self.getValues
            try:
                if self.sourceChannel.useMonitors:
                    self.value = self.sourceChannel.monitor
                else:
                    self.value = self.sourceChannel.value - self.sourceChannel.background if self.sourceChannel.getDevice().subtractBackgroundActive() else self.sourceChannel.value
            except RuntimeError:
                self.removeEvents()

    def removeEvents(self):
        if self.sourceChannel is not None:
            if self.sourceChannel.useMonitors:
                if self.relayValueEvent in self.sourceChannel.getParameterByName(self.MONITOR).extraEvents:
                    self.sourceChannel.getParameterByName(self.MONITOR).extraEvents.remove(self.relayValueEvent)
            else:
                if self.relayValueEvent in self.sourceChannel.getParameterByName(self.VALUE).extraEvents:
                    self.sourceChannel.getParameterByName(self.VALUE).extraEvents.remove(self.relayValueEvent)

    def updateDisplay(self):
        # in general scan channels should be passive, but we need to react to changes in which channel should be displayed
        if self.scan.display is not None and not self.loading and not self.scan.initializing:
            self.scan.display.initFig()
            self.scan.plot(update=self.scan.recording, done=not self.scan.recording)

    @property
    def loading(self):
        return self.scan.loading

class QLabviewSpinBox(QSpinBox):
    """Implements handling of arrow key events based on curser position similar as in LabView."""
    def __init__(self, parent=None, indicator=False):
        super().__init__(parent)
        self.indicator = indicator
        self.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.setMinimumWidth(54)
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
        if cur==0 and '-' not in text: # left of number
            pos= len(text)-1
        if cur<=1 and '-' in text: # left of number
            pos= len(text)-2
        val=self.value()+10**pos*step # use step for sign
        self.setValue(val)
        # keep cursor position fixed relative to .
        newText = self.lineEdit().text()
        if len(newText) > len(text):
            if cur == 0 and '-' not in text:
                self.lineEdit().setCursorPosition(2)
            elif cur <= 1 and '-' in text:
                self.lineEdit().setCursorPosition(3)
            else:
                self.lineEdit().setCursorPosition(cur + 1)
        elif len(newText) < len(text):
            self.lineEdit().setCursorPosition(max(cur - 1, 0))

class QLabviewDoubleSpinBox(QDoubleSpinBox):
    """Implements handling of arrow key events based on curser position similar as in LabView."""
    def __init__(self, parent=None, indicator=False, displayDecimals=2):
        super().__init__(parent)
        self.indicator = indicator
        self.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.setRange(-np.inf, np.inf) # limit explicitly if needed, this seems more useful than the [0, 100] default range
        self.setDisplayDecimals(displayDecimals)
        self.NAN = 'NaN'
        if indicator:
            self.setReadOnly(True)
            self.preciseValue = 0

    def contextMenuEvent(self, event):
        if self.indicator:
            event.ignore()
        else:
            return super().contextMenuEvent(event)

    def setDisplayDecimals(self, prec):
        # decimals used for display.
        self.displayDecimals = prec
        # keep internal precision higher if explicitly defined. ensure minimum precision corresponds to display
        self.setDecimals(max(self.displayDecimals, self.decimals()))
        self.value = self.value

    def valueFromText(self, text):
        return float(text)

    def textFromValue(self, value):
        """make sure nan and inf will be represented by NaN."""
        if np.isnan(value) or np.isinf(value):
            return self.NAN
        else:
            return f'{value:.{self.displayDecimals}f}'

    def value(self):
        if self.text() == self.NAN:
            return np.nan
        return super().value()

    def setValue(self, val):
        super().setValue(val)
        if np.isnan(val) or np.isinf(val):
            self.lineEdit().setText(self.NAN) # needed in rare cases where setting to nan would set to maximum

    def wheelEvent(self, event):
        event.ignore()

    def stepBy(self, step):
        """Handles stepping value depending con caret position. This implementation works with negative numbers and of number of digits before the dot."""
        if self.text() == self.NAN:
            return
        text = self.lineEdit().text()
        cur = self.lineEdit().cursorPosition()
        dig = len(text.strip('-').split('.')[0])
        # first digit
        if cur <= 1 or cur <= 2 and '-' in text:
            pos = dig - 1
        # digits before decimal
        elif cur < dig and '-' not in text:
            pos = dig - cur
        elif cur < dig + 1 and '-' in text:
            pos = dig - cur + 1
        # last digit before decimal
        elif cur == dig and '-' not in text or cur == dig + 1 and '-' in text:
            pos = 0
        # first digit after decimal
        elif cur == dig + 1 and '-' not in text or cur == dig + 2 and '-' in text:
            pos = -1
        # remaining digits after decimal
        else:
            pos = dig-cur + 2 if '-' in text else dig-cur + 1
        val=self.value()+10**pos*step # use step for sign
        self.setValue(val)
        # keep cursor position fixed relative to .
        newText = self.lineEdit().text()
        if len(newText) > len(text):
            if cur == 0 and '-' not in text:
                self.lineEdit().setCursorPosition(2)
            elif cur <= 1 and '-' in text:
                self.lineEdit().setCursorPosition(3)
            else:
                self.lineEdit().setCursorPosition(cur + 1)
        elif len(newText) < len(text):
            self.lineEdit().setCursorPosition(max(cur - 1, 0))

    # def sizeHint(self): # use fixed sizes based on expected values instead of dynamically adjusting every time value changes
    #     """Return reasonable size hint based on content within minimum and maximum limits"""
    #     return QSize(max(self.minimumWidth(), QFontMetrics(self.lineEdit().font()).horizontalAdvance(self.text() or " ") + 10), self.height())

class QLabviewSciSpinBox(QLabviewDoubleSpinBox):
    """Spinbox for scientific notation."""
    # inspired by https://gist.github.com/jdreaver/0be2e44981159d0854f5
    # Regular expression to find floats. Match groups are the whole string, the
    # whole coefficient, the decimal part of the coefficient, and the exponent part.

    class FloatValidator(QValidator):
        """Validates input for correct scientific notation."""
        _float_re = re.compile(r'(([+-]?\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?)')

        def valid_float_string(self, string):
            match = self._float_re.search(string)
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

    def __init__(self, parent=None, indicator=False, displayDecimals=2):
        self.validator = self.FloatValidator()
        super().__init__(parent, indicator=indicator, displayDecimals=displayDecimals)
        self.setDecimals(1000) # need this to allow internal handling of data as floats 1E-20 = 0.0000000000000000001

    def validate(self, text, position):
        return self.validator.validate(text, position)

    def fixup(self, text):
        return self.validator.fixup(text)

    def textFromValue(self, value):
        if np.isnan(value) or np.isinf(value):
            return self.NAN
        else:
            return f'{value:.{self.displayDecimals}E}'.replace('E-0', 'E-')

    def stepBy(self, step):
        if self.text() == self.NAN:
            return
        text = self.lineEdit().text()
        cur = self.lineEdit().cursorPosition()
        v, p = text.split('E')
        sign = '-' if p[0] == '-' else ''
        pot = ''.join([pp for pp in p[1:].lstrip('0')])
        pot = '0' if pot == '' else pot
        if cur <= 2 and '-' not in v or cur <= 3 and '-' in v:
            pos = 0
        else: # right of dot
            pos = 3-cur if '-' in v else 2-cur
        self.setValue(float(str(float(v)+10**pos*step) + 'E' + sign + pot))
        # keep cursor position fixed relative to .
        newText = self.lineEdit().text()
        if len(newText) > len(text):
            if cur == 0 and '-' not in v:
                self.lineEdit().setCursorPosition(2)
            elif cur <= 1 and '-' in v:
                self.lineEdit().setCursorPosition(3)
            else:
                self.lineEdit().setCursorPosition(cur + 1)
        elif len(newText) < len(text):
            self.lineEdit().setCursorPosition(max(cur - 1, 0))

class ControlCursor(Cursor):
    """Extending internal implementation to get draggable cursor."""
    # based on https://matplotlib.org/3.5.0/gallery/misc/cursor_demo.html
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
    """ComboBox that allows to restore its value upon restart using an internal :class:`~esibd.core.Setting`"""

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

class CheckBox(QCheckBox):
    """Allows to set values in a widget in a consistent way."""

    class SignalCommunicate(QObject):
        setValueFromThreadSignal = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self.signalComm = self.SignalCommunicate()
        self.signalComm.setValueFromThreadSignal.connect(self.setValue)

    def setValue(self, value):
        self.setChecked(value)

class ToolButton(QToolButton):
    """Allows to set values in a widget in a consistent way."""

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
        self.icon = icon
        self.toolTip = toolTip
        self.signalComm = self.SignalCommunicate()
        self.signalComm.setValueFromThreadSignal.connect(self.setValue)

    def getIcon(self):
        return self.icon

    def getToolTip(self):
        return self.toolTip

    def setValue(self, value):
        self.setChecked(value)

class StateAction(Action):
    """Extends QActions to show different icons depending on a state.
    Values are restored using QSettings if name is provided."""

    def __init__(self, parentPlugin, toolTipFalse='', iconFalse=None, toolTipTrue='', iconTrue=None, event=None, before=None, attr=None, restore=True, default='false'):
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
            # setattr with property only works on the class, not the instance. Thus prone to cause conflict when multiple instances of a class use this feature
            # This could be avoided by inheriting to create a unique copy of the class for each instance, which does not seem very clean
            # setattr(self.parentPlugin.__class__, self.attr, makeStateWrapper(self)) # allows to access state by using attribute from parentPlugin
        self.event = event
        if event is not None:
            self.triggered.connect(event)
        if restore and self.fullName is not None:
            self.state = qSet.value(self.fullName, defaultValue=default, type=bool)
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

    def getIcon(self):
        return self.iconTrue if self.state else self.iconFalse

    def getToolTip(self):
        return self.toolTipTrue if self.state else self.toolTipFalse

    def setValue(self, value):
        self.state = value

class MultiState():

    def __init__(self, label='', toolTip='', icon=None):
        self.label = label
        self.toolTip = toolTip
        self.icon = icon

class MultiStateAction(Action):
    """Extends QActions to show different icons depending on multiple states.
    Values are restored using QSettings if name is provided."""

    class Labels():
        pass

    def __init__(self, parentPlugin, states=None, event=None, before=None, attr=None, restore=True, default=0):
        super().__init__(states[0].icon, states[0].toolTip, parentPlugin)
        self.parentPlugin = parentPlugin
        self.states = states
        # self.labels = enum.Enum('labels', {key: value for key, value in zip([state.label for state in self.states], range(len(self.states)))})
        self.labels = self.Labels() # use labels as parameters to avoid hard coding
        for state in self.states:
            setattr(self.labels, state.label, state.label)
        # self.setCheckable(True) # checked state is binary -> not useful for multiple states, but needed to trigger the triggered event
        # self.toggled.connect(self.updateIcon)
        self.setToolTip(states[0].toolTip)
        self.attr = attr
        self.fullName = None
        if self.attr is None:
            self.setObjectName(f'{self.parentPlugin.name}/{states[0].toolTip}')
        else:
            self.fullName = f'{self.parentPlugin.name}/{self.attr}'
            self.setObjectName(self.fullName)
            # setattr with property only works on the class, not the instance. Thus prone to cause conflict when multiple instances of a class use this feature
            # This could be avoided by inheriting to create a unique copy of the class for each instance, which does not seem very clean
            # setattr(self.parentPlugin.__class__, self.attr, makeStateWrapper(self)) # allows to access state by using attribute from parentPlugin
        self.event = event
        if event is not None:
            self.triggered.connect(lambda: (self.rollState(), event()))
        if restore and self.fullName is not None:
            self._state = min(int(qSet.value(self.fullName, default)), len(states)-1)
        else:
            self._state = 0 # init
        self.updateIcon()
        if before is None:
            self.parentPlugin.titleBar.addAction(self)
        else:
            self.parentPlugin.titleBar.insertAction(before, self)

    def stateFromLabel(self, label):
        return next((i for i in range(len(self.states)) if self.states[i].label == label), 0)

    def labelFromState(self, state):
        return self.states[state].label

    def rollState(self):
        self._state = np.mod(self._state + 1, len(self.states))
        self.updateIcon()

    @property
    def state(self): # use labels for api
        return self.labelFromState(self._state)

    @state.setter
    def state(self, label):
        self._state = self.stateFromLabel(label)

    def updateIcon(self):
        if self.fullName is not None:
            qSet.setValue(self.fullName, self._state) # store state as int
        self.setIcon(self.getIcon())
        self.setToolTip(self.getToolTip())

    def getIcon(self):
        return self.states[self._state].icon

    def getToolTip(self):
        return self.states[self._state].toolTip

    def setValue(self, value):
        # value should be a valid label corresponding to one of the defined states
        self._state = self.stateFromLabel(value)

class CompactComboBox(QComboBox):
    """Combobox that stays small while showing full content in dropdown menu.s"""
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
        # but under Windows they get truncated
        # here we calculate the maximum width among the items
        # and set QComboBox.view() to accommodate this
        # which makes items show full width under Windows
        view = self.view()
        fm = self.fontMetrics()
        maxWidth = max([fm.size(Qt.TextFlag.TextSingleLine, self.itemText(i)).width() for i in range(self.count())]) + 50 # account for scrollbar and margins
        if maxWidth:
            view.setMinimumWidth(maxWidth)

class DockWidget(QDockWidget):
    """DockWidget with custom title bar allows to intercept the close and float events triggered by user."""
    # future desired features:
    # - floating docks should be able to be maximized/minimized and appear as separate windows of the same software in task bar
    # floating windows should not disappear when dragged below taskbar but jump back as normal windows
    # - some of these are possible with pyqtgraph but this introduces other limitations and bugs
    # Open bug: https://bugreports.qt.io/browse/QTBUG-118578 see also  https://stackoverflow.com/questions/77340981/how-to-prevent-crash-with-qdockwidget-and-custom-titlebar

    class SignalCommunicate(QObject):
        dockClosingSignal = pyqtSignal()

    def __init__(self, plugin):
        self.plugin = plugin
        self.title = self.plugin.name
        if hasattr(self.plugin, 'parentPlugin'):
            self.title = self.plugin.parentPlugin.name
        if hasattr(self.plugin, 'scan') and self.plugin.scan is not None:
            self.title = self.plugin.scan.name
        super().__init__(self.title, QApplication.instance().mainWindow)
        self.signalComm = self.SignalCommunicate()
        self.signalComm.dockClosingSignal.connect(self.plugin.closeGUI)
        self.setObjectName(f'{self.plugin.pluginType}_{self.plugin.name}') # essential to make restoreState work!
        self.setTitleBarWidget(plugin.titleBar)
        self.topLevelChanged.connect(lambda: self.on_top_level_changed())
        self.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable | QDockWidget.DockWidgetFeature.DockWidgetFloatable) # | QDockWidget.DockWidgetFeature.DockWidgetClosable)
        self.setWidget(self.plugin.mainDisplayWidget)

    def on_top_level_changed(self):
        # self.plugin.print('on_top_level_changed', flag=PRINT.DEBUG)
        # there are no signals available to be emitted at the end of dragging or when tabifying.
        # for now I am just using a long delay and hope that the operation has been completed before toggleTitleBar is called
        if not self.plugin.pluginManager.finalizing and not self.plugin.pluginManager.loading:
            self.plugin.pluginManager.toggleTitleBarDelayed(update=True, delay=3000)

    def toggleTitleBar(self):
        """Updates titleBar as dock is changing from floating to docked states."""
        # self.plugin.print('toggleTitleBar', flag=PRINT.DEBUG)
        if self.plugin.initializedDock: # may have changed between toggleTitleBarDelayed and toggleTitleBar
            if self.isFloating(): # dock is floating on its own
                # self.setWindowFlags(Qt.WindowType.Window)
                if self.plugin.titleBarLabel is not None:
                    self.plugin.titleBarLabel.setText(self.title)
                if hasattr(self.plugin, 'floatAction'):
                    self.plugin.floatAction.state = True
                    # self.plugin.floatAction.setVisible(False)
            else: # dock is inside the mainWindow or an external window
                if hasattr(self.plugin, 'floatAction'):
                    self.plugin.floatAction.state = False
                    # do not allow to float from external windows as this causes GUI instabilities (empty external windows, crash without error, ...)
                    # need to allow float to leave external window -> need to make safe / dragging using standard titleBar works but not using custom titleBar
                    # self.plugin.floatAction.setVisible(isinstance(self.parent(), QMainWindow))
                if hasattr(self.plugin, 'titleBarLabel') and self.plugin.titleBarLabel is not None:
                    self.plugin.titleBarLabel.setText(self.title) # need to apply for proper resizing, even if set to '' next
                    if hasattr(self.parent(), 'tabifiedDockWidgets') and len(self.parent().tabifiedDockWidgets(self)) > 0:
                        self.plugin.titleBarLabel.setText('')
                    if self.plugin.pluginManager.tabBars: # might be null if there are no tabbed docks
                        for tabBar in self.plugin.pluginManager.tabBars:
                            for i in range(tabBar.count()):
                                if tabBar.tabText(i) == self.title:
                                    tabBar.setTabIcon(i, QIcon() if getIconMode() == 'Labels' else self.plugin.getIcon())
                                    # if getIconMode() == 'Icons':
                                    #     tabBar.tabIcon(i).setToolTip(self.title) cannot assign tooltip
                if not isinstance(self.parent(), QMainWindow):
                    self.parent().setStyleSheet(self.plugin.pluginManager.styleSheet) # use same separators as in main window

    def closeEvent(self, event):
        self.signalComm.dockClosingSignal.emit()
        return super().closeEvent(event)

class Icon(QIcon):
    """QIcon that allows to save the icon file name. Allows to reuse icon elsewhere, e.g., for html about dialog."""

    def __init__(self, file, pixmap=None, desaturate=False):
        if isinstance(file, Path):
            file = file.as_posix()
        if desaturate:
            image = Image.open(file).convert("RGBA")
            r, g, b, a = image.split()
            grayscale = Image.merge("RGB", (r, g, b)).convert("L")
            pixmap = QPixmap.fromImage(ImageQt(Image.merge("RGBA", (grayscale, grayscale, grayscale, a))))
        if pixmap is None:
            super().__init__(file)
        else:
            super().__init__(pixmap)
        self.fileName = file # remember for later access

class TreeWidget(QTreeWidget):

    def __init__(self, parent=None, minimizeHeight=False):
        super().__init__(parent)
        self.minimizeHeight = minimizeHeight

    def totalItems(self):
        "total number of items at top level and first child level"
        total_items = 0
        for i in range(self.topLevelItemCount()):
            top_item = self.topLevelItem(i)
            total_items += 1  # Count the top-level item
            total_items += top_item.childCount()# Add the count of its children
        return total_items

    def totalHeight(self):
        total_height = self.header().height()
        for i in range(self.topLevelItemCount()):
            top_item = self.topLevelItem(i)
            total_height += self.visualItemRect(top_item).height()
            for j in range(top_item.childCount()):
                total_height += self.visualItemRect(top_item.child(j)).height()
        return total_height

    def itemWidth(self):
        if self.topLevelItemCount() > 0:
            for i in range(self.topLevelItemCount()):
                if self.visualItemRect(self.topLevelItem(i)).width() > 0: # ignore hidden channels
                    return self.visualItemRect(self.topLevelItem(i)).width()
        else:
            return 300

    def tree_height_hint_complete(self):
        item_height = self.visualItemRect(self.topLevelItem(0)).height() if self.topLevelItemCount() > 0 else 12
        return self.header().height() + self.totalItems() * item_height + 10

    def tree_height_hint_minimal(self):
        item_height = self.visualItemRect(self.topLevelItem(0)).height() if self.topLevelItemCount() > 0 else 12
        return self.header().height() + min(self.totalItems(), 4) * item_height + 10

    def count_child_items(self, item):
        count = item.childCount()
        for i in range(item.childCount()):
            count += self.count_child_items(item.child(i))
        return count

    def itemRect(self):
        """Returns the QRect of all visible items."""
        return QRect(self.rect().left(), self.rect().top(), min(self.rect().width(), self.itemWidth()), min(self.rect().height(), self.totalHeight()))

    def grabItems(self):
        return self.grab(self.itemRect())

    def sizeHint(self):
        return QSize(self.width(), self.tree_height_hint_minimal() if self.minimizeHeight else self.tree_height_hint_complete())

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

    def resizeEvent(self, QResizeEvent): # pylint: disable = unused-argument # matching standard signature
        self.update()

    def paintEvent(self, QPaintEvent): # pylint: disable = unused-argument, missing-function-docstring # matching standard signature
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

class LineEdit(QLineEdit):
    # based on https://stackoverflow.com/questions/79309361/prevent-editingfinished-signal-from-qlineedit-after-programmatic-text-update
    userEditingFinished = pyqtSignal(str)

    def __init__(self, parent=None, tree=None):
        super().__init__(parent)
        self._edited = False
        # Regular expression to allow only letters (both upper and lower case), digits, and spaces + mathematical symbols and brackets for equations
        self.valid_chars = r'^[a-zA-Z0-9\s\-_\(\)\[\]\{\}\.*;:" \'<>^?=\+\\/,~!@#$%&]*$'
        self.tree = tree
        self.editingFinished.connect(self.onEditingFinished)
        self.textEdited.connect(self.onTextEdited)
        self.textChanged.connect(self.onTextChanged)
        self.setMinimumWidth(50)  # Set a reasonable minimum width
        self.max_width = 300

    def onTextEdited(self):
        # edited by user, emitted on every keystroke
        self._edited = True

    def onTextChanged(self, text):
        # text changed by user or setText
        self.updateGeometry() # adjust width to text
        self.validateInput()

    def validateInput(self):
        """Validate the text and remove invalid characters"""
        current_text = self.text()
        # Remove any character that doesn't match the valid_chars regex
        if not re.match(self.valid_chars, current_text):
            # Filter the text, keeping only valid characters
            filtered_text = ''.join([char for char in current_text if re.match(self.valid_chars, char)])
            [print(f'Removing invalid character {char} from {current_text}') for char in current_text if not re.match(self.valid_chars, char)]
            self.setText(filtered_text)  # Update the QLineEdit with valid characters only

    def onEditingFinished(self):
        # editing finished by Enter or loosing focus
        if self._edited:
            self._edited = False
            if self.tree is not None:
                self.tree.scheduleDelayedItemsLayout()
            self.userEditingFinished.emit(self.text())

    def sizeHint(self):
        """Return reasonable size hint based on content within minimum and maximum limits"""
        return QSize(min(max(self.minimumWidth(), QFontMetrics(self.font()).horizontalAdvance(self.text() or " ") + 10), self.max_width), self.height())

class TextEdit(QPlainTextEdit):
    """Editor that is compatible with :class:`~esibd.core.NumberBar`"""
    # based on https://gist.github.com/Axel-Erfurt/8c84b5e70a1faf894879cd2ab99118c2

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

    def keyPressEvent(self, e): # pylint: disable = missing-function-docstring
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

class IconStatusBar(QStatusBar):
    iconClicked = pyqtSignal(bool)
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setStyleSheet('''
            QStatusBar { color: transparent; }
            QToolButton#statusBarIconWidget { border: none; }
        ''')

        self._iconWidget = QToolButton(objectName='statusBarIconWidget')
        # self._iconWidget.setEnabled(False) # indicator only
        self.addWidget(self._iconWidget)
        # add direct references to the icon functions
        self.icon = self._iconWidget.icon
        self.setIcon = self._iconWidget.setIcon
        # force the button to always show the icon, even if the
        # current style default is different
        self._iconWidget.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)

        # just set an arbitrary icon
        # self.icon_message = self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxInformation)
        # self.icon_error = self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxCritical)
        # self.icon_warning = self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxWarning)
        self.icon_warning = Icon(internalMediaPath / 'unicode_warning.png')
        self.icon_error   = Icon(internalMediaPath / 'unicode_error.png')
        self.icon_info    = Icon(internalMediaPath / 'unicode_info.png')
        self.icon_explorer= Icon(PROGRAM_ICON)
        self.setIcon(self.icon_explorer)

        self._statusLabel = QLabel()
        self._statusLabel.setMinimumWidth(1) # allow ignoring the size hint
        self.addWidget(self._statusLabel)

        # self.messageChanged.connect(self._updateStatus)

    def showMessage(self, message, msecs=...):
        # ignore internal statusbar which would overlay with our custom label
        self._statusLabel.setText(message)

    def setFlag(self, flag=PRINT.MESSAGE):
        match flag:
            case PRINT.WARNING:
                self.setIcon(self.icon_warning)
            case PRINT.ERROR:
                self.setIcon(self.icon_error)
            case PRINT.EXPLORER:
                self.setIcon(self.icon_explorer)
            case _:
                self.setIcon(self.icon_info)

class NumberBar(QWidget):
    """A bar that displays line numbers of an associated editor."""
    # based on https://gist.github.com/Axel-Erfurt/8c84b5e70a1faf894879cd2ab99118c2

    def __init__(self, parent = None):
        super().__init__(parent)
        self.editor = parent
        self.editor.blockCountChanged.connect(self.update_width)
        self.editor.updateRequest.connect(self.update_on_scroll)
        self.update_width('1')
        self.lineBarColor = Qt.GlobalColor.black

    def updateTheme(self):
        self.lineBarColor = QColor(colors.bg)

    def update_on_scroll(self, rect, scroll): # pylint: disable = unused-argument # keeping consistent signature
        if self.isVisible():
            if scroll:
                self.scroll(0, scroll)
            else:
                self.update()

    def update_width(self, string):
        width = self.fontMetrics().horizontalAdvance(str(string)) + 8 # changed from width to horizontalAdvance
        if self.width() != width:
            self.setFixedWidth(width)

    def paintEvent(self, event): # pylint: disable = missing-function-docstring
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
    """pyqtgraph.console.ConsoleWidget with colors adjusting to theme."""

    def __init__(self, parentPlugin, parent=None, namespace=None, historyFile=None, text=None, editor=None):
        super().__init__(parent, namespace, historyFile, text, editor)
        self.parentPlugin = parentPlugin
        font = QFont()
        font.setFamily("Courier New")
        font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        self.outputWarnings = QTextEdit()
        self.outputWarnings.setFont(font)
        self.outputWarnings.setReadOnly(True)
        self.outputErrors = QTextEdit()
        self.outputErrors.setFont(font)
        self.outputErrors.setReadOnly(True)
        # self.outputDebug = QTextEdit()
        # self.outputDebug.setFont(font)
        # self.outputDebug.setReadOnly(True)
        self.outputLayout = QStackedLayout()
        self.outputLayout.addWidget(self.output)
        self.outputLayout.addWidget(self.outputWarnings)
        self.outputLayout.addWidget(self.outputErrors)
        # self.outputLayout.addWidget(self.outputDebug)
        outputWidget = QWidget()
        outputWidget.setLayout(self.outputLayout)
        self.splitter.insertWidget(0, outputWidget)#.repl.layout.addChildLayout(self.outputLayout)
        self.splitter.setStyleSheet('QSplitter::handle{width:0px; height:0px;}')

        self.updateTheme()

    def updateTheme(self):
        self.output.setStyleSheet(f'QPlainTextEdit{{background-color:{colors.bg};}}')

    def scrollToBottom(self):
        sb = self.output.verticalScrollBar()
        sb.setValue(sb.maximum())

    def loadHistory(self): # extend to catch error if file does not exist
        h = None
        try:
            h = super().loadHistory()
        except EOFError as e:
            print(f'Could not load history: {e}')
        return h

    def _commandEntered(self, repl, cmd):
        # make sure submitted code will be visible even if filters were active before
        super()._commandEntered(repl, cmd)
        self.outputLayout.setCurrentIndex(0)
        self.parentPlugin.warningFilterAction.state = False
        self.parentPlugin.errorFilterAction.state = False


class ThemedNavigationToolbar(NavigationToolbar2QT):
    """Provides controls to interact with the figure.
    Adds light and dark theme support to NavigationToolbar2QT."""

    def __init__(self, canvas, parentPlugin=None, coordinates=True):
        super().__init__(canvas, parentPlugin, coordinates)
        self.parentPlugin = parentPlugin
        self.updateNavToolbarTheme()

    def updateNavToolbarTheme(self):
        """Changes color of icons in matplotlib navigation toolBar to match theme."""
        dark = getDarkMode()
        for a in self.actions()[:-1]:
            match a.text():
                case 'Home':
                    icon = self.parentPlugin.makeCoreIcon('home_large_dark.png' if dark else 'home_large.png')
                case 'Back':
                    icon = self.parentPlugin.makeCoreIcon('back_large_dark.png' if dark else 'back_large.png')
                case 'Forward':
                    icon = self.parentPlugin.makeCoreIcon('forward_large_dark.png' if dark else 'forward_large.png')
                case 'Pan':
                    icon = self.parentPlugin.makeCoreIcon('move_large_dark.png' if dark else 'move_large.png')
                case 'Zoom':
                    icon = self.parentPlugin.makeCoreIcon('zoom_to_rect_large_dark.png' if dark else 'zoom_to_rect_large.png')
                case 'Subplots':
                    icon = self.parentPlugin.makeCoreIcon('subplots_large_dark.png' if dark else 'subplots_large.png')
                case 'Customize':
                    icon = self.parentPlugin.makeCoreIcon('qt4_editor_options_large_dark.png' if dark else 'qt4_editor_options_large.png')
                case 'Save':
                    icon = self.parentPlugin.makeCoreIcon('filesave_large_dark.png' if dark else 'filesave_large.png')
            a.setIcon(icon)
            a.fileName = icon.fileName

    def save_figure(self, *args):
        limits = []
        if getDarkMode() and not getClipboardTheme():
            # use default light theme for clipboard
            with mpl.style.context('default'):
                for ax in self.parentPlugin.axes:
                    limits.append((ax.get_xlim(), ax.get_ylim()))
                self.parentPlugin.initFig() # canvas, figure, and, ThemedNavigationToolbar will be replaced after this
                # reconnect new canvas to old instance of ThemedNavigationToolbar to complete saving
                super().__init__(self.parentPlugin.canvas, self.parentPlugin, self.coordinates)
                self.parentPlugin.plot()
                for i, ax in enumerate(self.parentPlugin.axes):
                    ax.set_xlim(limits[i][0])
                    ax.set_ylim(limits[i][1])
                self.canvas.figure.set_facecolor(colors.bg_light)
                self.canvas.draw_idle()
                self.parentPlugin.processEvents()
                super().save_figure(*args)
        else:
            super().save_figure(*args)
        if getDarkMode() and not getClipboardTheme():
            # restore dark theme for use inside app
            self.parentPlugin.initFig()
            self.parentPlugin.plot()
            for i, ax in enumerate(self.parentPlugin.axes):
                ax.set_xlim(limits[i][0])
                ax.set_ylim(limits[i][1])
            self.canvas.draw_idle()
        self.parentPlugin.pluginManager.Explorer.populateTree() # show saved file in Explorer

class MZCalculator():
    """
    Add to a class derived from Scan.
    Allows to mark mass to charge (m/z) locations within a charge-state distribution, calculates absolute mass, and displays it on the axis.
    Use Ctrl + left mouse click to mark and Ctrl + right mouse click to reset."""
    def __init__(self, parentPlugin, ax=None):
        self.parentPlugin = parentPlugin
        if ax:
            self.ax = ax
            self.canvas = ax.figure.canvas
        self.mz = np.array([]) # array with selected m/z values
        self.cs = None
        self.charges=np.array([]) # for charge state
        self.maxChargeState = 200 # maximal value for lowest charge state
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
        if x is not None and y is not None:
            self.mz = np.append(self.mz, x)
            self.intensity = np.append(self.intensity, y)
            self.determine_mass_to_charge()

    def clear(self):
        self.mz = np.array([])
        self.intensity = np.array([])
        self.update_mass_to_charge()

    def determine_mass_to_charge(self):
        """Estimates charge states based on m/z values provided by user by minimizing standard deviation of absolute mass within a charge state series.
        Provides standard deviation for neighboring series to allow for validation of the result."""
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
        return f'{label} mass (Da): {np.average(self.mz*np.flip(self.charges[self.c1+offset:self.c1+offset+len(self.mz)])):.2f}, std: {self.STD[self.c1+offset]:.2f}'

    def update_mass_to_charge(self):
        for ann in [child for child in self.ax.get_children() if isinstance(child, mpl.text.Annotation)]: #[self.seAnnArrow, self.seAnnFile, self.seAnnFWHM]:
            ann.remove()
        if len(self.mz) > 1:
            for x, y, charge in zip(self.mz, self.intensity, self.cs):
                self.ax.annotate(text=f'{charge}', xy=(x, y), xycoords='data', ha='center')
            self.ax.annotate(text=f"{self.mass_string(-1, 'lower  ')}\n{self.mass_string( 0, 'likely  ')}\n{self.mass_string(+1, 'higher')}\n"
                                    + '\n'.join([f'mz:{mass:10.2f} z:{charge:4}' for mass, charge in zip(self.mz, self.cs)]),
                                xy=(0.02, 0.98), xycoords='axes fraction', fontsize=8, ha='left', va='top')
        self.parentPlugin.labelPlot(self.ax, self.parentPlugin.file.name)

class PlotItem(pg.PlotItem):
    """PlotItem providing xyLabel."""

    def __init__(self, _parent=None, groupLabel='', tickWidth=50, showXY=True, **kwargs):
        super().__init__(**kwargs)
        self._parent = _parent
        self.tickWidth = tickWidth
        self.showXY = showXY
        self.plotWidgetFont = QFont()
        self.plotWidgetFont.setPixelSize(13)
        if groupLabel != '':
            self.groupLabel = LabelItem(anchor=(1, 1))
            self.groupLabel.setParentItem(self.getViewBox())
            self.groupLabel.setText(groupLabel)
            self.groupLabel.setPos(10, 0)
            self.groupLabel.setColor(colors.fg)
        if showXY:
            self.xyLabel = LabelItem(anchor=(1, 1))
            self.xyLabel.setParentItem(self.getViewBox())
            self.xyLabel.setColor(colors.fg)

    def init(self):
        self.showGrid(x=True, y=True, alpha=0.1)
        self.showAxis('top')
        self.getAxis('top').setStyle(showValues=False)
        self.showLabel('top', show=False)
        # self.setLabel('left','<font size="5">Current (pA)</font>') # no label needed as output channels can have various different units -> use plot labels instead
        self.setMouseEnabled(x=False, y=True) # keep auto pan in x running, use settings to zoom in x
        self.disableAutoRange(pg.ViewBox.XAxis)
        self.setAxisItems({'left': SciAxisItem('left')})
        self.setAxisItems({'right': SciAxisItem('right')})
        self.updateGrid()
        self.setAxisItems({'bottom': pg.DateAxisItem()}) #, size=5
        self.setLabel('bottom', '<font size="4">Time</font>', color=colors.fg) # has to be after setAxisItems
        self.getAxis('bottom').setTickFont(self.plotWidgetFont)
        self.connectMouse()

    def finalizeInit(self):
        # self.setContentsMargins(0, 0, 10, 0) # prevent right axis from being cut off
        for pos in ['left','top','right','bottom']:
            self.getAxis(pos).setPen(pg.mkPen(color=colors.fg, width=2)) # avoid artifacts with too thin lines
            self.getAxis(pos).setTextPen(pg.mkPen(color=colors.fg))
        for pos in ['left','right']:
            self.getAxis(pos).setTickFont(self.plotWidgetFont)
            self.getAxis(pos).setWidth(self.tickWidth) # fixed space independent on tick formatting. labels may be hidden if too small!
        # self.addLegend(labelTextColor=colors.fg, colCount=3, offset=0.1, labelTextSize='8pt') # before adding plots # call externally if needed
        # self.disableAutoRange() # 50 % less CPU usage for about 1000 data points. For 10000 and more it does not make a big difference anymore.

    def connectMouse(self):
        # call after adding to GraphicsLayout as scene is not available before
        self.scene().sigMouseMoved.connect(self.mouseMoveEvent)
        self.sigXRangeChanged.connect(self.parentPlot)

    def mouseMoveEvent(self, ev):
        if self.showXY:
            pos = ev # called with QPointF instead of event?
            if self.getViewBox().geometry().contains(pos): # add offset
                pos = self.getViewBox().mapSceneToView(pos)
                try:
                    if self.ctrl.logYCheck.isChecked():
                        self.xyLabel.setText(f"t = {datetime.fromtimestamp(pos.x()).strftime('%Y-%m-%d %H:%M:%S')}, y = {10**pos.y():.2e}")
                    else:
                        self.xyLabel.setText(f"t = {datetime.fromtimestamp(pos.x()).strftime('%Y-%m-%d %H:%M:%S')}, y = {pos.y():.2f}")
                    self.xyLabel.setPos(self.getViewBox().geometry().width()-self.xyLabel.boundingRect().width()-4, 2)
                except (OSError, ValueError, OverflowError): # as e throws errors before time axis is initialized
                    # self._parent.print(f'PlotItem mouseMoveError: {e}', flag=PRINT.DEBUG)
                    pass
            else:
                self.xyLabel.setText('')
        if isinstance(ev, QMouseEvent):
            super().mouseMoveEvent(ev)

    def parentPlot(self):
        """Plot if Xrange changed by user.
        When looking at larger x ranges sections might not be shown due to data thinning.
        Make sure the number of displayed data points is appropriate for your data."""
        if self._parent is not None and self.getViewBox().mouseEnabled()[0]:
            # self._parent.print('sigXRangeChanged', flag=PRINT.DEBUG)
            self._parent.parentPlugin.signalComm.plotSignal.emit()

class PlotWidget(pg.PlotWidget):
    """PlotWidget providing xyLabel."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs, plotItem = PlotItem(**kwargs))
        self.init = self.getPlotItem().init
        self.finalizeInit = self.getPlotItem().finalizeInit
        self.setMinimumHeight(30) # can fit more plots on top of each other
        self.setBackground(colors.bg)

    @property
    def legend(self):
        return self.plotItem.legend

class LabelItem(pg.LabelItem):

    def setColor(self, color):
        self.setText(self.text, color=color)

class SciAxisItem(pg.AxisItem): # pylint: disable = abstract-method
    """Based on original logTickStrings.
    Only difference to source code is 0.1g -> .0e and consistent use of 1 = 10⁰."""
    # based on https://pyqtgraph.readthedocs.io/en/latest/_modules/pyqtgraph/graphicsItems/AxisItem.html

    # no ticks when zooming in too much: https://github.com/pyqtgraph/pyqtgraph/issues/1505

    def __init__(self, orientation, pen=None, textPen=None, tickPen=None, linkView=None, parent=None, maxTickLength=-5, showValues=True, text='', units='', unitPrefix='', **args):
        super().__init__(orientation, pen, textPen, tickPen, linkView, parent, maxTickLength, showValues, text, units, unitPrefix, **args)
        self.enableAutoSIPrefix(False) # always show complete numbers in ticks. especially for currents and pressures dividing by a random factor is very confusing

    def logTickStrings(self, values, scale, spacing):
        estrings = [f'{x:.0e}' for x in 10 ** np.array(values) * scale]
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

class TimeoutLock(object):
    """A Lock that allows to specify a timeout inside a with statement.
    Can be used as normal Lock or optionally using 'with self.lock.acquire_timeout(1) as lock_acquired:'"""
    # based on https://stackoverflow.com/questions/16740104/python-lock-with-statement-and-timeout
    def __init__(self, _parent):
        self._lock = threading.Lock()
        self._parent = _parent
        self.print = _parent.print

    def acquire(self, blocking=True, timeout=-1):
        return self._lock.acquire(blocking, timeout)

    @contextmanager
    def acquire_timeout(self, timeout, timeoutMessage=None, lock_acquired=False):
        """
        :param timeout: timeout in seconds
        :type timeout: float, optional
        :param timeoutMessage: Message shown in case of a timeout
        :type timeoutMessage: str, optional
        :param lock_acquired: True if lock has already been acquired in callstack. Use to prevent deadlocks
        :type lock_acquired: bool, optional
        """
        result = lock_acquired or self._lock.acquire(timeout=timeout)

        # use next three lines only temporary to get more information on errors (file and line number not available when using except)
        # yield result
        # if result and not lock_acquired:
        #     self._lock.release()

        try:
            yield result
        except Exception as e:
            self.print(f'Error while using lock: {e}\nStack:{"".join(traceback.format_stack()[:-1])}', flag=PRINT.ERROR) # {e}
            self._parent.errorCount += 1
        finally:
            if result and not lock_acquired:
                self._lock.release()
            if self._parent.errorCount > 10:
                if hasattr(self._parent, 'closeCommunication'):
                    self.print(f'Closing communication of {self._parent.name} after more than 10 consecutive errors.', flag=PRINT.ERROR) # {e}
                    self._parent.closeCommunication()
        if not result and timeoutMessage is not None:
            self.print(timeoutMessage, flag=PRINT.ERROR)

    def release(self):
        self._lock.release()

    def __enter__(self):
        self._lock.__enter__()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._lock.__exit__(exc_type, exc_val, exc_tb)

class DeviceController(QObject):
    """Each :class:`~esibd.plugins.Device` or :class:`~esibd.core.Channel` comes with a :class:`~esibd.core.DeviceController`. The
    :class:`~esibd.core.DeviceController` is not itself a :class:`~esibd.plugins.Plugin`. It only abstracts the direct
    hardware communication from :class:`plugins<esibd.plugins.Plugin>` allowing them to use minimal and
    consistent code that can be adjusted and reused independently of the
    hardware. It should do all resource or time intensive communication work
    in parallel threads to keep the GUI responsive. Following the
    producer-consumer pattern, the :class:`~esibd.core.DeviceController` reads values from a physical device and assigns
    them to the corresponding :class:`~esibd.core.Channel`. The :class:`devices<esibd.plugins.Device>` will collect data from
    the :class:`~esibd.core.Channel` independently. In case you work with time sensitive
    experiments this concept will need to be adapted. Feel free to use the
    basic functionality provided by :class:`~esibd.core.DeviceController` or implement
    your own from scratch. As the :class:`~esibd.core.DeviceController` only interacts with your
    custom :class:`~esibd.core.Channel` or :class:`~esibd.plugins.Device`, there are no general requirements for
    its implementation."""

    class SignalCommunicate(QObject): # signals called from external thread and run in main thread
        """Object that bundles pyqtSignals for the :class:`~esibd.core.DeviceController`. Extend to add additional events."""
        initCompleteSignal = pyqtSignal()
        """Signal that is emitted after successful initialization of device communication."""
        closeCommunicationSignal = pyqtSignal()
        """Signal that triggers the acquisition to stop after communication errors."""
        updateValueSignal = pyqtSignal()
        """Signal that transfers new data from the :attr:`~esibd.core.DeviceController.acquisitionThread` to the corresponding channels."""

    parent : any # Device or Channel, cannot specify without causing circular import
    """Reference to the associated class."""
    print : callable
    """Reference to :meth:`~esibd.plugins.Plugin.print`."""
    port : serial.Serial = None
    """Port for serial communication."""
    initThread : Thread = None
    """A parallel thread used to initialize communication."""
    acquisitionThread : Thread = None
    """A parallel thread that regularly reads values from the device."""
    lock : TimeoutLock # Lock
    """Lock used to avoid race conditions when communicating with the hardware."""
    acquiring : bool = False
    """True, while *acquisitionThread* is running. *AcquisitionThread* terminates if set to False."""
    initialized : bool = False
    """Indicates if communications has been initialized successfully and not yet terminated."""
    initializing : bool = False
    """Indicates if communications is being initialized."""

    def __init__(self, _parent):
        super().__init__()
        self.channel = None # overwrite with parent if applicable
        self.device = _parent # overwrite with channel.getDevice() if applicable
        self.lock = TimeoutLock(_parent=self) # init here so each instance gets its own lock
        self.port = None
        self.signalComm = self.SignalCommunicate()
        self.signalComm.initCompleteSignal.connect(self.initComplete)
        self.signalComm.updateValueSignal.connect(self.updateValue)
        self.signalComm.closeCommunicationSignal.connect(self.closeCommunication)

    @property
    def name(self):
        return self.device.name # initially set to _parent, may be overwritten with self.channel.getDevice()

    @property
    def errorCount(self):
        return self.device.errorCount
    @errorCount.setter
    def errorCount(self, count):
        self.device.errorCount = count

    def print(self, message, flag=PRINT.MESSAGE):
        controller_name = f'{self.channel.name[:15]:15s} controller' if self.channel is not None else 'Controller'
        self.device.print(f'{controller_name}: {message}', flag=flag)

    def initializeCommunication(self):
        """Starts the :meth:`~esibd.core.DeviceController.initThread`."""
        self.print('initializeCommunication', PRINT.DEBUG)
        if self.initializing:
            return
        if self.acquisitionThread is not None and self.acquisitionThread.is_alive():
            self.closeCommunication() # terminate old thread before starting new one
        self.initializing = True
        self.errorCount = 0
        self.initThread = Thread(target=self.fakeInitialization if getTestMode() else self.runInitialization, name=f'{self.device.name} initThread')
        self.initThread.daemon = True
        self.initThread.start() # initialize in separate thread

    def runInitialization(self):
        """Hardware specific initialization of communication. Executed in initThread (no access to GUI!)."""

    def fakeInitialization(self):
        """Called in test mode instead of runInitialization"""
        time.sleep(2)
        self.signalComm.initCompleteSignal.emit()
        self.print('Faking values for testing!', PRINT.WARNING)
        self.initializing = False

    def initComplete(self):
        """Called after successful initialization to start acquisition from main thread (access to GUI!)."""
        self.initialized = True
        self.startAcquisition()

    def startAcquisition(self):
        """Starts data acquisition from physical device."""
        self.print('startAcquisition', PRINT.DEBUG)
        if not self.initialized:
            self.print('Cannot start acquisition. Not initialized', PRINT.DEBUG)
            return
        if self.acquisitionThread is not None and self.acquisitionThread.is_alive():
            if self.device.log:
                self.device.print('Wait for data reading thread to complete before restarting acquisition.', PRINT.WARNING)
            self.acquiring = False
            self.acquisitionThread.join(timeout=5)
            if self.acquisitionThread.is_alive():
                self.print('Data reading thread did not complete. Reset connection manually.', PRINT.ERROR)
                return
        self.acquisitionThread = Thread(target=self.runAcquisition, args =(lambda: self.acquiring,), name=f'{self.device.name} acquisitionThread')
        self.acquisitionThread.daemon = True
        self.acquiring = True # terminate old thread before starting new one
        self.acquisitionThread.start()

    def runAcquisition(self, acquiring):
        """Runs acquisition loop. Executed in acquisitionThread.
        Overwrite with hardware specific acquisition code."""
        while acquiring():
            with self.lock.acquire_timeout(1, timeoutMessage='Could not acquire lock to acquire data') as lock_acquired:
                if lock_acquired:
                    if getTestMode():
                        pass # implement fake feedback
                    else:
                        pass # implement real feedback
                    self.signalComm.updateValueSignal.emit()
            time.sleep(self.device.interval/1000) # release lock before waiting!

    def updateValue(self):
        """Called from acquisitionThread to update the
        value of the channel(s) in the main thread.
        Overwrite with specific update code."""

    def closeCommunication(self):
        """Closes all open ports.
        This should free up all resources and allow for clean reinitialization.
        Extend to add hardware specific code
        Make sure acquisition is stopped before communication is closed.
        """
        self.print('closeCommunication', PRINT.DEBUG)
        if self.acquiring:
            self.stopAcquisition() # only call if not already called by device
        self.initialized = False

    def stopAcquisition(self):
        """Terminates acquisition but leaves communication initialized."""
        self.print('stopAcquisition', PRINT.DEBUG)
        if self.device.recording and self.channel is None:
            # stop recording if controller is stopping acquisition
            # continue if only a channel controller is stopping acquisition
            self.device.recording = False
        if self.acquisitionThread is not None:
            with self.lock.acquire_timeout(1, timeoutMessage='Could not acquire lock to stop acquisition.'):
                # use lock in runAcquisition to make sure acquiring flag is not changed before last call completed
                # set acquiring flag anyways if timeout expired. Possible errors have to be handled
                self.acquiring = False
            return True
        return False

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
            self.clearBuffer(port) # make sure communication does not break if for any reason the port is not empty. E.g. old return value has not been read.
            port.write(bytes(message, encoding))
        except serial.SerialTimeoutException as e:
            self.print(f'Timeout while writing message, try to reinitialize communication: {e}. Message: {message}.', PRINT.ERROR)
        except serial.PortNotOpenError as e:
            self.print(f'Port not open, try to reinitialize communication: {e}. Message: {message}.', PRINT.ERROR)
            self.signalComm.closeCommunicationSignal.emit()
        except serial.SerialException as e:
            self.print(f'Serial error, try to reinitialize communication: {e}. Message: {message}.', PRINT.ERROR)
            self.signalComm.closeCommunicationSignal.emit()
        except AttributeError as e:
            self.print(f'Attribute error, try to reinitialize communication: {e}. Message: {message}.', PRINT.ERROR)
            if port is not None:
                self.signalComm.closeCommunicationSignal.emit()

    def serialRead(self, port, encoding='utf-8', EOL='\n', strip=None):
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
            if EOL == '\n':
                if strip is not None:
                    return port.readline().decode(encoding).strip(strip).rstrip()
                else:
                    return port.readline().decode(encoding).rstrip()
            else: # e.g. EOL == '\r'
                if strip is not None:
                    return port.read_until(EOL.encode(encoding)).decode(encoding).strip(strip).rstrip()
                else:
                    return port.read_until(EOL.encode(encoding)).decode(encoding).rstrip()
        except UnicodeDecodeError as e:
            self.print(f'Error while decoding message: {e}', PRINT.ERROR)
        except serial.SerialTimeoutException as e:
            self.print(f'Timeout while reading message, try to reinitialize communication: {e}', PRINT.ERROR)
            self.signalComm.closeCommunicationSignal.emit()
        except serial.SerialException as e:
            self.print(f'Serial error, try to reinitialize communication: {e}', PRINT.ERROR)
            self.signalComm.closeCommunicationSignal.emit()
        except AttributeError as e:
            self.print(f'Attribute error, try to reinitialize communication: {e}', PRINT.ERROR)
            if port is not None:
                self.signalComm.closeCommunicationSignal.emit()
        return ''

    def clearBuffer(self, port=None):
        port = port if port is not None else self.port
        if port is None:
            return
        x = port.inWaiting()
        if x > 0:
            port.read(x)

class SplashScreen(QSplashScreen):
    """Program splash screen that indicates loading."""

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
        self.index = np.mod(self.index + 1, len(SPLASHIMAGE))
        self.label.setPixmap(QPixmap(SPLASHIMAGE[self.index].as_posix()))

    def show(self):
        super().show()
        QApplication.processEvents()

    def close(self):
        self.closed=True
        self.timer.stop()
        return super().close()

class VideoRecorder():
    """Allows to record videos of a plugin."""
    # ! capture real contextual cursor instead of drawing fixed cursor requires recording with external library FFmpeg

    def __init__(self, parentPlugin):
        self.parentPlugin = parentPlugin
        self.recordWidget = parentPlugin.dock
        self.timer = QTimer()
        self.timer.timeout.connect(self.capture_frame)
        self.fps = 10  # Frames per second
        self.frameCount = 0
        self.is_recording = False
        self.cursor_pixmap = self.parentPlugin.makeCoreIcon('cursor.png').pixmap(32)

    def startRecording(self):
        # return
        if self.parentPlugin.pluginManager.testing and not self.parentPlugin.pluginManager.Settings.showVideoRecorders:
            return
        self.frameCount = 0
        self.video_writer = None
        self.screen = QGuiApplication.screenAt(self.recordWidget.mapToGlobal(QPoint(0, 0)))
        if self.screen is not None:
            self.is_recording = True
            self.parentPlugin.pluginManager.Settings.incrementMeasurementNumber()
            self.file = self.parentPlugin.pluginManager.Settings.getMeasurementFileName(f'_{self.parentPlugin.name}.mp4')
            self.parentPlugin.videoRecorderAction.state = True
            self.parentPlugin.videoRecorderAction.setVisible(True)
            self.screen_geometry = self.screen.geometry()
            self.dpr = self.screen.devicePixelRatio()
            self.timer.start(int(1000 / self.fps))
            self.parentPlugin.print(f'Start recording {self.file.name}')
        else:
            self.parentPlugin.print('Cannot start recording. Screen not found.', flag=PRINT.ERROR)

    def capture_frame(self):
        if not self.is_recording:
            return
        full_screenshot = self.screen.grabWindow(0) # should be called from main thread

        # Capture the current mouse position
        cursor_pos_global  = QCursor().pos()
        # Overlay the cursor on the full-screen image
        painter = QPainter(full_screenshot)
        painter.drawPixmap(int((cursor_pos_global.x() - self.screen_geometry.x())), int((cursor_pos_global.y() - self.screen_geometry.y())), self.cursor_pixmap)
        painter.end()
        global_pos = self.recordWidget.mapToGlobal(QPoint(0, 0))  # Widget's global position
        screen_x = global_pos.x() - self.screen_geometry.x()
        screen_y = global_pos.y() - self.screen_geometry.y()
        # Define cropping rectangle in local screen coordinates
        rect = QRect(int(screen_x * self.dpr), int(screen_y * self.dpr), int(self.recordWidget.width() * self.dpr), int(self.recordWidget.height() * self.dpr))
        cropped_screenshot = full_screenshot.copy(rect)
        image = cropped_screenshot.toImage().convertToFormat(QImage.Format.Format_RGBA8888)  # Ensure correct format
        if self.frameCount == 0:
            self.width, self.height = image.width(), image.height()
            # Note cv2.VideoWriter_fourcc(*'H264') H.264 codec (MPEG-4 AVC) would achieve smaller file sizes,
            # but requires independent codec installation and would not work out of the box
            self.video_writer = cv2.VideoWriter(self.file, cv2.VideoWriter_fourcc(*"mp4v"), self.fps, (self.width, self.height))
        elif (image.width(), image.height()) != (self.width, self.height):
            self.parentPlugin.print('Resizing during video recording not supported. Stopping recording.', flag=PRINT.WARNING)
            self.stopRecording()
            return
        elif self.frameCount > 600*self.fps: # limit recording to 10 minutes
            self.parentPlugin.print('Stopping video recording after reaching 5 minute limit.', flag=PRINT.WARNING)
            self.stopRecording()
            return
        buffer = image.bits() # Get image data as a bytes object
        buffer.setsize(image.sizeInBytes())
        frame = np.frombuffer(buffer, dtype=np.uint8).reshape((self.height, self.width, 4)) # Convert to NumPy array
        frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGBA2BGR) # Convert RGBA to BGR for OpenCV
        self.video_writer.write(frame_bgr)
        self.frameCount += 1

    def stopRecording(self):
        if self.is_recording:
            self.timer.stop()
            self.parentPlugin.videoRecorderAction.state = False
            if self.frameCount == 0:
                self.parentPlugin.print('No frames have been recorded')
                return
            self.is_recording = False
            self.video_writer.release()
            self.parentPlugin.print(f'Saved {self.file.name}')
            self.parentPlugin.pluginManager.Explorer.populateTree()

class RippleEffect(QWidget):
    """Creates a fading ripple effect at the clicked QAction."""

    def __init__(self, parent, x, y, color=QColor(138, 180, 247)):
        super().__init__(parent)
        self.x, self.y = x, y
        self.color = color
        self.radius = 20  # Initial ripple size
        self.opacity = 1.0  # Full opacity
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.expand)
        self.timer.start(80)  # ms steps
        self.setGeometry(parent.rect())
        self.show()

    def expand(self):
        """Expands and fades the ripple effect."""
        self.radius -= 4  # Increase size
        self.opacity -= 0.1  # Reduce opacity
        if self.opacity <= 0 or self.radius <= 0:
            self.timer.stop()
            self.deleteLater()  # Remove effect
        self.update()  # Trigger repaint

    def paintEvent(self, event):
        """Draws the ripple effect."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(self.color.red(), self.color.green(), self.color.blue(), int(255 * self.opacity))
        pen = QPen(color, 6)
        painter.setPen(pen)
        painter.drawEllipse(self.x - self.radius, self.y - self.radius, self.radius * 2, self.radius * 2)

class MouseInterceptor(QObject):

    rippleEffectSignal = pyqtSignal(int, int, QColor)

    def __init__(self, window):
        super().__init__()
        self.window = window
        self.rippleEffectSignal.connect(self.ripple)

    def ripple(self, x, y, color):
        RippleEffect(self.window, x, y, color)

    def eventFilter(self, obj, event):
        """Intercepts mouse clicks and applies ripple effect."""
        if isinstance(event, QMouseEvent) and event.type() == QMouseEvent.Type.MouseButtonPress and self.window.pluginManager.Settings.showMouseClicks:
            local_pos = self.window.mapFromGlobal(event.globalPosition().toPoint())
            if event.button() == Qt.MouseButton.LeftButton:
                QTimer.singleShot(200, lambda: self.rippleEffectSignal.emit(local_pos.x(), local_pos.y(), QColor(colors.highlight)))
            elif event.button() == Qt.MouseButton.RightButton:
                QTimer.singleShot(200, lambda: self.rippleEffectSignal.emit(local_pos.x(), local_pos.y(), QColor(255, 50, 50)))
        return False
