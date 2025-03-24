""" This module contains only :class:`plugins<esibd.plugins.Plugin>` and plugin templates.
The user controls generally have a large amount of logic integrated and can act as an intelligent database.
This avoids complex and error prone synchronization between redundant data in the UI and a separate database.
Every parameter should only exist in one unique location at run time."""
# Separating the logic from the PyQt specific UI elements may be required in the future,
# but only if there are practical and relevant advantages that outweigh the drawbacks of managing synchronization."""

import sys
import os
import io
import ast
import itertools
import requests
from itertools import islice
from pathlib import Path
from threading import Thread, Timer, current_thread, main_thread
from typing import List
import timeit
import time
import inspect
from datetime import datetime
import configparser
# import traceback
import h5py
import simple_pid
import numpy as np
# from scipy.ndimage import uniform_filter1d
import pyperclip
from send2trash import send2trash
from asteval import Interpreter
import keyboard as kb
import pyqtgraph as pg
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.backend_bases import MouseButton
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from PyQt6.QtWidgets import (QLineEdit, QWidget, QSizePolicy, QScrollBar, QPushButton, QPlainTextEdit, QHBoxLayout, QVBoxLayout, QLabel,
                            QTreeWidgetItem, QTreeWidget, QApplication, QTreeWidgetItemIterator, QMenu, QHeaderView, QToolBar,
                            QFileDialog, QInputDialog, QComboBox, QSpinBox, QCheckBox, QToolButton, QSplitter, QDockWidget)
from PyQt6.QtGui import QFont, QKeySequence, QShortcut, QIcon, QImage, QAction, QTextCursor #, QPixmap, QScreen, QColor
from PyQt6.QtCore import Qt, QUrl, QSize, QLoggingCategory, pyqtSignal, QObject, QTimer #, QRect
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6 import QtCore
import esibd.core as EsibdCore
import esibd.const as EsibdConst
from esibd.core import (INOUT, Parameter, PluginManager, parameterDict, DynamicNp, PRINT, Channel, MetaChannel, TimeoutLock, ScanChannel, RelayChannel, # DeviceController,
                        ToolButton, QLabviewSpinBox, QLabviewDoubleSpinBox, QLabviewSciSpinBox, MultiState, PlotWidget, PlotItem, TreeWidget, Icon)
from esibd.const import * # pylint: disable = wildcard-import, unused-wildcard-import  # noqa: F403
if sys.platform == 'win32':
    import win32com.client
aeval = Interpreter()

class Plugin(QWidget):
    """:class:`Plugins<esibd.plugins.Plugin>` abstract basic GUI code for devices, scans, and other high level UI elements.
    All plugins are ultimately derived from the :class:`~esibd.plugins.Plugin` class.
    The doc string of the plugin class will be shown in the corresponding help window
    unless documentation is implemented explicitly."""

    LOAD    = 'Load'
    SAVE    = 'Save'
    IMPORT  = 'Import'
    EXPORT  = 'Export'
    TIME    = 'Time'
    UTF8    = 'utf-8'
    FILTER_INI_H5 = 'INI or H5 File (*.ini *.h5)'
    previewFileTypes : List[str] = [] # specify in child class if applicable
    """File extensions that are supported by this plugin. If a corresponding
       file is selected in the :meth:`~esibd.plugins.Explorer`, the plugins :meth:`~esibd.plugins.Plugin.loadData` function will be called."""
    pluginType : PluginManager.TYPE = PluginManager.TYPE.INTERNAL # overwrite in child class mandatory
    """The type defines the location of the plugin in the user interface and allows to run
       operations on a group of plugins with the same type using :meth:`~esibd.core.PluginManager.getPluginsByType`."""
    name : str          = '' # specify in child class mandatory
    """A unique name that will be used in the graphic user interface.
       Plugins can be accessed directly from the :ref:`sec:console` using their name."""
    documentation : str = None # specify in child class
    """The plugin documentation used in the internal about dialog in the :ref:`sec:browser`.
    If None, the doc string *__doc__* will be used instead.
    """
    version : str       = '' # specify in child class mandatory
    """The version of the plugin. Plugins are independent programs that
       require independent versioning and documentation."""
    optional : bool     = True # specify in child to prevent user from disabling this plugin
    """Defines if the user can deactivate the plugin in the :class:`~esibd.core.PluginManager` user interface."""
    supportedVersion : str = f'{PROGRAM_VERSION.major}.{PROGRAM_VERSION.minor}'
    """By default the current program version is used. You can
       define a fixed plugin version and future program versions will
       state that they are incompatible with this plugin. This can be used to
       prompt developers to update and test their plugins before
       distributing them for a more recent program version."""
    dependencyPath = Path('') # will be set when plugin is loaded. dependencies can be in the same folder as the plugin file or sub folders therein
    titleBar : QToolBar
    """Actions can be added to the titleBar using :meth:`~esibd.plugins.Plugin.addAction` or :meth:`~esibd.plugins.Plugin.addStateAction`."""
    titleBarLabel : QLabel
    """The label used in the titleBar."""
    canvas : FigureCanvas
    """The canvas the figure renders into."""
    navToolBar : EsibdCore.ThemedNavigationToolbar
    """Provides controls to interact with the figure."""
    dependencyPath : Path
    """Path to the plugin file defining the plugin. Can be used to locate
       corresponding dependencies like external scripts or media which are
       stored next to the plugin file or in sub folders relative to its location."""
    pluginManager : EsibdCore.PluginManager
    """A reference to the central :class:`~esibd.core.PluginManager`."""
    dock : EsibdCore.DockWidget
    """The dockWidget that allows to float and rearrange the plugin user interface."""
    scan = None
    """A :meth:`~esibd.plugins.Scan` that provides content to display."""
    fig : plt.figure
    """A figure, initialized e.g. using `plt.figure(constrained_layout=True, dpi=getDPI())`
       and followed by `self.makeFigureCanvasWithToolbar(self.fig)`."""
    axes : List[mpl.axes.Axes]
    """The axes of :attr:`~esibd.plugins.Plugin.fig`."""
    initializedGUI : bool
    """A flag signaling if the plugin graphical user interface has been initialized.
       You may want to ignore certain events before initialization is complete."""
    initializedDock : bool
    """A flag signaling if the plugin :attr:`~esibd.plugins.Plugin.dock` has been initialized.
       You may want to ignore certain events before initialization is complete."""
    lock : TimeoutLock
    """Locks are used to make sure methods decorated with @synchronized() cannot run in parallel,
       but one call has to be completed before the next."""
    iconFile : str = ''
    """Default icon file. Expected to be in dependencyPath."""
    iconFileDark : str = ''
    """Default icon file for dark mode. Expected to be in dependencyPath. Will fallback to iconFile."""
    useAdvancedOptions : bool = False
    """Adds toolbox icon to show advanced plugin options."""

    class SignalCommunicate(QObject): # signals that can be emitted by external threads
        """Object than bundles pyqtSignals for the Channelmanager"""
        testCompleteSignal = pyqtSignal()

    def __init__(self, pluginManager=None, dependencyPath=None):
        super().__init__()
        if pluginManager is not None:
            self.pluginManager = pluginManager # provide access to other plugins through pluginManager
        self.display = None # may be added by child class
        self._loading = 0
        self.labelAnnotation = None
        self.dock = None
        self.lock = TimeoutLock(_parent=self)
        self.fig = None
        self.errorCount = 0
        self.axes = []
        self.canvas = None
        self.navToolBar = None
        self.copyAction = None
        self.initializedGUI = False
        self.initializedDock = False # visible in GUI, some plugins will only appear when needed to display specific content
        if dependencyPath is not None:
            self.dependencyPath = dependencyPath
        self.dataClipboardIcon = self.makeCoreIcon('clipboard-paste-document-text.png')
        self.imageClipboardIcon = self.makeCoreIcon('clipboard-paste-image.png')
        self._testing = False
        self.signalComm = self.SignalCommunicate()
        self.signalComm.testCompleteSignal.connect(self.testComplete)

    def print(self, message, flag=PRINT.MESSAGE):
        """The print function will send a message to stdout, the statusbar, the
        :ref:`sec:console`, and if enabled to the logfile. It will automatically add a
        timestamp and the name of the sending plugin.

        :param message: A short informative message.
        :type message: str
        :param flag: Flag used to adjust message display, defaults to :attr:`~esibd.const.PRINT.MESSAGE`
        :type flag: :meth:`~esibd.const.PRINT`, optional
        """
        self.pluginManager.logger.print(message, self.name, flag)

    @property
    def loading(self):
        """A flag that can be used to suppress certain events while loading data or initializing the user interface.
        Make sure the flag is reset after every use. Internal logic allows nested use."""
        return self._loading != 0

    @loading.setter
    def loading(self, loading):
        if loading:
            self._loading +=1
        else:
            self._loading -= 1

    def test(self):
        """Runs :meth:`~esibd.plugins.Plugin.runTestParallel` in parallel thread."""
        self.raiseDock(True)
        self.testing = True
        self.print(f'Starting testing for {self.name} {self.version}.')
        self.pluginManager.Console.mainConsole.input.setText(f'{self.name}.stopTest()') # prepare to stop
        Timer(0, self.runTestParallel).start()

    def stopTest(self):
        self.signalComm.testCompleteSignal.emit()

    def testControl(self, control, value, delay=0, label=None):
        """Changes control states and triggers corresponding events."""
        if not self.testing:
            return
        widget = control
        if label is not None:
            message = label
        elif hasattr(control, 'toolTip') and not isinstance(control, (QAction)):
            # Actions already have tooltip in their objectName
            message = f'Testing {control.objectName()} with value {value} {control.toolTip() if callable(control.toolTip) else control.toolTip}  '
        else:
            message = f'Testing {control.objectName()} with value {value}'
        message = message.replace('\n', '')
        message = message if len(message) <= 86 else f'{message[:83]}…' # limit length to keep log clean
        with self.lock.acquire_timeout(5, timeoutMessage=f'Could not acquire lock to test {message}') as lock_acquired: # allow any critical function to finish before testing next control
            if lock_acquired:
                self.print(message)
                if hasattr(control, 'signalComm'):
                    control.signalComm.setValueFromThreadSignal.emit(value)
                if isinstance(control, QAction):
                    if isinstance(control, (EsibdCore.StateAction, EsibdCore.MultiStateAction)):
                        control.state = value
                    control.triggered.emit(value) # c.isChecked()
                    widget = control.associatedObjects()[1] # second object is associated QToolButton
                elif isinstance(control, QComboBox):
                    index = control.findText(str(value))
                    control.setCurrentIndex(index)
                    control.currentIndexChanged.emit(index) # c.currentIndex()
                elif isinstance(control, (QLineEdit)):
                    control.editingFinished.emit()
                elif isinstance(control, (QSpinBox, QLabviewSpinBox, QLabviewDoubleSpinBox, QLabviewSciSpinBox)):
                    control.valueChanged.emit(value)
                    control.editingFinished.emit()
                elif isinstance(control, (QCheckBox)):
                    control.setChecked(value)
                    control.stateChanged.emit(value) # c.isChecked()
                elif isinstance(control, (QToolButton, QPushButton)):
                    control.clicked.emit()
                elif isinstance(control, (pg.ColorButton)):
                    control.sigColorChanged.emit(control)
                elif isinstance(control, (QLabel)):
                    pass # ignore labels as they are always indicators and not connected to events
                else:
                    self.print(f'No test implemented for class {type(control)}')
                if current_thread() is not main_thread(): # self.pluginManager.Settings.showMouseClicks and
                    main_center = widget.mapTo(self.pluginManager.mainWindow, widget.rect().center())
                    QApplication.instance().mouseInterceptor.rippleEffectSignal.emit(
                    main_center.x(), main_center.y(), QColor(colors.highlight))
                    time.sleep(.1)
        # Sleep after releasing lock!
        # Use minimal required delays to make sure event can be processed before triggering next one.
        # Ideally acquire lock to process event and make sure next one is triggered one lock is released, instead of using delay.
        time.sleep(max(delay, 0.5) if self.pluginManager.Settings.showVideoRecorders else delay)

    def runTestParallel(self):
        """Runs a series of tests by changing values of selected controls and triggering the corresponding events.
        Extend and add call to super().runTestParallel() to the end to make sure testing flag is set to False after all test completed!
        """
        # ... add sequence of spaced events to trigger and test all functionality
        if self.initializedDock:
            self.testControl(self.aboutAction, True)
        self.signalComm.testCompleteSignal.emit()

    @synchronized()
    def testComplete(self):
        # queue this behind any other synchronized function that is still being tested
        self.testing = False

    @property
    def testing(self):
        return self.pluginManager.testing
    @testing.setter
    def testing(self, state):
        self._testing = state

    def processEvents(self):
        if not self.testing: # avoid triggering unrelated events queued by testing
            QApplication.processEvents()

    def waitForCondition(self, condition, interval=0.1, timeout=5, timeoutMessage =''):
        """Waits until condition returns false or timeout expires.
        This can be safer and easier to understand than using signals and locks.
        The flag not just blocks other functions but informs them and allows them to react instantly.

        :param condition: will wait for condition to return True
        :type condition: callable
        :param interval: wait interval seconds before checking condition
        :type interval: float
        :param timeout: timeout in seconds
        :type timeout: float
        :param timeoutMessage: message displayed if timeout is reached
        :type timeoutMessage: str
        """
        start = time.time()
        self.print(f'Waiting for {timeoutMessage}', flag=PRINT.DEBUG)
        while not condition():
            if time.time() - start < timeout:
                time.sleep(interval)
                if current_thread() is main_thread(): # do not block other events in main thread
                    self.processEvents()
            else:
                self.print(f'Timeout reached while waiting for {timeoutMessage}', flag=PRINT.ERROR)
                return False
        return True

    def addToolbarStretch(self):
        self.stretchAction = QAction() # allows adding actions in front of stretch later on
        self.stretchAction.setVisible(False)
        self.titleBar.addAction(self.stretchAction)
        self.stretch = QWidget() # acts as spacer
        self.stretch.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.titleBar.addWidget(self.stretch)

    def setFloat(self):
        if self.initializedDock:
            self.dock.setFloating(self.floatAction.state)
            if not self.floatAction.state:
                self.raiseDock()

    def initGUI(self):
        """Initializes the graphic user interface (GUI), independent of all other plugins."""
        # hierarchy: self -> mainDisplayLayout -> mainDisplayWidget -> mainLayout
        # mainDisplayLayout and mainDisplayWidget only exist to enable conversion into a dockArea
        # mainLayout contains the actual content
        self.print('initGUI', PRINT.DEBUG)
        if not self.initializedGUI:
            if self.layout() is None: # layout will be retained even if dock is closed.
                self.mainDisplayLayout = QVBoxLayout()
                self.setLayout(self.mainDisplayLayout)
                self.mainDisplayLayout.setContentsMargins(0, 0, 0, 0)
            self.mainDisplayWidget = QWidget()
            self.mainDisplayLayout.addWidget(self.mainDisplayWidget)
            self.mainLayout = QVBoxLayout()
            self.mainLayout.setContentsMargins(0, 0, 0, 0)
            self.mainDisplayWidget.setLayout(self.mainLayout)
            self.vertLayout = QVBoxLayout() # contains row(s) with buttons on top and content below
            self.vertLayout.setSpacing(0)
            self.vertLayout.setContentsMargins(0, 0, 0, 0)
            self.mainLayout.addLayout(self.vertLayout)
            self.titleBar = QToolBar()
            self.titleBar.setIconSize(QSize(16, 16))
            self.titleBarLabel = QLabel('')
            self.titleBar.addWidget(self.titleBarLabel)
            if self.useAdvancedOptions:
                self.advancedAction = self.addStateAction(lambda: self.toggleAdvanced(None), f'Show advanced options for {self.name}.', self.makeCoreIcon('toolbox.png'),
                                                  f'Hide advanced options for {self.name}.', self.makeCoreIcon('toolbox--pencil.png'), attr='advanced')
                self.advancedAction.state = False # always off on start
            self.initializedGUI = True

    def finalizeInit(self, aboutFunc=None):
        """Executed after all other Plugins are initialized. Use this for code
        that modifies other :class:`Plugins<esibd.plugins.Plugin>`, e.g. adding an :class:`~esibd.core.Action` to the :class:`~esibd.plugins.DeviceManager`.

        :param aboutFunc: Function displaying the about dialog of the plugin, defaults to None.
            :meth:`~esibd.plugins.Plugin.about` is used if no other is provided.
        :type aboutFunc: method, optional
        """
        # dock should be present if this is called
        self.loading = True
        self.print('finalizeInit', PRINT.DEBUG)
        self.addToolbarStretch()
        self.aboutAction = self.addAction(event=lambda: self.about() if aboutFunc is None else aboutFunc(), toolTip=f'About {self.name}.', icon=self.makeCoreIcon('help_large_dark.png' if getDarkMode() else 'help_large.png'))
        self.floatAction = self.addStateAction(event=lambda: self.setFloat(), toolTipFalse=f'Float {self.name}.', iconFalse=self.makeCoreIcon('application.png'), toolTipTrue=f'Dock {self.name}.', iconTrue=self.makeCoreIcon('applications.png')
                            # , attr='floating' cannot use same attribute for multiple instances of same class # https://stackoverflow.com/questions/1325673/how-to-add-property-to-a-class-dynamically
                            )
        if self.pluginType in [PluginManager.TYPE.DISPLAY, PluginManager.TYPE.LIVEDISPLAY] and not self == self.pluginManager.Browser:
            self.closeAction = self.addAction(lambda: self.closeUserGUI(), f'Close {self.name}.', self.makeCoreIcon('close_dark.png' if getDarkMode() else 'close_light.png'))
        self.updateTheme()
        self.loading = False
        # extend or overwrite to add code that should be executed after all other plugins have been initialized, e.g. modifications of other plugins

    def afterFinalizeInit(self):
        """Execute after all other plugins are finalized"""
        self.videoRecorderAction = self.addStateAction(event=lambda: self.toggleVideoRecorder(), toolTipFalse=f'Record video of {self.name}.',
            iconFalse=self.makeCoreIcon('record_start.png'), toolTipTrue=f'Stop and save video of {self.name}.',
            iconTrue=self.makeCoreIcon('record_stop.png'), before=self.aboutAction)
        self.videoRecorderAction.setVisible(self.pluginManager.Settings.showVideoRecorders)

    def initDock(self):
        """Initializes the :class:`~esibd.core.DockWidget`."""
        if not self.initializedDock:
            self.dock = EsibdCore.DockWidget(self)

    def provideDock(self):
        """Adds existing :attr:`~esibd.plugins.Plugin.dock` to UI at position defined by :attr:`esibd.plugins.Plugin.pluginType`."""
        mw = self.pluginManager.mainWindow
        if not self.initializedDock:
            self.print('provideDock', PRINT.DEBUG)
            self.loading = True
            self.initGUI()
            self.initDock()
            if self.pluginType == PluginManager.TYPE.DEVICEMGR: # should be loaded before any other plugin
                mw.splitDockWidget(self.pluginManager.topDock, self.dock, Qt.Orientation.Vertical) # below topDock
            elif self.pluginType == PluginManager.TYPE.LIVEDISPLAY:
                liveDisplays = self.pluginManager.DeviceManager.getActiveLiveDisplays()
                if len(liveDisplays) == 0:
                    mw.splitDockWidget(self.pluginManager.topDock, self.dock, Qt.Orientation.Vertical) # below topDock
                else:
                    mw.tabifyDockWidget(liveDisplays[-1].dock, self.dock) # add to other live displays
            elif self.pluginType in [PluginManager.TYPE.CHANNELMANAGER, PluginManager.TYPE.INPUTDEVICE, PluginManager.TYPE.OUTPUTDEVICE, PluginManager.TYPE.CONTROL, PluginManager.TYPE.SCAN]:
                if self.pluginManager.firstControl is None:
                    self.pluginManager.firstControl = self
                    mw.splitDockWidget(self.pluginManager.DeviceManager.dock, self.dock, Qt.Orientation.Vertical) # below DeviceManager
                else:
                    mw.tabifyDockWidget(self.pluginManager.firstControl.dock, self.dock)
            elif self.pluginType == PluginManager.TYPE.CONSOLE:
                mw.splitDockWidget(self.pluginManager.firstControl.dock, self.dock, Qt.Orientation.Vertical)
            elif self.pluginType == PluginManager.TYPE.DISPLAY:
                if self.pluginManager.firstDisplay is None:
                    self.pluginManager.firstDisplay = self
                    mw.splitDockWidget(self.pluginManager.firstControl.dock, self.dock, Qt.Orientation.Horizontal)
                else:
                    mw.tabifyDockWidget(self.pluginManager.firstDisplay.dock, self.dock)
            self.initializedDock = True # only true after initializing and adding dock to GUI
            self.loading = False
            if not self.pluginManager.finalizing and not self.pluginManager.loading:
                self.toggleTitleBarDelayed()
            self.videoRecorder = EsibdCore.VideoRecorder(parentPlugin=self)
            return True # dock has been created
        return False # dock already exists

    def raiseDock(self, _show=True):
        """Raises :attr:`dock<esibd.plugins.Plugin.dock>` if _show is True."""
        if _show and self.initializedDock:
            QTimer.singleShot(0, self.dock.raise_) # give time for UI to draw before raising the dock
        # self.loading = False

    def toggleAdvanced(self, advanced=None):
        """Overwrite to show advanced options."""
        self.print('toggleAdvanced not implemented')

    def requiredPlugin(self, name):
        """Displays error message if required plugin is not available."""
        if not hasattr(self.pluginManager, name):
            self.print(f'Plugin {name} required for {self.name} {self.version}', PRINT.ERROR)

    def addAction(self, event=None, toolTip='', icon=None, before=None):
        """Adds a simple Action to the toolBar.

        :param func: The function triggered by the action, defaults to None
        :type func: method, optional
        :param toolTip: The toolTip of the action, defaults to ''
        :type toolTip: str, optional
        :param icon: The icon of the action, defaults to None
        :type icon: :class:`~esibd.core.Icon`, optional
        :param before: The existing action before which the new action will be placed, defaults to None. If None, the new action will be added to the end.
        :type before: :class:`~esibd.core.Action`, optional
        :return: The new Action
        :rtype: :class:`~esibd.core.Action`
        """
        # first arguments of func have to be "self" and "checked".
        # If you do not need "checked" use "lambda: func()" instead of func as argument to this function to prevent your parameters from being overwritten
        if isinstance(icon, str):
            icon=self.makeIcon(icon)
        a = EsibdCore.Action(icon, toolTip, self) # icon, toolTip, parent
        a.triggered.connect(event)
        a.setObjectName(f"{self.name}/toolTip: {toolTip.strip('.')}.")
        if before is None:
            self.titleBar.addAction(a)
        else:
            self.titleBar.insertAction(before, a)
        return a

    def addStateAction(self, event=None, toolTipFalse='', iconFalse=None, toolTipTrue='', iconTrue=None, before=None, attr=None, restore=True, default='false'):
        """Adds an action with can be toggled between two states, each having a
        dedicated tooltip and icon.

        :param event: The function triggered by the stateAction, defaults to None
        :type event: method, optional
        :param toolTipFalse: The toolTip of the stateAction if state is False, defaults to ''
        :type toolTipFalse: str, optional
        :param iconFalse: The icon of the stateAction if state is False, defaults to None
        :type iconFalse: :class:`~esibd.core.Icon`, optional
        :param toolTipTrue: The toolTip of the stateAction if state is True, defaults to ''
        :type toolTipTrue: str, optional
        :param iconTrue: The icon of the stateAction if state is True, defaults to None
        :type iconTrue: :class:`~esibd.core.Icon`, optional
        :param before: An existing action or stateAction before which the new action will be placed, defaults to None.
            If None, the new stateAction will be added to the end.
        :type before: :class:`~esibd.core.Action`, optional
        :param attr: used to save and restore state, defaults to None
        :type attr: str, optional
        :param restore: If True state will be restored when the program is restarted, defaults to True
        :type restore: bool, optional
        :param default: Default state as saved by qSettings, defaults to false
        :type default: str, optional
        :return: The new StateAction
        :rtype: :class:`~esibd.core.StateAction`

        """
        # Using wrapper allows to pass parentPlugin implicitly and keep signature consistent.
        return EsibdCore.StateAction(parentPlugin=self, toolTipFalse=toolTipFalse, iconFalse=iconFalse, toolTipTrue=toolTipTrue,
                                     iconTrue=iconTrue, event=event, before=before, attr=attr, restore=restore, default=default)

    def addMultiStateAction(self, event=None, states=None, before=None, attr=None, restore=True, default=0):
        """Adds an action with can be toggled between two states, each having a
        dedicated tooltip and icon.

        :param event: The function triggered by the stateAction, defaults to None
        :type event: method, optional
        :param states: The list of states the control can represent, defaults to a list of empty states
        :type states: List[:class:`~esibd.core.MultiState`], optional
        :param before: An existing action or stateAction before which the new action will be placed, defaults to None.
            If None, the new stateAction will be added to the end.
        :type before: :class:`~esibd.core.Action`, optional
        :param attr: Used to save and restore state, defaults to None
        :type attr: str, optional
        :param restore: If True state will be restored when the program is restarted, defaults to True
        :type restore: bool, optional
        :param default: Index of default state, defaults to 0
        :type default: int, optional
        :return: The new StateAction
        :rtype: :class:`~esibd.core.StateAction`

        """
        # Using wrapper allows to pass parentPlugin implicitly and keep signature consistent.
        return EsibdCore.MultiStateAction(parentPlugin=self, states=states, event=event, before=before, attr=attr, restore=restore, default=default)

    def toggleTitleBar(self):
        """Adjusts the title bar layout and :attr:`~esibd.plugins.Plugin.titleBarLabel` depending on the state of the :attr:`~esibd.plugins.Plugin.dock` (tabbed, floating, ...).
        Extend to make sure toggleTitleBar is called for dependent plugins.
        """
        self.dock.toggleTitleBar()

    def toggleTitleBarDelayed(self, delay=500):
        QTimer.singleShot(delay, lambda: self.toggleTitleBar())

    def addContentWidget(self, cw):
        """Use this to add your main content widget to the user interface.

        :param cw: Content widget
        :type cw: QWidget
        """
        self.vertLayout.addWidget(cw)

    def addContentLayout(self, lay):
        """Use this to add a content layout instead of a content widget to the user interface.

        :param lay: Content layout
        :type lay: QLayout
        """
        self.vertLayout.addLayout(lay)

    def supportsFile(self, file):
        """Tests if a file is supported by the plugin, based on file name or content.

        :param file: File that has been selected by the user.
        :type file: pathlib.Path
        :return: Returns True if the file is supported by the plugin. Test if supported based on file extension or content.
        :rtype: bool
        """
        return any(file.name.lower().endswith(fileType.lower()) for fileType in self.previewFileTypes)

    def loadData(self, file, _show=True):
        """Loads and displays data from file.
        This should only be called for files where :meth:`~esibd.plugins.Plugin.supportsFile` returns True.
        Overwrite depending on data supported by the plugin.

        :param file: File from which to load data.
        :type file: pathlib.Path
        :param _show: Show plugin after loading data, defaults to True. Some files are handled by multiple plugins and only one of them should be shown by default.
        :type _show: bool, optional
        """
        self.print(f'Loading data from {file} not implemented.', PRINT.ERROR)

    def getSupportedFiles(self):
        # extend to include previewFileTypes of associated displays if applicable
        return self.previewFileTypes

    def hdfUpdateVersion(self, f):
        info_group = self.requireGroup(f, INFO)
        for key, value in infoDict(self.name).items():
            info_group.attrs[key] = value

    def requireGroup(self, group, name):
        """Replaces require_group from h5py, and adds support for track_order."""
        if name in group:
            return group[name]
        else:
            return group.create_group(name=name, track_order=True)

    def expandTree(self, tree):
        # expand all categories
        it = QTreeWidgetItemIterator(tree, QTreeWidgetItemIterator.IteratorFlag.HasChildren)
        while it.value():
            it.value().setExpanded(True)
            it +=1

    def toggleVideoRecorder(self):
        if self.videoRecorderAction.state:
            self.videoRecorder.startRecording()
        else:
            self.videoRecorder.stopRecording()

    def about(self):
        """Displays the about dialog of the plugin using the :ref:`sec:browser`."""
        self.pluginManager.Browser.setAbout(self, f'About {self.name}', f"""
            <p>{self.documentation if self.documentation is not None else self.__doc__}<br></p>
            <p>Supported files: {', '.join(self.getSupportedFiles())}<br>
            Supported version: {self.supportedVersion}<br></p>"""
            + # add programmer info in testmode, otherwise only show user info
            f"""<p>Plugin type: {self.pluginType.value}<br>
            Optional: {self.optional}<br>
            Dependency path: {self.dependencyPath.resolve()}<br></p>"""
            +
            self.getToolBarActionsHTML()
            )

    def getToolBarActionsHTML(self):
        if not hasattr(self, 'titleBar'):
            return ''
        actionsHTML = '<p>Icon Legend:<br>'
        for action in self.titleBar.actions():
            if action.iconText() != '':
                if isinstance(action, (EsibdCore.Action, EsibdCore.StateAction, EsibdCore.MultiStateAction)) and hasattr(action.getIcon(), 'fileName'):
                    actionsHTML += f"<span><img src='{Path(action.getIcon().fileName).resolve()}' style='vertical-align: middle;' width='16'/><span style='vertical-align: middle;'> {action.getToolTip()}</span></span><br>\n"
                elif hasattr(action, 'fileName'):
                    actionsHTML += f"<span><img src='{Path(action.fileName).resolve()}' style='vertical-align: middle;' width='16'/><span style='vertical-align: middle;'> {action.toolTip()}</span></span><br>\n"
                else:
                    self.print(f'QAction with iconText {action.iconText()} has no attribute fileName', flag=PRINT.WARNING) # assign fileName if missing
        actionsHTML += '</p>'
        return actionsHTML

    def makeFigureCanvasWithToolbar(self, figure):
        """Creates :meth:`~esibd.plugins.Plugin.canvas`, which can be added to the user interface, and
        adds the corresponding :meth:`~esibd.plugins.Plugin.navToolBar` to the plugin :meth:`~esibd.plugins.Plugin.titleBar`.

        :param figure: A matplotlib figure.
        :type figure: matplotlib.pyplot.figure
        """
        if self.canvas is not None:
            self.canvas.setVisible(False) # need to get out of the way quickly when changing themes, deletion may take longer
            self.canvas.deleteLater()
            self.navToolBar.deleteLater()
        self.canvas = FigureCanvas(figure)
        self.navToolBar = EsibdCore.ThemedNavigationToolbar(self.canvas, parentPlugin=self) # keep reference in order to reset navigation
        for action in self.navToolBar.actions()[:-1]: # last action is empty and undocumented
            if hasattr(self, 'stretchAction'):
                self.titleBar.insertAction(self.stretchAction, action)
            else:
                self.titleBar.addAction(action)

    def labelPlot(self, ax, label):
        """Adds file name labels to plot to trace back which file it is based on."""
        fontsize = 10
        # call after all other plotting operations are completed for scaling to work properly
        if self.labelAnnotation is not None:
            try:
                self.labelAnnotation.remove()
            except (ValueError, NotImplementedError):
                pass # might have been deleted already
        self.labelAnnotation = ax.annotate(text=label, xy=(.98,.98), fontsize=fontsize, xycoords='axes fraction', textcoords='axes fraction',
                                        ha='right', va='top', bbox=dict(boxstyle='square, pad=.2', fc=plt.rcParams['axes.facecolor'], ec='none'), clip_on=True)
        self.processEvents() # trigger paint to get width
        labelWidth = self.labelAnnotation.get_window_extent(renderer=ax.get_figure().canvas.get_renderer()).width
        axisWidth = ax.get_window_extent().transformed(ax.get_figure().dpi_scale_trans.inverted()).width*ax.get_figure().dpi*.9
        self.labelAnnotation.set_size(min(max(fontsize / labelWidth * axisWidth, 1), 10))
        # ax.plot([0.8, 1], [0.95, 0.95], transform=ax.transAxes, color='green') # workaround for label vs legend clash not working
        # https://stackoverflow.com/questions/57328170/draw-a-line-with-matplotlib-using-the-axis-coordinate-system
        if hasattr(ax, 'cursor'): # cursor position changes after adding label... -> restore
            ax.cursor.updatePosition()
        ax.figure.canvas.draw_idle()

    def removeAnnotations(self, ax):
        for ann in [child for child in ax.get_children() if isinstance(child, mpl.text.Annotation)]:#[self.seAnnArrow, self.seAnnFile, self.seAnnFWHM]:
            ann.remove()

    def getIcon(self, desaturate=False):
        """Gets the plugin icon. Consider using a themed icon that works in dark and light modes.
        Overwrite only if definition of iconFile and iconFileDark is not sufficient.

        :return: Icon
        :rtype: :class:`~esibd.core.Icon`
        """
        # e.g. return self.darkIcon if getDarkMode() else self.lightIcon
        if self.iconFile != '':
            return self.makeIcon(self.iconFileDark if getDarkMode() and self.iconFileDark != '' else self.iconFile, desaturate=desaturate)
        else:
            return self.makeCoreIcon('help_large_dark.png' if getDarkMode() else 'help_large.png', desaturate=desaturate)

    def makeCoreIcon(self, file, desaturate=False):
        return self.makeIcon(file=file, path=internalMediaPath, desaturate=desaturate)

    def makeIcon(self, file, path=None, desaturate=False):
        """Returns an icon based on a filename. Looks for files in the :meth:`~esibd.plugins.Plugin.dependencyPath`.

        :param file: Icon file name.
        :type file: str
        :return: Icon
        :rtype: :class:`~esibd.core.Icon`
        """
        iconPath = Path(str((path if path is not None else self.dependencyPath) / file))
        if not iconPath.exists():
            self.print(f'Could not find icon {iconPath.as_posix()}', flag=PRINT.WARNING)
            return Icon(internalMediaPath / 'unicode_error.png')
        return Icon(iconPath, desaturate=desaturate)

    def updateTheme(self):
        """Changes between dark and light themes. Most
        controls should update automatically as the color pallet is changed.
        Only update the remaining controls using style sheets.
        Extend to adjust colors to app theme.
        """
        if self.fig is not None and not self.loading and (self.scan is None or self.scan.file is not None):
            self.initFig()
            self.plot()
        if hasattr(self, 'navToolBar') and self.navToolBar is not None:
            self.navToolBar.updateNavToolbarTheme()
        if hasattr(self, 'closeAction'):
            self.closeAction.setIcon(self.makeCoreIcon('close_dark.png' if getDarkMode() else 'close_light.png'))
        if hasattr(self, 'aboutAction'):
            self.aboutAction.setIcon(self.makeCoreIcon('help_large_dark.png' if getDarkMode() else 'help_large.png'))

    def initFig(self):
        """Will be called when a :ref:`display<sec:displays>` is closed and reopened or the theme
        is changed. Overwrite your figure initialization here to make sure all references are updated correctly."""
        self.fig = None
        self.canvas = None

    def provideFig(self):
        if self.fig is not None and rgb_to_hex(self.fig.get_facecolor()) != colors.bg:
            # need to create new fig to change matplotlib style
            plt.close(self.fig)
            self.fig = None
        if self.fig is None:
            self.fig = plt.figure(constrained_layout=True, dpi=getDPI(), label=f'{self.name} figure')
            self.makeFigureCanvasWithToolbar(self.fig)
            self.addContentWidget(self.canvas)
        else:
            self.fig.clf() # reuse if possible
            self.fig.set_constrained_layout(True)
            self.fig.set_dpi(getDPI())
        self.axes = []

    @plotting
    def plot(self):
        """If applicable, overwrite with a plugin specific plot method."""

    @synchronized()
    def copyClipboard(self):
        """Copy matplotlib figure to clipboard."""
        limits = []
        buffer = io.BytesIO()
        if getDarkMode() and not getClipboardTheme():
            # use default light theme for clipboard
            with mpl.style.context('default'):
                for ax in self.axes:
                    limits.append((ax.get_xlim(), ax.get_ylim()))
                size = self.fig.get_size_inches()
                self.initFig()
                self.plot()
                for i, ax in enumerate(self.axes):
                    ax.set_xlim(limits[i][0])
                    ax.set_ylim(limits[i][1])
                self.fig.set_size_inches(size)
                self.canvas.draw_idle()
                # QApplication.clipboard().setPixmap(self.canvas.grab()) # does not work on just drawn image -> pixelated -> use buffer
                self.fig.savefig(buffer, format='png', bbox_inches='tight', dpi=getDPI(), facecolor='w') # safeFig in default context
        else:
            self.fig.savefig(buffer, format='png', bbox_inches='tight', dpi=getDPI())
            # QApplication.clipboard().setPixmap(self.canvas.grab()) # grabs entire canvas and not just figure
        QApplication.clipboard().setImage(QImage.fromData(buffer.getvalue()))
        buffer.close()
        if getDarkMode() and not getClipboardTheme():
            # restore dark theme for use inside app
            self.initFig()
            self.plot()
            for i, ax in enumerate(self.axes):
                ax.set_xlim(limits[i][0])
                ax.set_ylim(limits[i][1])
            self.canvas.draw_idle()

    @synchronized()
    def copyLineDataClipboard(self, line):
        if line is not None:
            text = ''
            for x, y in zip(line.get_xdata(), line.get_ydata()):
                text += f'{x:12.2e}\t{y:12.2e}\n'
            QApplication.clipboard().setText(text)

    def setLabelMargin(self, ax, margin):
        """Sets top margin only, to reserve space for file name label.

        :param ax: The axis to which to add the top margin
        :type ax: matplotlib.pyplot.axis
        :param margin: The margin to add. 0.15 -> add 15 % margin
        :type margin: float

        """ # not yet implemented https://stackoverflow.com/questions/49382105/set-different-margins-for-left-and-right-side
        # ax.set_ymargin(0) # we do not use margins
        # ax.autoscale_view() # useless after limits are set -> use autoscale
        ax.autoscale(True)
        lim = ax.get_ylim()
        delta = np.diff(lim)
        ax.set_ylim(lim[0], lim[1] + delta*margin)

    def addRightAxis(self, ax):
        """Adds additional y labels on the right."""
        # .tick_params(labelright=True) does only add labels
        # .tick_right() removes ticks on left
        # -> link second axis as a workaround
        axr = ax.twinx()
        axr.tick_params(direction="out", right=True)
        axr.sharey(ax)
        if ax.get_yscale() == 'log':
            axr.set_yscale('log')

    def tilt_xlabels(self, ax, rotation=30):
        # replaces autofmt_xdate which is currently not compatible with constrained_layout
        # https://currents.soest.hawaii.edu/ocn_data_analysis/_static/Dates_Times.html
        for label in ax.get_xticklabels(which='major'):
            label.set_ha('right')
            label.set_rotation(rotation)

    def getDefaultSettings(self):
        """Defines a dictionary of :meth:`~esibd.core.parameterDict` which specifies default settings for this plugin.
        Overwrite or extend as needed to define specific settings that will be added to :ref:`sec:settings` section.

        :return: Settings dictionary
        :rtype: {:meth:`~esibd.core.parameterDict`}
        """
        ds = {}
        # ds[f'{self.name}/SettingName'] = parameterDict(...)
        return ds

    def displayActive(self):
        return self.display is not None and self.display.initializedDock

    def close(self):
        """Closes plugin cleanly without leaving any data or communication
        running. Extend to make sure your custom data and custom
        communication is closed as well."""

    def closeUserGUI(self):
        """Called when the user closes a single plugin.
        Extend to react to user triggered closing.
        """
        self.closeGUI()

    def closeGUI(self):
        """Closes the user interface but might keep data available in case the
        user interface is restored later.
        Closes all open references. Extend to save data and make hardware save if needed."""
        self.close()
        if self.dock is not None and self.initializedDock:
            self.dock.deleteLater()
        if hasattr(self, 'fig'):
            plt.close(self.fig)
        self.fig = None
        self.canvas = None
        self.titleBar = None
        self.initializedGUI = False
        self.initializedDock = False

class StaticDisplay(Plugin):
    """Displays :class:`~esibd.plugins.Device` data from file."""
    pluginType=PluginManager.TYPE.DISPLAY

    def __init__(self, parentPlugin, **kwargs):
        self.parentPlugin = parentPlugin # another Plugin
        self.name = f'{parentPlugin.name} Static Display'
        self.file = None
        self.previewFileTypes = [] # extend in derived classes, define here to avoid cross talk between instances
        super().__init__(**kwargs)

    def initGUI(self):
        """:meta private:"""
        super().initGUI()
        self.legend = None
        self.outputLayout = QVBoxLayout()
        self.plotWidgetFont = QFont()
        self.plotWidgetFont.setPixelSize(15)
        self.staticPlotWidget = EsibdCore.PlotWidget(_parent=self)
        self.staticPlotWidget.showGrid(x=True, y=True, alpha=0.1)
        self.staticPlotWidget.showAxis('top')
        self.staticPlotWidget.getAxis('top').setStyle(showValues=False)
        self.staticPlotWidget.showLabel('top', show=False)
        self.staticPlotWidget.setAxisItems({'right': EsibdCore.SciAxisItem('right')})
        self.staticPlotWidget.setAxisItems({'left': EsibdCore.SciAxisItem('left')})
        self.staticPlotWidget.getAxis('left').setTickFont(self.plotWidgetFont)
        self.staticPlotWidget.getAxis('right').setTickFont(self.plotWidgetFont)
        self.staticPlotWidget.getAxis('bottom').setTickFont(self.plotWidgetFont)
        self.staticPlotWidget.setAxisItems({'bottom': pg.DateAxisItem()})
        self.staticPlotWidget.setLabel('bottom', '<font size="5">Time</font>') # has to be after setAxisItems
        self.staticPlotWidget.enableAutoRange(x=True)
        self.outputLayout.addWidget(self.staticPlotWidget)
        self.staticPlotWidget.setLogMode(False , self.parentPlugin.logY)
        self.initFig()
        self.addContentLayout(self.outputLayout)
        self.initData()

    def initFig(self):
        """:meta private:"""
        if self.fig is not None and rgb_to_hex(self.fig.get_facecolor()) != colors.bg:
            # need to create new fig to change matplotlib style
            plt.close(self.fig)
            self.fig = None
        if self.fig is None:
            self.fig = plt.figure(constrained_layout=True, dpi=getDPI(), label=f'{self.name} staticDisplay figure')
            self.makeFigureCanvasWithToolbar(self.fig)
            self.outputLayout.addWidget(self.canvas)
        else:
            self.fig.clf() # reuse if possible
            self.fig.set_constrained_layout(True)
            self.fig.set_dpi(getDPI())
        self.axes = []
        self.axes.append(self.fig.add_subplot(111))

    def finalizeInit(self, aboutFunc=None):
        """:meta private:"""
        # for a in self.navToolBar.actions()[:-1]: # last action is empty and undocumented
        #     self.titleBar.addAction(a)
        super().finalizeInit(aboutFunc)
        self.copyAction = self.addAction(lambda: self.copyClipboard(), f'{self.name} to clipboard.', self.imageClipboardIcon, before=self.aboutAction)
        self.plotEfficientAction = self.addStateAction(event=lambda: self.togglePlotType(), toolTipFalse='Use matplotlib plot.', iconFalse=self.makeCoreIcon('mpl.png'),
                                                       toolTipTrue='Use pyqtgraph plot.', iconTrue=self.makeCoreIcon('pyqt.png'), attr='plotEfficient', before=self.copyAction)
        self.togglePlotType()
        self.staticPlotWidget.updateGrid()

    def getIcon(self, **kwargs):
        return self.parentPlugin.getIcon(**kwargs)

    def runTestParallel(self):
        """:meta private:"""
        if self.initializedDock:
            self.testControl(self.copyAction, True, 1)
            self.testControl(self.plotEfficientAction, not self.plotEfficientAction.state, 1)
        super().runTestParallel()

    # @synchronized() do not use same lock for extended version of already decorated super().copyClipboard()
    def copyClipboard(self):
        """Extends matplotlib based version to add support for pyqtgraph."""
        if self.plotEfficientAction.state: # matplotlib
            super().copyClipboard()
        else: # pyqt
            if getDarkMode() and not getClipboardTheme():
                try:
                    setDarkMode(False) # temporary switch to light mode
                    viewRange = self.staticPlotWidget.viewRange()
                    self.updateTheme() # use default light theme for clipboard
                    self.staticPlotWidget.setRange(xRange=viewRange[0], yRange=viewRange[1], padding=0)
                    self.processEvents() # update GUI before grabbing
                    QApplication.clipboard().setPixmap(self.staticPlotWidget.grab())
                except Exception as e:
                    self.print(f'Error while plotting in light theme: {e}')
                finally: # make sure darkmode is restored even after errors
                    setDarkMode(True) # restore dark theme
                    self.updateTheme() # restore dark theme
                    self.staticPlotWidget.setRange(xRange=viewRange[0], yRange=viewRange[1], padding=0)
            else:
                QApplication.clipboard().setPixmap(self.staticPlotWidget.grab())

    def provideDock(self):
        """:meta private:"""
        if super().provideDock():
            self.finalizeInit()
            self.afterFinalizeInit()

    def supportsFile(self, file):
        """:meta private:"""
        if super().supportsFile(file):
            return True
        elif self.pluginManager.DeviceManager.supportsFile(file):
            with h5py.File(file, 'r') as h5File:
                return self.parentPlugin.name in h5File
        else:
            return False

    def loadData(self, file, _show=True):
        """:meta private:"""
        # using linewidget to display
        self.file = file
        self.provideDock()
        self.initData()
        if self.loadDataInternal(file):
            self.outputs.reverse() # reverse to plot first outputs on top of later outputs
            self.plot(update=True)
            self.raiseDock(_show)
        else:
            self.print(f'Could not load file {file.name}.', PRINT.WARNING)

    def togglePlotType(self):
        self.staticPlotWidget.setVisible(not self.plotEfficientAction.state)
        self.canvas.setHidden(not self.plotEfficientAction.state)
        for a in self.navToolBar.actions()[:-1]: # last action is empty and undocumented
            a.setVisible(self.plotEfficientAction.state)
        if self.file is not None and len(self.outputs) > 0:
            self.plot(update=True)

    def updateStaticPlot(self):
        # update if channel settings have changed and data is present
        if self.initializedDock and not self.loading and len(self.outputs) > 0:
            self.plot()

    def plot(self, update=False):
        """Plots channels from file, using real channel information (color, linewidth, linestyle, ...) if available."""
        # as this is only done once we can plot all data without thinning
        if self.plotEfficientAction.state:
            self.axes[0].clear()
            self.axes[0].set_xlabel(self.TIME)
            if self.parentPlugin.logY:
                self.axes[0].set_yscale('log')
            self.tilt_xlabels(self.axes[0])
        else:
            self.staticPlotWidget.clear()
            self.legend = self.staticPlotWidget.addLegend(labelTextColor=colors.fg) # before adding plots
        for output in self.outputs:
            length = min(self.inputs[0].getRecordingData().shape[0], output.getRecordingData().shape[0])
            x = self.inputs[0].getRecordingData()[-length:]
            y = self.parentPlugin.convertDataDisplay((output.getRecordingData()-output.recordingBackground)[:length]
                                           if self.parentPlugin.useBackgrounds and self.parentPlugin.subtractBackgroundActive()
                                           else output.getRecordingData()[:length])
            if output.sourceChannel is None:
                if self.plotEfficientAction.state:
                    self.axes[0].plot([datetime.fromtimestamp(float(_time)) for _time in x], y, label=f'{output.name} ({output.unit})')
                else:
                    self.staticPlotWidget.plot(x, y, name=f'{output.name} ({output.unit})') # initialize empty plots
            elif output.sourceChannel.display:
                if output.smooth != 0:
                    # y = uniform_filter1d(y, output.smooth) # revert to this if nan_policy becomes https://github.com/scipy/scipy/pull/17393
                    y = smooth(y, output.smooth)
                if self.plotEfficientAction.state:
                    self.axes[0].plot([datetime.fromtimestamp(float(_time)) for _time in x], y, label=f'{output.name} ({output.unit})',
                                      color=output.color, linewidth=output.linewidth/2, linestyle=output.linestyle)
                else:
                    self.staticPlotWidget.plot(x, y, pen=pg.mkPen((output.color), width=output.linewidth,
                                                                  style=output.getQtLineStyle()), name=f'{output.name} ({output.unit})')
        if self.plotEfficientAction.state:
            self.setLabelMargin(self.axes[0], 0.15)
            self.navToolBar.update() # reset history for zooming and home view
            self.canvas.get_default_filename = lambda: self.file.with_suffix('.pdf') # set up save file dialog
            self.labelPlot(self.axes[0], self.file.name)
            legend = self.axes[0].legend(loc='best', prop={'size': 7}, frameon=False)
            legend.set_in_layout(False)
        elif update:
            self.staticPlotWidget.autoRange() # required to trigger update

    def initData(self):
        self.inputs, self.outputs = [], []

    def loadDataInternal(self, file):
        """Load data in standard format. Overwrite in derived classes to add support for old file formats."""
        with h5py.File(file, 'r') as h5file:
            if self.parentPlugin.name not in h5file:
                return False
            group = h5file[self.parentPlugin.name]
            if not (INPUTCHANNELS in group and OUTPUTCHANNELS in group):
                return False
            self.inputs.append(MetaChannel(parentPlugin=self, name=self.TIME, recordingData=group[INPUTCHANNELS][self.TIME][:]))
            output_group = group[OUTPUTCHANNELS]
            for name, item in output_group.items():
                if name.endswith('_BG'):
                    self.outputs[-1].recordingBackground = item[:]
                else:
                    self.outputs.append(MetaChannel(parentPlugin=self, name=name, recordingData=item[:], unit=item.attrs[UNIT] if UNIT in item.attrs else ''))
        return True # return True if loading was successful # make sure to follow this pattern when extending!

    def generatePythonPlotCode(self):
        with open(self.pluginManager.Explorer.activeFileFullPath.with_suffix('.py'), 'w', encoding=UTF8) as plotFile:
            plotFile.write(f"""import h5py
import matplotlib.pyplot as plt
from datetime import datetime

inputs, outputs = [], []
class MetaChannel():
    def __init__(self, name, recordingData, initialValue=None, recordingBackground=None, unit=''):
        self.name = name
        self.recordingData = recordingData
        self.initialValue = initialValue
        self.recordingBackground = recordingBackground
        self.unit = unit

    @property
    def logY(self):
        if self.unit in ['mbar', 'Pa']:
            return True
        else:
            return False

with h5py.File('{self.pluginManager.Explorer.activeFileFullPath.as_posix()}','r') as h5file:
    group = h5file['{self.parentPlugin.name}']

    inputs.append(MetaChannel(name='Time', recordingData=group['Input Channels']['Time'][:]))

    output_group = group['Output Channels']
    for name, data in output_group.items():
        if name.endswith('_BG'):
            outputs[-1].recordingBackground = data[:]
        else:
            outputs.append(MetaChannel(name=name, recordingData=data[:], unit=data.attrs['Unit']))

# replace following with your custom code
subtract_backgrounds = False # switch to True to subtract background signals if available

fig=plt.figure(constrained_layout=True, )
ax = fig.add_subplot(111)
ax.set_xlabel('Time')
{"ax.set_yscale('log')" if self.parentPlugin.logY else ''}

for i, output in enumerate(outputs):
    length = min(inputs[0].recordingData.shape[0], output.recordingData.shape[0])
    x = inputs[0].recordingData[-length:]
    y = (output.recordingData-output.recordingBackground)[:length] if output.recordingBackground is not None and subtract_backgrounds else output.recordingData[:length]
    ax.plot([datetime.fromtimestamp(float(_time)) for _time in x], y, label=f'{{output.name}} ({{output.unit}})')

ax.legend(loc = 'best', prop={{'size': 7}}, frameon=False)
plt.show()
        """)

    def updateTheme(self):
        """:meta private:"""
        super().updateTheme()
        self.staticPlotWidget.setBackground(colors.bg)
        fg = colors.fg
        self.staticPlotWidget.getAxis('left').setTextPen(fg)
        self.staticPlotWidget.getAxis('top').setTextPen(fg)
        self.staticPlotWidget.getAxis('right').setTextPen(fg)
        self.staticPlotWidget.getAxis('bottom').setTextPen(fg)
        self.staticPlotWidget.setLabel('bottom','<font size="5">Time</font>', color=fg) # do not overwrite text!
        self.staticPlotWidget.getPlotItem().xyLabel.setColor(fg)
        if self.legend is not None:
            self.legend.setLabelTextColor(fg)
        self.updateStaticPlot() # triggers update of legend
        if not self.loading:
            self.togglePlotType()

# import pyqtgraph.multiprocess as mp

class LiveDisplay(Plugin):
    """Live displays show the history of measured data over time.
    Use the start/pause icon to control data recording. The toolbar
    provides icons to initialize and stop acquisition, optionally
    subtract backgrounds, or export displayed data to the current session.
    Data is only collected if the corresponding live display is visible.
    The length of the displayed history is determined by the display time
    control in the tool bar.

    Frequently updating those plots is typically the computationally most
    expensive action. Thus you might want to reduce
    the number of displayed data points in the :ref:`acquisition settings<sec:acquisition_settings>`. This will make sure that
    the graphs are updated less frequently and select a smaller but
    consistent subset of data points for a smooth visualization. While
    PyQtGraph provides its own algorithms for down sampling data (accessible
    via the context menu), they tend to cause a flicker when updating data."""
    documentation = """Live displays show the history of measured data over time.
    Use the start/pause icon to control data recording. The toolbar
    provides icons to initialize and stop acquisition, optionally
    subtract backgrounds, or export displayed data to the current session.
    Data is only collected if the corresponding live display is visible.
    The length of the displayed history is determined by the display time
    control in the tool bar.

    Frequently updating those plots is typically the computationally most
    expensive action. Thus you might want to reduce
    the number of displayed data points in the Settings. This will make sure that
    the graphs are updated less frequently and select a smaller but
    consistent subset of data points for a smooth visualization. While
    PyQtGraph provides its own algorithms for down sampling data (accessible
    via the context menu), they tend to cause a flicker when updating data."""

    pluginType = PluginManager.TYPE.LIVEDISPLAY
    useAdvancedOptions = True
    DISPLAYTIME = 'displayTime'

    def __init__(self, parentPlugin=None, **kwargs):
        self.parentPlugin = parentPlugin # should be a device that will define which channel to plot
        self.name = f'{parentPlugin.name} Live Display'
        self.dataFileType = f'_{self.parentPlugin.name.lower()}.dat.h5'
        self.previewFileTypes = [self.dataFileType]
        self.stackedGraphicsLayoutWidget = None
        self.livePlotWidgets = []
        self.channelGroups = {}
        self._updateLegend = True
        super().__init__(**kwargs)

    def initGUI(self):
        """:meta private:"""
        super().initGUI()
        self.plotSplitter = None
        if self.parentPlugin.pluginType in [self.pluginManager.TYPE.INPUTDEVICE, self.pluginManager.TYPE.OUTPUTDEVICE]:
            self.exportAction = self.addAction(event=lambda: self.parentPlugin.exportOutputData(), toolTip=f'Save visible {self.parentPlugin.name} data to current session.', # pylint: disable=unnecessary-lambda
                           icon=self.makeCoreIcon('database-export.png'))
            self.addAction(event=lambda: self.parentPlugin.closeCommunication(), toolTip=f'Close {self.parentPlugin.name} communication.', icon=self.makeCoreIcon('stop.png'))
            self.addAction(event=lambda: self.parentPlugin.initializeCommunication(), toolTip=f'Initialize {self.parentPlugin.name} communication.', icon=self.makeCoreIcon('rocket-fly.png'))
        self.recordingAction = self.addStateAction(lambda: self.parentPlugin.toggleRecording(manual=True), f'Start {self.parentPlugin.name} data acquisition.', self.makeCoreIcon('play.png'),
                                                   f'Pause {self.parentPlugin.name} data acquisition.', self.makeCoreIcon('pause.png'))
        self.recordingAction.state = self.parentPlugin.recordingAction.state
        if self.parentPlugin.pluginType in [self.pluginManager.TYPE.INPUTDEVICE, self.pluginManager.TYPE.OUTPUTDEVICE]:
            self.clearHistoryAction = self.addAction(event=lambda: self.parentPlugin.clearHistory(), toolTip=f'Clear {self.parentPlugin.name} history.', icon=self.makeCoreIcon('clipboard-empty.png'))
            self.clearHistoryAction.setVisible(False) # usually not required as number of data points is already limited. only show in advanced mode
            if self.parentPlugin.useBackgrounds:
                self.subtractBackgroundAction = self.addStateAction(toolTipFalse=f'Subtract background for {self.parentPlugin.name}.', iconFalse=self.makeCoreIcon('eraser.png'),
                                                        toolTipTrue=f'Ignore background for {self.parentPlugin.name}.', iconTrue=self.makeCoreIcon('eraser.png'),
                                                        event=lambda: self.subtractBackgroundChanged())
                self.subtractBackgroundAction.state = self.parentPlugin.subtractBackgroundAction.state
                self.addAction(event=lambda: self.parentPlugin.setBackground(), toolTip=f'Set current value as background for {self.parentPlugin.name}.', icon=self.makeCoreIcon('eraser--pencil.png'))
        self.stackAction = self.addMultiStateAction(states=[MultiState('vertical', 'Stack axes horizontally.', self.makeCoreIcon('stack_horizontal.png')),
                                                            MultiState('horizontal', 'Stack axes on top of each other.', self.makeCoreIcon('stack_top.png')),
                                                            MultiState('stacked', 'Stack axes vertically.', self.makeCoreIcon('stack_vertical.png'))],
                                                        event=lambda: (self.initFig(), self.plot(apply=True)), attr='stackMode')
        self.groupAction = self.addMultiStateAction(states=[MultiState('all', 'Group channels by device.', self.makeCoreIcon('group_device.png')),
                                                            MultiState('device', 'Group channels by unit.', self.makeCoreIcon('group_unit.png')),
                                                            MultiState('unit', 'Group channels by group parameter.', self.makeCoreIcon('group_group.png')),
                                                            MultiState('group', 'Show all channels together.', self.makeCoreIcon('group_all.png'))],
                                                        event=lambda: (self.initFig(), self.plot(apply=True)), attr='groupMode')
        self.displayTimeComboBox = EsibdCore.RestoreFloatComboBox(parentPlugin=self, default='2', items='-1, 0.2, 1, 2, 3, 5, 10, 60, 600, 1440', attr=self.DISPLAYTIME,
                                                        event=lambda: self.displayTimeChanged(), _min=.2, _max=3600,
                                                        toolTip=f'Length of displayed {self.parentPlugin.name} history in min. When -1, all history is shown.')

    def finalizeInit(self, aboutFunc=None):
        """:meta private:"""
        super().finalizeInit(aboutFunc)
        self.copyAction = self.addAction(lambda: self.copyClipboard(), f'{self.name} to clipboard.', self.imageClipboardIcon, before=self.aboutAction)
        self.titleBar.insertWidget(self.copyAction, self.displayTimeComboBox)
        self.plot(apply=True)

    def toggleAdvanced(self, advanced=None):
        if hasattr(self, 'clearHistoryAction'):
            self.clearHistoryAction.setVisible(self.advancedAction.state)

    def displayTimeChanged(self):
        if len(self.livePlotWidgets) > 0:
            for livePlotWidget in self.livePlotWidgets:
                livePlotWidget.enableAutoRange(x=False, y=True)
                if isinstance(livePlotWidget, (pg.PlotItem, pg.PlotWidget)) and livePlotWidget.getViewBox().mouseEnabled()[0]:
                    livePlotWidget.setMouseEnabled(x=False, y=True)
        self.plot(apply=True)

    def subtractBackgroundChanged(self):
        # relay change to action in parentPlugin
        self.parentPlugin.subtractBackgroundAction.state = self.subtractBackgroundAction.state
        self.parentPlugin.subtractBackgroundAction.triggered.emit(self.subtractBackgroundAction.state)

    def getDisplayTime(self):
        """Gets displaytime independent of displayTimeComboBox"""
        # displayTimeComboBox does not exist if display is hidden
        return float(qSet.value(f'{self.name}/{self.DISPLAYTIME}', '2'))

    def clearPlot(self):
        """Clears all references to plotCurves, plotItems, and legends.
        To be recreated if needed."""
        # self.print('clearPlot', flag=PRINT.DEBUG)
        for channel in self.parentPlugin.getChannels():
            channel.clearPlotCurve()
        for livePlotWidget in self.livePlotWidgets:
            livePlotWidget.hide()
            livePlotWidget.deleteLater()
        if self.stackedGraphicsLayoutWidget is not None:
            try:
                self.stackedGraphicsLayoutWidget.hide()
                self.stackedGraphicsLayoutWidget.deleteLater()
            except RuntimeError:
                pass # Ignore if already been deleted
            finally:
                self.stackedGraphicsLayoutWidget = None
        if self.plotSplitter is not None:
            self.plotSplitter.hide()
            self.plotSplitter.deleteLater()
            self.plotSplitter = None
        self.livePlotWidgets = []
        self._updateLegend = True

    def getGroups(self):
        self.channelGroups = {}
        match self.groupAction.state:
            case self.groupAction.labels.device:
                groupLabels = list(set([channel.getDevice().name for channel in self.parentPlugin.getActiveChannels() if channel.display]))
                groups = [[] for _ in range(len(groupLabels))]
                [groups[groupLabels.index(channel.getDevice().name)].append(channel) for channel in self.parentPlugin.getActiveChannels() if channel.display]
            case self.groupAction.labels.unit:
                groupLabels = list(set([channel.unit for channel in self.parentPlugin.getActiveChannels() if channel.display]))
                groups = [[] for _ in range(len(groupLabels))]
                [groups[groupLabels.index(channel.unit)].append(channel) for channel in self.parentPlugin.getActiveChannels() if channel.display]
            case self.groupAction.labels.group:
                groupLabels = list(set([channel.displayGroup for channel in self.parentPlugin.getActiveChannels() if channel.display]))
                groups = [[] for _ in range(len(groupLabels))]
                [groups[groupLabels.index(channel.displayGroup)].append(channel) for channel in self.parentPlugin.getActiveChannels() if channel.display]
            case _:  # all
                groupLabels = [self.parentPlugin.name]
                groups = [[channel for channel in self.parentPlugin.getActiveChannels() if channel.display]]
        for label, group in zip(groupLabels, groups):
            self.channelGroups[label] = group
        self.channelGroups = dict(sorted(self.channelGroups.items())) # sort by groupLabel
        return self.channelGroups

    # @synchronized() called by updateTheme, copy clipboard, ... cannot decorate without causing deadlock
    def initFig(self):
        if not self.waitForCondition(condition=lambda: not self.pluginManager.plotting, timeoutMessage='init figure.', timeout=1):
            return # NOTE: using the self.pluginManager.plotting flag instead of a lock, is more resilient as it works across multiple functions and nested calls
        self.print('initFig', flag=PRINT.DEBUG)
        self.pluginManager.plotting = True
        self.clearPlot()
        self.plotWidgetFont = QFont()
        self.plotWidgetFont.setPixelSize(13)
        self.plotSplitter = QSplitter() # create new plotSplitter as old widgets are not garbage collected fast enough for copyClipboard
        self.plotSplitter.setStyleSheet('QSplitter::handle{width:0px; height:0px;}')
        self.noPlotLabel = QLabel('Nothing to plot. Display a channel with data in the selected display time.')
        self.noPlotLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.plotSplitter.addWidget(self.noPlotLabel)
        self.addContentWidget(self.plotSplitter)
        self.noPlotLabel.setVisible(len(self.getGroups()) == 0)
        for i, (groupLabel, group) in enumerate(self.getGroups().items()):
            logY = all([channel.logY for channel in group])
            if self.stackAction.state in [self.stackAction.labels.horizontal, self.stackAction.labels.vertical]:
                livePlotWidget = PlotWidget(_parent=self, groupLabel=groupLabel)
                self.plotSplitter.addWidget(livePlotWidget)
                livePlotWidget.init()
                livePlotWidget.setLogMode(False, logY)
                self.livePlotWidgets.append(livePlotWidget)
                if self.stackAction.state == self.stackAction.labels.vertical:
                    livePlotWidget.addLegend(labelTextColor=colors.fg, colCount=3, offset=0.15, labelTextSize='8pt') # before adding plots
                    self.plotSplitter.setOrientation(Qt.Orientation.Vertical)
                    if i < len(self.channelGroups)-1: # only label bottom x axis
                        livePlotWidget.hideAxis('bottom')
                else: # self.stackAction.state == self.stackAction.labels.horizontal:
                    livePlotWidget.addLegend(labelTextColor=colors.fg, colCount=1, offset=0.15, labelTextSize='8pt') # before adding plots
                    self.plotSplitter.setOrientation(Qt.Orientation.Horizontal)
                if i > 0: # link to previous
                    livePlotWidget.setXLink(self.livePlotWidgets[0])
                livePlotWidget.finalizeInit()
            else: # self.stackAction.state == self.stackAction.labels.stacked:
                # Based on https://github.com/pyqtgraph/pyqtgraph/blob/master/pyqtgraph/examples/MultiplePlotAxes.py
                # had to use older version to allow for multiple left axes https://stackoverflow.com/questions/42931474/how-can-i-have-multiple-left-axisitems-with-the-same-alignment-position-using-py
                # should soon become standard functionality and then this can be replaced https://github.com/pyqtgraph/pyqtgraph/pull/1359
                # self.livePlotWidgets[0] will be a plotItem the following elements will be linked viewBoxes
                plotColumn = (len(self.channelGroups)+1)//2 -1
                if i == 0:
                    self.stackedGraphicsLayoutWidget = pg.GraphicsLayoutWidget()
                    self.stackedGraphicsLayoutWidget.setBackground(colors.bg)
                    self.plotSplitter.addWidget(self.stackedGraphicsLayoutWidget)
                    livePlotWidget = PlotItem(showXY=False) # pg.PlotItem()
                    self.stackedGraphicsLayoutWidget.addItem(livePlotWidget, 0, plotColumn, rowspan=2)
                    livePlotWidget.init()
                    livePlotWidget.showGrid(False, False)
                    if len(self.channelGroups) == 1:
                        livePlotWidget.showAxis('right')
                        livePlotWidget.showLabel('right', show=False)
                        livePlotWidget.getAxis('right').setStyle(showValues=False)
                    livePlotWidget.axis_leftright = livePlotWidget.getAxis('left')
                    livePlotWidget.hideButtons() # remove autorange button
                    if len(self.channelGroups) > 2:
                        livePlotWidget.dummyAx = pg.AxisItem(orientation='bottom') # Blank axis used for aligning extra y axes
                        livePlotWidget.dummyAx.setPen(colors.bg)
                        livePlotWidget.dummyAx.setStyle(showValues=False)
                        livePlotWidget.dummyAx.setHeight(38) # empirical constant
                        self.stackedGraphicsLayoutWidget.addItem(livePlotWidget.dummyAx, 1, 0)
                    livePlotWidget.vb.sigResized.connect(self.updateStackedViews)
                    livePlotWidget.addLegend(labelTextColor=colors.fg, colCount=3, offset=0.15, labelTextSize='8pt')
                    livePlotWidget.setLogMode(y=logY) # set for PlotItem
                    livePlotWidget.finalizeInit()
                else:
                    livePlotWidget = pg.ViewBox()
                    self.livePlotWidgets[0].scene().addItem(livePlotWidget)
                    if i == 1: # use original right axis
                        self.livePlotWidgets[0].showAxis('right')
                        livePlotWidget.axis_leftright = self.livePlotWidgets[0].getAxis('right')
                    else:
                        livePlotWidget.axis_leftright = EsibdCore.SciAxisItem('left' if np.mod(i, 2)==0 else 'right')
                    livePlotWidget.axis_leftright.linkToView(livePlotWidget)
                    livePlotWidget.setXLink(self.livePlotWidgets[0])
                    livePlotWidget.axis_leftright.setLogMode(y=logY) # set for AxisItem instead of ViewBox
                if i > 1:
                    columnOffset = (i)//2
                    self.stackedGraphicsLayoutWidget.addItem(livePlotWidget.axis_leftright, 0, plotColumn-columnOffset if np.mod(i, 2)==0 else plotColumn+columnOffset)
                livePlotWidget.axis_leftright.setLabel(groupLabel)
                livePlotWidget.axis_leftright.setTickFont(self.plotWidgetFont)
                livePlotWidget.axis_leftright.setPen(pg.mkPen(color=colors.fg, width=2))
                livePlotWidget.axis_leftright.setTextPen(pg.mkPen(color=colors.fg))
                livePlotWidget.axis_leftright.setWidth(60 if logY else 40)
                livePlotWidget.setMouseEnabled(x=False, y=True)
                self.livePlotWidgets.append(livePlotWidget)
            if self.stackAction.state == self.stackAction.labels.stacked:
                self.updateStackedViews() # call after all initialized
        self.pluginManager.plotting = False

    def updateStackedViews(self):
        if self.stackAction.state == self.stackAction.labels.stacked:
            for livePlotWidget in self.livePlotWidgets[1:]:
                livePlotWidget.setGeometry(self.livePlotWidgets[0].vb.sceneBoundingRect())
                livePlotWidget.linkedViewChanged(self.livePlotWidgets[0].vb, livePlotWidget.XAxis)

    def getIcon(self, **kwargs):
        return self.parentPlugin.getIcon(**kwargs)

    def runTestParallel(self):
        """:meta private:"""
        if self.initializedDock:
            # init, start, pause, stop acquisition will be tested by DeviceManager
            self.testControl(self.copyAction, True)
            # self.testControl(self.clearHistoryAction, True) # keep history, test manually if applicable
            if hasattr(self, 'exportAction'):
                self.testControl(self.exportAction, True)
        super().runTestParallel()

    @synchronized()
    def copyClipboard(self):
        self.print('copyClipboard', flag=PRINT.DEBUG)
        """Extends matplotlib based version to add support for pyqtgraph."""
        # Test in light mode with and without mouse enabled
        # Test in dark mode with and without mouse enabled, with and without
        if len(self.livePlotWidgets) == 0:
            self.print('Plot not initialized', flag=PRINT.WARNING)
            return
        if getDarkMode() and not getClipboardTheme():
            try:
                setDarkMode(False) # temporary switch to light mode
                restoreAutoRange = all([not livePlotWidget.getViewBox().mouseEnabled()[0] # all have x mouse disabled
                    for livePlotWidget in self.livePlotWidgets if isinstance(livePlotWidget, (pg.PlotItem, pg.PlotWidget))])
                viewRange = self.livePlotWidgets[0].viewRange()
                sizes = self.plotSplitter.sizes()
                self.parentPlugin.clearPlot()
                self.initFig()
                self.plotSplitter.setSizes(sizes)
                self.livePlotWidgets[0].setMouseEnabled(x=True, y=True) # prevents autoscaling
                self.livePlotWidgets[0].setRange(xRange=viewRange[0], yRange=viewRange[1], padding=0)
                self.plot()
                self.processEvents() # update GUI before grabbing
                QApplication.clipboard().setPixmap(self.plotSplitter.grab())
            except Exception as e:
                self.print(f'Error while plotting in light theme: {e}')
            finally: # make sure darkmode is restored even after errors
                setDarkMode(True) # restore dark theme
                self.parentPlugin.clearPlot()
                self.initFig()
                self.plotSplitter.setSizes(sizes)
                if not restoreAutoRange:
                    # self.livePlotWidgets[0].getViewBox().enableAutoRange(x=False)
                    self.livePlotWidgets[0].setMouseEnabled(x=True, y=True)
                    self.livePlotWidgets[0].setRange(xRange=viewRange[0], yRange=viewRange[1], padding=0)
                self.plot()
        else:
            QApplication.clipboard().setPixmap(self.plotSplitter.grab())

    def provideDock(self):
        """:meta private:"""
        if super().provideDock():
            self.finalizeInit()
            self.afterFinalizeInit()

    def getTimeAxes(self):
        timeAxes = {}
        for device in list(set([channel.getDevice() for channel in self.parentPlugin.getChannels()])):
            # device could be a general channel manager, in which case this call is directed to all real devices corresponding to the managed channels
            # time axis should only be called once per device in each plot cycle
            # all new entries including time are added in one step to avoid any chance of unequal array sizes
            _time = device.time.get()
            i_min = 0
            i_max = 0
            n = 1
            timeAxis = []
            if (len(self.livePlotWidgets) > 0 and  # range determined by user
                any([livePlotWidget.getViewBox().mouseEnabled()[0] and livePlotWidget.getAxis('bottom').range[0] != 0
                     for livePlotWidget in self.livePlotWidgets if isinstance(livePlotWidget, (pg.PlotItem, pg.PlotWidget))])):
                t_min, t_max = self.livePlotWidgets[0].getAxis('bottom').range # is [0, 1] if nothing has been plotted before, use display time in this case
                i_min = np.argmin(np.abs(_time - t_min))
                i_max = np.argmin(np.abs(_time - t_max))
                n = max(int((i_max-i_min)/self.pluginManager.DeviceManager.max_display_size), 1) if self.pluginManager.DeviceManager.limit_display_size else 1
                timeAxis = device.time.get(_min=i_min, _max=i_max, n=n)
                # self.print(f'range from x axis {i_min} {i_max} {n} {len(timeAxis)}')
            else: # displayTime determines range
                if device.time.size > 0:
                    i_min = (np.argmin(np.abs(_time - (time.time() - self.getDisplayTime()*60)))
                                    if self.getDisplayTime() != -1 else 0)
                    i_max = None
                    t_length = _time.shape[0] - i_min # number of indices within displaytime before thinning
                    # determine by how much to limit number of displayed data points
                    n = max(int(t_length/self.pluginManager.DeviceManager.max_display_size), 1) if self.pluginManager.DeviceManager.limit_display_size else 1
                    timeAxis = device.time.get(_min=i_min, n=n)
            timeAxes[device.name] = i_min, i_max, n, timeAxis
        return timeAxes

    def plot(self, apply=False):
        """Plots the enabled and initialized channels in the main output plot
            The x axis is either time or a selected channel

        :param apply: Apply most recent data, otherwise update rate depends on data thinning
        :type apply: bool
        """
        if not self.initializedDock: # ignore request to plot if livedisplay is not visible
            return
        if len(self.livePlotWidgets) != len(self.getGroups()):
            self.initFig()
            apply = True # need to plot everything after initializing
        if len(self.livePlotWidgets) == 0:
            return
        if (not self.initializedDock or self.parentPlugin.pluginManager.loading
            or self.pluginManager.Settings.loading or self.pluginManager.plotting):
            return # values not yet available
        if hasattr(self.parentPlugin, 'time') and self.parentPlugin.time.size < 1: # no data
            return
        # self.print('plot', flag=PRINT.DEBUG) only uncomment for specific testing to prevent spamming the console
        self.pluginManager.plotting = True # protect from recursion
        # flip array to speed up search of most recent data points
        # may return None if no value is older than displaytime
        timeAxes = self.getTimeAxes()
        for livePlotWidget, channels in zip(self.livePlotWidgets, self.channelGroups.values()):
            self.plotGroup(livePlotWidget, timeAxes, channels, apply)

        if all([not livePlotWidget.getViewBox().mouseEnabled()[0] # all have x mouse disabled
                for livePlotWidget in self.livePlotWidgets if isinstance(livePlotWidget, (pg.PlotItem, pg.PlotWidget))]):
            if self.getDisplayTime() != -1:
                self.livePlotWidgets[0].setXRange(time.time()-self.getDisplayTime()*60, time.time()) # x axis linked to all others
            else:
                self.livePlotWidgets[0].setXRange(self.parentPlugin.minTime(), time.time())

        if self._updateLegend:
            for livePlotWidget, channels in zip(self.livePlotWidgets, self.channelGroups.values()):
                if isinstance(livePlotWidget, (pg.PlotItem, pg.PlotWidget)):
                    livePlotWidget.legend.clear()
                else:
                    livePlotWidget = self.livePlotWidgets[0]
                for channel in channels:
                    if channel.plotCurve is not None:
                        livePlotWidget.legend.addItem(channel.plotCurve, name=channel.plotCurve.name())
            self._updateLegend = False

        if self.parentPlugin.pluginType in [self.pluginManager.TYPE.INPUTDEVICE, self.pluginManager.TYPE.OUTPUTDEVICE] and self.parentPlugin.recording:
            self.parentPlugin.measureInterval()
        self.pluginManager.plotting = False

    def plotGroup(self, livePlotWidget, timeAxes, channels, apply):
        for channel in channels[::-1]: # reverse order so channels on top of list are also plotted on top of others
            self.plotChannel(livePlotWidget, timeAxes, channel, apply)

    def plotChannel(self, livePlotWidget, timeAxes, channel, apply):
        if (channel.enabled or not channel.real) and channel.display and channel.time.size != 0:
            i_min, i_max, n, timeAxis = timeAxes[channel.getDevice().name]
            if apply or np.remainder(i_min, n) == 0: # otherwise no update required
                if timeAxis.shape[0] > 1: # need at least 2 data points to plot connecting line segment
                    if channel.plotCurve is None:
                        if isinstance(livePlotWidget, (pg.PlotItem, pg.PlotWidget)):
                            channel.plotCurve = livePlotWidget.plot(pen=pg.mkPen((channel.color), width=channel.linewidth,
                                                    style=channel.getQtLineStyle()), name=f'{channel.name} ({channel.unit})') # initialize empty plots
                        else: # pg.ViewBox
                            channel.plotCurve = pg.PlotDataItem(pen=pg.mkPen((channel.color), width=channel.linewidth,
                                                    style=channel.getQtLineStyle()), name=f'{channel.name} ({channel.unit})') # initialize empty plots
                            channel.plotCurve.setLogMode(xState=False, yState=channel.logY) # has to be set for axis and ViewBox https://github.com/pyqtgraph/pyqtgraph/issues/2603
                            livePlotWidget.addItem(channel.plotCurve) # works for plotWidgets as well as viewBoxes
                            channel.plotCurve._legend = self.livePlotWidgets[0].legend # have to explicitly remove from legend before deleting!
                        self._updateLegend = True # curve added
                        channel.plotCurve._parent = livePlotWidget # allows to remove from _parent before deleting, preventing _parent from trying to access deleted object
                    # plotting is very expensive, array manipulation is negligible even with 50000 data points per channel
                    # channel should at any point have as many data points as timeAxis (missing bits will be filled with nan as soon as new data comes in)
                    # however, cant exclude that one data point added between definition of timeAxis and y
                    y = channel.convertDataDisplay(channel.getValues(subtractBackground=channel.getDevice().subtractBackgroundActive(),
                                          _min=i_min, _max=i_max, n=n)) # ignore last data point, possibly added after definition of timeAx #, _callSync='off'
                    if y.shape[0] == 0 or all(np.isnan(y)):
                        # cannot draw if only np.nan (e.g. when zooming into old data where a channel did not exist or was not enabled and data was padded with np.nan)
                        channel.clearPlotCurve()
                    else:
                        length = min(timeAxis.shape[0], y.shape[0]) # make sure x any y have same shape
                        if channel.smooth != 0:
                            # y = uniform_filter1d(y, channel.smooth) # revert once nan_policy implemented
                            y = smooth(y, channel.smooth)
                        channel.plotCurve.setData(timeAxis[:length], y[:length])
                else:
                    channel.clearPlotCurve()
        else:
            channel.clearPlotCurve()

    def closeUserGUI(self):
        """:meta private:"""
        self.parentPlugin.toggleLiveDisplayAction.state = False # state is remembered and restored from setting
        # self.remoteView.close() # not using parallelization for now
        super().closeUserGUI()

    def closeGUI(self):
        """:meta private:"""
        if not self.pluginManager.closing:
            self.parentPlugin.clearPlot() # plotCurve references will be deleted and have to be recreated later if needed
            self.pluginManager.toggleTitleBarDelayed(update=True)
        super().closeGUI()

    def updateTheme(self):
        """:meta private:"""
        super().updateTheme()
        if not self.loading:
            self.parentPlugin.clearPlot() # recreate plot with new colors
            self.plot(apply=True)

class ChannelManager(Plugin):

    name='Channel Manager'  # overwrite after inheriting
    version = '1.0'
    pluginType = PluginManager.TYPE.CONTROL  # overwrite after inheriting
    previewFileTypes = []
    optional = False
    useAdvancedOptions = True

    class SignalCommunicate(Plugin.SignalCommunicate): # signals that can be emitted by external threads
        """Object than bundles pyqtSignals for the Channelmanager"""
        plotSignal = pyqtSignal()
        """Signal that triggers plotting of history."""

    StaticDisplay = StaticDisplay
    """Defined here so that overwriting only affects single instance in device and not all instances.

    :meta private:
    """
    LiveDisplay = LiveDisplay
    """Defined here so that overwriting only affects single instance in device and not all instances.

    :meta private:
    """
    channels : List[Channel]
    """List of :class:`channels<esibd.core.Channel>`."""
    channelType = EsibdCore.Channel
    """Type of :class:`~esibd.core.Channel` used by the device. Overwrite by appropriate type in derived classes."""
    staticDisplay : StaticDisplay
    """Internal plugin to display data from file."""
    liveDisplay : LiveDisplay
    """Internal plugin to display data in real time."""
    useBackgrounds : bool = False
    """If True, the device implements controls to define and subtract background signals."""
    useDisplays = True
    """use liveDisplay, StaticDisplay, ChannelPlot, and all related functionality."""
    useMonitors = False
    """Use record monitors and compare them to set points."""
    useOnOffLogic = False
    """Creates an Action in the DeviceManager that handles turning key functions on and off."""

    class ChannelPlot(Plugin):
        """Simplified version of the Line plugin for plotting channels."""

        version = '1.0'
        pluginType = PluginManager.TYPE.DISPLAY

        def __init__(self, parentPlugin, pluginManager=None, dependencyPath=None):
            super().__init__(pluginManager, dependencyPath)
            self.parentPlugin = parentPlugin
            self.name = f'{parentPlugin.name} Channel Plot'

        def initGUI(self):
            super().initGUI()
            self.initFig()

        def initFig(self):
            self.provideFig()
            self.axes.append(self.fig.add_subplot(111))
            self.line = None

        def provideDock(self):
            if super().provideDock():
                self.finalizeInit()
                self.afterFinalizeInit()

        def finalizeInit(self, aboutFunc=None):
            super().finalizeInit(aboutFunc)
            self.copyAction = self.addAction(lambda: self.copyClipboard(), f'{self.name} channel plot to clipboard.', icon=self.imageClipboardIcon, before=self.aboutAction)

        def getIcon(self, desaturate=False):
            return self.parentPlugin.getIcon()

        def runTestParallel(self):
            if self.initializedDock:
                self.testControl(self.copyAction, True)
            # super().runTestParallel() handled by Channelmanager

        def plot(self):
            """Plots current values from all real :class:`channels<esibd.core.Channel>`."""
            self.axes[0].clear()
            channels = [channel for channel in self.parentPlugin.getChannels() if not hasattr(channel, 'real') or channel.real]
            y = [channel.value for channel in channels]
            labels = [channel.name for channel in channels]
            _colors = [channel.color for channel in channels]
            x = np.arange(len(y))
            self.axes[0].scatter(x, y, marker='.', color=_colors)
            self.axes[0].set_ylabel(self.parentPlugin.unit if hasattr(self.parentPlugin, 'unit') else '')
            self.axes[0].set_xticks(x, labels, rotation=30, ha='right', rotation_mode='anchor')
            self.canvas.draw_idle()

    def __init__(self, **kwargs): # Always use keyword arguments to allow forwarding to parent classes.
        super().__init__(**kwargs)
        self.channels = []
        self.channelsChanged = False
        self.channelPlot = None
        self.confINI = f'{self.name}.ini' # not a file extension, but complete filename to save and restore configurations
        self.confh5 = f'_{self.name.lower()}.h5'
        self.previewFileTypes = [self.confINI, self.confh5]
        self.changeLog = []
        self.lagging = 0
        self._recording = False
        self.staticDisplay = self.StaticDisplay(parentPlugin=self, **kwargs) if self.useDisplays else None # need to initialize to access previewFileTypes
        self.liveDisplay = self.LiveDisplay(parentPlugin=self, **kwargs) if self.useDisplays else None
        if self.useDisplays:
            self.signalComm.plotSignal.connect(self.liveDisplay.plot)
        self.dataThread = None

    def initGUI(self):
        super().initGUI()
        self.advancedAction.toolTipFalse = f'Show advanced options and virtual channels for {self.name}.'
        self.advancedAction.toolTipTrue = f'Hide advanced options and virtual channels for {self.name}.'
        self.advancedAction.setToolTip(self.advancedAction.toolTipFalse)
        self.importAction = self.addAction(lambda: self.loadConfiguration(file=None), f'Import {self.name} channels and values.', icon=self.makeCoreIcon('blue-folder-import.png'))
        self.exportAction = self.addAction(lambda: self.exportConfiguration(file=None), f'Export {self.name} channels and values.', icon=self.makeCoreIcon('blue-folder-export.png'))
        self.saveAction = self.addAction(lambda: self.saveConfiguration(), f'Save {self.name} channels in current session.', icon=self.makeCoreIcon('database-export.png'))
        self.duplicateChannelAction = self.addAction(event=lambda: self.duplicateChannel(), toolTip='Insert copy of selected channel.', icon=self.makeCoreIcon('table-insert-row.png'))
        self.deleteChannelAction    = self.addAction(event=lambda: self.deleteChannel(), toolTip='Delete selected channel.', icon=self.makeCoreIcon('table-delete-row.png'))
        self.moveChannelUpAction    = self.addAction(event=lambda: self.moveChannel(up=True), toolTip='Move selected channel up.', icon=self.makeCoreIcon('table-up.png'))
        self.moveChannelDownAction  = self.addAction(event=lambda: self.moveChannel(up=False), toolTip='Move selected channel down.', icon=self.makeCoreIcon('table-down.png'))
        if self.useDisplays:
            self.channelPlotAction = self.addAction(lambda: self.showChannelPlot(), f'Plot {self.name} values.', icon=self.makeCoreIcon('chart.png'))
            self.toggleLiveDisplayAction = self.addStateAction(toolTipFalse=f'Show {self.name} live display.', iconFalse=self.makeCoreIcon('system-monitor.png'),
                                              toolTipTrue=f'Hide {self.name} live display.', iconTrue=self.makeCoreIcon('system-monitor--minus.png'),
                                              attr='showLiveDisplay', event=lambda: self.toggleLiveDisplay(), default='true')
        self.tree = TreeWidget()
        self.addContentWidget(self.tree)
        self.loadConfiguration(default=True)

    def finalizeInit(self, aboutFunc=None):
        if self.useOnOffLogic:
            self.onAction = self.pluginManager.DeviceManager.addStateAction(event=lambda: self.setOn(), toolTipFalse=f'{self.name} on.', iconFalse=self.getIcon(desaturate=True),
                                                                  toolTipTrue=f'{self.name} off.', iconTrue=self.getIcon(),
                                                                 before=self.pluginManager.DeviceManager.aboutAction)
        super().finalizeInit(aboutFunc)
        self.copyAction = self.addAction(lambda: self.copyClipboard(), f'{self.name} channel image to clipboard.', self.imageClipboardIcon, before=self.aboutAction)
        self.toggleLiveDisplay()

    def isOn(self):
        """Overwrite to signal if device output (e.g. for voltage supplies) is on."""
        if self.useOnOffLogic:
            return self.onAction.state
        else:
            return False

    def setOn(self, on=None):
        if on is not None and self.onAction.state is not on:
            self.onAction.state = on

    def runTestParallel(self):
        """:meta private:"""
        if self.initializedDock:
            # Note: ignore repeated line indicating testing of device.name as static and live displays have same name
            if hasattr(self, 'channelPlotAction') and self.channelPlotAction is not None:
                self.testControl(self.channelPlotAction, True)#, 1
            self.testControl(self.advancedAction, True)
            self.testControl(self.saveAction, True)
            self.testControl(self.copyAction, True)
            for parameter in self.channels[0].parameters:
                if parameter.name not in [Channel.COLOR] and not parameter.indicator: # color requires user interaction, indicators do not trigger events
                    self.testControl(parameter.getWidget(), parameter.value, .1,
                                     label=f'Testing {self.channels[0].name}.{parameter.name} {parameter.toolTip if parameter.toolTip is not None else "No toolTip."}')
            self.testControl(self.channels[0].getParameterByName(Channel.SELECT).getWidget(), True, .1)
            self.testControl(self.moveChannelDownAction, True, 1)
            self.testControl(self.moveChannelUpAction, True, 1)
            self.testControl(self.duplicateChannelAction, True, 1)
            self.testControl(self.deleteChannelAction, True, 1)
            self.testControl(self.advancedAction, False)
            if self.useOnOffLogic: # should be off for previous tests, as closing (for delete, duplicate, move) requires user input
                self.testControl(self.onAction, True)
            if self.useDisplays:
                if self.initializedDock:
                    if self.staticDisplayActive():
                        self.staticDisplay.raiseDock(True)
            #             self.testControl(self.staticDisplay.videoRecorderAction, True)
                        self.staticDisplay.runTestParallel()
            #             self.testControl(self.staticDisplay.videoRecorderAction, False)
            if self.channelPlotActive():
                    self.channelPlot.raiseDock(True)
            #         self.testControl(self.channelPlot.videoRecorderAction, True)
                    self.channelPlot.runTestParallel()
            #         self.testControl(self.channelPlot.videoRecorderAction, False)
                # init, start, pause, stop acquisition will be tested by DeviceManager
        super().runTestParallel()

    def copyClipboard(self):
        # global_rect = QRect(self.tree.mapToGlobal(self.tree.rect().topLeft()), self.tree.mapToGlobal(self.tree.rect().bottomRight()))
        # QApplication.clipboard().setPixmap(QApplication.primaryScreen().grabWindow(self.tree.winId(), global_rect.x(), global_rect.y(), global_rect.width(), global_rect.height()))
        QApplication.clipboard().setPixmap(self.tree.grabItems())

    INTERVAL = 'Interval'

    def getDefaultSettings(self):
        """ Define specific settings that will be added to the general settings tab.
        Settings will be generated automatically if not found in the settings file.
        Overwrite and extend as needed."""
        ds = {}
        ds[f'{self.name}/{self.INTERVAL}'] = parameterDict(value=2000, _min=100, _max=10000, toolTip=f'Interval for {self.name} in ms.',
                                                                widgetType=Parameter.TYPE.INT, event=lambda: self.intervalChanged(), attr='interval', instantUpdate=False)
        return ds

    def customConfigFile(self, file):
        return self.pluginManager.Settings.configPath / file

    def getChannelByName(self, name):
        """Returns a device specific channel based on its unique name."""
        return next((channel for channel in self.channels if channel.name.strip().lower() == name.strip().lower()), None)

    def getSelectedChannel(self):
        """Returns selected channel. Note, channels can only be selected in advanced mode."""
        return next((channel for channel in self.channels if channel.select), None)

    def getChannels(self):
        # allows to replace list of internal channels with corresponding source channels if applicable.
        return self.channels

    def minTime(self):
        if hasattr(self, 'time'):
            return self.time.get()[0]
        else:
            return np.min([channel.time.get()[0] for channel in self.getChannels() if channel.time.size > 0])

    def getActiveChannels(self):
        # allows to replace list of internal channels with corresponding source channels if applicable.
        return [channel for channel in self.getChannels() if (channel.enabled or not channel.real)]

    def getDataChannels(self):
        return [channel for channel in self.channels if channel.getValues().shape[0] != 0]

    def addChannel(self, item, index=None):
        """Maps dictionary to :class:`~esibd.core.Channel`."""
        channel = self.channelType(device=self, tree=self.tree)
        if index is None:
            self.channels.append(channel)
            self.tree.addTopLevelItem(channel) # has to be added before populating
        else:
            self.channels.insert(index, channel)
            self.tree.insertTopLevelItem(index, channel) # has to be added before populating
        channel.initGUI(item)

    def modifyChannel(self):
        selectedChannel = self.getSelectedChannel()
        if selectedChannel is None:
            self.print('No channel selected.')
            return None
        else:
            return selectedChannel

    @synchronized()
    def duplicateChannel(self):
        selectedChannel = self.modifyChannel()
        if selectedChannel is not None:
            self.print(f'duplicateChannel {selectedChannel.name}', flag=PRINT.DEBUG)
            index=self.channels.index(selectedChannel)
            newChannelDict = selectedChannel.asDict()
            newChannelDict[selectedChannel.NAME] = f'{selectedChannel.name}_copy'
            self.loading = True
            self.addChannel(item=newChannelDict, index=index + 1)
            self.loading = False
            newChannel = self.getChannelByName(newChannelDict[selectedChannel.NAME])
            self.channelSelection(selectedChannel = newChannel) # trigger deselecting original channel
            self.tree.scheduleDelayedItemsLayout()
            return newChannel

    @synchronized()
    def deleteChannel(self):
        selectedChannel = self.modifyChannel()
        if selectedChannel is not None:
            self.print(f'deleteChannel {selectedChannel.name}', flag=PRINT.DEBUG)
            if len(self.channels) == 1:
                self.print('Need to keep at least one channel.')
                return
            selectedChannel.onDelete()
            index = self.channels.index(selectedChannel)
            self.channels.pop(index)
            self.tree.takeTopLevelItem(index)
            self.channels[min(index, len(self.channels)-1)].select = True
            self.pluginManager.reconnectSource(selectedChannel)

    @synchronized()
    def moveChannel(self, up):
        """Moves the channel up or down in the list of channels.

        :param up: Move up if True, else down.
        :type up: bool
        """
        selectedChannel = self.modifyChannel()
        if selectedChannel is not None:
            self.print(f'moveChannel {selectedChannel.name} {"up" if up else "down"}', flag=PRINT.DEBUG)
            index = self.channels.index(selectedChannel)
            if index == 0 and up or index == len(self.channels)-1 and not up:
                self.print(f"Cannot move channel further {'up' if up else 'down'}.")
                return
            self.loading = True
            selectedChannel.onDelete()
            self.channels.pop(index)
            self.tree.takeTopLevelItem(index)
            oldValues = selectedChannel.values.get()
            oldValue = selectedChannel.value
            if selectedChannel.useBackgrounds:
                oldBackgrounds = selectedChannel.backgrounds
                oldBackground = selectedChannel.background
            if up:
                self.addChannel(item=selectedChannel.asDict(), index=index - 1)
            else:
                self.addChannel(item=selectedChannel.asDict(), index=index + 1)
            newChannel = self.getChannelByName(selectedChannel.name)
            if len(oldValues) > 0:
                newChannel.values = DynamicNp(initialData=oldValues, max_size=self.maxDataPoints)
                newChannel.value = oldValue
                if newChannel.useBackgrounds:
                    newChannel.backgrounds = oldBackgrounds
                    newChannel.background = oldBackground
            self.loading = False
            self.pluginManager.reconnectSource(newChannel)
            self.tree.scheduleDelayedItemsLayout()
            return newChannel

    def plot(self, apply=False):
        if self.liveDisplayActive():
            self.liveDisplay.plot(apply=apply)

    def clearPlot(self):
        if self.liveDisplayActive() and not self.pluginManager.closing:
            self.liveDisplay.clearPlot()

    def convertDataDisplay(self, data):
        """Overwrite to apply scaling and offsets to data before it is displayed. Use, e.g., to convert to another unit."""
        return data

    @synchronized()
    def saveConfiguration(self):
        self.pluginManager.Settings.incrementMeasurementNumber()
        file = self.pluginManager.Settings.getMeasurementFileName(self.confh5)
        self.exportConfiguration(file)
        self.print(f'Saved {file.name}')

    CHANNEL = 'Channel'

    def exportConfiguration(self, file=None, default=False):
        """Saves an .ini or .h5 file which contains the configuration for this :class:`~esibd.plugins.Device`.
        The .ini file can be easily edited manually with a text editor to add more :class:`channels<esibd.core.Channel>`."""
        if len(self.channels) == 0:
            self.print('No channels found to export.', PRINT.ERROR)
            return
        if default:
            file = self.customConfigFile(self.confINI)
        if file is None: # get file via dialog
            file = Path(QFileDialog.getSaveFileName(parent=None, caption=SELECTFILE, filter=self.FILTER_INI_H5)[0])
        if file != Path('.'):
            if file.suffix == FILE_INI:
                confParser = configparser.ConfigParser()
                confParser[INFO] = infoDict(self.name)
                for i, channel in enumerate(self.channels):
                    confParser[f'{self.CHANNEL}_{i:03d}'] = channel.asDict(temp=True, formatValue=True)
                with open(file, 'w', encoding=self.UTF8) as configFile:
                    confParser.write(configFile)
            else: # h5
                with h5py.File(file, 'a', track_order=True) as h5file:
                    self.hdfUpdateVersion(h5file)
                    group = self.requireGroup(h5file, self.name)
                    for parameter in self.channels[0].asDict(temp=True):
                        if parameter in group:
                            self.print(f'Ignoring duplicate parameter {parameter}', PRINT.WARNING)
                            continue
                        widgetType = self.channels[0].getParameterByName(parameter).widgetType
                        data = [channel.getParameterByName(parameter).value for channel in self.channels]
                        dtype = None
                        if widgetType == Parameter.TYPE.INT:
                            dtype = np.int32
                        elif widgetType == Parameter.TYPE.FLOAT:
                            dtype = np.float32
                        elif widgetType == Parameter.TYPE.BOOL:
                            dtype = np.bool_ # used to be bool8
                        elif widgetType == Parameter.TYPE.COLOR:
                            data = [channel.getParameterByName(parameter).value for channel in self.channels]
                            dtype = 'S7'
                        else: # widgetType in [Parameter.TYPE.COMBO, Parameter.TYPE.INTCOMBO, Parameter.TYPE.TEXT, Parameter.TYPE.LABEL]:
                            dtype = f'S{len(max([str(string) for string in data], key=len))}' # use length of longest string as fixed length is required
                        group.create_dataset(name=parameter, data=np.asarray(data, dtype=dtype)) # do not save as attributes. very very memory intensive!
        if not self.pluginManager.loading:
            self.pluginManager.Explorer.populateTree()

    @synchronized()
    def toggleAdvanced(self, advanced=None):
        # self.print('toggleAdvanced', flag=PRINT.DEBUG)
        if advanced is not None:
            self.advancedAction.state = advanced
        self.importAction.setVisible(self.advancedAction.state)
        self.exportAction.setVisible(self.advancedAction.state)
        self.duplicateChannelAction.setVisible(self.advancedAction.state)
        self.deleteChannelAction.setVisible(self.advancedAction.state)
        self.moveChannelUpAction.setVisible(self.advancedAction.state)
        self.moveChannelDownAction.setVisible(self.advancedAction.state)
        for i, item in enumerate(self.channels[0].getSortedDefaultChannel().values()):
            if item[Parameter.ADVANCED]:
                self.tree.setColumnHidden(i, not self.advancedAction.state)
        for channel in self.channels:
            if self.inout == INOUT.NONE:
                channel.setHidden(False)
            else:
                if channel.inout == INOUT.IN:
                    channel.setHidden(not (self.advancedAction.state or channel.active))
                else: # INOUT.OUT:
                    channel.setHidden(not (self.advancedAction.state or channel.active or channel.display))
        # Collapses all channels of same color below selected channels.
        for channel in self.channels:
            index = self.channels.index(channel)
            while True:
                if index == 0:
                    break
                c_above = self.channels[index-1]
                if c_above.color != channel.color:
                    break
                if c_above.collapse or (c_above.isHidden() and c_above.active):
                    channel.setHidden(True)
                    break
                index = index-1

    def intervalChanged(self):
        """Extend to add code to be executed in case the :ref:`acquisition_interval` changes."""
        pass

    def loadConfiguration(self, file=None, default=False, append=False):
        """Loads :class:`channel<esibd.core.Channel>` configuration from file.
        If only values should be loaded without complete reinitialization, use :attr:`loadValues<esibd.plugins.Device.loadValues>` instead.

        :param file: File from which to load configuration, defaults to None
        :type file: pathlib.Path, optional
        :param default: Use internal configuration file if True, defaults to False
        :type default: bool, optional
        """
        if default:
            file = self.customConfigFile(self.confINI)
        if file is None: # get file via dialog
            if hasattr(self, 'initialized') and self.initialized():
                self.print('Stop communication to load channels.', flag=PRINT.WARNING)
                return
            file = Path(QFileDialog.getOpenFileName(parent=None, caption=SELECTFILE, filter=self.FILTER_INI_H5,
                                                    directory=self.pluginManager.Settings.getFullSessionPath().as_posix())[0])
        if file != Path('.'):
            self.loading = True
            self.tree.setUpdatesEnabled(False)
            self.tree.setRootIsDecorated(False) # no need to show expander
            if file.suffix == EsibdCore.FILE_INI:
                if file.exists(): # create default if not exist
                    confParser = configparser.ConfigParser()
                    confParser.read(file)
                    if len(confParser.items()) < 3: # minimum: DEFAULT, Info, and one Channel
                        self.print(f'File {file} does not contain valid channels. Repair the file manually or delete it, ' +
                                                    ' to trigger generation of a valid default channel on next start.', PRINT.WARNING)
                        self.tree.setHeaderLabels(['No valid channels found. Repair or delete config file.'])
                        self.tree.setUpdatesEnabled(True)
                        self.loading = False
                        return
                    self.updateChannelConfig([item for name, item in confParser.items() if name not in [Parameter.DEFAULT.upper(), EsibdCore.VERSION, EsibdCore.INFO]], file, append=append)
                else: # Generate default settings file if file was not found.
                    # To update files with new parameters, simply delete the old file and the new one will be generated.
                    if self.channels == []:
                        self.print(f'Generating default config file {file}')
                        for i in range(9):
                            self.addChannel(item={Parameter.NAME : f'{self.name}{i+1}'})
                    else:
                        self.print(f'Generating config file {file}')
                    self.exportConfiguration(file, default=True)
            else: # file.suffix == EsibdCore.FILE_H5:
                with h5py.File(name=file, mode='r', track_order=True) as h5file:
                    group = h5file[self.name]
                    items = [{} for _ in range(len(group[Parameter.NAME]))]
                    for i, name in enumerate(group[Parameter.NAME].asstr()):
                        items[i][Parameter.NAME] = name
                    default = self.channelType(device=self, tree=None)
                    for name, parameter in default.getSortedDefaultChannel().items():
                        values = None
                        if parameter[Parameter.WIDGETTYPE] in [Parameter.TYPE.INT, Parameter.TYPE.FLOAT]:
                            values = group[name]
                        elif parameter[Parameter.WIDGETTYPE] == Parameter.TYPE.BOOL:
                            values = [str(_bool) for _bool in group[name]]
                        else:
                            values = group[name].asstr()
                        for i, value in enumerate(values):
                            items[i][name] = value
                    self.updateChannelConfig(items, file, append=append)

            self.tree.setHeaderLabels([(name.title() if dict[Parameter.HEADER] is None else dict[Parameter.HEADER])
                                                    for name, dict in self.channels[0].getSortedDefaultChannel().items()])
            self.tree.header().setStretchLastSection(False)
            self.tree.header().setMinimumSectionSize(0)
            self.tree.header().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
            for channel in self.getChannels():
                channel.collapseChanged(toggle=False)
            self.toggleAdvanced(self.advancedAction.state) # keep state after importing new configuration
            self.tree.setUpdatesEnabled(True)
            self.tree.scheduleDelayedItemsLayout()
            self.loading=False
            self.pluginManager.DeviceManager.globalUpdate(inout=self.inout)
            # if there was a history, it has been invalidated by reinitializing all channels.
            if not self.pluginManager.loading:
                for channel in self.getChannels():
                    channel.clearPlotCurve()

    @property
    def LOADVALUES(self):
        return f'Load {self.name} values.'

    def loadValues(self, file=None, append=False):
        """Loads values only, instead of entire configuration, for :class:`channels<esibd.core.Channel>` matching in file and current configuration.
        Channels that exist in the file but not in the current configuration will be ignored.
        Only used by input devices."""
        if file is None: # get file via dialog
            file = Path(QFileDialog.getOpenFileName(parent=None, caption=SELECTFILE, filter=self.FILTER_INI_H5)[0])
        if file != Path('.'):
            self.changeLog = [f'Change log for loading values for {self.name} from {file.name}:']
            if file.suffix == EsibdCore.FILE_INI:
                confParser = configparser.ConfigParser()
                confParser.read(file)
                for name, item in confParser.items():
                    if name not in [Parameter.DEFAULT.upper(), EsibdCore.VERSION, EsibdCore.INFO]:
                        self.updateChannelValue(item.get(Parameter.NAME), float(item.get(Parameter.VALUE, '0')))
            else: # FILE_H5
                with h5py.File(name=file, mode='r', track_order=True) as h5file:
                    group = h5file[self.name]
                    for name, value in zip(group[Parameter.NAME].asstr(), group[Parameter.VALUE]):
                        self.updateChannelValue(name, value)
            if len(self.changeLog) == 1:
                self.changeLog.append('No changes.')
            self.pluginManager.Text.setText('\n'.join(self.changeLog) + '\n', _show=False, append=append)
            self.print('Values updated. Change log available in Text plugin.')

    def updateChannelValue(self, name, value):
        channel = self.getChannelByName(name)
        if channel is not None:
            parameter = channel.getParameterByName(Parameter.VALUE)
            initialVal = channel.value
            channel.value=value
            if initialVal != channel.value: # c.value might be different from value due to coerced range
                self.changeLog.append(f'Value of channel {name} changed from {parameter.formatValue(initialVal)} to {parameter.formatValue(channel.value)} {self.unit}.')
        else:
            self.print(f'Could not find channel {name}.', PRINT.WARNING)

    def updateChannelConfig(self, items, file, append=False):
        """Scans for changes when loading configuration and displays change log
        before overwriting old channel configuration.

        :param items: :class:`~esibd.core.Channel` items from file
        :type items: List[:class:`~esibd.core.Channel`]
        :param file: config file
        :type file: pathlib.Path
        """
        # Note: h5diff can be used alternatively to find changes, but the output is not formatted in a user friendly way (hard to correlate values with channels).
        if not self.pluginManager.loading:
            self.changeLog = [f'Change log for loading channels for {self.name} from {file.name}:']
            self.changeLog += self.compareItemsConfig(items)[0]
            self.pluginManager.Text.setText('\n'.join(self.changeLog) + '\n', _show=False, append=append) # show changelog
            self.print('Configuration updated. Change log available in Text plugin.')
        # clear and load new channels
        for channel in self.channels:
            channel.onDelete()
        self.channels=[]
        self.tree.clear()
        for item in items:
            self.addChannel(item=item)
            if np.mod(len(self.channels), 5) == 0:
                self.processEvents()
                #print(f'{self.name} {len(self.channels)} channels')
        if not self.pluginManager.loading:
            self.pluginManager.connectAllSources() # previous channels have become invalid

    def compareItemsConfig(self, items, ignoreIndicators=False):
        """Compares channel items from file with current configuration.
        This allows to track changes and decide if files need to be updated.

        :param items: :class:`~esibd.core.Channel` items from file
        :type items: List[:class:`~esibd.core.Channel`]
        :param ignoreIndicators: Set to True if deciding about file updates (indicators are not saved in files).
        :type ignoreIndicators: bool
        """
        changeLog = []
        changed = True
        default=self.channelType(device=self, tree=None)
        for item in items:
            channel = self.getChannelByName(item[Parameter.NAME])
            if channel is None:
                changeLog.append(f'Adding channel {item[Parameter.NAME]}')
            else:
                for name in default.getSortedDefaultChannel():
                    if name in channel.tempParameters():
                        continue
                    parameter = channel.getParameterByName(name)
                    if name in item and not parameter.equals(item[name]):
                        if parameter.indicator and ignoreIndicators:
                            continue
                        changeLog.append(f'Updating parameter {name} on channel {channel.name} from {parameter.formatValue()} to {parameter.formatValue(item[name])}')
        newNames = [item[Parameter.NAME] for item in items]
        for channel in self.getChannels():
            if channel.name not in newNames:
                changeLog.append(f'Removing channel {channel.name}')
        if len(changeLog) == 0:
            changeLog.append('No changes.')
            changed = False
        return changeLog, changed

    def channelConfigChanged(self, file=None, default=True):
        """Scans for changes when saving configuration."""
        changed = False
        if default:
            file = self.customConfigFile(self.confINI)
        if file.exists():
            confParser = configparser.ConfigParser()
            confParser.read(file)
            if len(confParser.items()) > 2: # minimum: DEFAULT, Info, and one Channel
                items = [i for name, i in confParser.items() if name not in [Parameter.DEFAULT.upper(), EsibdCore.VERSION, EsibdCore.INFO]]
                changeLog, changed = self.compareItemsConfig(items, ignoreIndicators=True) # pylint: disable = unused-variable
                # self.pluginManager.Text.setText('\n'.join(changeLog), False) # optionally use changelog for debugging
        return changed

    def channelSelection(self, selectedChannel):
        if selectedChannel.select: # only one channel should be selected at all times
            for channel in self.channels: # all channels, independent on active, display, initialized ...
                if channel is not selectedChannel:
                    channel.select = False

    def channelPlotActive(self):
        return self.channelPlot is not None and self.channelPlot.initializedDock

    def toggleChannelPlot(self, visible):
        if visible:
            if self.channelPlot is None or not self.channelPlot.initializedDock:
                self.channelPlot = self.ChannelPlot(parentPlugin=self, pluginManager=self.pluginManager, dependencyPath=self.dependencyPath)
                self.channelPlot.provideDock()
        elif self.channelPlot is not None and self.channelPlot.initializedDock:
            self.channelPlot.closeGUI()

    @synchronized()
    def showChannelPlot(self):
        self.toggleChannelPlot(True)
        self.channelPlot.raiseDock(True)
        self.channelPlot.plot()

    def startRecording(self):
        if self.dataThread is not None and self.dataThread.is_alive():
            self.print('Wait for data recording thread to complete before restarting acquisition.', PRINT.WARNING)
            self.recording = False
            self.dataThread.join(timeout=5) # may freeze GUI temporarily but need to be sure old thread is stopped before starting new one
            if self.dataThread.is_alive():
                self.print('Data recording thread did not complete. Reset connection manually.', PRINT.ERROR)
                return
        self.clearPlot() # update legend in case channels have changed
        self.recording = True
        self.lagging = 0
        self.dataThread = Thread(target=self.runDataThread, args=(lambda: self.recording,), name=f'{self.name} dataThread')
        self.dataThread.daemon = True # Terminate with main app independent of stop condition
        self.dataThread.start()

    def toggleRecording(self, on=None, manual=True):
        """Toggle plotting of data in :class:`~esibd.plugins.LiveDisplay`.
        Extend to add recoding logic for devices.

        :param on: If true recording will be turned on, if false it will be turned off. If already on or off nothing happens. If None, recording is toggled.
        :type on: bool, optional
        :param manual: If true, signal was send directly from corresponding live display. Otherwise might be send from device manager
        :type manual: bool, optional
        """
        if (on is not None and not on) or (on is None and self.recording):
            # toggle off
            if self.recording:
                self.recording = False
        else: # (on is not None and on) (on is None and not self.recording):
            # toggle on if not already running
            if not self.recording:
                if self.liveDisplayActive():
                    self.clearPlot()
                self.startRecording()

    def runDataThread(self, recording):
        """Regularly triggers plotting of data.
        Overwrite to add logic for appending data to channels."""
        while recording():
            self.signalComm.plotSignal.emit()
            time.sleep(self.interval/1000) # in seconds # wait at end to avoid emitting signal after recording set to False

    @property
    def recording(self):
        return self._recording
    @recording.setter
    def recording(self, recording):
        self._recording = recording
        # allow output widgets to react to change if acquisition state
        if hasattr(self, 'recordingAction'):
            self.recordingAction.state = self.recording
            if self.liveDisplayActive():
                self.liveDisplay.recordingAction.state = self.recording

    def supportsFile(self, file):
        return any(file.name.endswith(suffix) for suffix in (self.getSupportedFiles())) # does not support any files for preview, only when explicitly loading

    def closeCommunication(self):
        """Stops recording and also closes all device communication.
        Extend to add custom code to close device communication."""
        if self.useOnOffLogic and self.onAction.state:
            self.setOn(False)
        self.recording = False

    def initializeCommunication(self):
        """Extend to initialize communication.
        Can be used to initialize GUI.
        Redirect initialization of hardware communication to the corresponding :class:`~esibd.core.DeviceController`."""
        self.clearPlot()

    def close(self):
        if self.channelConfigChanged(default=True) or self.channelsChanged:
            self.exportConfiguration(default=True)
        super().close()

    def closeGUI(self):
        """:meta private:"""
        self.toggleChannelPlot(False)
        self.toggleLiveDisplay(False)
        self.toggleStaticDisplay(False)
        super().closeGUI()

    def toggleTitleBar(self):
        """:meta private:"""
        super().toggleTitleBar()
        if self.liveDisplayActive():
            self.liveDisplay.toggleTitleBar()
        if self.staticDisplayActive():
            self.staticDisplay.toggleTitleBar()

    @synchronized()
    def toggleLiveDisplay(self, visible=None):
        if self.liveDisplay is None:
            return # liveDisplay not supported
        if (visible if visible is not None else self.toggleLiveDisplayAction.state):
            if not self.liveDisplayActive(): # only if not already visible
                self.liveDisplay.provideDock()
            self.liveDisplay.raiseDock(True)
        else:
            if self.liveDisplayActive():
                self.liveDisplay.closeGUI()

    def liveDisplayActive(self):
        return self.liveDisplay is not None and self.liveDisplay.initializedDock

    def toggleStaticDisplay(self, visible):
        if self.staticDisplay is None:
            return # staticDisplay not supported
        if visible:
            if not self.staticDisplayActive(): # only if not already visible
                self.staticDisplay.provideDock()
            self.staticDisplay.raiseDock(True)
        elif self.staticDisplayActive():
            self.staticDisplay.closeGUI()

    def staticDisplayActive(self):
        return self.staticDisplay is not None and self.staticDisplay.initializedDock

    def updateTheme(self):
        """:meta private:"""
        super().updateTheme()
        self.loading = True
        for channel in self.getChannels():
            channel.updateColor()
        self.loading = False
        if self.staticDisplayActive():
            self.staticDisplay.updateTheme()
        if self.liveDisplayActive():
            self.liveDisplay.updateTheme()

class Device(ChannelManager):
    """:class:`Devices<esibd.plugins.Device>` are used to handle communication with one or more
    physical devices, provide controls to configure the device and display live or
    previously recorded data. There are *input devices* (sending input from
    the user to hardware) and *output devices* (reading outputs from
    hardware). Note that some *input devices* may also read back data from
    hardware to confirm that the user defined values are applied correctly.

    The main interface consists of a list of :ref:`sec:channels`. By
    default only the physically relevant information is shown. By entering
    the *advanced mode*, additional channel parameters can be configured. The
    configuration can be exported and imported, though once all channels
    have been setup it is sufficient to only load values which can be done
    using a file dialog or from the context menu of an appropriate file in
    the :ref:`sec:explorer`. After loading the configurations or values, a change log will be
    available in the :ref:`sec:text` plugin to quickly identify what has changed. Each
    device also comes with a :ref:`display<sec:displays>` and a :ref:`live display<sec:live_displays>`.
    The current values can also be plotted to get a quick overview and identify any
    unusual values."""
    documentation = """Device plugins are used to handle communication with one or more
    devices, provide controls to configure the device and display live or
    previously recorded data. There are input devices (sending input from
    the user to hardware) and output devices (reading outputs from
    hardware). Note that some input devices may also read back data from
    hardware to confirm that the user defined values are applied correctly.

    The main interface consists of a list of channels. By
    default only the physically relevant information is shown. By entering
    the advanced mode, additional channel parameters can be configured. The
    configuration can be exported and imported, though once all channels
    have been setup it is sufficient to only load values which can be done
    using a file dialog or from the context menu of an appropriate file in
    the Explorer. After loading the configurations or values, a change log will be
    available in the Text plugin to quickly identify what has changed. Each
    device also comes with a display and a live display.
    The current values can also be plotted to get a quick overview and identify any
    unusual values."""

    version = 1.0
    optional = True
    name = 'Device' # overwrite after inheriting
    pluginType = PluginManager.TYPE.INPUTDEVICE
    """ :class:`Devices<esibd.plugins.Device>` are categorized as input or output devices.
    Overwrite with :attr:`~esibd.core.PluginManager.TYPE.OUTPUTDEVICE` after inheriting if applicable."""

    MAXSTORAGE = 'Max storage'
    MAXDATAPOINTS = 'Max data points'
    LOGGING = 'Logging'
    unit : str = 'unit'
    """Unit used in user interface."""
    inout : INOUT
    """Flag specifying if this is an input or output device."""
    useBackgrounds = False

    class SignalCommunicate(ChannelManager.SignalCommunicate):
        appendDataSignal    = pyqtSignal()
        """Signal that triggers appending of data from channels to history."""

    def __init__(self, **kwargs): # Always use keyword arguments to allow forwarding to parent classes.
        super().__init__(**kwargs)
        if self.pluginType == PluginManager.TYPE.INPUTDEVICE:
            self.inout = INOUT.IN
        else:
            self.inout = INOUT.OUT
        self.logY = False
        self.updating = False # Suppress events while channel equations are evaluated
        self.time = DynamicNp(dtype=np.float64)
        self.lastIntervalTime = time.time()*1000
        self.interval_tolerance = None # how much the acquisition interval is allowed to deviate
        self.signalComm.appendDataSignal.connect(self.appendData)
        # implement a controller based on DeviceController(_parent=self). In some cases there is no controller for the device, but for every channel. Adjust
        self.controller = None
        self.subtractBackgroundAction = None
        self.errorCountTimer = QTimer()
        self.errorCountTimer.timeout.connect(self.resetErrorCount)
        self.errorCountTimer.setInterval(600000) # 10 min i.e. 600000 msec

    def initGUI(self):
        """:meta private:"""
        super().initGUI()
        self.closeCommunicationAction = self.addAction(event=lambda: self.closeCommunication(), toolTip=f'Close {self.name} communication.', icon=self.makeCoreIcon('stop.png'))
        self.initAction = self.addAction(event=lambda: self.initializeCommunication(), toolTip=f'Initialize {self.name} communication.', icon=self.makeCoreIcon('rocket-fly.png'))
        self.recordingAction = self.addStateAction(lambda: self.toggleRecording(manual=True), f'Start {self.name} data acquisition.', self.makeCoreIcon('play.png'),
                                                   f'Pause {self.name} data acquisition.', self.makeCoreIcon('pause.png'))
        if self.useBackgrounds:
            self.subtractBackgroundAction = self.addStateAction(toolTipFalse=f'Subtract background for {self.name}.', iconFalse=self.makeCoreIcon('eraser.png'),
                                                        toolTipTrue=f'Ignore background for {self.name}.', iconTrue=self.makeCoreIcon('eraser.png'),
                                                        attr='subtractBackground', event=lambda: self.subtractBackgroundChanged())
            self.addAction(event=lambda: self.setBackground(), toolTip=f'Set current value as background for {self.name} based on last 5 s.', icon=self.makeCoreIcon('eraser--pencil.png'))
        self.estimateStorage()
        if self.inout == INOUT.IN:
            self.addAction(lambda: self.loadValues(None), f'Load {self.name} values only.', before=self.saveAction, icon=self.makeCoreIcon('table-import.png'))
        self.restoreOutputData()

    def getDefaultSettings(self):
        """ Define device specific settings that will be added to the general settings tab.
        Settings will be generated automatically if not found in the settings file.
        Overwrite and extend as needed."""
        defaultSettings = super().getDefaultSettings()
        defaultSettings[f'{self.name}/{self.INTERVAL} (measured)'] = parameterDict(value=0, internal=True,
        toolTip=f'Measured plot interval for {self.name} in ms.\n'+
                'If this deviates multiple times in a row, the number of display points will be reduced and eventually acquisition\n'+
                'will be stopped to ensure the application remains responsive.\n'+
                f'Go to advanced mode to see how many seconds {self.name} has been lagging.',
                                                                widgetType=Parameter.TYPE.INT, indicator=True, _min=0, _max=10000, attr='interval_measured')
        defaultSettings[f'{self.name}/Lagging'] = parameterDict(value=0, internal=True, indicator=True, advanced=True,
        toolTip='Shows for how many seconds the device has not been able to achieve the desired interval.\n'+
                'After 10 seconds the number of displayed data points will be reduced.\n'+
                'After 60 seconds the communication will be stopped to keep the application responsive.',
                                                                widgetType=Parameter.TYPE.INT, _min=0, attr='lagging_seconds')
        defaultSettings[f'{self.name}/{self.MAXSTORAGE}'] = parameterDict(value=50, widgetType=Parameter.TYPE.INT, _min=5, _max=500, event=lambda: self.estimateStorage(),
                                                          toolTip='Maximum amount of storage used to store history in MB. Updated on next restart to prevent accidental data loss!', attr='maxStorage')
        defaultSettings[f'{self.name}/{self.MAXDATAPOINTS}'] = parameterDict(value=500000, indicator=True, widgetType=Parameter.TYPE.INT, attr='maxDataPoints',
        toolTip='Maximum number of data points saved per channel, based on max storage.\n' +
        'If this is reached, older data will be thinned to allow to keep longer history.')
        defaultSettings[f'{self.name}/Logging'] = parameterDict(value=False, toolTip='Show warnings in console. Only use when debugging to keep console uncluttered.',
                                          widgetType=Parameter.TYPE.BOOL, attr='log')
        defaultSettings[f'{self.name}/Error count'] = parameterDict(value=0, toolTip='Communication errors within last 10 minutes.\n' +
                                                                   'Communication will be stopped if this reaches 10.\n' +
                                                                   'Will be reset after 10 minutes without errors or on initialization.',
                                          widgetType=Parameter.TYPE.INT, attr='errorCount', indicator=True, event=lambda: self.errorCountChanged())
        return defaultSettings

    def runTestParallel(self):
        """:meta private:"""
        if self.useBackgrounds:
            self.testControl(self.subtractBackgroundAction, not self.subtractBackgroundAction.state, 1)
        super().runTestParallel()

    def intervalChanged(self):
        """Extend to add code to be executed in case the :ref:`acquisition_interval` changes."""
        super().intervalChanged()
        self.estimateStorage()

    def subtractBackgroundChanged(self):
        if self.liveDisplayActive():
            self.liveDisplay.subtractBackgroundAction.state = self.subtractBackgroundAction.state
        self.plot(apply=True)

    def errorCountChanged(self):
        if self.errorCount != 0:
            self.errorCountTimer.start() # will reset in after interval unless another error happens before and restarts the timer

    def resetErrorCount(self):
        self.errorCount = 0

    def startAcquisition(self):
        """Starts device Acquisition.
        Default implementation works when using :class:`~esibd.core.DeviceController`."""
        self.appendData(nan=True) # prevent interpolation to old data
        if self.controller is None:
            if self.channels[0].controller is not None:
                for channel in self.channels:
                    if channel.enabled:
                        channel.controller.startAcquisition()
        else:
            self.controller.startAcquisition()

    def stopAcquisition(self):
        """Stops device acquisition. Communication stays initialized!
        Default implementation works when using :class:`~esibd.core.DeviceController`."""
        if self.controller is None:
            if self.channels[0].controller is not None:
                for channel in self.channels:
                    channel.controller.stopAcquisition()
        else:
            self.controller.stopAcquisition()

    def initialized(self):
        """Extend or overwrite to indicate when the device is initialized.
        Default implementation works when using :class:`~esibd.core.DeviceController`."""
        if self.controller is None:
            if self.channels[0].controller is None:
                return False
            else:
                return any([channel.controller.initialized for channel in self.channels])
        else:
            return self.controller.initialized

    def initializeCommunication(self):
        initialRecording = self.recording
        self.appendData(nan=True) # prevent interpolation to old data
        if self.controller is None:
            if self.channels[0].controller is not None:
                for channel in self.channels:
                    if channel.enabled:
                        channel.controller.initializeCommunication()
        else:
            self.controller.initializeCommunication()
        super().initializeCommunication()
        if initialRecording:
            self.startRecording()

    def closeCommunication(self):
        """Stops all communication.
        Make sure that final calls to device are send from main thread or use a delay
        so they are not send after connection has terminated!"""
        self.stopAcquisition() # stop acquisition before terminating communication
        if self.controller is None:
            if self.channels[0].controller is not None:
                for channel in self.channels:
                    channel.controller.closeCommunication()
        else:
            self.controller.closeCommunication()
        super().closeCommunication()

    def getSupportedFiles(self):
        if self.useDisplays:
            return self.previewFileTypes+self.staticDisplay.previewFileTypes+self.liveDisplay.previewFileTypes
        else:
            return self.previewFileTypes

    def setBackground(self):
        """Sets the background based on current channel values.
        Only used by output devices."""
        if self.useBackgrounds:
            for channel in self.getChannels(): # save present signal as background
                # use average of last 5 s if possible
                length = min(int(5000/self.interval), len(channel.getValues(subtractBackground=False)))
                values = channel.getValues(subtractBackground=False)[-length:]
                if not any([np.isnan(value) for value in values]):
                    channel.background = np.mean(values)
                elif not np.isnan(values[-1]):
                    channel.background = values[-1]
                else:
                    channel.background = np.nan

    def subtractBackgroundActive(self):
        return self.subtractBackgroundAction.state if self.useBackgrounds else False
        # independent of GUI
        # return self.useBackgrounds and qSet.value(f'{self.name}/subtractBackground', 'false', type=bool)

    def estimateStorage(self):
        numChannelsBackgrounds = len(self.channels) * 2 if self.useBackgrounds else len(self.channels)
        self.maxDataPoints = (self.maxStorage * 1024**2 - 8) / (4 * numChannelsBackgrounds)  # including time channel
        totalDays = self.interval / 1000 * self.maxDataPoints / 3600 / 24
        self.pluginManager.Settings.settings[f'{self.name}/{self.MAXDATAPOINTS}'].getWidget().setToolTip(
        f'Using an interval of {self.interval} ms and maximum storage of {self.maxStorage:d} MB allows for\n'+
        f'a history of {totalDays:.2f} days or {self.maxDataPoints} data points for {len(self.channels)} channels.\n'+
        'After this time, data thinning will allow to retain even older data, but at lower resolution.')

    def applyValues(self, apply=False):
        """Applies :class:`~esibd.core.Channel` values to physical devices. Only used by input :class:`devices<esibd.plugins.Device>`.

        :param apply: If false, only values that have changed since last apply will be updated, defaults to False
        :type apply: bool, optional
        """

    @synchronized()
    def exportOutputData(self, default=False):
        if default:
            _time = self.time.get()
            if _time.shape[0] == 0:
                return # no data to save
            file = Path(self.pluginManager.Settings.configPath) / self.confh5.strip('_')
        else:
            self.pluginManager.Settings.incrementMeasurementNumber()
            file = self.pluginManager.Settings.getMeasurementFileName(self.liveDisplay.previewFileTypes[0])
        with h5py.File(name=file, mode='w' if default else 'a', track_order=True) as h5File:
            self.hdfUpdateVersion(h5File)
            self.appendOutputData(h5File, default=default)
        self.print(f'Stored data in {file.name}')
        if default:
            self.exportConfiguration(file=file)
        else:
            self.pluginManager.DeviceManager.exportConfiguration(file=file) # save corresponding device settings in measurement file
            self.pluginManager.Explorer.populateTree()

    def appendOutputData(self, h5file, default=False):
        """Appends :class:`~esibd.plugins.Device` data to hdf file."""
        fullRange = True
        group = self.requireGroup(h5file, self.name) #, track_order=True
        _time = self.time.get()
        if not default and _time.shape[0] > 0 and len(self.liveDisplay.livePlotWidgets) > 0:
            # Only save currently visible data (specific regions of interest).
            # Otherwise history of last few days might be added to files, making it hard to find the region of interest.
            # Complete data can still be exported if needed by displaying entire history before exporting.
            # if default == True: save entire history to default file for restoring on next start
            t_min, t_max = self.liveDisplay.livePlotWidgets[0].getAxis('bottom').range
            i_min = np.argmin(np.abs(_time - t_min))
            i_max = np.argmin(np.abs(_time - t_max))
            fullRange = False
        input_group = self.requireGroup(group, INPUTCHANNELS)
        try:
            input_group.create_dataset(self.TIME, data=_time if fullRange else _time[i_min:i_max], dtype=np.float64, track_order=True) # need double precision to keep all decimal places
        except ValueError as e:
            self.print(f'Could not create data set. If the file already exists, make sure to increase the measurement number and try again. Original error: {e}', PRINT.ERROR)
            return
        output_group = self.requireGroup(group, OUTPUTCHANNELS)
        # avoid using getValues() function and use get() to make sure raw data, without background subtraction or unit correction etc. is saved in file
        for channel in self.getDataChannels():
            if channel.name in output_group:
                self.print(f'Ignoring duplicate channel {channel.name}', PRINT.WARNING)
                continue
            value_dataset = output_group.create_dataset(channel.name, data=channel.values.get() if fullRange else channel.values.get()[i_min:i_max], dtype='f')
            value_dataset.attrs[UNIT] = self.unit
            if self.useBackgrounds:
                # Note: If data format will be changed in future (ensuring backwards compatibility), consider saving single 2D data set with data and background instead. for now, no need
                background_dataset = output_group.create_dataset(channel.name + '_BG', data=channel.backgrounds.get() if fullRange else channel.backgrounds.get()[i_min:i_max], dtype='f')
                background_dataset.attrs[UNIT] = self.unit

    def restoreOutputData(self):
        """Restores data from internal restore file."""
        file = Path(self.pluginManager.Settings.configPath) / self.confh5.strip('_')
        if file.exists():
            self.print(f'Restoring data from {file.name}')
            with h5py.File(name=file, mode='r', track_order=True) as h5file:
                try:
                    if self.name not in h5file:
                        return
                    group = h5file[self.name]
                    if not (INPUTCHANNELS in group and OUTPUTCHANNELS in group):
                        return False
                    input_group = group[INPUTCHANNELS]
                    self.time = DynamicNp(initialData=input_group[self.TIME][:], max_size=self.maxDataPoints, dtype=np.float64)
                    output_group = group[OUTPUTCHANNELS]
                    for name, item in output_group.items():
                        channel = self.getChannelByName(name.strip('_BG'))
                        if channel is not None:
                            if name.endswith('_BG'):
                                channel.backgrounds = DynamicNp(initialData=item[:], max_size=self.maxDataPoints)
                            else:
                                channel.values = DynamicNp(initialData=item[:], max_size=self.maxDataPoints)
                except RuntimeError as e:
                    self.print(f'Could not restore data from {file.name}. You can try to fix and then restart. If you record new data it will be overwritten! Error {e}', flag=PRINT.ERROR)

    def close(self):
        self.closeCommunication()
        self.exportOutputData(default=True)
        super().close()

    def loadData(self, file, _show=True):
        """:meta private:"""
        if self.liveDisplay.supportsFile(file) or self.staticDisplay.supportsFile(file):
            self.staticDisplay.loadData(file, _show)
        else:
            if self.inout == INOUT.IN:
                self.pluginManager.Text.setText('Load values using right click or import channels from file explicitly.', False)
            else:
                self.pluginManager.Text.setText('Import channels from file explicitly.', False)

    def updateValues(self, N=2, apply=False):
        """Updates channel values based on equations.
        This minimal implementation will not give a warning about circular definitions.
        It will also fail if expressions are nested on more than N levels but N can be increased as needed.
        N=2 should however be sufficient for day to day work.
        More complex algorithms should only be implemented if they are required to solve a practical problem."""
        if self.updating or self.pluginManager.closing:
            return
        self.updating = True # prevent recursive call caused by changing values from here
        channels = self.pluginManager.DeviceManager.channels(inout=INOUT.IN) if self.inout == INOUT.IN else self.pluginManager.DeviceManager.channels(inout=INOUT.BOTH)
        channelNames = [channel.name for channel in channels if channel.name != '']
        channelNames.sort(reverse=True, key=len) # avoid replacing a subset of a longer name with a matching shorter name of another channel
        for _ in range(N): # go through parsing N times, in case the dependencies are not ordered
            for channel in [channel for channel in self.channels if not channel.active and channel.equation != '']: # ignore if no equation defined
                equ = channel.equation
                error = False
                for name in channelNames:
                    if name in equ:
                        channel_equ = next((channel for channel in channels if channel.name == name), None)
                        if channel_equ is None:
                            self.print(f'Could not find channel {name} in equation of channel {channel.name}.', PRINT.WARNING)
                            error = True
                        else:
                            equ = equ.replace(channel_equ.name, f'{channel_equ.value-channel_equ.background if channel.useBackgrounds else channel_equ.value}')
                if error:
                    self.print(f'Could not resolve equation of channel {channel.name}: {channel.equation}', PRINT.WARNING)
                else:
                    result = aeval(equ) #  or 0 # evaluate # does catch exception internally so we cannot except them here
                    if result is not None:
                        channel.value = result
                    else:
                        self.print(f'Could not evaluate equation of {channel.name}: {channel.equation}')
                        channel.value = np.nan
        if self.inout == INOUT.IN:
            self.applyValues(apply)
        self.updating = False

    def appendData(self, nan=False):
        if self.initialized() or nan:
            self.updateValues() # this makes equations work for output devices.
            # Equations for output devices are evaluated only when plotting. Calling them for every value change event would cause a massive computational load.
            for channel in self.getChannels():
                channel.appendValue(lenT=self.time.size, nan=nan) # add time after values to make sure value arrays stay aligned with time array
            self.time.add(time.time()) # add time in seconds
            if self.liveDisplayActive():
                self.signalComm.plotSignal.emit()
            else:
                self.measureInterval()

    def measureInterval(self):
        # free up resources by limiting data points or stopping acquisition if UI becomes unresponsive
        # * when GUI thread becomes unresponsive, this function is sometimes delayed and sometimes too fast.
        self.interval_measured = int((time.time()*1000-self.lastIntervalTime)) if self.lastIntervalTime is not None else self.interval
        self.interval_tolerance = self.interval/5 # larger margin for error if interval is large.
        self.lag_limit = max(10, int(10000/self.interval)) # 10 seconds, independent of interval (at least 10 steps)
        if abs(self.interval_measured - self.interval) < self.interval_tolerance:
            self.lagging = max(0, self.lagging-1) # decrease gradually, do not reset completely if a single iteration is on time
        elif self.interval_measured > self.interval + self.interval_tolerance: # increase self.lagging and react if interval is longer than expected
            if self.lagging < self.lag_limit:
                self.lagging += 1
            elif self.lagging < 6*self.lag_limit: # lagging 10 s in a row -> reduce data points
                if self.lagging == self.lag_limit:
                    self.pluginManager.DeviceManager.limit_display_size = True
                    if self.pluginManager.DeviceManager.max_display_size > 1000:
                        self.pluginManager.DeviceManager.max_display_size = 1000 # keep if already smaller
                        self.print(f'Slow GUI detected, limiting number of displayed data points to {self.pluginManager.DeviceManager.max_display_size} per channel. Communication will be stopped in 50 s unless GUI becomes responsive again.', flag=PRINT.WARNING)
                    else:
                        self.print('Slow GUI detected. Communication will be stopped in 50 s unless GUI becomes responsive again.', flag=PRINT.WARNING)
                elif self.lagging%self.lag_limit == 0:
                    self.print(f'Slow GUI detected. Consider decreasing device interval, displayed channels, and other GUI intensive functions. Communication will be stopped in {10*(6-self.lagging/self.lag_limit)} s unless GUI becomes responsive again.', flag=PRINT.WARNING)
                self.lagging += 1
            else: # lagging 60 s in a row -> stop acquisition
                if self.lagging == 6*self.lag_limit:
                    self.print('Slow GUI detected, stopped acquisition. Reduce number of active channels or acquisition interval.'+
                               ' Identify which plugin(s) is(are) most resource intensive and contact plugin author.', flag=PRINT.WARNING)
                    # self.pluginManager.DeviceManager.closeCommunication(message='Stopping communication due to unresponsive user interface.')
                    self.closeCommunication()
        else:
            # keep self.lagging unchanged. One long interval can be followed by many short intervals when GUI is catching up with events.
            # This might happen due to another part of the program blocking the GUI temporarily or after decreasing max_display_size.
            # This should not trigger a reaction but also should not reset self.lagging as plotting is not yet stable.
            pass
        self.lagging_seconds = int(self.lagging*self.interval/1000)
        self.lastIntervalTime = time.time()*1000

    def toggleRecording(self, on=None, manual=False):
        """Toggle recoding of data in :class:`~esibd.plugins.LiveDisplay`."""
        if (on is not None and not on) or (on is None and self.recording):
            # Turn off if not already off
            if self.recording:
                self.recording = False
                self.pluginManager.DeviceManager.stopScans()
        else: # (on is not None and on) (on is None and not self.recording):
            # Turn on if not already on
            if not self.recording:
                self.clearPlot()
                if not self.initialized():
                    self.initializeCommunication() # will start recording when initialization is complete
                else:
                    self.startAcquisition()
                self.startRecording()

    def clearHistory(self):
        self.clearPlot()
        for channel in self.getChannels():
            channel.clearHistory(max_size=self.maxDataPoints)
        self.time = DynamicNp(max_size=self.maxDataPoints, dtype=np.float64)

    def runDataThread(self, recording):
        """Regularly triggers reading and appending of data.
        This uses the current value of :class:`channels<esibd.core.Channel>` which is updated
        independently by the corresponding :class:`~esibd.core.DeviceController`."""
        while recording():
            # time.sleep precision in low ms range on windows -> will usually be a few ms late
            # e.g. 0.1 will not give a true 10 Hz repetition rate
            # if that becomes important and decreasing the interval to compensate for delay is not sufficient a better method is required
            interval_measured = int((time.time()*1000-self.lastIntervalTime)) if self.lastIntervalTime is not None else self.interval
            interval_tolerance = max(100, self.interval/5)
            if interval_measured >= self.interval - interval_tolerance: # do only emit when at least self.interval has expired to prevent unresponsive application due to queue of multiple emissions
                self.signalComm.appendDataSignal.emit()
            else:
                self.print('Skipping appending data as previous request is still being processed.', flag=PRINT.DEBUG)
                self.lastIntervalTime = time.time()*1000 # reset reference for next interval
            time.sleep(self.interval/1000) # in seconds # wait at end to avoid emitting signal after recording set to False

    def duplicateChannel(self):
        if self.modifyChannel() is None:
            return
        if self.initialized():
            self.print(f"Stop communication for {self.name} to duplicate selected channel.", flag=PRINT.WARNING)
            return
        super().duplicateChannel()

    def deleteChannel(self):
        if self.modifyChannel() is None:
            return
        if self.initialized():
            self.print(f"Stop communication for {self.name} to delete selected channel.", flag=PRINT.WARNING)
            return
        super().deleteChannel()

    def moveChannel(self, up):
        if self.modifyChannel() is None:
            return
        if self.initialized():
            self.print(f"Stop communication for {self.name} to move selected channel.", flag=PRINT.WARNING)
            return
        super().moveChannel(up)

    def getUnit(self):
        """Overwrite if you want to change units dynamically."""
        return self.unit

class Scan(Plugin):
    """:class:`Scans<esibd.plugins.Scan>` are all sort of measurements that record any number of outputs as a
    function of any number of inputs. The main interface consists of a list of
    scan settings. Each scan comes with a tailored display
    optimized for its specific data format. :ref:`sec:scan_settings` can be imported
    and exported from the scan toolbar, though in most cases it will be
    sufficient to import them from the context menu of a previously saved
    scan file in the :ref:`sec:explorer`. When all settings are defined and all relevant channels are
    communicating the scan can be started. A scan can be stopped at any
    time. At the end of a scan the corresponding file will be saved to the
    :ref:`session path<sec:session_settings>`. The filename is displayed inside the corresponding graph to
    allow to find the file later based on exported figures. Scan files are
    saved in the widely used HDF5 file format that allows to keep data and
    metadata together in a structured binary file. External viewers, such as
    HDFView, or minimal python scripts based on the h5py package can be used
    if files need to be accessed externally. Use the
    context menu of a scan file to create a template plot file using h5py
    and adjust it to your needs."""
    documentation = """Scans are all sort of measurements that record any number of outputs as a
    function of any number of inputs. The main interface consists of a list of
    scan settings. Each scan comes with a tailored display
    optimized for its specific data format. Scan settings can be imported
    and exported from the scan toolbar, though in most cases it will be
    sufficient to import them from the context menu of a previously saved
    scan file in the Explorer. When all settings are defined and all relevant channels are
    communicating the scan can be started. A scan can be stopped at any
    time. At the end of a scan the corresponding file will be saved to the
    session path. The filename is displayed inside the corresponding graph to
    allow to find the file later based on exported figures. Scan files are
    saved in the widely used HDF5 file format that allows to keep data and
    metadata together in a structured binary file. External viewers, such as
    HDFView, or minimal python scripts based on the h5py package can be used
    if files need to be accessed externally. Use the
    context menu of a scan file to create a template plot file using h5py
    and adjust it to your needs."""

    pluginType = PluginManager.TYPE.SCAN
    useAdvancedOptions = True

    PARAMETER   = 'Parameter'
    VERSION     = 'Version'
    VALUE       = 'Value'
    UNIT        = UNIT
    NOTES       = 'Notes'
    DISPLAY     = 'Display'
    LEFTRIGHT   = 'Left-Right'
    UPDOWN      = 'Up-Down'
    WAITLONG    = 'Wait long'
    LARGESTEP   = 'Large step'
    WAIT        = 'Wait'
    AVERAGE     = 'Average'
    SCANTIME     = 'Scan time'
    INTERVAL    = 'Interval'
    FROM        = 'From'
    TO          = 'To'
    STEP        = 'Step'
    CHANNEL     = 'Channel'
    SCAN        = 'Scan'
    INPUTCHANNELS = INPUTCHANNELS
    OUTPUTCHANNELS = OUTPUTCHANNELS
    MYBLUE='#1f77b4'
    MYGREEN='#00aa00'
    MYRED='#d62728'
    getChannelByName : callable
    """Reference to :meth:`~esibd.plugins.DeviceManager.getChannelByName`."""
    file : Path
    """The scan file. Either existing file or file to be created when scan finishes."""
    useDisplayChannel : bool
    """If True, a combobox will be created to allow to select for which
       channel data should be displayed."""
    measurementsPerStep : int
    """Number of measurements per step based on the average time and acquisition rate."""
    display : Plugin
    """The internal plugin used to display scan data."""
    runThread : Thread
    """Parallel thread that updates the scan channel(s) and reads out the display channel(s)."""
    inputs : List[EsibdCore.MetaChannel]
    """List of input :class:`meta channels<esibd.core.MetaChannel>`."""
    outputs : List[EsibdCore.ScanChannel]
    """List of output :class:`meta channels<esibd.core.ScanChannel>`."""
    channels : List[EsibdCore.ScanChannel]
    """List of output :class:`meta channels<esibd.core.ScanChannel>`."""
    useDisplayParameter = False
    """Use display parameter to control which scan channels are displayed."""

    class SignalCommunicate(Plugin.SignalCommunicate):
        """Object that bundles pyqtSignals."""
        scanUpdateSignal        = pyqtSignal(bool)
        """Signal that triggers update of the figure and, if True is passed, saving of data."""
        updateRecordingSignal   = pyqtSignal(bool)
        """Signal that allows to stop recording from an external thread."""
        saveScanCompleteSignal  = pyqtSignal()
        """Signal that confirms that scan data has been saved and a new scan can be started."""

    ScanChannel = ScanChannel # allows children to extend this

    class TreeSplitter(QSplitter):

        def __init__(self, scan, **kwargs):
            self.scan = scan
            super().__init__(**kwargs)

        def resizeEvent(self, event):
            super().resizeEvent(event)  # Ensure default behavior
            # make sure settingsTree takes up as much space as possible but there is no gap between settingsTree and channelTree
            self.setSizes([self.scan.settingsTree.sizeHint().height(), self.height()-self.scan.settingsTree.sizeHint().height()])

    class Display(Plugin):
        """Display for base scan. Extend as needed.

        :meta private:
        """
        pluginType=PluginManager.TYPE.DISPLAY

        def __init__(self, scan, **kwargs):
            self.scan = scan
            self.name = f'{self.scan.name} Display'
            self.plot = self.scan.plot
            super().__init__(**kwargs)

        def initGUI(self):
            """:meta private:"""
            super().initGUI()
            self.mouseMoving = False
            self.mouseActive = False
            self.initFig() # make sure that channel dependent parts of initFig are only called after channels are initialized.

        def initFig(self):
            # self.print('initFig', flag=PRINT.DEBUG)
            self.provideFig()

        def provideDock(self):
            """:meta private:"""
            if super().provideDock():
                self.finalizeInit()
                self.afterFinalizeInit()

        def finalizeInit(self, aboutFunc=None):
            """:meta private:"""
            super().finalizeInit(aboutFunc)
            self.copyAction = self.addAction(lambda: self.copyClipboard(), f'{self.name} to clipboard.', self.imageClipboardIcon, before=self.aboutAction)
            if self.scan.useDisplayChannel:
                self.loading = True
                self.scan.loading = True
                self.displayComboBox = EsibdCore.CompactComboBox()
                self.displayComboBox.setMaximumWidth(100)
                self.displayComboBox.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed)
                self.displayComboBox.currentIndexChanged.connect(self.scan.updateDisplayChannel)
                self.titleBar.insertWidget(self.copyAction, self.displayComboBox)
                self.updateTheme()
                self.loading = False
                self.scan.loading = False

        def getIcon(self, **kwargs):
            return self.scan.getIcon(**kwargs)

        def runTestParallel(self):
            """:meta private:"""
            if self.initializedDock:
                self.testControl(self.copyAction, True, .5)
            # super().runTestParallel() # handled by scan

        def mouseEvent(self, event):  # use mouse to move beam # use ctrl key to avoid this while zooming
            """Handles dragging beam in 2D scan or setting retarding grid potential in energy scan"""
            if not self.mouseActive:
                return
            if self.mouseMoving and not event.name == 'button_release_event': # dont trigger events until last one has been processed
                return
            else:
                self.mouseMoving = True
                if event.button == MouseButton.LEFT and kb.is_pressed('ctrl') and event.xdata is not None:
                    for i, _input in enumerate(self.scan.inputs):
                        if _input.sourceChannel is not None:
                            _input.value = event.xdata if i == 0 else event.ydata # 3D not supported
                        else:
                            self.print(f'Could not find channel {self.scan.inputs[i].name}.')
                    if self.axes[-1].cursor is not None:
                        self.axes[-1].cursor.ondrag(event)
                self.mouseMoving = False

        def closeGUI(self):
            """:meta private:"""
            if self.scan.finished:
                return super().closeGUI()
            else:
                self.print('Cannot close while scan is recording.')

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.getChannelByName = self.pluginManager.DeviceManager.getChannelByName
        self._finished  = True
        self.file = None
        self.configINI = f'{self.name}.ini'
        self.previewFileTypes = [self.configINI, f'{self.name.lower()}.h5']
        self.useDisplayChannel = False
        self.measurementsPerStep = 0
        self.display = None
        self.runThread = None
        self.saveThread = None
        self.settingsTree = None
        self.channelTree = None
        self.initializing = False
        self.channels = []
        self.signalComm.scanUpdateSignal.connect(self.scanUpdate)
        self.signalComm.updateRecordingSignal.connect(self.updateRecording)
        self.signalComm.saveScanCompleteSignal.connect(self.saveScanComplete)
        self.init()

    def initGUI(self):
        """:meta private:"""
        self.loading = True
        super().initGUI()
        self.treeSplitter = self.TreeSplitter(scan=self, orientation=Qt.Orientation.Vertical)
        self.treeSplitter.setStyleSheet('QSplitter::handle{width:0px; height:0px;}')
        self.settingsTree = TreeWidget()
        self.settingsTree.setMinimumWidth(200)
        self.settingsTree.setHeaderLabels([self.PARAMETER, self.VALUE])
        self.settingsTree.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.settingsTree.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        # size to content prevents manual resize
        self.settingsTree.header().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.settingsLayout = QHBoxLayout()
        self.settingsLayout.setContentsMargins(0, 0, 0, 0)
        self.settingsLayout.setSpacing(0)
        self.settingsLayout.addWidget(self.settingsTree, alignment=Qt.AlignmentFlag.AlignTop)
        widget = QWidget()
        # widget.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Preferred)
        # widget.sizeHint = self.settingsTree.sizeHint
        widget.setLayout(self.settingsLayout)
        self.treeSplitter.addWidget(widget)
        self.treeSplitter.setCollapsible(0, False)
        self.channelTree = TreeWidget() #minimizeHeight=True)
        self.channelTree.header().setStretchLastSection(False)
        self.channelTree.header().setMinimumSectionSize(0)
        self.channelTree.header().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.channelTree.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.channelTree.setRootIsDecorated(False)
        # self.channelLayout = QHBoxLayout()
        # self.channelLayout.setContentsMargins(0, 0, 0, 0)
        # self.channelLayout.addWidget(self.channelTree, stretch=1, alignment=Qt.AlignmentFlag.AlignTop)
        # widget = QWidget()
        # widget.setLayout(self.channelLayout)
        # widget.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.MinimumExpanding)
        # widget.sizeHint = self.channelTree.sizeHint
        # self.treeSplitter.addWidget(widget)
        self.treeSplitter.addWidget(self.channelTree)
        self.treeSplitter.setCollapsible(1, False)
        # self.treeSpacer = QWidget()
        # self.treeSpacer.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        # self.treeSplitter.addWidget(self.treeSpacer)
        self.addContentWidget(self.treeSplitter)
        self.settingsMgr = SettingsManager(parentPlugin=self, pluginManager=self.pluginManager, name=f'{self.name} Settings', tree=self.settingsTree,
                                        defaultFile=self.pluginManager.Settings.configPath / self.configINI)
        self.settingsMgr.addDefaultSettings(plugin=self)
        self.settingsMgr.init()
        self.expandTree(self.settingsMgr.tree)
        self.notes = '' # should always have current notes or no notes
        self.addAction(lambda: self.loadSettings(file=None), f'Load {self.name} settings.', icon=self.makeCoreIcon('blue-folder-import.png'))
        self.addAction(lambda: self.saveSettings(file=None), f'Export {self.name} settings.', icon=self.makeCoreIcon('blue-folder-export.png'))
        self.recordingAction = self.addStateAction(lambda: self.toggleRecording(), f'Start {self.name} scan.', self.makeCoreIcon('play.png'), 'Stop.', self.makeCoreIcon('stop.png'))
        self.estimateScanTime()
        self.addOutputChannels()
        self.loading = False

    def finalizeInit(self, aboutFunc=None):
        super().finalizeInit(aboutFunc)
        self.statusAction = self.pluginManager.DeviceManager.addAction(event=lambda: self.statusActionEvent(), toolTip=f'{self.name} is running. Go to {self.name}.', icon=self.getIcon(),
                                                                 before=self.pluginManager.DeviceManager.aboutAction)
        self.statusAction.setVisible(False)

    def statusActionEvent(self):
        self.raiseDock(True)
        self.display.raiseDock(True)

    def afterFinalizeInit(self):
        super().afterFinalizeInit()
        self.connectAllSources()

    def connectAllSources(self):
        # self.print('connectAllSources', flag=PRINT.DEBUG)
        # for input in self.inputs: # are connected on creation
        #     input.connectSource()
        for channel in self.channels:
            channel.connectSource()

    def init(self):
        for channel in self.channels:
            channel.onDelete()
        if self.channelTree is not None:
            self.channelTree.clear()
        self.inputs, self.outputs, self.channels = [], [], []

    def runTestParallel(self):
        """:meta private:"""
        # * testing the scan itself is done by DeviceManager
        if self.initializedDock:
            if self.display is not None:
                self.display.raiseDock(True)
                # self.testControl(self.display.videoRecorderAction, True) # done by device manager
                self.display.runTestParallel()
                # self.testControl(self.display.videoRecorderAction, False)
        super().runTestParallel()

    @property
    def recording(self):
        """True if currently recording.
        Set to False to stop recording and save available data."""
        return self.recordingAction.state
    @recording.setter
    def recording(self, recording):
        # make sure to only call from main thread as GUI is affected!
        self.recordingAction.state = recording
        self.statusAction.setVisible(recording)

    @property
    def finished(self):
        """True before and after scanning. Even when :attr:`~esibd.plugins.Scan.recording` is set to False
        it will take time for the scan to complete and be ready to be started again."""
        return self._finished
    @finished.setter
    def finished(self, finished):
        self._finished = finished
        # disable inputs while scanning
        for setting in [self.FROM, self.TO, self.STEP, self.CHANNEL]:
            if setting in self.settingsMgr.settings:
                self.settingsMgr.settings[setting].setEnabled(finished)

    def updateFile(self):
        self.pluginManager.Settings.incrementMeasurementNumber()
        self.file = self.pluginManager.Settings.getMeasurementFileName(f'_{self.name.lower()}.h5')
        self.display.file = self.file # for direct access of MZCalculator or similar addons that are not aware of the scan itself

    def updateDisplayChannel(self):
        if self.display is not None and self.useDisplayChannel and (not self.pluginManager.loading and not self.loading
                                                                    and not self.settingsMgr.loading and not self.recording):
            self.plot(update=False, done=True)

    def updateDisplayDefault(self):
        if self.display is not None and self.useDisplayChannel:
            self.loading = True
            i = self.display.displayComboBox.findText(self.displayDefault)
            if i == -1:
                self.display.displayComboBox.setCurrentIndex(0)
            else:
                self.display.displayComboBox.setCurrentIndex(i)
            self.loading = False
            self.updateDisplayChannel()
        if self.finished and not self.recording and not self.loading:
            self.init()
            self.addOutputChannels()

    def populateDisplayChannel(self):
        if self.display is not None and self.useDisplayChannel:
            self.loading = True
            self.display.displayComboBox.clear()
            for output in self.outputs: # use channels form current acquisition or from file.
                self.display.displayComboBox.insertItem(self.display.displayComboBox.count(), output.name)
            self.loading = False
            self.updateDisplayDefault()

    def loadSettings(self, file=None, default=False):
        self.settingsMgr.loadSettings(file=file, default=default)
        self.expandTree(self.settingsMgr.tree)
        self.updateDisplayChannel()
        self.estimateScanTime()
        # self.settingsTree.fitAllItems()

    def saveSettings(self, file=None, default=False):
        self.settingsMgr.saveSettings(file=file, default=default)

    def getDefaultSettings(self):
        """:meta private:"""
        # ATTENTION: Changing setting names will cause backwards incompatibility unless handled explicitly!
        ds = {}
        ds[self.NOTES]  = parameterDict(value='', toolTip='Add specific notes to current scan. Will be reset after scan is saved.', widgetType=Parameter.TYPE.TEXT,
                                        attr='notes')
        ds[self.DISPLAY] = parameterDict(value='RT_Front-Plate', toolTip='Default output channel used when scanning. Other channels defined here will be recorded as well.',
                                         items='RT_Front-Plate, RT_Detector, RT_Sample-Center, RT_Sample-End, LALB-Aperture',
                                         widgetType=Parameter.TYPE.COMBO, attr='displayDefault', event=lambda: self.updateDisplayDefault())
        # * alternatively the wait time could be determined proportional to the step.
        # While this would be technically cleaner and more time efficient,
        # the present implementation is easier to understand and should work well as long as the step sizes do not change too often
        ds[self.WAIT]         = parameterDict(value=500, toolTip='Wait time between small steps in ms.', _min=10, event=lambda: self.estimateScanTime(),
                                                                        widgetType=Parameter.TYPE.INT, attr='wait')
        ds[self.WAITLONG]     = parameterDict(value=2000, toolTip=f'Wait time between steps larger than {self.LARGESTEP} in ms.', _min=10,
                                                                        widgetType=Parameter.TYPE.INT, attr='waitLong', event=lambda: self.estimateScanTime())
        ds[self.LARGESTEP]    = parameterDict(value=2, toolTip='Threshold step size to use longer wait time.', event=lambda: self.estimateScanTime(),
                                                                        widgetType=Parameter.TYPE.FLOAT, attr='largestep')
        ds[self.AVERAGE]      = parameterDict(value=1000, toolTip='Average time in ms.', widgetType=Parameter.TYPE.INT, attr='average', event=lambda: self.estimateScanTime())
        ds[self.SCANTIME]     = parameterDict(value='n/a', toolTip='Estimated scan time.', widgetType=Parameter.TYPE.LABEL, attr='scantime', internal=True, indicator=True)
        return ds

    def getOutputIndex(self):
        """Gets the index of the output channel corresponding to the currently selected display channel. See :attr:`~esibd.plugins.Scan.useDisplayChannel`.
        """
        if self.useDisplayChannel:
            try:
                if self.display.initializedDock:
                    return next((i for i, output in enumerate(self.outputs) if output.name == self.display.displayComboBox.currentText()), 0)
                else:
                    return next((i for i, output in enumerate(self.outputs) if output.name == self.displayDefault), 0)
            except ValueError:
                return 0
        return 0

    def initScan(self):
        """Initializes all data and metadata.
        Returns True if initialization successful and scan is ready to start.
        Will likely need to be adapted for custom scans."""
        self.initializing = True
        initializedOutputs = 0
        for name in self.settingsMgr.settings[self.DISPLAY].items:
            channel = self.getChannelByName(name, inout=INOUT.OUT)
            if channel is None:
                channel = self.getChannelByName(name, inout=INOUT.IN)
            if channel is None:
                self.print(f'Could not find channel {name}.', PRINT.WARNING)
            elif not channel.getDevice().initialized():
                self.print(f'{channel.getDevice().name} is not initialized.', PRINT.WARNING)
            elif not channel.acquiring and not channel.getDevice().recording:
                self.print(f'{channel.name} is not acquiring.', PRINT.WARNING)
            else:
                initializedOutputs += 1
        self.addOutputChannels()
        self.initializing = False
        if initializedOutputs > 0:
            self.measurementsPerStep = max(int((self.average/self.outputs[0].getDevice().interval))-1, 1)
            self.toggleDisplay(True)
            self.updateFile()
            self.populateDisplayChannel()
            return True
        else:
            self.print('No initialized output channel found.', PRINT.WARNING)
            return False

    def addOutputChannels(self):
        self.print('addOutputChannels', flag=PRINT.DEBUG)
        if len(self.inputs) == 0:
            recordingData = None
        elif len(self.inputs) == 1: # 1D scan
            recordingData = np.zeros(len(self.inputs[0].getRecordingData())) # cant reuse same array for all outputs as they would refer to same instance.
        else: # 2D scan, higher dimensions not jet supported
            lengths = [len(input.getRecordingData()) for input in self.inputs]
            recordingData = np.zeros(np.prod(lengths)).reshape(*lengths).transpose()
            # note np.zeros works better than np.full(len, np.nan) as some plots give unexpected results when given np.nan
        if self.DISPLAY in self.getDefaultSettings():
            for name in self.settingsMgr.settings[self.DISPLAY].items:
                self.addOutputChannel(name=name, recordingData=recordingData.copy() if recordingData is not None else None)
            self.channelTree.setHeaderLabels([(name.title() if dict[Parameter.HEADER] is None else dict[Parameter.HEADER])
                                                    for name, dict in self.channels[0].getSortedDefaultChannel().items()])
            self.toggleAdvanced(False)
        else:
            self.channelTree.hide()

    def addOutputChannel(self, name, unit='', recordingData=None, initialValue=None, recordingBackground=None):
        channel = self.ScanChannel(device=self, tree=self.channelTree)
        if recordingData is not None:
            channel.recordingData = recordingData
        if initialValue is not None:
            channel.initialValue = initialValue
        if recordingBackground is not None:
            channel.recordingBackground = recordingBackground
        self.channelTree.addTopLevelItem(channel) # has to be added before populating
        channel.initGUI(item={Parameter.NAME : name, ScanChannel.UNIT : unit})
        if not self.loading:
            channel.connectSource()
        self.channels.append(channel)
        if (self.loading and channel.recordingData is not None) or (channel.sourceChannel is not None and (channel.acquiring or channel.getDevice().recording)):
            # virtual channels will not necessarily be acquiring but they will be populated if their device is recording
            self.outputs.append(channel)
        return channel

    def addInputChannel(self, name, _from, to, step):
        """Converting channel to generic input data. Returns True if channel is valid for scanning."""
        channel = self.getChannelByName(name, inout=INOUT.IN)
        if channel is None:
            self.print(f'No channel found with name {name}.', PRINT.WARNING)
            return False
        else:
            if _from == to:
                self.print('Limits are equal.', PRINT.WARNING)
                return False
            elif channel.min > min(_from, to) or channel.max < max(_from, to):
                self.print(f'Limits are larger than allowed for {name}.', PRINT.WARNING)
                return False
            elif not channel.getDevice().initialized():
                self.print(f'{channel.getDevice().name} is not initialized.', PRINT.WARNING)
                return False
            recordingData = self.getSteps(_from, to, step)
            if len(recordingData) < 3:
                self.print('Not enough steps.', PRINT.WARNING)
                return False
            self.inputs.append(MetaChannel(parentPlugin=self, name=name, recordingData=recordingData, inout=INOUT.IN))
            return True

    def getSteps(self, _from, to, step):
        """Returns steps based on _from, to, and step parameters."""
        if _from == to:
            self.print('Limits are equal.', PRINT.WARNING)
            return None
        else:
            return np.arange(_from, to+step*np.sign(to-_from), step*np.sign(to-_from))

    def getData(self, i, inout):
        """Gets the data of a scan channel based on index and type.

        :param i: Index of channel.
        :type i: int
        :param inout: Type of channel.
        :type inout: :attr:`~esibd.const.INOUT`
        :return: The requested data.
        :rtype: numpy.array
        """
        return self.inputs[i].getRecordingData() if inout == INOUT.IN else self.outputs[i].getRecordingData()

    def toggleAdvanced(self, advanced=None):
        # self.print('toggleAdvanced', flag=PRINT.DEBUG)
        if advanced is not None:
            self.advancedAction.state = advanced
        if len(self.channels) > 0:
            for i, item in enumerate(self.channels[0].getSortedDefaultChannel().values()):
                if item[Parameter.ADVANCED]:
                    self.channelTree.setColumnHidden(i, not self.advancedAction.state)

    def estimateScanTime(self):
        """Estimates scan time. Will likely need to be adapted for custom scans."""
        # overwrite with scan specific estimation if applicable
        if hasattr(self, '_from'):
            # Simple time estimate for scan with single input channel.
            steps = self.getSteps(self._from, self.to, self.step)
            seconds = 0 # estimate scan time
            for i in range(len(steps)): # pylint: disable = consider-using-enumerate
                waitLong = False
                if not waitLong and abs(steps[i-1]-steps[i]) > self.largestep:
                    waitLong=True
                seconds += (self.waitLong if waitLong else self.wait) + self.average
            seconds = round((seconds)/1000)
            self.scantime = f'{seconds//60:02d}:{seconds%60:02d}'
        else:
            self.scantime = 'n/a'

    def saveData(self, file):
        """Writes generic scan data to hdf file."""
        with h5py.File(file, 'a', track_order=True) as h5File:
            # avoid using getValues() function and use get() to make sure raw data, without background subtraction or unit correction etc. is saved in file
            top_group = self.requireGroup(h5File, self.name) #, track_order=True
            input_group = self.requireGroup(top_group, self.INPUTCHANNELS)
            for j, _input in enumerate(self.inputs):
                try:
                    dataset = input_group.create_dataset(name=_input.name, data=self.getData(j, INOUT.IN), track_order=True)
                    dataset.attrs[self.UNIT] = self.inputs[j].unit
                except ValueError as e:
                    self.print(f'Cannot create dataset for channel {_input.name}: {e}', PRINT.ERROR)

            output_group = self.requireGroup(top_group, self.OUTPUTCHANNELS)
            for j, output in enumerate(self.outputs):
                if output.name in output_group:
                    self.print(f'Ignoring duplicate channel {output.name}', PRINT.WARNING)
                    continue
                try:
                    dataset = output_group.create_dataset(name=output.name, data=self.getData(j, INOUT.OUT), track_order=True)
                    dataset.attrs[self.UNIT] = self.outputs[j].unit
                except ValueError as e:
                    self.print(f'Cannot create dataset for channel {output.name}: {e}', PRINT.ERROR)

    def loadData(self, file, _show=True):
        """:meta private:"""
        if file.name.endswith(self.configINI):
            return # will be handled by Text plugin
        else:
            if self.finished:
                self.toggleDisplay(True)
                self.file = file
                self.display.file = file # for direct access of MZCalculator or similar addons that are not aware of the scan itself
                self.loading = True
                self.init()
                self.loadDataInternal()
                self.connectAllSources()
                if self.useDisplayChannel:
                    self.populateDisplayChannel() # select default scan channel if available
                self.loading = False
                self.plot(update=False, done=True) # self.populateDisplayChannel() does not trigger plot while loading
                self.display.raiseDock(_show)
            else:
                self.print('Cannot open file while scanning.', PRINT.WARNING)

    def loadDataInternal(self):
        """Loads data from scan file. Data is stored in scan-neutral format of input and output channels.
        Extend to provide support for previous file formats."""
        with h5py.File(self.file, 'r') as h5file:
            group = h5file[self.name]
            input_group = group[self.INPUTCHANNELS]
            for name, data in input_group.items():
                self.inputs.append(MetaChannel(parentPlugin=self, name=name, recordingData=data[:], unit=data.attrs[self.UNIT]))
            output_group = group[self.OUTPUTCHANNELS]
            for name, data in output_group.items():
                self.addOutputChannel(name=name, unit=data.attrs[self.UNIT], recordingData=data[:])

    def generatePythonPlotCode(self):
        """Saves minimal code to create a plot which can be customized by the user."""
        with open(self.pluginManager.Explorer.activeFileFullPath.with_suffix('.py'), 'w', encoding=UTF8) as plotFile:
            plotFile.write(self.pythonLoadCode() + self.pythonPlotCode())

    def pythonLoadCode(self):
        return f"""import h5py
import numpy as np
import matplotlib.pyplot as plt
inputs, outputs = [], []
class MetaChannel():
    def __init__(self, name, recordingData, initialValue=None, recordingBackground=None, unit=''):
        self.name = name
        self.recordingData = recordingData
        self.initialValue = initialValue
        self.recordingBackground = recordingBackground
        self.unit = unit

    @property
    def logY(self):
        if self.unit in ['mbar', 'Pa']:
            return True
        else:
            return False

with h5py.File('{self.pluginManager.Explorer.activeFileFullPath.as_posix()}','r') as h5file:
    group = h5file['{self.name}']

    input_group = group['Input Channels']
    for name, data in input_group.items():
        inputs.append(MetaChannel(name=name, recordingData=data[:], unit=data.attrs['Unit']))
    output_group = group['Output Channels']
    for name, data in output_group.items():
        outputs.append(MetaChannel(name=name, recordingData=data[:], unit=data.attrs['Unit']))

output_index = next((i for i, output in enumerate(outputs) if output.name == '{self.outputs[0].name}'), 0) # select channel to plot

"""

    def pythonPlotCode(self):
        """Defines minimal code to create a plot which can be customized by user.
        Accessible from context menu of scan files.
        Overwrite to add scan specific plot code here."""
        return """# Add your custom plot code here:"""

    def toggleRecording(self):
        """Handles start and stop of scan."""
        if self.recording:
            if self.finished:
                self.init()
                if self.initScan():
                    if self.runThread is not None and self.recording: # stop old scan if applicable
                        self.recordingAction.state = False # allow thread to finish without triggering toggleRecording recursion
                        self.runThread.join()
                        self.recordingAction.state = True
                    self.finished = False
                    self.plot(update=False, done=False) # init plot without data, some widgets may be able to update data only without redrawing the rest
                    self.runThread = Thread(target=self.run, args =(lambda: self.recording,), name=f'{self.name} runThread')
                    self.runThread.daemon = True
                    self.runThread.start()
                    self.display.raiseDock()
                else:
                    self.recordingAction.state = False
            else:
                self.print('Wait for scan to finish.')
                self.recordingAction.state = False
        else:
            self.print('Stopping scan.')
        self.statusAction.setVisible(self.recordingAction.state)

    def scanUpdate(self, done=False):
        # self.print(f"Plot time: {timeit.timeit('self.plot(update=not done, done=done)', number=1, globals={'self': self, 'done': done})}", flag=PRINT.DEBUG)
        self.plot(update=not done, done=done)
        if done: # save data
            self.saveThread = Thread(target=self.saveScanParallel, args=(self.file,), name=f'{self.name} saveThread')
            self.saveThread.daemon = True # Terminate with main app independent of stop condition
            self.saveThread.start()

    def saveScanParallel(self, file):
        """Keeps GUI interactive by saving scan data in external thread."""
        # only reads data from gui but does not modify it -> can run in parallel thread
        self.settingsMgr.saveSettings(file=file) # save settings
        self.saveData(file=file) # save data to same file
        self.pluginManager.DeviceManager.exportConfiguration(file=file) # save corresponding device settings in measurement file
        self.pluginManager.Settings.saveSettings(file=file)
        if hasattr(self.pluginManager, 'Notes'):
            self.pluginManager.Notes.saveData(file=file)
        self.signalComm.saveScanCompleteSignal.emit()
        self.print(f'Saved {file.name}')

    def saveScanComplete(self):
        if not self.pluginManager.closing:
            self.pluginManager.Explorer.populateTree()
            self.notes='' # reset after saved to last scan
        self.finished = True # Main thread waits for this on closing. No new scan can be started before the previous one is finished

    @plotting
    def plot(self, update=False, **kwargs): # pylint: disable = unused-argument # use **kwargs to allow child classed to extend the signature
        """Plot showing a current or final state of the scan.
        Extend to add scan specific plot code.
        Make sure to also use the @plotting decorator when overwriting this function!

        :param update: If update is True, only data will be updates, otherwise entire figure will be initialized, defaults to False
        :type update: bool, optional
        """

    def updateToolBar(self, update):
        if len(self.outputs) > 0 and not update:
            self.display.navToolBar.update()
            self.display.canvas.get_default_filename = lambda: self.file.with_suffix('.pdf') # set up save file dialog

    def updateRecording(self, recording):
        # trigger from external thread to assure GUI update happens in main thread
        self.recording = recording

    def run(self, recording):
        """Steps through input values, records output values, and triggers plot update.
        Executed in runThread. Will likely need to be adapted for custom scans."""
        steps = list(itertools.product(*[input.getRecordingData() for input in self.inputs]))
        self.print(f'Starting scan M{self.pluginManager.Settings.measurementNumber:03}. Estimated time: {self.scantime}')
        for i, step in enumerate(steps): # scan over all steps
            waitLong = False
            for j, _input in enumerate(self.inputs):
                if not waitLong and abs(_input.value-step[j]) > self.largestep:
                    waitLong=True
                _input.updateValueSignal.emit(step[j])
            time.sleep(((self.waitLong if waitLong else self.wait)+self.average)/1000) # if step is larger than threshold use longer wait time

            for j, output in enumerate(self.outputs):
                if len(self.inputs) == 1: # 1D scan
                    output.recordingData[i] = np.mean(output.getValues(subtractBackground=output.getDevice().subtractBackgroundActive(), length=self.measurementsPerStep))
                else: # 2D scan, higher dimensions not jet supported
                    output.recordingData[i%len(self.inputs[1].getRecordingData()), i//len(self.inputs[1].getRecordingData())] = np.mean(output.getValues(subtractBackground=output.getDevice().subtractBackgroundActive(),
                                                                                                                  length=self.measurementsPerStep))
            if i == len(steps)-1 or not recording(): # last step
                for j, _input in enumerate(self.inputs):
                    _input.updateValueSignal.emit(_input.initialValue)
                time.sleep(.5) # allow time to reset to initial value before saving
                self.signalComm.scanUpdateSignal.emit(True) # update graph and save data
                self.signalComm.updateRecordingSignal.emit(False)
                break # in case this is last step
            else:
                # self.print('self.signalComm.scanUpdateSignal.emit(False)', flag=PRINT.DEBUG)
                self.signalComm.scanUpdateSignal.emit(False) # update graph

    def close(self):
        """:meta private:"""
        super().close()
        # if self.initializedDock:
        #     self.settingsMgr.saveSettings(default=True) # scan settings saved immediately when changed
        if self.recording:
            self.recording = False

    def closeGUI(self):
        """:meta private:"""
        self.toggleDisplay(False)
        super().closeGUI()

    def toggleDisplay(self, visible):
        if visible:
            if self.display is None or not self.display.initializedDock:
                self.display = self.Display(scan=self, pluginManager=self.pluginManager)
                self.display.provideDock()
        elif self.displayActive():
            self.display.closeGUI()

    def updateTheme(self):
        """:meta private:"""
        super().updateTheme()
        if self.displayActive():
            self.display.updateTheme()

class Browser(Plugin):
    """The Browser is used to display various file formats. In addition, it
    provides access to the program description and documentation. Finally, it shows
    the about content of other plugins when clicking on their respective question mark icons."""
    # Should show caret when mouse over selectable text but only shows pointer.

    name = 'Browser'
    version = '1.0'
    optional = False
    pluginType = PluginManager.TYPE.DISPLAY
    iconFile = 'QWebEngine.png'

    previewFileTypes = ['.pdf', '.html', '.htm', '.svg', '.wav', '.mp3', '.ogg', '.mp4','.avi']
    # '.mp4','.avi' only work with codec https://doc.qt.io/qt-5/qtwebengine-features.html#audio-and-video-codecs
    previewFileTypes.extend(['.jpg', '.jpeg', '.png', '.bmp', '.gif'])
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        web_engine_context_log = QLoggingCategory("qt.webenginecontext")
        web_engine_context_log.setFilterRules("*.info=false")
        self.ICON_BACK       = self.makeCoreIcon('arrow-180.png')
        self.ICON_FORWARD    = self.makeCoreIcon('arrow.png')
        self.ICON_RELOAD     = self.makeCoreIcon('arrow-circle-315.png')
        self.ICON_STOP       = self.makeCoreIcon('cross.png')
        self.ICON_HOME       = self.makeCoreIcon('home.png')
        self.ICON_MANUAL     = self.makeCoreIcon('address-book-open.png')
        self.file = None
        self.title = None
        self.html = None
        self.plugin = None

    def initDock(self):
        """:meta private:"""
        super().initDock()
        self.dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures) # not floatable or movable

    def initGUI(self):
        """:meta private:"""
        super().initGUI()
        self.webEngineView = QWebEngineView(parent=QApplication.instance().mainWindow)
        # self.webEngineView.page().settings().setUnknownUrlSchemePolicy(QWebEngineSettings.UnknownUrlSchemePolicy.AllowAllUnknownUrlSchemes)
        # self.webEngineView.page().settings().setAttribute(QWebEngineSettings.WebAttribute.AutoLoadImages, True)
        self.webEngineView.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        self.webEngineView.settings().setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, True) # required to open local PDFs

        self.webEngineView.loadFinished.connect(self.adjustLocation)

        self.titleBar.setIconSize(QSize(16, 16)) # match size of other titleBar elements
        self.backAction = self.webEngineView.pageAction(QWebEnginePage.WebAction.Back)
        self.backAction.setIcon(self.ICON_BACK)
        self.backAction.setObjectName('backAction')
        self.backAction.fileName = self.ICON_BACK.fileName
        self.titleBar.addAction(self.backAction)
        self.forwardAction = self.webEngineView.pageAction(QWebEnginePage.WebAction.Forward)
        self.forwardAction.setIcon(self.ICON_FORWARD)
        self.forwardAction.setObjectName('forwardAction')
        self.forwardAction.fileName = self.ICON_FORWARD.fileName
        self.titleBar.addAction(self.forwardAction)
        self.reloadAction = self.webEngineView.pageAction(QWebEnginePage.WebAction.Reload)
        self.reloadAction.setIcon(self.ICON_RELOAD)
        self.reloadAction.setObjectName('reloadAction')
        self.reloadAction.fileName = self.ICON_RELOAD.fileName
        self.titleBar.addAction(self.reloadAction)
        self.stopAction = self.webEngineView.pageAction(QWebEnginePage.WebAction.Stop)
        self.stopAction.setIcon(self.ICON_STOP)
        self.stopAction.setObjectName('stopAction')
        self.stopAction.fileName = self.ICON_STOP.fileName
        self.titleBar.addAction(self.stopAction)
        self.homeAction = self.addAction(self.openAbout, 'Home', self.ICON_HOME)
        self.locationEdit = QLineEdit()
        self.locationEdit.setSizePolicy(QSizePolicy.Policy.Expanding, self.locationEdit.sizePolicy().verticalPolicy())
        self.locationEdit.returnPressed.connect(self.loadUrl)
        self.locationEdit.setMaximumHeight(QPushButton().sizeHint().height())
        self.titleBar.addWidget(self.locationEdit)
        self.docAction = self.addAction(self.openDocumentation, 'Offline Documentation', self.ICON_MANUAL)
        self.addContentWidget(self.webEngineView)

    def finalizeInit(self, aboutFunc=None):
        """:meta private:"""
        super().finalizeInit(aboutFunc)
        self.floatAction.deleteLater()
        delattr(self, 'floatAction')
        self.stretch.deleteLater()
        self.openAbout()

    def runTestParallel(self):
        """:meta private:"""
        if self.initializedDock:
            self.testControl(self.docAction, True, .5)
            self.testControl(self.homeAction, True, .5)
            self.testControl(self.backAction, True, .5)
            self.testControl(self.forwardAction, True, .5)
            self.testControl(self.stopAction, True, .5)
            self.testControl(self.reloadAction, True, .5)
        super().runTestParallel()

    def loadData(self, file, _show=True):
        """:meta private:"""
        self.provideDock()
        self.file = file
        # overwrite parent
        if any(file.name.endswith(fileType) for fileType in ['.html','.htm']):
            self.webEngineView.load(QUrl.fromLocalFile(file.as_posix()))
            # self.webEngineView.setUrl(QUrl(f'file:///{file.as_posix()}'))
        elif any(file.name.endswith(fileType) for fileType in ['.mp4','.avi']):
            self.webEngineView.setHtml('Note: .mp4 and .avi files are not supported due to licensing limitations as explained <a href="https://doc.qt.io/qt-5/qtwebengine-features.html#audio-and-video-codecs">here</a>.\nPlease open in external program.')
        elif file.name.endswith('.svg'):
            # self.webEngineView.setUrl(QUrl(f'file:///{file.as_posix()}')) # does not scale
            # does not work when using absolute path directly for src. also need to replace empty spaces to get valid url
            self.webEngineView.setHtml(f'<img src={file.name.replace(" ","%20")} width="100%"/>',
                baseUrl=QUrl.fromLocalFile(file.as_posix().replace(" ","%20")))
        else: #if file.name.endswith('.pdf', ...):
            self.webEngineView.setUrl(QUrl(f'file:///{file.as_posix()}'))
            # self.webEngineView.??? how to collapse thumbnail / Document outline after loading pdf?
        self.raiseDock(_show)

    def loadUrl(self):
        self.webEngineView.load(QUrl.fromUserInput(self.locationEdit.text()))

    def adjustLocation(self):
        if self.title is None:
            self.locationEdit.setText(self.webEngineView.url().toString().replace('%5C','/'))
            self.html = None
            self.plugin = None
        else:
            self.locationEdit.setText(self.title)
            self.title = None # reset for next update

    def openDocumentation(self):
        self.title = 'Offline Documentation'
        self.loadData(file=(Path(__file__).parent / 'docs/index.html').resolve())

    def openAbout(self):
        """Simple dialog displaying program purpose, version, and creators"""
        updateHTML = '(Offline)'
        try:
            response = requests.get('https://github.com/ioneater/ESIBD-Explorer/releases/latest')
            onlineVersion = version.parse(response.url.split('/').pop())
            if PROGRAM_VERSION >= onlineVersion:
                updateHTML = '(<span style="color: green">Up to date!</span>)'
            elif PROGRAM_VERSION > onlineVersion:
                updateHTML = f'(<a href="https://github.com/ioneater/ESIBD-Explorer/releases/latest">Version {onlineVersion.base_version} available!</a>)'
        except requests.exceptions.ConnectionError:
            pass
        self.setHtml(title=f'About {PROGRAM_NAME}.', html=f"""
        <h1><img src='{PROGRAM_ICON.resolve()}' width='22'> {PROGRAM_NAME} {PROGRAM_VERSION} {updateHTML}</h1>{ABOUTHTML}""")

    def setHtml(self, title, html):
        self.provideDock()
        self.html = html
        self.title = title
        self.webEngineView.setHtml(self.htmlStyle() + self.html, baseUrl=QUrl.fromLocalFile(Path().resolve().as_posix().replace(" ","%20"))) # baseURL required to access local files
        self.raiseDock(True)

    def setAbout(self, plugin, title, html):
        self.provideDock()
        self.title = title
        self.html = html
        self.plugin = plugin
        # baseURL required to access local files
        self.webEngineView.setHtml(self.htmlStyle() + self.htmlTitle(self.plugin) + self.html, baseUrl=QUrl.fromLocalFile(Path().resolve().as_posix().replace(" ","%20")))
        self.raiseDock(True)

    def htmlStyle(self):
        return f"""
        <style>
        body {{
          background-color: {colors.bg};
          color: {colors.fg};
        }}
        a:link    {{color: #8ab4f8; background-color: transparent; text-decoration: none; }}
        a:visited {{color: #c58af9; background-color: transparent; text-decoration: none; }}
        a:hover   {{color: #8ab4f8; background-color: transparent; text-decoration: underline; }}
        a:active  {{color: #8ab4f8; background-color: transparent; text-decoration: underline; }}
        </style>"""

    def htmlTitle(self, plugin):
        return f"<h1><img src='{Path(plugin.getIcon().fileName).resolve()}' width='22'> {plugin.name} {plugin.version}</h1>"

    def updateTheme(self):
        """:meta private:"""
        super().updateTheme()
        if self.html is not None:
            if self.plugin is None:
                self.setHtml(self.title, self.html)
            else:
                self.setAbout(self.plugin, self.title, self.html)

class Text(Plugin):
    """The Text plugin may contain additional useful representation of files,
    even if they are handled by other plugins. In addition, it may contain
    information such as change logs after loading settings or
    configurations from file. It also allows to edit and save simple text files."""

    name = 'Text'
    version = '1.0'
    optional = False
    pluginType = PluginManager.TYPE.DISPLAY
    previewFileTypes = ['.txt', '.dat', '.ter', '.cur', '.tt', '.log', '.py', '.star', '.pdb1', '.css', '.js', '.html', '.tex', '.ini', '.bat']
    iconFile = 'text.png'
    iconFileDark = 'text_dark.png'

    class SignalCommunicate(Plugin.SignalCommunicate):
        setTextSignal = pyqtSignal(str, bool)

    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.signalComm.setTextSignal.connect(self.setText)

    def initGUI(self):
        """:meta private:"""
        super().initGUI()
        self.editor = EsibdCore.TextEdit()
        self.editor.setFont(QFont('Courier', 10))
        self.numbers = EsibdCore.NumberBar(parent=self.editor)
        lay = QHBoxLayout()
        lay.addWidget(self.numbers)
        lay.addWidget(self.editor)
        self.addContentLayout(lay)

    def provideDock(self):
        """:meta private:"""
        if super().provideDock():
            self.finalizeInit()
            self.afterFinalizeInit()

    def finalizeInit(self, aboutFunc=None):
        """:meta private:"""
        super().finalizeInit(aboutFunc)
        self.addAction(lambda: self.saveFile(), 'Save', icon=self.makeCoreIcon('disk-black.png'), before=self.aboutAction)
        self.wordWrapAction = self.addStateAction(event=lambda: self.toggleWordWrap, toolTipFalse='Word wrap on.', iconFalse=self.makeCoreIcon('ui-scroll-pane-text.png'),
                                                  toolTipTrue='Word wrap off.', before=self.aboutAction, attr='wordWrap')
        self.textClipboardAction = self.addAction(lambda: self.copyTextClipboard(),
                       'Copy text to clipboard.', icon=self.makeCoreIcon('clipboard-paste-document-text.png'), before=self.aboutAction)
        self.toggleWordWrap()

    def runTestParallel(self):
        """:meta private:"""
        if self.initializedDock:
            self.testControl(self.wordWrapAction, True)
            self.testControl(self.textClipboardAction, True)
        super().runTestParallel()

    def updateTheme(self):
        """:meta private:"""
        super().updateTheme()
        if not self.pluginManager.loading:
            self.numbers.updateTheme()

    def saveFile(self):
        file = None
        if self.pluginManager.Explorer.activeFileFullPath is not None:
            file = Path(QFileDialog.getSaveFileName(parent=None, caption=SELECTFILE, directory=self.pluginManager.Explorer.activeFileFullPath.as_posix())[0])
        else:
            file = Path(QFileDialog.getSaveFileName(parent=None, caption=SELECTFILE)[0])
        if file != Path('.'):
            with open(file, 'w', encoding=self.UTF8) as textFile:
                textFile.write(self.editor.toPlainText())
            self.pluginManager.Explorer.populateTree()

    def loadData(self, file, _show=True):
        """:meta private:"""
        self.provideDock()
        self.editor.clear()
        if any(file.name.endswith(fileType) for fileType in self.previewFileTypes):
            try:
                with open(file, encoding=self.UTF8) as dataFile:
                    for line in islice(dataFile, 1000): # dont use f.read() as files could potentially be very large
                        self.editor.insertPlainText(line) # always populate text box but only change to tab if no other display method is available
            except UnicodeDecodeError as e:
                self.print(f'Cant read file: {e}')
        self.editor.verticalScrollBar().triggerAction(QScrollBar.SliderAction.SliderToMinimum)   # scroll to top
        self.raiseDock(_show)

    def setText(self, text, _show=False, append=False):
        self.provideDock()
        if append:
            self.editor.appendPlainText(text)
        else:
            self.editor.setPlainText(text)
        tc = self.editor.textCursor()
        tc.setPosition(0)
        self.editor.setTextCursor(tc)
        self.raiseDock(_show)

    def setTextParallel(self, text, _show=False):
        self.signalComm.setTextSignal.emit(text, _show)

    def inspect(self, obj, _filter=None):
        _list = []
        if _filter is not None:
            _list = [repr(member) for member in inspect.getmembers(obj) if _filter in repr(member)]
        else:
            _list = [repr(member) for member in inspect.getmembers(obj)]
        self.setText('\n'.join(_list), True)

    @synchronized()
    def copyTextClipboard(self):
        QApplication.clipboard().setText(self.editor.toPlainText())

    @synchronized()
    def toggleWordWrap(self):
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth if self.wordWrapAction.state else QPlainTextEdit.LineWrapMode.NoWrap)

class Tree(Plugin):
    """The Tree plugin gives an overview of the content of .py, .hdf5, and
    .h5 files. This includes configuration or scan files and even python source code.
    It can also help inspect any object using Tree.inspect() or give an overview of icons using Tree.iconOverview() from the :ref:`sec:console`."""
    documentation = """The Tree plugin gives an overview of the content of .py, .hdf5, and
    .h5 files. This includes configuration or scan files and even python source code.
    It can also help inspect any object using Tree.inspect() or give an overview of icons using Tree.iconOverview() from the Console."""

    name = 'Tree'
    version = '1.0'
    optional = False
    pluginType = PluginManager.TYPE.DISPLAY
    h5PreviewFileTypes = ['.hdf5','.h5']
    pyPreviewFileTypes = ['.py']
    previewFileTypes = h5PreviewFileTypes + pyPreviewFileTypes
    iconFile = 'tree.png'

    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.ICON_ATTRIBUTE = str(self.dependencyPath / 'blue-document-attribute.png')
        self.ICON_DATASET = str(self.dependencyPath / 'database-medium.png')
        self.ICON_FUNCTIONMETHOD = str(self.dependencyPath / 'block-small.png')
        self.ICON_CLASS =   str(self.dependencyPath / 'application-block.png')
        self.ICON_GROUP =   str(self.dependencyPath / 'folder.png')
        self._inspect = False

    def initGUI(self):
        """:meta private:"""
        super().initGUI()
        self.tree = QTreeWidget()
        self.addContentWidget(self.tree)
        self.tree.itemExpanded.connect(self.expandObjet)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.initContextMenu)

    def provideDock(self):
        """:meta private:"""
        if super().provideDock():
            self.finalizeInit()
            self.afterFinalizeInit()

    def loadData(self, file, _show=True):
        """:meta private:"""
        self.provideDock()
        self.tree.clear()
        self.tree.setHeaderHidden(True)
        self._inspect = False
        if any(file.name.endswith(fileType) for fileType in self.h5PreviewFileTypes):
            with h5py.File(file, 'r', track_order=True) as dataFile:
                self.hdfShow(dataFile, self.tree.invisibleRootItem(), 0)
        else: # self.pyPreviewFileTypes
            # """from https://stackoverflow.com/questions/44698193/how-to-get-a-list-of-classes-and-functions-from-a-python-file-without-importing/67840804#67840804"""
            with open(file, encoding=self.UTF8) as file:
                node = ast.parse(file.read())
            functions = [node for node in node.body if isinstance(node,(ast.FunctionDef, ast.AsyncFunctionDef))]
            classes = [node for node in node.body if isinstance(node, ast.ClassDef)]
            for function in functions:
                function_widget = QTreeWidgetItem(self.tree,[function.name])
                function_widget.setIcon(0, QIcon(self.ICON_FUNCTIONMETHOD))
                function_widget.setToolTip(0, ast.get_docstring(function))
                function_widget.setExpanded(True)
            for _class in classes:
                self.pyShow(_class, self.tree, 0)
        if self.tree.topLevelItemCount() == 0: # show text if no items found
            self.pluginManager.Text.provideDock()
            self.pluginManager.Text.raiseDock(_show)
        else:
            self.raiseDock(_show)

    def hdfShow(self, f, tree, level):
        for name, item in f.items():
            if isinstance(item, h5py.Group):
                group = QTreeWidgetItem(tree,[name])
                group.setIcon(0, QIcon(self.ICON_GROUP))
                if level < 1:
                    group.setExpanded(True)
                for attribute, value in item.attrs.items():
                    attribute_widget = QTreeWidgetItem(group,[f'{attribute}: {value}'])
                    attribute_widget.setIcon(0, QIcon(self.ICON_ATTRIBUTE))
                self.hdfShow(item, group, level+1)
            elif isinstance(item, h5py.Dataset):
                dataset_widget = QTreeWidgetItem(tree,[name])
                dataset_widget.setIcon(0, QIcon(self.ICON_DATASET))

    def pyShow(self, _class, tree, level):
        class_widget = QTreeWidgetItem(tree,[_class.name])
        class_widget.setIcon(0, QIcon(self.ICON_CLASS))
        class_widget.setToolTip(0, ast.get_docstring(_class))
        if level < 1:
            class_widget.setExpanded(True)
        for __class in [node for node in _class.body if isinstance(node, ast.ClassDef)]:
            self.pyShow(__class, class_widget, level+1)
        for method in [node for node in _class.body if isinstance(node, ast.FunctionDef)]:
            method_widget = QTreeWidgetItem(class_widget,[method.name])
            method_widget.setIcon(0, QIcon(self.ICON_FUNCTIONMETHOD))
            method_widget.setToolTip(0, ast.get_docstring(method))

    def inspect(self, obj, _filter=None):
        self.provideDock()
        self._inspect = True
        self.tree.clear()
        self.tree.setHeaderHidden(False)
        self.tree.setHeaderLabels(['Object','Value'])
        self.tree.setColumnCount(2)
        self.tree.setColumnWidth(0, 200)
        self.tree.header().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.tree.header().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tree.setUpdatesEnabled(False)
        self.inspect_recursive(tree=self.tree.invisibleRootItem(), obj=obj, _filter=_filter)
        self.tree.setUpdatesEnabled(True)

    def expandObjet(self, element):
        if self._inspect:
            self.tree.setUpdatesEnabled(False)
            self.inspect_recursive(tree=element, obj=element.obj)
            self.tree.setUpdatesEnabled(True)
            element.setExpanded(True)

    def inspect_recursive(self, tree, obj, _filter=None, recursionDepth=2):
        """Recursively populates the object tree.
        Will also be called as user expands items.
        Similar logic is used for Explorer, but here we do not need to worry about changing filters or items that have been removed."""
        if recursionDepth == 0:
            return
        recursionDepth = recursionDepth - 1
        children_text = [tree.child(i).text(0) for i in range(tree.childCount())] # list of existing children
        if isinstance(obj, List):
            list_preview_number = 5 # only show subset of list
            for i, element in enumerate(obj[:list_preview_number]):
                element_name = f'[{i}]'
                if element_name in children_text: # reuse existing
                    element_widget = tree.child(children_text.index(element_name))
                else: # add new
                    element_widget = QTreeWidgetItem(tree, [element_name])
                    element_widget.setIcon(0, QIcon(self.ICON_ATTRIBUTE))
                    element_widget.setText(1, f'{element}')
                    element_widget.obj = element
                if not isinstance(element, (bool, float, int, str, Enum)):
                    self.inspect_recursive(tree=element_widget, obj=element, recursionDepth=recursionDepth)
            if len(obj) > list_preview_number and '...' not in children_text:
                _ = QTreeWidgetItem(tree, ['...'])
                _.setIcon(0, QIcon(self.ICON_ATTRIBUTE))
        else:
            object_names = [object_name for object_name in dir(obj) if not object_name.startswith('_') and (_filter is None or _filter.lower() in object_name.lower())]
            variable_names = []
            callable_names = []
            for object_name in object_names:
                try:
                    attr = getattr(obj, object_name)
                    if callable(attr):
                        callable_names.append(object_name)
                    else:
                        variable_names.append(object_name)
                except AttributeError:
                    pass # apparently some libraries keep deprecated attributes, just to throw deprecation AttributeError if they are accessed.
                except (ValueError, RuntimeError) as e:
                    self.print(f'Problem with object {object_name}: {e}', flag=PRINT.WARNING)
            for object_name in variable_names:
                attr = getattr(obj, object_name)
                variable_name = object_name if isinstance(attr, List) else f'{object_name}'
                if variable_name in children_text:
                    variable_widget = tree.child(children_text.index(variable_name))
                else:
                    variable_widget = QTreeWidgetItem(tree, [variable_name])
                    variable_widget.setIcon(0, QIcon(self.ICON_ATTRIBUTE))
                    if not isinstance(attr, List):
                        variable_widget.setText(1, repr(attr))
                    variable_widget.obj = attr
                if not isinstance(attr, (bool, float, int, str, Enum)):
                    self.inspect_recursive(tree=variable_widget, obj=attr, recursionDepth=recursionDepth)
            for object_name in callable_names:
                if object_name in children_text:
                    class_method_widget = tree.child(children_text.index(object_name))
                else:
                    attr = getattr(obj, object_name)
                    class_method_widget = QTreeWidgetItem(tree, [object_name])
                    class_method_widget.setIcon(0, QIcon(self.ICON_CLASS if inspect.isclass(attr) else self.ICON_FUNCTIONMETHOD))
                    if attr.__doc__ is not None:
                        class_method_widget.setText(1, attr.__doc__.split('\n')[0])
                        class_method_widget.setToolTip(1, attr.__doc__)
        self.raiseDock(True)

    def initContextMenuBase(self, widget, pos):
        """General implementation of a context menu.
        The relevant actions will be chosen based on the type and properties of the :class:`~esibd.core.Parameter`."""
        contextMenu = QMenu(self.tree)
        copyClipboardAction = contextMenu.addAction('Copy to clipboard')
        contextMenu = contextMenu.exec(self.tree.mapToGlobal(pos))
        if contextMenu is not None:
            if contextMenu is copyClipboardAction:
                column_index = -1
                header = self.tree.header()
                for col in range(self.tree.columnCount()):
                    rect = header.sectionViewportPosition(col)
                    if rect <= pos.x() < rect + header.sectionSize(col):
                        column_index = col
                        break
                if column_index != -1:
                    QApplication.clipboard().setText(widget.text(column_index))

    def initContextMenu(self, pos):
        try:
            self.initContextMenuBase(self.tree.itemAt(pos), pos)
        except KeyError as e:
            self.print(e)

    def iconOverview(self):
        self.provideDock()
        self.tree.clear()
        self.tree.setHeaderHidden(False)
        self.tree.setHeaderLabels(['Icon','Tooltip'])
        self.tree.setColumnCount(2)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        for plugin in self.pluginManager.plugins:
            plugin_widget = QTreeWidgetItem(self.tree, [plugin.name])
            plugin_widget.setIcon(0, plugin.getIcon())
            self.tree.setFirstColumnSpanned(self.tree.indexOfTopLevelItem(plugin_widget), self.tree.rootIndex(), True)  # Spans all columns
            # description = plugin.documentation if plugin.documentation is not None else plugin.__doc__
            # plugin_widget.setText(1, description.splitlines()[0][:100] )
            # plugin_widget.setToolTip(1, description)
            self.addActionWidgets(plugin_widget, plugin)
            if hasattr(plugin, 'liveDisplay') and plugin.liveDisplayActive():
                widget = QTreeWidgetItem(plugin_widget, [plugin.liveDisplay.name])
                widget.setIcon(0, plugin.liveDisplay.getIcon())
                widget.setFirstColumnSpanned(True)
                self.addActionWidgets(widget, plugin.liveDisplay)
            if hasattr(plugin, 'staticDisplay') and plugin.staticDisplayActive():
                widget = QTreeWidgetItem(plugin_widget, [plugin.staticDisplay.name])
                widget.setIcon(0, plugin.staticDisplay.getIcon())
                widget.setFirstColumnSpanned(True)
                self.addActionWidgets(widget, plugin.staticDisplay)
            if hasattr(plugin, 'channelPlot') and plugin.channelPlotActive():
                widget = QTreeWidgetItem(plugin_widget, [plugin.channelPlot.name])
                widget.setIcon(0, plugin.channelPlot.getIcon())
                widget.setFirstColumnSpanned(True)
                self.addActionWidgets(widget, plugin.channelPlot)
            if hasattr(plugin, 'display') and plugin.displayActive():
                widget = QTreeWidgetItem(plugin_widget, [plugin.display.name])
                widget.setIcon(0, plugin.display.getIcon())
                widget.setFirstColumnSpanned(True)
                self.addActionWidgets(widget, plugin.display)
            plugin_widget.setExpanded(True)

        # self.expandTree(self.tree)
        self.raiseDock(True)

    def addActionWidgets(self, tree, plugin):
        if hasattr(plugin, 'titleBar'):
            for action in plugin.titleBar.actions():
                if action.iconText() != '' and action.isVisible():
                    action_widget = QTreeWidgetItem(tree)
                    action_widget.setIcon(0, action.icon if isinstance(action, (EsibdCore.Action, EsibdCore.StateAction, EsibdCore.MultiStateAction)) else action.icon())
                    action_widget.setText(1, action.iconText())

class Console(Plugin):
    # ! Might need to switch to to more stable QtConsole eventually
    """The console should typically not be needed, unless you are a developer
    or assist in debugging an issue. It is activated from the tool bar of
    the :ref:`sec:settings`. Status messages will be logged here. In addition you can
    also enable writing status messages to a log file, that can be shared
    with a developer for debugging. All features implemented in the user
    interface and more can be accessed directly from this console. Use at
    your own Risk! You can select some commonly used examples directly from
    the combo box to get started."""
    documentation = """The console should typically not be needed, unless you are a developer
    or assist in debugging an issue. It is activated from the tool bar of
    the settings. Status messages will be logged here. In addition you can
    also enable writing status messages to a log file, that can be shared
    with a developer for debugging. All features implemented in the user
    interface and more can be accessed directly from this console. Use at
    your own Risk! You can select some commonly used examples directly from
    the combo box to get started."""

    pluginType = PluginManager.TYPE.CONSOLE
    name = 'Console'
    version = '1.0'
    optional = False
    triggerComboBoxSignal = pyqtSignal(int)
    iconFile = 'terminal.png'

    class SignalCommunicate(Plugin.SignalCommunicate):
        writeSignal = pyqtSignal(str)
        executeSignal = pyqtSignal(str)

    def initDock(self):
        """:meta private:"""
        super().initDock()
        self.dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures) # not floatable or movable

    def initGUI(self):
        """:meta private:"""
        super().initGUI()
        self.mainDisplayWidget.setMinimumHeight(1) # enable hiding
        self.historyFile = validatePath(qSet.value(f'{GENERAL}/{CONFIGPATH}', defaultConfigPath), defaultConfigPath)[0] / 'console_history.bin'
        # self.historyFile.touch(exist_ok=True) # will be created next time the program closes, touch creates an invalid file
        # self.historyFile = open(hf, 'w')
        self.mainConsole    = EsibdCore.ThemedConsole(parentPlugin=self, historyFile=self.historyFile)
        self.mainConsole.repl._lastCommandRow = 0 # not checking for None if uninitialized! -> initialize
        self.vertLayout.addWidget(self.mainConsole, 1) # https://github.com/pyqtgraph/pyqtgraph/issues/404 # add before hintsTextEdit
        self.commonCommandsComboBox = EsibdCore.CompactComboBox()
        self.commonCommandsComboBox.wheelEvent = lambda event: None
        self.commonCommandsComboBox.addItems([
            "select command",
            "Tree.iconOverview() # Show icon overview.",
            "Browser.previewFileTypes # access plugin properties directly using plugin name",
            "ISEG.controller # get device specific hardware manager",
            "RBD.channels # get channels of a device",
            "Energy.display.fig # get specific figure",
            "Tree.inspect(Settings) # show methods and attributes of any object in Tree plugin",
            "Tree.inspect(Settings, _filter='session') # show methods and attributes of any object in Tree plugin",
            "timeit.timeit('Beam.plot(update=True, done=False)', number=100, globals=globals()) # time execution of plotting",
            "channel = DeviceManager.getChannelByName('RT_Front-Plate', inout=INOUT.IN) # get specific input channel",
            "channel.asDict(temp=True) # Returns list of channel parameters and their value.",
            "channel.getParameterByName(channel.ENABLED).getWidget().height() # get property of specific channel",
            "parameter = channel.getParameterByName(channel.ENABLED) # get specific channel parameter",
            "print(parameter.widgetType, parameter.value, parameter.getWidget()) # print parameter properties",
            "channel.getParameterByName(channel.VALUE).getWidget().setStyleSheet('background-color:red;') # test widget styling",
            "_=[parameter.getWidget().setStyleSheet('background-color:red;border: 0px;padding: 0px;margin: 0px;') for parameter in channel.parameters]",
            "PluginManager.showThreads() # show all active threads",
            "[plt.figure(num).get_label() for num in plt.get_fignums()] # show all active matplotlib figures",
            "# Module=EsibdCore.dynamicImport('ModuleName','C:/path/to/module.py') # import a python module, e.g. to run generated plot files.",
            "# PluginManager.test() # Automated testing of all active plugins. Can take a few minutes."
        ])
        self.commonCommandsComboBox.setMaximumWidth(150)
        self.commonCommandsComboBox.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed)
        self.commonCommandsComboBox.currentIndexChanged.connect(self.commandChanged)
        self.mainConsole.repl.inputLayout.insertWidget(1, self.commonCommandsComboBox)
        self.mainConsole.historyBtn.deleteLater()
        self.mainConsole.exceptionBtn.deleteLater()
        self.triggerComboBoxSignal.connect(self.triggerCombo)
        self.signalComm.writeSignal.connect(self.write)
        self.signalComm.executeSignal.connect(self.execute)
        # self.mainConsole.repl.input.installEventFilter(self.pluginManager.mainWindow) # clears input on Ctrl + C like a terminal. Not using it as it also prevents copy paste!
        for message in self.pluginManager.logger.backLog:
            self.write(message)
        self.pluginManager.logger.backLog = []

    def finalizeInit(self, aboutFunc=None):
        """:meta private:"""
        super().finalizeInit(aboutFunc)
        self.floatAction.deleteLater()
        delattr(self, 'floatAction')
        namespace = {'timeit':timeit, 'EsibdCore':EsibdCore, 'EsibdConst':EsibdConst, 'sys':sys, 'np':np, 'itertools':itertools, 'plt':plt, 'inspect':inspect, 'INOUT':INOUT, 'qSet':qSet,
                    'Parameter':Parameter, 'QtCore':QtCore, 'Path':Path, 'Qt':Qt, 'PluginManager':self.pluginManager, 'importlib':importlib, 'version': version,
                      'datetime':datetime, 'QApplication':QApplication, 'self':QApplication.instance().mainWindow, 'help':lambda: self.help()}
        for plugin in self.pluginManager.plugins: # direct access to plugins
            namespace[plugin.name] = plugin
        self.mainConsole.localNamespace = namespace
        self.errorFilterAction = self.addStateAction(toolTipFalse='Show only errors.', iconFalse=self.makeCoreIcon('unicode_error.png'),
                                              toolTipTrue='Show all messages.', iconTrue=self.makeCoreIcon('unicode_error.png'),
                                              before=self.aboutAction, event=lambda: self.toggleMessageFilter(error=True))
        self.warningFilterAction = self.addStateAction(toolTipFalse='Show only warnings.', iconFalse=self.makeCoreIcon('unicode_warning.png'),
                                              toolTipTrue='Show all messages.', iconTrue=self.makeCoreIcon('unicode_warning.png'),
                                              before=self.aboutAction, event=lambda: self.toggleMessageFilter(error=False))
        self.toggleLoggingAction = self.addStateAction(toolTipFalse='Write to log file.', iconFalse=self.makeCoreIcon('blue-document-list.png'), attr='logging',
                                              toolTipTrue='Disable logging to file.', iconTrue=self.makeCoreIcon('blue-document-medium.png'),
                                              before=self.aboutAction, event=lambda: self.toggleLogging(), default='true')
        self.openLogAction = self.addAction(toolTip='Open log file.', icon=self.makeCoreIcon('blue-folder-open-document-text.png'), before=self.aboutAction, event=lambda: self.pluginManager.logger.openLog())
        self.inspectAction = self.addAction(toolTip='Inspect object.', icon=self.makeCoreIcon('zoom_to_rect_large_dark.png' if getDarkMode() else 'zoom_to_rect_large.png'),
                                            before=self.toggleLoggingAction, event=lambda: self.inspect())
        self.closeAction = self.addAction(lambda: self.hide(), 'Hide.', self.makeCoreIcon('close_dark.png' if getDarkMode() else 'close_light.png'))

    def addToNamespace(self, key, value):
        self.mainConsole.localNamespace[key] = value

    def runTestParallel(self):
        """:meta private:"""
        # if self.initializedDock:
            # self.testControl(self.openLogAction, True) # will be opened at the end as to not interfere with video recording
        # test all predefined commands. Make sure critical commands are commented out to avoid reset and testing loop etc.
        for i in range(self.commonCommandsComboBox.count())[1:]:
            if not self.testing:
                break
            # self.triggerComboBoxSignal.emit(i) # ? causes logger to break: print no longer redirected to console, terminal, or file!
            # self.mainConsole.input.sigExecuteCmd.emit(self.commonCommandsComboBox.itemText(i)) # works but does not add command to history
            command = self.commonCommandsComboBox.itemText(i)
            self.print(f"Testing command: {command if len(command) <= 70 else f'{command[:67]}…'}")
            with self.lock.acquire_timeout(timeout=1, timeoutMessage=f'Could not acquire lock to test {self.commonCommandsComboBox.itemText(i)}') as lock_acquired:
                if lock_acquired:
                    self.signalComm.executeSignal.emit(self.commonCommandsComboBox.itemText(i))
        super().runTestParallel()

    def triggerCombo(self, i):
        self.commonCommandsComboBox.setCurrentIndex(i)

    def commandChanged(self, _):
        if self.commonCommandsComboBox.currentIndex() != 0:
            self.execute(self.commonCommandsComboBox.currentText())
            self.commonCommandsComboBox.setCurrentIndex(0)

    def write(self, message):
        """Writes to integrated console to keep track of message history."""
        # avoid using self.mainConsole.repl.write() because stdout is already handled by core.Logger
        if self.initializedGUI:
            if current_thread() is main_thread():
                self.mainConsole.output.moveCursor(QTextCursor.MoveOperation.End)
                self.mainConsole.output.insertPlainText(message)
                self.mainConsole.scrollToBottom()
                if '⚠️' in message: # 🪲⚠️❌ℹ️❖
                    self.mainConsole.outputWarnings.moveCursor(QTextCursor.MoveOperation.End)
                    self.mainConsole.outputWarnings.insertPlainText(message + '\n')
                    sb = self.mainConsole.outputWarnings.verticalScrollBar()
                    sb.setValue(sb.maximum())
                elif '❌' in message:
                    self.mainConsole.outputErrors.moveCursor(QTextCursor.MoveOperation.End)
                    self.mainConsole.outputErrors.insertPlainText(message + '\n')
                    sb = self.mainConsole.outputErrors.verticalScrollBar()
                    sb.setValue(sb.maximum())
            else:
                self.signalComm.writeSignal.emit(message)

    def toggleMessageFilter(self, error=True):
        if error:
            self.warningFilterAction.state = False
        else:
            self.errorFilterAction.state = False
        if self.warningFilterAction.state:
            self.mainConsole.outputLayout.setCurrentIndex(1)
        elif self.errorFilterAction.state:
            self.mainConsole.outputLayout.setCurrentIndex(2)
        else:
            self.mainConsole.outputLayout.setCurrentIndex(0)

    def toggleVisible(self):
        self.dock.setVisible(self.pluginManager.Settings.showConsoleAction.state)

    def toggleLogging(self):
        qSet.setValue(LOGGING, self.toggleLoggingAction.state)
        if self.toggleLoggingAction.state:
            self.pluginManager.logger.open()
        else:
            self.pluginManager.logger.close()

    def inspect(self):
        if self.mainConsole.input.text() == '':
            self.mainConsole.input.setText('Enter object to be inspected here first.')
        else:
            self.execute(f'Tree.inspect({self.mainConsole.input.text()})')

    def help(self):
        self.print(f'Read the docs online at http://esibd-explorer.rtfd.io/ or offline at {(Path(__file__).parent / "docs/index.html").resolve()} to get help.')

    @synchronized(timeout=1)
    def execute(self, command):
        self.mainConsole.input.setText(command)
        self.mainConsole.input.execCmd()
        self.mainConsole.input.setFocus()

    def clear(self):
        self.mainConsole.input.setText('')

    def hide(self):
        self.pluginManager.Settings.showConsoleAction.state = False
        self.pluginManager.Settings.showConsoleAction.triggered.emit(False)

    def updateTheme(self):
        """:meta private:"""
        super().updateTheme()
        self.mainConsole.updateTheme()
        if hasattr(self, 'inspectAction'):
            self.inspectAction.setIcon(self.makeCoreIcon('zoom_to_rect_large_dark.png' if getDarkMode() else 'zoom_to_rect_large.png'))

class SettingsManager(Plugin):
    """Bundles multiple :class:`settings<esibd.core.Setting>` into a single object to handle shared functionality."""

    version = '1.0'
    pluginType = PluginManager.TYPE.INTERNAL

    def __init__(self, parentPlugin, defaultFile, name=None, tree=None, **kwargs):
        super().__init__(**kwargs)
        self.defaultFile = defaultFile
        self.parentPlugin = parentPlugin
        if name is not None:
            self.name = name
        self.tree = tree
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.initSettingsContextMenu)
        self.defaultSettings = {}
        self.settings = {}

    def addDefaultSettings(self, plugin):
        self.defaultSettings.update(plugin.getDefaultSettings())
        # generate property for direct access of setting value from parent
        for name, default in plugin.getDefaultSettings().items():
            if default[Parameter.ATTR] is not None:
                setattr(plugin.__class__, default[Parameter.ATTR], makeSettingWrapper(name, self))

    def initSettingsContextMenu(self, pos):
        try:
            if hasattr(self.tree.itemAt(pos), 'fullName'):
                self.initSettingsContextMenuBase(self.settings[self.tree.itemAt(pos).fullName], self.tree.mapToGlobal(pos))
        except KeyError as e: # setting could not be identified
            self.print(e)

    OPENPATH  = 'Open Path'
    SETTINGS    = 'Settings'
    ADDSETTOCONSOLE  = 'Add Setting to Console'

    def initSettingsContextMenuBase(self, setting, pos):
        """General implementation of a context menu.
        The relevant actions will be chosen based on the type and properties of the :class:`~esibd.core.Setting`."""
        settingsContextMenu = QMenu(self.tree)
        openPathAction = None
        changePathAction = None
        addItemAction = None
        editItemAction = None
        removeItemAction = None
        copyClipboardAction = None
        setToDefaultAction = None
        makeDefaultAction = None
        addSettingToConsoleAction = None
        if getShowDebug():
            addSettingToConsoleAction = settingsContextMenu.addAction(self.ADDSETTOCONSOLE)
        if setting.widgetType == Parameter.TYPE.PATH:
            openPathAction = settingsContextMenu.addAction(self.OPENPATH)
            changePathAction = settingsContextMenu.addAction(SELECTPATH)
        elif (setting.widgetType in [Parameter.TYPE.COMBO, Parameter.TYPE.INTCOMBO, Parameter.TYPE.FLOATCOMBO]
                and not isinstance(setting.parent, Channel) and not setting.fixedItems):
            # Channels are part of Devices which define items centrally
            addItemAction = settingsContextMenu.addAction(Channel.ADDITEM)
            editItemAction = settingsContextMenu.addAction(Channel.EDITITEM)
            removeItemAction = settingsContextMenu.addAction(Channel.REMOVEITEM)
        if not isinstance(setting.parent, Channel):
            if setting.widgetType == Parameter.TYPE.LABEL:
                copyClipboardAction = settingsContextMenu.addAction('Copy to clipboard.')
            else:
                setToDefaultAction = settingsContextMenu.addAction(f'Set to Default: {setting.default}')
                makeDefaultAction = settingsContextMenu.addAction('Make Default')
        if not settingsContextMenu.actions():
            return
        settingsContextMenuAction = settingsContextMenu.exec(pos)
        if settingsContextMenuAction is not None: # no option selected (NOTE: if it is None this could trigger a non initialized action which is also None if not tested here)
            if settingsContextMenuAction is addSettingToConsoleAction:
                self.pluginManager.Console.addToNamespace('setting', setting)
                self.pluginManager.Console.execute('setting')
            elif settingsContextMenuAction is copyClipboardAction:
                pyperclip.copy(setting.value)
            elif settingsContextMenuAction is setToDefaultAction:
                setting.setToDefault()
            elif settingsContextMenuAction is makeDefaultAction:
                setting.makeDefault()
            elif settingsContextMenuAction is openPathAction:
                openInDefaultApplication(setting.value)
            elif settingsContextMenuAction is changePathAction:
                startPath = setting.value
                newPath = Path(QFileDialog.getExistingDirectory(self.pluginManager.mainWindow, SELECTPATH, startPath.as_posix(),
                                                                QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontResolveSymlinks))
                if newPath != Path('.'): # directory has been selected successfully
                    setting.value = newPath
            elif settingsContextMenuAction is addItemAction:
                text, ok = QInputDialog.getText(self, Channel.ADDITEM, Channel.ADDITEM)
                if ok and text != '':
                    setting.addItem(text)
            elif settingsContextMenuAction is editItemAction:
                text, ok = QInputDialog.getText(self, Channel.EDITITEM, Channel.EDITITEM, text=str(setting.value))
                if ok and text != '':
                    setting.editCurrentItem(text)
            elif settingsContextMenuAction is removeItemAction:
                setting.removeCurrentItem()

    def init(self):
        # call this after creating the instance, as the instance is required during initialization
        # call after all defaultSettings have been added!
        self.loadSettings(default=True)

    def loadSettings(self, file=None, default=False):
        """Loads settings from hdf or ini file."""
        self.loading = True
        if default:
            file = self.defaultFile
        if file is None: # get file via dialog
            file = Path(QFileDialog.getOpenFileName(parent=self.pluginManager.mainWindow, caption=SELECTFILE,
                                                    directory=self.pluginManager.Settings.configPath.as_posix(), filter=self.FILTER_INI_H5)[0])
        if file == Path('.'):
            return
        useFile = False
        defaults_added = False
        items = []
        if file.suffix == FILE_INI:
            # Load settings from INI file
            if file != Path('.') and file.exists():
                confParser = configparser.ConfigParser()
                try:
                    confParser.read(file)
                    useFile = True
                except KeyError:
                    pass
            for name, default in self.defaultSettings.items():
                if not default[Parameter.INTERNAL] and useFile and name not in confParser:
                    self.print(f'Using default value {default[Parameter.VALUE]} for setting {name}.')
                    defaults_added = True
                items.append(EsibdCore.parameterDict(name=name,
                    value=confParser[name][Parameter.VALUE] if useFile and name in confParser and Parameter.VALUE in confParser[name] else default[Parameter.VALUE],
                    default=confParser[name][Parameter.DEFAULT] if useFile and name in confParser and Parameter.DEFAULT in confParser[name] else default[Parameter.DEFAULT],
                    items=confParser[name][Parameter.ITEMS] if useFile and name in confParser and Parameter.ITEMS in confParser[name] else default[Parameter.ITEMS],
                    fixedItems=default[Parameter.FIXEDITEMS],
                    _min=default[Parameter.MIN], _max=default[Parameter.MAX],
                    internal=default[Parameter.INTERNAL] if Parameter.INTERNAL in default else False,
                    advanced=default[Parameter.ADVANCED] if Parameter.ADVANCED in default else False,
                    indicator=default[Parameter.INDICATOR] if Parameter.INDICATOR in default else False,
                    instantUpdate=default[Parameter.INSTANTUPDATE] if Parameter.INSTANTUPDATE in default else True,
                    displayDecimals=default[Parameter.DISPLAYDECIMALS] if Parameter.DISPLAYDECIMALS in default else 2,
                    toolTip=default[Parameter.TOOLTIP],
                    tree=self.tree if default[Parameter.WIDGET] is None else None,
                    widgetType=default[Parameter.WIDGETTYPE], widget=default[Parameter.WIDGET],
                    event=default[Parameter.EVENT]))
        else:
            with h5py.File(file, 'r' if file.exists() else 'w') as h5file:
                if self.parentPlugin.name == self.SETTINGS:
                    group = h5file[self.parentPlugin.name]
                    useFile = True
                elif self.parentPlugin.name in h5file and self.SETTINGS in h5file[self.parentPlugin.name]:
                    group = h5file[self.parentPlugin.name][self.SETTINGS]
                    useFile = True
                for name, default in self.defaultSettings.items():
                    if useFile and name not in group:
                        self.print(f'Using default value {default[Parameter.VALUE]} for setting {name}.')
                        defaults_added = True
                    items.append(EsibdCore.parameterDict(name=name,
                        value=group[name].attrs[Parameter.VALUE] if useFile and name in group and Parameter.VALUE in group[name].attrs else default[Parameter.VALUE],
                        default=group[name].attrs[Parameter.DEFAULT] if useFile and name in group and Parameter.DEFAULT in group[name].attrs else default[Parameter.DEFAULT],
                        items=group[name].attrs[Parameter.ITEMS] if useFile and name in group and Parameter.ITEMS in group[name].attrs else default[Parameter.ITEMS],
                        fixedItems=default[Parameter.FIXEDITEMS],
                        _min=default[Parameter.MIN], _max=default[Parameter.MAX],
                        internal=default[Parameter.INTERNAL] if Parameter.INTERNAL in default else False,
                        advanced=default[Parameter.ADVANCED] if Parameter.ADVANCED in default else False,
                        indicator=default[Parameter.INDICATOR] if Parameter.INDICATOR in default else False,
                        instantUpdate=default[Parameter.INSTANTUPDATE] if Parameter.INSTANTUPDATE in default else True,
                        displayDecimals=default[Parameter.DISPLAYDECIMALS] if Parameter.DISPLAYDECIMALS in default else 2,
                        toolTip=default[Parameter.TOOLTIP],
                        tree=self.tree if default[Parameter.WIDGET] is None else None, # dont use tree if widget is provided independently
                        widgetType=default[Parameter.WIDGETTYPE], widget=default[Parameter.WIDGET],
                        event=default[Parameter.EVENT]))
        self.updateSettings(items, file)
        if not useFile: # create default if not exist
            self.print(f'Adding default settings in {file.name} for {self.parentPlugin.name}.')
            self.saveSettings(file=file)
        elif defaults_added:
            self.saveSettings(file=file) # update file with defaults. Defaults would otherwise not be written to file unless they are changed by the user.

        # self.expandTree(self.tree)
        self.tree.collapseAll() # only session should be expanded by default
        self.tree.expandItem(self.tree.topLevelItem(1))
        self.loading = False

    def updateSettings(self, items, file):
        """Scans for changes and shows change log before overwriting old channel configuration."""
        # Note: h5diff can be used alternatively to find changes, but the output is not formatted in a user friendly way (hard to correlate values with channels).
        if not self.pluginManager.loading:
            self.changeLog = [f'Change log for loading {self.name} from {file.name}:']
            for item in items:
                if item[Parameter.NAME] in self.settings:
                    if not item[Parameter.INTERNAL]:
                        setting = self.settings[item[Parameter.NAME]]
                        if not setting.equals(item[Parameter.VALUE]):
                            self.changeLog.append(f'Updating setting {setting.fullName} from {setting.formatValue()} to {setting.formatValue(item[Parameter.VALUE])}')
                else:
                    self.changeLog.append(f'Adding setting {item[Parameter.NAME]}')
            newNames = [item[Parameter.NAME] for item in items]
            for setting in self.settings.values():
                if setting.fullName not in newNames:
                    self.changeLog.append(f'Removing setting {setting.fullName}')
            if len(self.changeLog) == 1:
                self.changeLog.append('No changes.')
            self.pluginManager.Text.setText('\n'.join(self.changeLog), False) # show changelog
            self.print('Settings updated. Change log available in Text plugin.')
        self.settings.clear() # clear and load new settings
        self.tree.clear() # Remove all previously existing widgets. They will be recreated based on settings in file.
        for item in items:
            self.addSetting(item)

    def addSetting(self, item):
        self.settings[item[Parameter.NAME]] = EsibdCore.Setting(_parent=self, name=item[Parameter.NAME], value=item[Parameter.VALUE], default=item[Parameter.DEFAULT],
                            items=item[Parameter.ITEMS], fixedItems=item[Parameter.FIXEDITEMS], _min=item[Parameter.MIN], _max=item[Parameter.MAX], internal=item[Parameter.INTERNAL],
                            indicator=item[Parameter.INDICATOR], instantUpdate=item[Parameter.INSTANTUPDATE], displayDecimals=item[Parameter.DISPLAYDECIMALS], toolTip=item[Parameter.TOOLTIP],
                            tree=item[Parameter.TREE], widgetType=item[Parameter.WIDGETTYPE], widget=item[Parameter.WIDGET], event=item[Parameter.EVENT],
                            parentItem=self.hdfRequireParentItem(item[Parameter.NAME], self.tree.invisibleRootItem()), advanced=item[Parameter.ADVANCED])

    def hdfRequireParentItem(self, name, parentItem):
        names = name.split('/')
        if len(names) > 1: # only ensure parents are there. last widget will be created as an Setting
            for name_part in name.split('/')[:-1]:
                children = [parentItem.child(i) for i in range(parentItem.childCount())] # list of existing children
                children_text = [child.text(0) for child in children]
                if name_part in children_text: # reuse existing
                    parentItem = parentItem.child(children_text.index(name_part))
                else:
                    parentItem = QTreeWidgetItem(parentItem,[name_part])
        return parentItem

    def saveSettings(self, file=None, default=False): # public method
        """Saves settings to hdf or ini file."""
        if default:
            file = self.defaultFile
        if file is None: # get file via dialog
            file = Path(QFileDialog.getSaveFileName(parent=self.pluginManager.mainWindow, caption=SELECTFILE,
                                                    directory=self.pluginManager.Settings.configPath.as_posix(), filter=self.FILTER_INI_H5)[0])
        if file == Path('.'):
            return
        if file.suffix == FILE_INI:
            # load and update content. Keep settings of currently used plugins untouched as they may be needed when these plugins are enabled in the future
            config = configparser.ConfigParser()
            if file.exists():
                config.read(file)
            config[INFO] = infoDict(self.name)
            for name, default in self.defaultSettings.items():
                if name not in [Parameter.DEFAULT.upper(), VERSION] and not self.settings[name].internal:
                    if name not in config:
                        config[name] = {}
                    config[name][Parameter.VALUE]     = self.settings[name].formatValue()
                    config[name][Parameter.DEFAULT]   = self.settings[name].formatValue(self.settings[name].default)
                    if default[Parameter.WIDGETTYPE] in [Parameter.TYPE.COMBO, Parameter.TYPE.INTCOMBO, Parameter.TYPE.FLOATCOMBO]:
                        config[name][Parameter.ITEMS] = ','.join(self.settings[name].items)
            with open(file, 'w', encoding=self.UTF8) as configFile:
                config.write(configFile)
        else:
            with h5py.File(file, 'w' if default else 'a', track_order=True) as h5file: # will update if exist, otherwise create
                h5py.get_config().track_order = True
                self.hdfUpdateVersion(h5file)
                if self.parentPlugin.name == self.SETTINGS:
                    settings_group = self.requireGroup(h5file, self.parentPlugin.name)
                else:
                    plugin_group = self.requireGroup(h5file, self.parentPlugin.name)
                    settings_group = self.requireGroup(plugin_group, self.SETTINGS)
                for name, default in self.defaultSettings.items():
                    if name not in [Parameter.DEFAULT.upper(), VERSION] and not self.settings[name].internal:
                        self.hdfSaveSetting(settings_group, name, default)

    def hdfSaveSetting(self, group, name, default):
        for name_part in name.split('/'):
            group = self.requireGroup(group, name_part)
        group.attrs[Parameter.VALUE]        = self.settings[name].value
        group.attrs[Parameter.DEFAULT]      = self.settings[name].default
        if default[Parameter.WIDGETTYPE] in [Parameter.TYPE.COMBO, Parameter.TYPE.INTCOMBO, Parameter.TYPE.FLOATCOMBO]:
            group.attrs[Parameter.ITEMS]    = ','.join(self.settings[name].items)

class Settings(SettingsManager):
    """The settings plugin allows to edit, save, and load all general program
    and hardware settings. Settings can be edited either directly or using
    the context menu that opens on right click. Settings are stored in an
    .ini file which can be edited directly with any text editor if needed. The
    settings file that is used on startup is automatically generated if it
    does not exist. Likewise, default values are used for any missing
    parameters. Setting files can be exported or imported from the user
    interface. A change log will show which settings have changed after importing.
    In addition, the plugin manager and console can be opened from here."""

    version     = '1.0'
    pluginType  = PluginManager.TYPE.CONTROL
    name        = 'Settings'
    optional = False
    showConsoleAction = None
    iconFile = 'gear.png'
    useAdvancedOptions = True

    def __init__(self, pluginManager, **kwargs):
        self.tree = QTreeWidget() # Note. If settings will become closable in the future, tree will need to be recreated when it reopens
        self.tree.setHeaderLabels(['Parameter','Value'])
        self.tree.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        # size to content prevents manual resize
        self.tree.header().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.confINI = f'{self.name}.ini'
        self.loadGeneralSettings = f'Load {PROGRAM_NAME} settings.'
        super().__init__(parentPlugin=self, tree=self.tree,
                         defaultFile=validatePath(qSet.value(f'{GENERAL}/{CONFIGPATH}', defaultConfigPath), defaultConfigPath)[0] / self.confINI, pluginManager=pluginManager, **kwargs)
        self.previewFileTypes = [self.confINI]

    def initDock(self):
        """:meta private:"""
        super().initDock()
        self.dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures) # not floatable or movable

    def initGUI(self):
        """:meta private:"""
        super().initGUI()
        self.addContentWidget(self.tree)
        self.loadSettingsAction = self.addAction(lambda: self.loadSettings(None), f'Load {PROGRAM_NAME} Settings.', icon=self.makeCoreIcon('blue-folder-import.png'))
        self.loadSettingsAction.setVisible(False)
        self.saveSettingsAction = self.addAction(lambda: self.saveSettings(None), f'Export {PROGRAM_NAME} Settings.', icon=self.makeCoreIcon('blue-folder-export.png'))
        self.saveSettingsAction.setVisible(False)
        self.addAction(lambda: self.pluginManager.managePlugins(), f'Manage {PROGRAM_NAME} Plugins.', icon=self.makeCoreIcon('block--pencil.png'))
        self.showConsoleAction = self.addStateAction(event=lambda: self.pluginManager.Console.toggleVisible(), toolTipFalse='Show Console.', iconFalse=self.makeCoreIcon('terminal.png'),
                                                 toolTipTrue='Hide Console.', iconTrue=self.makeCoreIcon('terminal--minus.png'), attr='showConsole')

    def runTestParallel(self):
        # cannot test file dialogs that require user interaction
        self.testControl(self.showConsoleAction, True)
        self.expandTree(self.tree)
        for setting in self.settings.values():
            if setting.name not in [DATAPATH, CONFIGPATH, PLUGINPATH, self.SESSIONPATH, DARKMODE, TESTMODE]:
                if f'{self.SESSION}/' not in setting.fullName: # do not change session path unintentionally during testing
                    self.testControl(setting.getWidget(), setting.value, label=f'Testing {setting.name} {setting.toolTip if setting.toolTip is not None else "No toolTip."}')
        super().runTestParallel()

    def finalizeInit(self, aboutFunc=None):
        """:meta private:"""
        super().finalizeInit(aboutFunc)
        self.floatAction.deleteLater()
        delattr(self, 'floatAction')
        self.requiredPlugin('DeviceManager')
        self.requiredPlugin('Explorer')
        self.toggleAdvanced()

    def init(self):
        """Call externally to init all internal settings and those of all other plugins."""
        self.addDefaultSettings(plugin=self) # make settings available via self.attr
        super().init() # call first time to only load internal settings to enable validation of datapath
        for plugin in self.pluginManager.plugins:
            if hasattr(plugin, 'getDefaultSettings') and not isinstance(plugin, Scan):
                # only if plugin has specified settings that are not handled by separate settingsMgr within the plugin
                try:
                    self.addDefaultSettings(plugin=plugin)
                except Exception as e:
                    self.print(f'Error loading settings for {plugin.name}: {e}')
        super().init() # call again to load all settings from all other plugins
        self.settings[f'{self.SESSION}/{self.MEASUREMENTNUMBER}']._valueChanged = False # make sure sessionpath is not updated after restoring measurement number

    def toggleAdvanced(self, advanced=None):
        self.loadSettingsAction.setVisible(self.advancedAction.state)
        self.saveSettingsAction.setVisible(self.advancedAction.state)
        for setting in self.settings.values():
            if setting.advanced:
                setting.setHidden(not self.advancedAction.state)

    def loadData(self, file, _show=False):
        """:meta private:"""
        return # nothing to do, content will be handled by Text plugin

    SESSION             = 'Session'
    MEASUREMENTNUMBER   = 'Measurement number'
    SESSIONPATH         = 'Session path'

    def getDefaultSettings(self):
        """Defines general default settings"""
        ds = {}
        ds[f'{GENERAL}/{DATAPATH}']=parameterDict(value=defaultDataPath,
                                        widgetType=Parameter.TYPE.PATH, internal=True, event=lambda: self.updateDataPath(), attr='dataPath')
        ds[f'{GENERAL}/{CONFIGPATH}']=parameterDict(value=defaultConfigPath,
                                        widgetType=Parameter.TYPE.PATH, internal=True, event=lambda: self.updateConfigPath(), attr='configPath')
        ds[f'{GENERAL}/{PLUGINPATH}']=parameterDict(value=defaultPluginPath,
                                        widgetType=Parameter.TYPE.PATH, internal=True, event=lambda: self.updatePluginPath(), attr='pluginPath')
        # validate config path before loading settings from file
        path, changed = validatePath(qSet.value(f'{GENERAL}/{DATAPATH}', defaultDataPath), defaultDataPath)
        if changed:
            qSet.setValue(f'{GENERAL}/{DATAPATH}', path)
        path, changed = validatePath(qSet.value(f'{GENERAL}/{CONFIGPATH}', defaultConfigPath), defaultConfigPath)
        if changed:
            qSet.setValue(f'{GENERAL}/{CONFIGPATH}', path)
            self.defaultFile = path / self.confINI
        path, changed = validatePath(qSet.value(f'{GENERAL}/{PLUGINPATH}', defaultPluginPath), defaultPluginPath)
        if changed:
            qSet.setValue(f'{GENERAL}/{PLUGINPATH}', path)
        # access using getDPI()
        ds[f'{GENERAL}/{DPI}']                    = parameterDict(value='100', toolTip='DPI used for graphs.', internal=True, event=lambda: self.updateDPI(),
                                                                items='100, 150, 200, 300', widgetType=Parameter.TYPE.INTCOMBO)
        # access using getTestMode()
        ds[f'{GENERAL}/{TESTMODE}']               = parameterDict(value=True, toolTip='Devices will fake communication in Testmode!', widgetType=Parameter.TYPE.BOOL,
                                    event=lambda: self.pluginManager.DeviceManager.closeCommunication() # pylint: disable=unnecessary-lambda # needed to delay execution until initialized
                                    , internal=True, advanced=True)
        ds[f'{GENERAL}/{DEBUG}']                  = parameterDict(value=False, toolTip='Show debug messages.', internal=True, widgetType=Parameter.TYPE.BOOL, advanced=True)
        ds[f'{GENERAL}/{DARKMODE}']               = parameterDict(value=True, toolTip='Use dark mode.', internal=True, event=lambda: self.pluginManager.updateTheme(),
                                                                widgetType=Parameter.TYPE.BOOL)
        ds[f'{GENERAL}/{CLIPBOARDTHEME}']          = parameterDict(value=True, toolTip='Use current theme when copying graphs to clipboard. Disable to always use light theme.',
                                                                internal=True, widgetType=Parameter.TYPE.BOOL)
        ds[f'{GENERAL}/{ICONMODE}']                = parameterDict(value='Icons', toolTip='Chose if icons, labels, or both should be used in tabs.', event=lambda: self.pluginManager.toggleTitleBarDelayed(update=False),
                                                                internal=True, widgetType=Parameter.TYPE.COMBO, items='Icons, Labels, Both', fixedItems=True)
        ds[f'{GENERAL}/Show video recorders']      = parameterDict(value=False, toolTip='Show icons to record videos of plugins.', event=lambda: self.pluginManager.toggleVideoRecorder(),
                                                                internal=True, widgetType=Parameter.TYPE.BOOL, attr='showVideoRecorders', advanced=True)
        ds[f'{GENERAL}/Highlight mouse clicks']    = parameterDict(value=False, toolTip='Highlight mouse clicks for screen cast creation.',
                                                                   internal=True, widgetType=Parameter.TYPE.BOOL, attr='showMouseClicks', advanced=True)
        ds[f'{self.SESSION}/{self.MEASUREMENTNUMBER}'] = parameterDict(value=0, _min=0, _max=100000000, toolTip='Self incrementing measurement number. Set to 0 to start a new session.',
                                                                widgetType=Parameter.TYPE.INT,
                                                                instantUpdate=False, # only trigger event when changed by user!
                                                                event=lambda: self.updateSessionPath(self.measurementNumber), attr='measurementNumber')
        ds[f'{self.SESSION}/{self.SESSIONPATH}']   = parameterDict(value='', toolTip='Path for storing session data. Relative to data path.',
                                                                widgetType=Parameter.TYPE.LABEL, attr='sessionPath')
        return ds

    def loadSettings(self, file=None, default=False):
        if self.pluginManager.DeviceManager.initialized():
            if EsibdCore.CloseDialog(title='Stop communication?', ok='Stop communication', prompt='Communication is still running. Stop communication before loading settings!').exec():
                self.pluginManager.DeviceManager.closeCommunication()
            else:
                return
        super().loadSettings(file=file, default=default)

    def updateDataPath(self):
        if not self.pluginManager.loading:
            self.pluginManager.DeviceManager.closeCommunication(message='Stopping communication before changing data path.')
            self.updateSessionPath()
            self.pluginManager.Explorer.updateRoot(self.dataPath)

    def updateConfigPath(self): # load settings from new conf path
        self.defaultFile = self.configPath / self.confINI
        if not self.pluginManager.loading:
            self.pluginManager.DeviceManager.closeCommunication(message='Stopping communication before changing config path.')
            splash = EsibdCore.SplashScreen()
            splash.show()
            self.loadSettings(self.defaultFile)
            self.processEvents()
            self.pluginManager.DeviceManager.restoreConfiguration()
            if self.pluginManager.logger.active:
                self.pluginManager.logger.close() # release old log file
                self.pluginManager.logger.open() # continue logging in new location
            splash.close()

    def updatePluginPath(self):
        if EsibdCore.CloseDialog(title='Restart now', ok='Restart now.', prompt='Plugins will be updated on next restart.').exec():
            self.pluginManager.closePlugins(reload=True)

    def incrementMeasurementNumber(self):
        """increment without triggering event"""
        self.measurementNumber += 1
        self.settings[f'{self.SESSION}/{self.MEASUREMENTNUMBER}']._valueChanged = False # prevent event
        self.settings[f'{self.SESSION}/{self.MEASUREMENTNUMBER}'].settingEvent() # only save new value without triggering updateSessionPath

    def updateSessionPath(self, mesNum=0):
        """Updates the session path based on settings. Overwrite if you want to use different fields instead.

        :param mesNum: measurement number, defaults to 0
        :type mesNum: int, optional
        """
        if not self.pluginManager.loading:
            self.sessionPath = self.pathInputValidation(self.buildSessionPath())
            self.measurementNumber = mesNum
            self.print(f'Updated session path to {self.sessionPath}')

    def buildSessionPath(self):
        return Path(*[datetime.now().strftime('%Y-%m-%d_%H-%M')])

    def updateDPI(self):
        for plugin in self.pluginManager.plugins:
            if hasattr(plugin, 'fig') and plugin.fig is not None:
                plugin.fig.set_dpi(getDPI())
                plugin.plot()

    def getFullSessionPath(self):
        fullSessionPath = Path(*[self.dataPath, self.sessionPath])
        fullSessionPath.mkdir(parents=True, exist_ok=True) # create if not already existing
        return fullSessionPath

    def getMeasurementFileName(self, extension):
        return self.getFullSessionPath() / f'{self.getFullSessionPath().name}_{self.measurementNumber:03d}{extension}'

    def componentInputValidation(self, c):
        illegal_characters = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
        return ''.join(char if char not in illegal_characters else '_' for char in c)

    def pathInputValidation(self, path):
        return Path(*[self.componentInputValidation(part) for part in path.parts])

    # def close(self):
    #     """:meta private:"""
    #     self.saveSettings(default=True) # not needed, settings are saved instantly when changed
    #     super().close()

class DeviceManager(Plugin):
    """The device manager, by default located below the :ref:`sec:live_displays`, bundles
    functionality of devices and thus allows to initialize, start, and stop
    data acquisition from all devices with a single click. Ideally, plugins
    that control potentially dangerous hardware like power supplies, cryo
    coolers, or vacuum valves should add a status icon to the instrument
    manager, so that their status is visible at all times and they can be
    shut down quickly, even when the corresponding plugin tab is is not
    selected. Internally, the device manager also serves as a
    central interface to all data channels, independent of the devices they
    belong to, making it easy to setup collection of any number of output
    signals as a function of any number of input signals."""
    documentation = """The device manager, by default located below the live displays, bundles
    functionality of devices and thus allows to initialize, start, and stop
    data acquisition from all devices with a single click. Ideally, plugins
    that control potentially dangerous hardware like power supplies, cryo
    coolers, or vacuum valves should add a status icon to the instrument
    manager, so that their status is visible at all times and they can be
    shut down quickly, even when the corresponding plugin tab is is not
    selected. Internally, the device manager also serves as a
    central interface to all data channels, independent of the devices they
    belong to, making it easy to setup collection of any output
    signals as a function of any input signals."""

    name = 'DeviceManager'
    version = '1.0'
    pluginType = PluginManager.TYPE.DEVICEMGR
    previewFileTypes = ['_combi.dat.h5']
    optional = False
    iconFile = 'DeviceManager.png'
    useAdvancedOptions = True

    class SignalCommunicate(Plugin.SignalCommunicate):
        """Object that bundles pyqtSignals."""
        storeSignal = pyqtSignal()
        """Signal that triggers storage of device data."""
        closeCommunicationSignal = pyqtSignal()
        """Signal that triggers stop communication."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.dataThread = None
        self._recording = False
        self.signalComm.storeSignal.connect(self.store)
        self.signalComm.closeCommunicationSignal.connect(self.closeCommunication)

    def initGUI(self):
        """:meta private:"""
        super().initGUI()
        self.importAction = self.addAction(lambda: self.loadConfiguration(file=None), 'Import all device channels and values.', icon=self.makeCoreIcon('blue-folder-import.png'))
        self.importAction.setVisible(False)
        self.exportAction = self.addAction(event=lambda: self.exportOutputData(), toolTip='Save all visible history and all channels to current session.', icon=self.makeCoreIcon('database-export.png')) # pylint: disable=unnecessary-lambda
        self.closeCommunicationAction = self.addAction(event=lambda: self.closeCommunication(manual=True), toolTip='Close all communication.', icon=self.makeCoreIcon('stop.png'))
        self.addAction(event=lambda: self.initializeCommunication(), toolTip='Initialize all communication.', icon=self.makeCoreIcon('rocket-fly.png'))
        # lambda needed to avoid "checked" parameter passed by QAction
        self.recordingAction = self.addStateAction(event=lambda: self.toggleRecording(), toolTipFalse='Start all data acquisition.',
                                                iconFalse=self.makeCoreIcon('play.png'), toolTipTrue='Stop all data acquisition.', iconTrue=self.makeCoreIcon('pause.png'))

    def initDock(self):
        """:meta private:"""
        super().initDock()
        self.dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures) # not floatable or movable
        self.dock.setMaximumHeight(22) # GUI will only consist of titleBar

    def finalizeInit(self, aboutFunc=None):
        """:meta private:"""
        self.requiredPlugin('Settings')
        self.globalUpdate(True)
        if hasattr(self.pluginManager, 'Settings') and self.pluginManager.Settings.sessionPath == '': # keep existing session path when restarting
            self.pluginManager.Settings.updateSessionPath()
        super().finalizeInit(aboutFunc)
        self.floatAction.deleteLater()
        delattr(self, 'floatAction')
        if hasattr(self, 'titleBarLabel'):
            self.titleBarLabel.deleteLater()
            self.titleBarLabel = None
        self.toggleTitleBarDelayed() # Label not needed for DeviceManager
        self.timer = QTimer()
        self.timer.timeout.connect(self.store)
        self.timer.setInterval(3600000) # every 1 hour
        self.timer.start()

    def afterFinalizeInit(self):
        super().afterFinalizeInit()
        self.videoRecorderAction.toolTipFalse = f'Record video of {PROGRAM_NAME}.'
        self.videoRecorderAction.toolTipTrue = f'Stop and save video of {PROGRAM_NAME}.'
        self.videoRecorderAction.setToolTip(self.videoRecorderAction.toolTipFalse)
        self.videoRecorder.recordWidget = self.pluginManager.mainWindow # record entire window

    def toggleAdvanced(self, advanced=None):
        self.importAction.setVisible(self.advancedAction.state)

    def loadConfiguration(self, file=None):
        if self.initialized():
            if EsibdCore.CloseDialog(title='Stop communication?', ok='Stop communication', prompt='Communication is still running. Stop communication before loading all configurations!').exec():
                self.closeCommunication()
            else:
                return
        file = Path(QFileDialog.getOpenFileName(parent=None, caption=SELECTFILE, filter=self.FILTER_INI_H5,
                    directory=self.pluginManager.Settings.getFullSessionPath().as_posix())[0])
        first=True
        for plugin in self.pluginManager.getPluginsByClass(ChannelManager):
            load = False
            with h5py.File(name=file, mode='r', track_order=True) as h5file:
                if plugin.name in h5file:
                    load=True
            if load:
                plugin.loadConfiguration(file=file, append=not first)
                first = False

    def runTestParallel(self):
        """:meta private:"""
        self.testControl(self.recordingAction, True, 3) # even in test mode initialization time of up to 2 seconds is simulated
        self.testControl(self.exportAction, True)#, 2
        for plugin in self.pluginManager.getPluginsByClass(ChannelManager):
            if plugin.useDisplays:
                initialState = plugin.toggleLiveDisplayAction.state
                self.testControl(plugin.toggleLiveDisplayAction, True, 1)
                if self.waitForCondition(condition=lambda: plugin.liveDisplayActive() and hasattr(plugin.liveDisplay, 'displayTimeComboBox'),
                                         timeoutMessage=f'live display of {plugin.name}.', timeout=10):
                    self.testControl(plugin.liveDisplay.displayTimeComboBox, 1)
                    # self.testControl(plugin.liveDisplay.videoRecorderAction, True)
                    plugin.liveDisplay.runTestParallel()
                    # if self.pluginManager.Settings.showVideoRecorders:
                    #     time.sleep(5) # record for 5 seconds
                    # self.testControl(plugin.liveDisplay.videoRecorderAction, False)
                self.testControl(plugin.toggleLiveDisplayAction, initialState, 1)
        for scan in self.pluginManager.getPluginsByType(PluginManager.TYPE.SCAN):
            if not self.testing:
                break
            # has to run here while all plugins are recording
            self.print(f'Starting scan {scan.name}.')
            scan.raiseDock(True)
            self.testControl(scan.recordingAction, True)
            if self.waitForCondition(condition=lambda: scan.display is not None and hasattr(scan.display, 'videoRecorderAction'),
                                     timeoutMessage=f'display of {scan.name} scan.', timeout=10):
                # self.testControl(scan.display.videoRecorderAction, True)
                time.sleep(5) # scan for 5 seconds
                self.print(f'Stopping scan {scan.name}.')
                self.testControl(scan.recordingAction, False)
                # wait for scan to finish and save file before starting next one to avoid scans finishing at the same time
                self.waitForCondition(condition=lambda: scan.finished, timeoutMessage=f'stopping {scan.name} scan.', timeout=30)
                # self.testControl(scan.display.videoRecorderAction, False)
        self.testControl(self.closeCommunicationAction, True) # cannot use this as it requires user interaction to confirm prompt
        super().runTestParallel()

    @property
    def recording(self):
        return any([plugin.recording for plugin in self.pluginManager.getPluginsByClass(ChannelManager)] + [self._recording])
    @recording.setter
    def recording(self, recording):
        self._recording = recording
        # allow output widgets to react to change if acquisition state
        self.recordingAction.state = recording

    def initialized(self):
        if self.pluginManager.loading:
            return False
        else:
            return any([plugin.initialized() for plugin in self.pluginManager.getPluginsByClass(Device)])

    def loadData(self, file, _show=True):
        """:meta private:"""
        for device in self.getDevices():
            device.loadData(file, _show)

    def channels(self, inout=INOUT.BOTH): # flat list of all channels
        # 15% slower than using cached channels but avoids need to maintain cashed lists when removing and adding channels
        return [y for x in [device.getChannels() for device in self.getDevices(inout)] for y in x]

    def getChannelByName(self, name, inout=INOUT.BOTH):
        """Get channel based on unique name and type.

        :param name: Unique channel name.
        :type name: str
        :param inout: Type of channel, defaults to :attr:`~esibd.const.INOUT.BOTH`
        :type inout: :attr:`~esibd.const.INOUT`, optional
        :return: The requested channel.
        :rtype: :class:`~esibd.core.Channel`
        """
        return next((channel for channel in self.channels(inout) if channel.name.strip().lower() == name.strip().lower()), None)

    def getInitializedOutputChannels(self):
        return [y for x in [device.getInitializedChannels() for device in self.getOutputs()] for y in x]

    def getDevices(self, inout=INOUT.BOTH):
        if inout == INOUT.BOTH:
            return self.getInputs() + self.getOutputs()
        if inout == INOUT.ALL:
            return self.getInputs() + self.getOutputs() + self.getRelays()
        elif inout == INOUT.IN:
            return self.getInputs()
        else: # inout == INOUT.OUT:
            return self.getOutputs()

    def getInputs(self):
        return self.pluginManager.getPluginsByType(EsibdCore.PluginManager.TYPE.INPUTDEVICE)

    def getOutputs(self):
        return self.pluginManager.getPluginsByType(EsibdCore.PluginManager.TYPE.OUTPUTDEVICE)

    def getRelays(self):
        return self.pluginManager.getPluginsByType(EsibdCore.PluginManager.TYPE.CHANNELMANAGER)

    def getActiveLiveDisplays(self):
        return [plugin.liveDisplay for plugin in self.pluginManager.getPluginsByClass(ChannelManager) if plugin.liveDisplayActive()]

    def getActiveStaticDisplays(self):
        return [plugin.staticDisplay for plugin in self.pluginManager.getPluginsByClass(ChannelManager) if plugin.staticDisplayActive()]

    def getDefaultSettings(self):
        """:meta private:"""
        defaultSettings = super().getDefaultSettings()
        defaultSettings['Acquisition/Max display points'] = parameterDict(value=2000, toolTip='Maximum number of data points per channel used for plotting. Decrease if plotting is limiting performance.',
                                                                event=lambda: self.livePlot(apply=True), widgetType=Parameter.TYPE.INT, _min=100, _max=100000, attr='max_display_size')
        defaultSettings['Acquisition/Limit display points'] = parameterDict(value=True, toolTip="Number of displayed data points will be limited to 'Max display points'", widgetType=Parameter.TYPE.BOOL,
                                                               event=lambda: self.livePlot(apply=True), attr='limit_display_size')
        return defaultSettings

    def restoreConfiguration(self):
        for device in self.getDevices():
            device.loadConfiguration(default=True)
            self.processEvents()
        for scan in self.pluginManager.getPluginsByType(PluginManager.TYPE.SCAN):
            scan.loadSettings(default=True)
            self.processEvents()

    def clearPlot(self):
        for plugin in self.pluginManager.getPluginsByClass(ChannelManager):
            plugin.clearPlot()

    def livePlot(self, apply=False):
        for liveDisplay in self.getActiveLiveDisplays():
            liveDisplay.plot(apply)

    def stopRecording(self):
        if EsibdCore.CloseDialog(title='Stop all recording?', ok='Stop all recording', prompt='Stop recording on all devices? Active scans will be stopped.').exec():
            self.recording = False
            for liveDisplay in self.getActiveLiveDisplays():
                liveDisplay.parentPlugin.recording = False
            self.stopScans()
        elif self.recording:
            self.recordingAction.state = self.recording

    def closeCommunication(self, manual=False, closing=False, message='Stopping communication.'):
        """Close all communication

        :param manual: Indicates if triggered by user, defaults to False
        :type manual: bool, optional
        """
        if not self.initialized():
            return # already closed
        if not manual or self.testing or EsibdCore.CloseDialog(title='Close all communication?', ok='Close all communication', prompt='Close communication with all devices?').exec():
            self.print(message)
            self.recording = False
            self.stopScans(closing=closing)
            for plugin in self.pluginManager.getPluginsByClass(ChannelManager):
                plugin.closeCommunication()

    def stopScans(self, closing=False):
        for scan in self.pluginManager.getPluginsByType(PluginManager.TYPE.SCAN):
            scan.recording = False # stop all running scans
        if closing:
            for scan in self.pluginManager.getPluginsByType(PluginManager.TYPE.SCAN):
                if not scan.finished: # Give scan time to complete and save file. Avoid scan trying to access main GUI after it has been destroyed.
                    self.print(f'Waiting for {scan.name} to finish.')
                    self.waitForCondition(condition=lambda: scan.finished, timeoutMessage=f'stopping scan {scan.name}.', timeout=30, interval=0.5)

    @synchronized()
    def exportOutputData(self, file=None):
        self.pluginManager.Settings.incrementMeasurementNumber()
        if file is None:
            file = self.pluginManager.Settings.getMeasurementFileName(self.previewFileTypes[0])
        with h5py.File(name=file, mode=('a'), track_order=True) as h5File:
            self.hdfUpdateVersion(h5File)
            for liveDisplay in self.getActiveLiveDisplays():
                if hasattr(liveDisplay.parentPlugin, 'appendOutputData'):
                    liveDisplay.parentPlugin.appendOutputData(h5File)
        self.exportConfiguration(file=file) # save corresponding device settings in measurement file
        self.print(f'Saved {file.name}')
        self.pluginManager.Explorer.populateTree()

    def updateStaticPlot(self):
        for staticDisplay in self.getActiveStaticDisplays():
            staticDisplay.updateStaticPlot()

    def exportConfiguration(self, file=None, default=False, inout=INOUT.BOTH):
        for plugin in self.pluginManager.getPluginsByClass(ChannelManager):
            plugin.exportConfiguration(file=file, default=default)

    def initializeCommunication(self):
        for plugin in self.pluginManager.getPluginsByClass(ChannelManager):
            plugin.initializeCommunication()

    def globalUpdate(self, apply=False, inout=INOUT.BOTH):
        # wait until all channels are complete before applying logic. will be called again when loading completed
        if any([device.loading for device in self.getDevices(inout)]) or self.pluginManager.loading:
            return
        if inout in [INOUT.BOTH, INOUT.IN]:
            for device in self.getInputs():
                device.updateValues(apply=apply)
        if inout in [INOUT.BOTH, INOUT.OUT]:
            for device in self.getOutputs():
                device.updateValues()

    def store(self):
        """Regularly stores device settings and data to minimize loss in the event of a program crash."""
        # * Make sure that no GUI elements are accessed when running from parallel thread!
        # * deamon=True is not used to prevent the unlikely case where the thread is terminated half way through because the program is closing.
        # * scan and plugin settings are already saved as soon as they are changing
        for device in self.getDevices():
            if device.recording: # will be exported when program closes even if not recording, this is just for the regular exports while the program is running
                Thread(target=device.exportOutputData, kwargs={'default':True}, name=f'{device.name} exportOutputDataThread').start()

    @synchronized()
    def toggleRecording(self):
        """Toggle recording of data."""
        # Check for duplicate channel names before starting all devices.
        # Note that the same name can occur once as and input and once as an output even though this is discouraged.
        for inout, put in zip([INOUT.IN, INOUT.OUT],['input','output']):
            seen = set()
            dupes = [x for x in [channel.name for channel in self.channels(inout=inout)] if x in seen or seen.add(x)]
            if len(dupes) > 0:
                self.print(f"The following {put} channel names have been used more than once: {', '.join(dupes)}", PRINT.WARNING)
        for plugin in self.pluginManager.getPluginsByClass(ChannelManager):
            if hasattr(plugin, 'recordingAction'):
                plugin.toggleRecording(on=self.recordingAction.state, manual=False)

    def close(self):
        """:meta private:"""
        super().close()
        self.timer.stop()

class Notes(Plugin):
    """The Notes plugin can be used to add quick comments to a session or any other folder.
    The comments are saved in simple text files that are loaded automatically once a folder is opened again.
    They are intended to complement but not to replace a lab book."""

    name = 'Notes'
    pluginType = PluginManager.TYPE.DISPLAY
    version = '1.0'
    iconFile = 'notes.png'

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def initGUI(self):
        """:meta private:"""
        super().initGUI()
        self.editor = EsibdCore.TextEdit()
        self.editor.setFont(QFont('Courier', 10))
        self.numbers = EsibdCore.NumberBar(parent=self.editor)
        lay = QHBoxLayout()
        lay.addWidget(self.numbers)
        lay.addWidget(self.editor)
        self.addContentLayout(lay)

    def saveData(self, file, default=False):
        """Adds current notes to existing file."""
        if default:
            self.file = file / 'notes.txt'
            if self.editor.toPlainText() != '':
                with open(self.file, 'w', encoding = self.UTF8) as textFile:
                    textFile.write(self.editor.toPlainText())
        elif file.name.endswith(FILE_H5):
            with h5py.File(file, 'a', track_order=True) as h5file:
                h5py.get_config().track_order = True
                group = self.requireGroup(h5file, self.name)
                group.attrs[Parameter.VALUE] = self.editor.toPlainText()

    def loadData(self, file, _show=True):
        """:meta private:"""
        self.provideDock()
        self.editor.clear()
        self.file = file / 'notes.txt'
        if self.file.exists(): # load and display notes if found
            with open(self.file, encoding=self.UTF8) as dataFile:
                self.editor.insertPlainText(dataFile.read())
        self.editor.verticalScrollBar().triggerAction(QScrollBar.SliderAction.SliderToMinimum)   # scroll to top
        self.raiseDock(_show)

    def updateTheme(self):
        """:meta private:"""
        super().updateTheme()
        self.numbers.updateTheme()

class Explorer(Plugin):
    """The integrated file explorer is used to navigate all results and
    complementary data. All files can be accessed independently using the operating system
    file explorer, e.g., when working on a computer where *ESIBD Explorer*
    is not installed. However, the integrated explorer connects dedicated :ref:`sec:displays`
    to all files that were created with or are supported by *ESIBD
    Explorer*. All supported files are preceded with an icon that indicates
    which plugin will be used to display them. The :ref:`data path<data_path>`, current
    :ref:`session path<sec:session_settings>`, and a search bar are accessible directly from here. File system
    links or shortcuts are supported as well.

    The displays were made to simplify data analysis and documentation.
    They use dedicated and customizable views that allow saving images as
    files or sending them to the clipboard for sharing or documentation in a
    lab book. Right clicking supported files opens a context menu that allows
    to load settings and configurations directly. For example, a scan file
    does not only contain the scan data, but also allows to inspect and
    restore all experimental settings used to record it. Note that the
    context menu only allows to load device values, but the files contain
    the entire device configuration. To restore the device configuration
    based on a scan file, import the file from the device toolbar. A double
    click will open the file in the external default program.
    Use third party tools like `HDFView <https://www.hdfgroup.org/downloads/hdfview/>`_
    to view *.hdf* files independently.

    The explorer may also be useful for other applications beyond managing
    experimental data. For example, if you organize the documentation of the
    experimental setup in folders following the hierarchy of components and sub
    components, it allows you to quickly find the corresponding manuals and
    order numbers. In combination with the :ref:`sec:notes` plugin, you can add comments to
    each component that will be displayed automatically as soon as you
    enter the corresponding folder."""
    documentation = """The integrated file explorer is used to navigate all results and
    complementary data. All files can be accessed independently using the operating system
    file explorer, e.g., when working on a computer where ESIBD Explorer
    is not installed. However, the integrated explorer connects dedicated displays
    to all files that were created with or are supported by ESIBD
    Explorer. All supported files are preceded with an icon that indicates
    which plugin will be used to display them. The data path, current
    session_settings, and a search bar are accessible directly from here. File system
    links or shortcuts are supported as well.

    The displays were made to simplify data analysis and documentation.
    They use dedicated and customizable views that allow saving images as
    files or sending them to the clipboard for sharing or documentation in a
    lab book. Right clicking supported files opens a context menu that allows
    to load settings and configurations directly. For example, a scan file
    does not only contain the scan data, but also allows to inspect and
    restore all experimental settings used to record it. Note that the
    context menu only allows to load device values, but the files contain
    the entire device configuration. To restore the device configuration
    based on a scan file, import the file from the device toolbar. A double
    click will open the file in the external default program.
    Use third party tools like HDFView
    to view .hdf files independently.

    The explorer may also be useful for other applications beyond managing
    experimental data. For example, if you organize the documentation of the
    experimental setup in folders following the hierarchy of components and sub
    components, it allows you to quickly find the corresponding manuals and
    order numbers. In combination with the Notes plugin, you can add comments to
    each component that will be displayed automatically as soon as you
    enter the corresponding folder."""

    name='Explorer'
    version = '1.0'
    pluginType = PluginManager.TYPE.CONTROL
    previewFileTypes = ['.lnk']
    optional = False
    iconFile = 'folder.png'
    displayContentSignal = pyqtSignal()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.ICON_FOLDER         = self.makeCoreIcon('folder.png')
        self.ICON_HOME           = self.makeCoreIcon('home.png')
        self.ICON_SESSION        = self.makeCoreIcon('book-open-bookmark.png')
        self.ICON_DOCUMENT       = self.makeCoreIcon('document.png')
        self.ICON_BACKWARD       = self.makeCoreIcon('arrow-180.png')
        self.ICON_FORWARD        = self.makeCoreIcon('arrow.png')
        self.ICON_UP             = self.makeCoreIcon('arrow-090.png')
        self.ICON_BACKWARD_GRAY  = self.makeCoreIcon('arrow_gray-180.png')
        self.ICON_FORWARD_GRAY   = self.makeCoreIcon('arrow_gray.png')
        self.ICON_UP_GRAY        = self.makeCoreIcon('arrow_gray-090.png')
        self.ICON_REFRESH        = self.makeCoreIcon('arrow-circle-315.png')
        self.ICON_BROWSE         = self.makeCoreIcon('folder-horizontal-open.png')
        self.activeFileFullPath = None
        self.history = []
        self.indexHistory = 0
        self.root = None
        self.notesFile = None
        self.displayContentSignal.connect(self.displayContent)
        self.populating = False
        self.loadingContent = False

    def initGUI(self):
        """:meta private:"""
        super().initGUI()
        self.tree = QTreeWidget()
        self.addContentWidget(self.tree)
        self.tree.currentItemChanged.connect(self.treeItemClicked)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.initExplorerContextMenu)
        self.tree.itemDoubleClicked.connect(self.treeItemDoubleClicked)
        self.tree.itemExpanded.connect(self.expandDir)
        self.tree.setHeaderHidden(True)

        self.backAction = self.addAction(self.backward, 'Backward', icon=self.ICON_BACKWARD)
        self.forwardAction = self.addAction(self.forward, 'Forward', icon=self.ICON_FORWARD)
        self.upAction = self.addAction(self.up, 'Up', icon=self.ICON_UP)
        self.refreshAction = self.addAction(lambda: self.populateTree(clear=False), 'Refresh', icon=self.ICON_REFRESH)
        self.dataPathAction = self.addAction(self.goToDataPath, 'Go to data path.', icon=self.ICON_HOME)

        self.currentDirLineEdit = QLineEdit()
        self.currentDirLineEdit.returnPressed.connect(self.updateCurDirFromLineEdit)
        self.currentDirLineEdit.setMinimumWidth(50)
        self.currentDirLineEdit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.titleBar.addWidget(self.currentDirLineEdit)

        self.browseAction = self.addAction(self.browseDir, 'Select folder.', icon=self.ICON_BROWSE)
        self.sessionAction = self.addAction(self.goToCurrentSession, 'Go to current session.', icon=self.ICON_SESSION)

        self.filterLineEdit = QLineEdit()
        self.filterLineEdit.setMaximumWidth(100)
        self.filterLineEdit.setMinimumWidth(50)
        self.filterLineEdit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.filterLineEdit.textChanged.connect(lambda: self.populateTree(clear=False))
        self.filterLineEdit.setPlaceholderText('Search')
        self.titleBar.addWidget(self.filterLineEdit)

        findShortcut = QShortcut(QKeySequence('Ctrl+F'), self)
        findShortcut.activated.connect(self.filterLineEdit.setFocus)

    def finalizeInit(self, aboutFunc=None):
        """:meta private:"""
        # Load directory after all other plugins loaded, to allow use icons for supported files
        self.updateRoot(self.pluginManager.Settings.dataPath, addHistory=True, loading=True) # do not trigger populate tree here, will be done when updating theme
        super().finalizeInit(aboutFunc)
        self.stretch.deleteLater()

    def runTestParallel(self):
        """:meta private:"""
        for action in [self.sessionAction, self.upAction, self.backAction, self.forwardAction, self.dataPathAction, self.refreshAction]:
            if not self.testing:
                break
            self.populating = True
            self.testControl(action, True)
            self.waitForCondition(condition=lambda: not self.populating, timeoutMessage=f'testing {action.objectName()}')
            # NOTE: using self.populating flag makes sure further test are only run after populating has completed. using locks and signals is more error prone
        testDir = self.pluginManager.Settings.dataPath / 'test_files'
        if testDir.exists():
            for file in testDir.iterdir():
                if not file.is_dir():
                    if not self.testing:
                        break
                    self.print(f"Loading file {shorten_text(file.name, 50)}.")
                    self.activeFileFullPath = file
                    self.displayContentSignal.emit() # call displayContent in main thread
                    self.loadingContent = True
                    self.waitForCondition(condition=lambda: not self.loadingContent, timeoutMessage=f'displaying content of {self.activeFileFullPath.name}')
        else:
            self.print(f'Could not find {testDir.as_posix()}. Please create and fill with files that should be loaded during testing.', flag=PRINT.WARNING)
        super().runTestParallel()

    def loadData(self, file, _show=True):
        """:meta private:"""
        self.provideDock()
        target = Path('')
        if sys.platform == "Linux":
            target = Path(os.path.realpath(str(file)))
        elif sys.platform == 'win32':
            shell = win32com.client.Dispatch("WScript.Shell")
            target = Path(shell.CreateShortCut(str(file)).Targetpath)
        if target.is_dir():
            self.updateRoot(target, addHistory=True)
        self.raiseDock(_show)
        # except:
        #     self.print(f'Error: cant open directory {target}')

    def LOADSETTINGS(self, p):
        if p.pluginType in [PluginManager.TYPE.INPUTDEVICE, PluginManager.TYPE.OUTPUTDEVICE]:
            return f'Load {p.name} channels.'
        else: # PLUGINSCAN, ...
            return f'Load {p.name} settings.'

    LOADALLVALUES = 'Load all device values.'

    def initExplorerContextMenu(self, pos):
        """Context menu for items in Explorer"""
        item = self.tree.itemAt(pos)
        if item is None:
            return
        openDirAction = None
        openContainingDirAction = None
        openFileAction = None
        deleteFileAction = None
        copyFileNameAction = None
        copyFullPathAction = None
        copyFolderNameAction = None
        runPythonCodeAction = None
        copyPlotCodeAction = None
        loadValuesActions = []
        loadSettingsActions = []
        explorerContextMenu = QMenu(self.tree)
        if self.getItemFullPath(item).is_dir(): # actions for folders
            openDirAction = explorerContextMenu.addAction('Open folder in file explorer.')
            deleteFileAction = explorerContextMenu.addAction('Move folder to recycle bin.')
            copyFolderNameAction = explorerContextMenu.addAction('Copy folder name to clipboard.')
        else:
            openContainingDirAction = explorerContextMenu.addAction('Open containing folder in file explorer.')
            openFileAction = explorerContextMenu.addAction('Open with default program.')
            copyFileNameAction = explorerContextMenu.addAction('Copy file name to clipboard.')
            copyFullPathAction = explorerContextMenu.addAction('Copy full file path to clipboard.')
            deleteFileAction = explorerContextMenu.addAction('Move to recycle bin.')
            if self.activeFileFullPath.suffix == FILE_H5:
                try:
                    with h5py.File(name=self.activeFileFullPath, mode='r') as h5File:
                        for device in self.pluginManager.DeviceManager.getDevices():
                            if device.name in h5File and device.pluginType == PluginManager.TYPE.INPUTDEVICE:
                                loadValuesActions.append(explorerContextMenu.addAction(device.LOADVALUES))
                        if len(loadValuesActions) > 1:
                            loadAllValuesAction = QAction(self.LOADALLVALUES)
                            explorerContextMenu.insertAction(loadValuesActions[0], loadAllValuesAction)
                            loadValuesActions.insert(0, loadAllValuesAction)
                        for plugin in self.pluginManager.getMainPlugins():
                            if plugin.pluginType == PluginManager.TYPE.SCAN and plugin.name in h5File: # not used very frequently for devices -> only show for scans
                                loadSettingsActions.append(explorerContextMenu.addAction(self.LOADSETTINGS(plugin)))
                except OSError:
                    self.print(f'Could not identify file type of {self.activeFileFullPath.name}', PRINT.ERROR)

                for device in self.pluginManager.DeviceManager.getDevices():
                    if device.liveDisplay.supportsFile(self.activeFileFullPath):
                        copyPlotCodeAction = explorerContextMenu.addAction(f'Generate {device.name} plot file.')
                        break # only use first match
                for scan in self.pluginManager.getPluginsByType(PluginManager.TYPE.SCAN):
                    if scan.supportsFile(self.activeFileFullPath):
                        copyPlotCodeAction = explorerContextMenu.addAction(f'Generate {scan.name} plot file.')
                        break # only use first match
            elif self.activeFileFullPath.suffix == FILE_INI:
                confParser = configparser.ConfigParser()
                try:
                    confParser.read(self.activeFileFullPath)
                    fileType = confParser[INFO][Parameter.NAME]
                except KeyError:
                    self.print(f'Could not identify file type of {self.activeFileFullPath.name}', PRINT.ERROR)
                else: # no exception
                    if fileType == self.pluginManager.Settings.name:
                        loadSettingsActions.append(explorerContextMenu.addAction(self.pluginManager.Settings.loadGeneralSettings))
                    else:
                        for device in self.pluginManager.DeviceManager.getDevices(inout = INOUT.IN):
                            if device.name == fileType:
                                loadValuesActions.append(explorerContextMenu.addAction(device.LOADVALUES))
            elif self.activeFileFullPath.suffix == FILE_PY:
                runPythonCodeAction = explorerContextMenu.addAction('Run file in python.')
            else:
                for display in self.pluginManager.getPluginsByType(PluginManager.TYPE.DISPLAY):
                    if display.supportsFile(self.activeFileFullPath) and hasattr(display, 'generatePythonPlotCode'):
                        copyPlotCodeAction = explorerContextMenu.addAction(f'Generate {display.name} plot file.')
                        break # only use first match

        explorerContextMenuAction = explorerContextMenu.exec(self.tree.mapToGlobal(pos))
        if explorerContextMenuAction is not None:
            if explorerContextMenuAction is openContainingDirAction:
                openInDefaultApplication(self.activeFileFullPath.parent)
            elif explorerContextMenuAction is openDirAction:
                openInDefaultApplication(self.getItemFullPath(item))
            elif explorerContextMenuAction is openFileAction:
                openInDefaultApplication(self.activeFileFullPath)
            elif explorerContextMenuAction is copyFileNameAction:
                pyperclip.copy(self.activeFileFullPath.name)
            elif explorerContextMenuAction is copyFullPathAction:
                pyperclip.copy(self.activeFileFullPath.as_posix())
            elif explorerContextMenuAction is copyFolderNameAction:
                pyperclip.copy(self.getItemFullPath(item).name)
            elif explorerContextMenuAction is deleteFileAction:
                send2trash(self.tree.selectedItems()[0].path_info)
                self.populateTree(clear=False)
            elif explorerContextMenuAction is runPythonCodeAction:
                self.pluginManager.Console.execute(f"Module = EsibdCore.dynamicImport('ModuleName','{self.activeFileFullPath.as_posix()}')")
            elif explorerContextMenuAction is copyPlotCodeAction:
                for device in self.pluginManager.DeviceManager.getDevices():
                    if device.liveDisplay.supportsFile(self.activeFileFullPath):
                        device.staticDisplay.generatePythonPlotCode()
                        self.populateTree(clear=False)
                        break # only use first match
                for scan in self.pluginManager.getPluginsByType(PluginManager.TYPE.SCAN):
                    if scan.supportsFile(self.activeFileFullPath):
                        scan.generatePythonPlotCode()
                        self.populateTree(clear=False)
                        break # only use first match
                for display in self.pluginManager.getPluginsByType(PluginManager.TYPE.DISPLAY):
                    if display.supportsFile(self.activeFileFullPath) and hasattr(display, 'generatePythonPlotCode'):
                        display.generatePythonPlotCode()
                        self.populateTree(clear=False)
                        break # only use first match
            elif explorerContextMenuAction in loadSettingsActions:
                for plugin in self.pluginManager.getMainPlugins():
                    if explorerContextMenuAction.text() == self.LOADSETTINGS(plugin):
                        plugin.loadSettings(file=self.activeFileFullPath)
            if explorerContextMenuAction in loadValuesActions:
                if explorerContextMenuAction.text() == self.pluginManager.Settings.loadGeneralSettings:
                    self.pluginManager.Settings.loadSettings(file=self.activeFileFullPath)
                elif explorerContextMenuAction.text() == self.LOADALLVALUES:
                    first = True
                    with h5py.File(name=self.activeFileFullPath, mode='r') as h5File:
                        for device in self.pluginManager.DeviceManager.getDevices():
                            if device.name in h5File and device.pluginType == PluginManager.TYPE.INPUTDEVICE:
                                device.loadValues(self.activeFileFullPath, append=not first)
                                first = False
                else:
                    for device in self.pluginManager.DeviceManager.getDevices(inout=INOUT.IN):
                        if explorerContextMenuAction.text() == device.LOADVALUES:
                            device.loadValues(self.activeFileFullPath)

    def treeItemDoubleClicked(self, item, _):
        if self.getItemFullPath(item).is_dir():
            self.updateRoot(self.getItemFullPath(item), addHistory=True)
        else: # treeItemDoubleClicked
            openInDefaultApplication(self.activeFileFullPath)

    def getItemFullPath(self, item):
        out = item.text(0)
        if item.parent():
            out = self.getItemFullPath(item.parent()) / out
        else:
            out = self.root / out
        return out

    def up(self):
        newRoot = Path(self.root).parent.resolve()
        self.updateRoot(newRoot, addHistory=True)

    def forward(self):
        self.indexHistory = min(self.indexHistory + 1, len(self.history)-1)
        self.updateRoot(self.history[self.indexHistory])

    def backward(self):
        self.indexHistory = max(self.indexHistory - 1, 0)
        self.updateRoot(self.history[self.indexHistory])

    def updateRoot(self, newRoot, addHistory = False, loading=False):
        self.rootChanging(self.root, newRoot)
        self.root = Path(newRoot)
        if addHistory:
            del self.history[self.indexHistory+1:] # remove voided forward options
            self.history.append(self.root)
            self.indexHistory = len(self.history)-1
        self.currentDirLineEdit.setText(self.root.as_posix())
        if not loading:
            self.populateTree(clear = True)

    @synchronized()
    def populateTree(self, clear=False):
        """Populates or updates fileTree."""
        self.populating = True
        for action in [self.backAction, self.forwardAction, self.upAction, self.refreshAction]:
            action.setEnabled(False)
        if clear: # otherwise existing tree will be updated (much more efficient)
            self.tree.clear()
        # update navigation arrows
        if self.indexHistory == len(self.history)-1:
            self.forwardAction.setIcon(self.ICON_FORWARD_GRAY)
        else:
            self.forwardAction.setIcon(self.ICON_FORWARD)
        if self.indexHistory == 0:
            self.backAction.setIcon(self.ICON_BACKWARD_GRAY)
        else:
            self.backAction.setIcon(self.ICON_BACKWARD)
        if self.root.parent == self.root: # no parent
            self.upAction.setIcon(self.ICON_UP_GRAY)
        else:
            self.upAction.setIcon(self.ICON_UP)

        self.load_project_structure(startPath=self.root, tree=self.tree.invisibleRootItem(), _filter=self.filterLineEdit.text(), clear=clear) # populate tree widget

        it = QTreeWidgetItemIterator(self.tree, QTreeWidgetItemIterator.IteratorFlag.HasChildren)
        while it.value():
            if it.value().isExpanded():
                self.load_project_structure(startPath=it.value().path_info, tree=it.value(), _filter=self.filterLineEdit.text(), clear=clear) # populate expanded dirs, independent of recursion depth
            it +=1
        self.populating = False
        for action in [self.backAction, self.forwardAction, self.upAction, self.refreshAction]:
            action.setEnabled(True)

    def browseDir(self):
        newPath = Path(QFileDialog.getExistingDirectory(parent=None, caption=SELECTPATH, directory=self.root.as_posix(),
                                                        options=QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontResolveSymlinks))
        if newPath != Path('.'):
            self.updateRoot(newPath, addHistory=True)

    def goToCurrentSession(self):
        self.updateRoot(self.pluginManager.Settings.getFullSessionPath(), addHistory=True)

    def goToDataPath(self):
        self.updateRoot(self.pluginManager.Settings.dataPath, addHistory=True)

    def updateCurDirFromLineEdit(self):
        path = Path(self.currentDirLineEdit.text())
        if path.exists():
            self.updateRoot(path, addHistory=True)
        else:
            self.print(f'Could not find directory: {path}', PRINT.ERROR)

    def treeItemClicked(self, item):
        if item is not None and not self.getItemFullPath(item).is_dir():
            if self.loadingContent:
                self.print(f'Ignoring {self.getItemFullPath(item).name} while loading {self.activeFileFullPath.name}')
                return
            self.activeFileFullPath = self.getItemFullPath(item)
            self.displayContent()
        # else:
            # item.setExpanded(not item.isExpanded()) # already implemented for double click

    def displayContent(self):
        """General wrapper for handling of files with different format.
        If a file format supported by a plugin is detected (including backwards compatible formats) the data will be loaded and shown in the corresponding view.
        Handling for a few general formats is implemented as well.
        For text based formats the text is also shown in the Text tab for quick access if needed.
        The actual handling is redirected to dedicated methods."""
        if self.populating: # avoid trigger display during filtering
            return
        self.loadingContent = True # avoid changing activeFileFullPath while previous file is still loading
        handled = False
        try:
            for plugin in [plugin for plugin in self.pluginManager.plugins if plugin.supportsFile(self.activeFileFullPath)]:
                message = f'displayContent {self.activeFileFullPath.name} using {plugin.name}'
                self.print(shorten_text(message, 86), flag=PRINT.DEBUG)
                plugin.loadData(file=self.activeFileFullPath, _show=not handled) # after widget is visible to make sure it is drawn properly
                handled = True # display first widget that supports file (others like tree or text come later and are optional)
            if not handled:
                message = f'No preview available for this type of {self.activeFileFullPath.suffix} file. Consider activating, implementing, or requesting a plugin.'
                self.print(message)
                self.pluginManager.Text.setText(message, True)
        finally:
            self.loadingContent = False

    def load_project_structure(self, startPath, tree, _filter, recursionDepth=2, clear=False):
        """from https://stackoverflow.com/questions/5144830/how-to-create-folder-view-in-pyqt-inside-main-window
        recursively maps the file structure into the internal explorer
        Note that recursion depth of 2 assures fast indexing. Deeper levels will be indexed as they are expanded.
        Data from multiple sessions can be accessed from the data path level by expanding the tree.
        Recursion depth of more than 2 can lead to very long loading times"""
        self.processEvents()
        # self.tree.update() does not update GUI before completion of event loop
        if recursionDepth == 0: # limit depth to avoid indexing entire storage (can take minutes)
            return
        recursionDepth = recursionDepth - 1
        if startPath.is_dir():
            # List of directories only
            dirlist = []
            for x in startPath.iterdir():
                try:
                    if (startPath / x).is_dir() and not any(x.name.startswith(sym) for sym in ['.','$']):
                        [y for y in (startPath / x).iterdir()] # pylint: disable = expression-not-assigned # raises PermissionError if access is denied, need to use iterator to trigger access
                        dirlist.append(x)
                except PermissionError as e:
                    self.print(f'{e}')
                    continue # skip directories that we cannot access
            # List of files only
            filelist = [x for x in startPath.iterdir() if not (startPath / x).is_dir() and not x.name.startswith('.')]

            children = [tree.child(i) for i in range(tree.childCount())] # list of existing children
            children_text = [child.text(0) for child in children]
            for element in dirlist: # add all dirs first, then all files
                path_info = startPath / element
                if element.name in children_text: # reuse existing
                    parent_itm = tree.child(children_text.index(element.name))
                else: # add new
                    parent_itm = QTreeWidgetItem(tree,[element.name])
                    parent_itm.path_info = path_info
                    parent_itm.setIcon(0, self.ICON_FOLDER)
                self.load_project_structure(startPath=path_info, tree=parent_itm, _filter=_filter, recursionDepth=recursionDepth, clear=clear)
            for element in [element for element in filelist if ((_filter is None or _filter == "" or _filter.lower() in element.name.lower()) and element.name not in children_text)]:
                # don't add files that do not match _filter and only add elements that do not exist already
                if clear: # add all items alphabetically
                    parent_itm = QTreeWidgetItem(tree,[element.name])
                else: # insert new items at alphabetically correct position
                    parent_itm = QTreeWidgetItem(None,[element.name])
                    index = next((children_text.index(child_text) for child_text in children_text if child_text > element.name), len(children_text))
                    tree.insertChild(index, parent_itm)
                    children_text.insert(index, element.name)
                parent_itm.path_info = startPath / element
                parent_itm.setIcon(0, self.getFileIcon(element))
            for child in children:
                if not (startPath / child.text(0)).exists():
                    tree.removeChild(child) # remove if does not exist anymore
                if (startPath / child.text(0)).is_file() and _filter is not None and _filter != "" and _filter.lower() not in child.text(0).lower():
                    tree.removeChild(child) # remove files if they do not match filter
        else:
            self.print(f'{startPath} is not a valid directory', PRINT.ERROR)

    def getFileIcon(self, file):
        plugin = next((plugin for plugin in self.pluginManager.plugins if plugin.supportsFile(file) if plugin not in [self.pluginManager.Tree, self.pluginManager.Text]), None)
        if plugin is None: # only use Tree or Text if no other supporting Plugin has been found
            plugin = next((plugin for plugin in self.pluginManager.plugins if plugin.supportsFile(file)), None)
        if plugin is not None:
            return plugin.getIcon()
        else:
            return self.ICON_DOCUMENT

    def expandDir(self, _dir):
        self.load_project_structure(startPath=_dir.path_info, tree=_dir, _filter=self.filterLineEdit.text())
        _dir.setExpanded(True)

    def rootChanging(self, oldRoot, newRoot):
        if hasattr(self.pluginManager, 'Notes'):
            # save old notes
            if oldRoot is not None:
                self.pluginManager.Notes.saveData(oldRoot, default=True)
            if newRoot is not None: # None on program closing
                self.pluginManager.Notes.loadData(newRoot, _show=False)

    def close(self):
        """:meta private:"""
        super().close()
        self.rootChanging(self.pluginManager.Explorer.root, None)

    def updateTheme(self):
        """:meta private:"""
        super().updateTheme()
        self.populateTree(clear=True)

class UCM(ChannelManager):
    """Unified Channel Manager (UCM) allows to specify a custom list of channels from all :class:`devices<esibd.plugins.Device>`.
    This allows to have the most relevant controls and information in one place.
    All logic remains within the corresponding device plugins. This is just an interface!
    To get started, simply add channels and name them after existing channels from other devices."""
    documentation = """Unified Channel Manager (UCM) allows to specify a custom list of channels from all devices.
    This allows to have the most relevant controls and information in one place.
    All logic remains within the corresponding device plugins. This is just an interface!
    To get started, simply add channels and name them after existing channels from other devices."""

    name='UCM'
    version = '1.0'
    pluginType = PluginManager.TYPE.CHANNELMANAGER
    previewFileTypes = []
    optional = True
    inout = INOUT.NONE
    maxDataPoints = 0 # UCM channels do not store data
    useMonitors = True
    iconFile = 'UCM.png'

    class UCMChannel(RelayChannel, Channel):
        """Minimal UI for abstract channel."""

        sourceChannel = None
        DEVICE   = 'Device'

        def connectSource(self):
            self.removeEvents() # free up previously used channel if applicable
            sources = [channel for channel in self.device.pluginManager.DeviceManager.channels(inout=INOUT.ALL)
                       if channel not in self.device.getChannels()
                       and channel.name.strip().lower() == self.name.strip().lower()]
            if len(sources) == 0:
                self.sourceChannel = None
                self.getValues = None
                self.notes = f'Could not find {self.name}'
                self.getParameterByName(self.DEVICE).getWidget().setIcon(self.device.makeCoreIcon('help_large_dark.png' if getDarkMode() else 'help_large.png'))
                self.getParameterByName(self.DEVICE).getWidget().setToolTip('Source: Unknown')
                self.getParameterByName(self.VALUE).getWidget().setVisible(False) # value not needed (no setValues)
                self.getParameterByName(self.MONITOR).getWidget().setVisible(False) # monitor not needed
            else:
                self.sourceChannel = sources[0]
                self.getParameterByName(self.DEVICE).getWidget().setIcon(self.sourceChannel.getDevice().getIcon())
                self.getParameterByName(self.DEVICE).getWidget().setToolTip(f'Source: {self.sourceChannel.device.name}')
                self.notes = f'Source: {self.sourceChannel.device.name}.{self.sourceChannel.name}'
                if len(sources) > 1:
                    self.print(f'More than one channel named {self.name}. Using {self.sourceChannel.getDevice().name}.{self.sourceChannel.name}. Use unique names to avoid this.', PRINT.WARNING)

                self.getValues = self.sourceChannel.getValues
                value = self.getParameterByName(self.VALUE)
                value.widgetType = self.sourceChannel.getParameterByName(self.VALUE).widgetType
                value.indicator = self.sourceChannel.getParameterByName(self.VALUE).indicator
                if self.MIN in self.sourceChannel.displayedParameters:
                    value.min = self.sourceChannel.getParameterByName(self.MIN).value
                    value.max = self.sourceChannel.getParameterByName(self.MAX).value
                value.applyWidget()
                if hasattr(self.sourceChannel.getDevice(), self.UNIT.lower()):
                    self.unit = self.sourceChannel.getDevice().unit
                elif hasattr(self.sourceChannel, self.UNIT.lower()):
                    self.unit = self.sourceChannel.unit
                else:
                    self.unit = ''
                if self.sourceChannel.useMonitors:
                    # show value and monitor
                    self.getParameterByName(self.MONITOR).widgetType = self.sourceChannel.getParameterByName(self.MONITOR).widgetType
                    self.getParameterByName(self.MONITOR).applyWidget()
                    self.getParameterByName(self.MONITOR).getWidget().setVisible(self.sourceChannel.real)
                    self.getParameterByName(self.VALUE).getWidget().setVisible(True)
                elif self.sourceChannel.inout == INOUT.OUT:
                    # only show value as monitor
                    self.getParameterByName(self.MONITOR).widgetType = self.sourceChannel.getParameterByName(self.VALUE).widgetType
                    self.getParameterByName(self.MONITOR).applyWidget()
                    self.getParameterByName(self.VALUE).getWidget().setVisible(False) # value not needed (no setValues)
                else:
                    # only show value
                    # self.getParameterByName(self.VALUE).getWidget().setVisible(False)
                    self.getParameterByName(self.MONITOR).getWidget().setVisible(False) # monitor not needed

                self.getSourceChannelValues()
                self.sourceChannel.getParameterByName(self.VALUE).extraEvents.append(self.relayValueEvent)
                if self.sourceChannel.useMonitors:
                    self.sourceChannel.getParameterByName(self.MONITOR).extraEvents.append(self.relayMonitorEvent)
                for parameterName in [self.LINEWIDTH, self.LINESTYLE, self.COLOR]:
                    if parameterName in self.sourceChannel.displayedParameters:
                        self.sourceChannel.getParameterByName(parameterName).extraEvents.append(self.updateDisplay)
            self.updateColor()
            self.scalingChanged()

        def setSourceChannelValue(self):
            if self.sourceChannel is not None:
                try:
                    self.sourceChannel.value = self.value
                except RuntimeError as e:
                    self.print(f'Error on updating {self.name}: {e}', PRINT.ERROR)
                    self.sourceChannel = None
                    self.connectSource()

        def relayValueEvent(self):
            if self.sourceChannel is not None:
                try:
                    value = self.sourceChannel.value - self.sourceChannel.background if self.sourceChannel.getDevice().subtractBackgroundActive() else self.sourceChannel.value
                    if self.sourceChannel.inout == INOUT.OUT:
                        self.monitor = value
                    else:
                        self.value = value
                except RuntimeError:
                    self.removeEvents()

        def relayMonitorEvent(self):
            if self.sourceChannel is not None:
                try:
                    self.monitor = self.sourceChannel.monitor
                    self.getParameterByName(self.MONITOR).getWidget().setStyleSheet(self.sourceChannel.getParameterByName(self.MONITOR).getWidget().styleSheet())
                except RuntimeError:
                    self.removeEvents()

        def monitorChanged(self):
            pass

        def getSourceChannelValues(self):
            if self.sourceChannel is not None:
                if self.sourceChannel.inout == INOUT.OUT:
                    self.monitor = self.sourceChannel.value
                else:
                    self.value = self.sourceChannel.value
                    if self.sourceChannel.useMonitors:
                        self.monitor = self.sourceChannel.monitor

        def onDelete(self):
            super().onDelete()
            self.removeEvents()

        def removeEvents(self):
            if self.sourceChannel is not None:
                if self.relayValueEvent in self.sourceChannel.getParameterByName(self.VALUE).extraEvents:
                    self.sourceChannel.getParameterByName(self.VALUE).extraEvents.remove(self.relayValueEvent)
                if self.sourceChannel.useMonitors and self.relayMonitorEvent in self.sourceChannel.getParameterByName(self.MONITOR).extraEvents:
                    self.sourceChannel.getParameterByName(self.MONITOR).extraEvents.remove(self.relayMonitorEvent)
                for parameterName in [self.LINEWIDTH, self.LINESTYLE, self.COLOR]:
                    if parameterName in self.sourceChannel.displayedParameters:
                        if self.updateDisplay in self.sourceChannel.getParameterByName(parameterName).extraEvents:
                            self.sourceChannel.getParameterByName(parameterName).extraEvents.remove(self.updateDisplay)

        def getDefaultChannel(self):
            channel = super().getDefaultChannel()
            channel.pop(Channel.EQUATION)
            channel.pop(Channel.ACTIVE)
            channel.pop(Channel.REAL)
            channel.pop(Channel.SMOOTH)
            channel.pop(Channel.LINEWIDTH)
            channel.pop(Channel.LINESTYLE)
            channel.pop(Channel.COLOR)
            channel[self.VALUE][Parameter.HEADER]   = 'Set value ' # channels can have different types of parameters and units
            channel[self.VALUE][Parameter.EVENT] = lambda: self.setSourceChannelValue()
            channel[self.MONITOR][Parameter.HEADER] = 'Read value' # channels can have different types of parameters and units
            channel[self.DEVICE] = parameterDict(value=False, widgetType=Parameter.TYPE.BOOL, advanced=False,
                                                 toolTip='Source device.', header='')
            channel[self.UNIT] = parameterDict(value='', widgetType=Parameter.TYPE.TEXT, advanced=False, attr='unit', header='Unit   ', indicator=True)
            channel[self.NOTES  ] = parameterDict(value='', widgetType=Parameter.TYPE.LABEL, advanced=True, attr='notes', indicator=True)
            channel[self.NAME][Parameter.EVENT] = lambda: self.connectSource()
            return channel

        def setDisplayedParameters(self):
            super().setDisplayedParameters()
            self.displayedParameters.remove(self.ENABLED)
            self.displayedParameters.remove(self.EQUATION)
            self.displayedParameters.remove(self.ACTIVE)
            self.displayedParameters.remove(self.REAL)
            self.displayedParameters.remove(self.SMOOTH)
            self.displayedParameters.remove(self.LINEWIDTH)
            self.displayedParameters.remove(self.LINESTYLE)
            self.displayedParameters.remove(self.COLOR)
            self.displayedParameters.append(self.NOTES)
            self.insertDisplayedParameter(self.DEVICE, self.NAME)
            self.insertDisplayedParameter(self.UNIT, self.DISPLAY)

        def tempParameters(self):
            return super().tempParameters() + [self.VALUE, self.NOTES, self.DEVICE, self.UNIT]

        def initGUI(self, item):
            super().initGUI(item)
            device = self.getParameterByName(self.DEVICE)
            device.widget = QPushButton()
            device.widget.setStyleSheet('QPushButton{border:none;}')
            device.applyWidget()

    channelType = UCMChannel

    def initGUI(self):
        super().initGUI()
        self.importAction.setToolTip(f'Import {self.name} channels.')
        self.exportAction.setToolTip(f'Export {self.name} channels.')
        self.recordingAction = self.addStateAction(lambda: self.toggleRecording(manual=True), f'Start {self.name} data acquisition.', self.makeCoreIcon('play.png'),
                                                   'Stop data acquisition.', self.makeCoreIcon('pause.png'))

    def afterFinalizeInit(self):
        super().afterFinalizeInit()
        self.connectAllSources(update=True)
        self.clearPlot() # init fig after connecting sources
        self.liveDisplay.plot(apply=True)

    def getChannels(self):
        return [channel for channel in self.channels if channel.sourceChannel is not None]

    def moveChannel(self, up):
        newChannel = super().moveChannel(up)
        if newChannel is not None:
            newChannel.connectSource()

    def duplicateChannel(self):
        newChannel = super().duplicateChannel()
        if newChannel is not None:
            newChannel.connectSource()

    def toggleRecording(self, on=None, manual=False):
        super().toggleRecording(on=on, manual=manual)
        if manual:
            for device in list(set([channel.getDevice() for channel in self.getChannels()])):
                device.toggleRecording(on=self.recording, manual=manual)

    def loadConfiguration(self, file=None, default=False, append=False):
        super().loadConfiguration(file, default, append=append)
        if not self.pluginManager.loading:
            self.connectAllSources(update=True)

    def loadData(self, file, _show=True):
        self.pluginManager.Text.setText('Import channels from file explicitly.', True)

    def connectAllSources(self, update=False):
        self.loading = True # suppress plot
        for channel in self.channels:
            if channel.sourceChannel is None or update:
                channel.connectSource()
            else: # only reconnect (disconnect) if the reference has become invalid
                try:
                    channel.sourceChannel.value # testing access to a parameter that depends on sourceChannel with no internal fallback
                except RuntimeError as e:
                    self.print(f'Source channel {channel.name} may have been lost: {e} Attempt reconnecting.', flag=PRINT.WARNING)
                    channel.connectSource()
        self.loading = False

    def reconnectSource(self, name):
        for channel in self.channels:
            if channel.name == name:
                self.print(f'Source channel {channel.name} may have been lost. Attempt reconnecting.', flag=PRINT.WARNING)
                channel.connectSource()

class PID(ChannelManager):
    """Allows to connect an input (controlling) and output (controlled) channel via PID logic.
    Whenever the output changes, the input will be adjusted to stabilize the output to its setpoint.
    Proportional: If you’re not where you want to be, get there.
    Integral: If you haven’t been where you want to be for a long time, get there faster.
    Derivative: If you’re getting close to where you want to be, slow down."""

    name='PID'
    version = '1.0'
    pluginType = PluginManager.TYPE.CHANNELMANAGER
    previewFileTypes = []
    optional = True
    inout = INOUT.NONE
    maxDataPoints = 0 # PID channels do not store data
    iconFile = 'PID.png'

    class PIDChannel(RelayChannel, Channel):
        """Minimal UI for abstract PID channel."""

        def __init__(self,**kwargs):
            super().__init__(**kwargs)
            self.inputChannel = None
            self.sourceChannel = None
            self.pid = None

        OUTPUT       = 'Output'
        OUTPUTDEVICE = 'OutputDevice'
        INPUT        = 'Input'
        INPUTDEVICE  = 'InputDevice'
        PROPORTIONAL = 'Proportional' # if you’re not where you want to be, get there
        INTEGRAL     = 'Integral'     # if you haven’t been where you want to be for a long time, get there faster
        DERIVATIVE   = 'Derivative'   # if you’re getting close to where you want to be, slow down
        SAMPLETIME   = 'Sampletime'

        def connectSource(self):
            self.removeEvents()
            self.sourceChannel, outNotes = self.findChannel(self.output, self.OUTPUTDEVICE)
            self.inputChannel, inNotes = self.findChannel(self.input, self.INPUTDEVICE)
            self.notes = f'Output: {outNotes}, Input: {inNotes}'
            if self.sourceChannel is None:
                self.getValues = None
            else:
                self.unit = self.sourceChannel.getDevice().unit
                self.getValues = self.sourceChannel.getValues
            if self.sourceChannel is None or self.inputChannel is None:
                return
            if self.sourceChannel.useMonitors:
                self.sourceChannel.getParameterByName(self.MONITOR).extraEvents.append(self.stepPID)
            else:
                self.sourceChannel.getParameterByName(self.VALUE).extraEvents.append(self.stepPID)
            self.pid = simple_pid.PID(self.p, self.i, self.d, setpoint=self.value, sample_time=self.sample_time,
                                      output_limits=(self.inputChannel.min, self.inputChannel.max))
            self.updateColor()

        def findChannel(self, name, DEVICE):
            channels = [channel for channel in self.device.pluginManager.DeviceManager.channels() if channel.name.strip().lower() == name.strip().lower()]
            selectedChannel = None
            notes = ''
            if len(channels) == 0:
                notes = f'Could not find {name}'
                self.getParameterByName(DEVICE).getWidget().setIcon(self.device.makeCoreIcon('help_large_dark.png' if getDarkMode() else 'help_large.png'))
                self.getParameterByName(DEVICE).getWidget().setToolTip('Source: Unknown')
            else:
                selectedChannel = channels[0]
                notes = f'{selectedChannel.getDevice().name}.{selectedChannel.name}'
                self.getParameterByName(DEVICE).getWidget().setIcon(selectedChannel.getDevice().getIcon())
                self.getParameterByName(DEVICE).getWidget().setToolTip(f'Source: {selectedChannel.getDevice().name}')
                if len(channels) > 1:
                    self.print(f'More than one channel named {name}. Using {selectedChannel.getDevice().name}.{selectedChannel.name}. Use unique names to avoid this.', PRINT.WARNING)
            return selectedChannel, notes

        def stepPID(self):
            try:
                if self.sourceChannel.useMonitors:
                    self.monitor = self.sourceChannel.monitor
                else:
                    self.monitor = self.sourceChannel.value - self.sourceChannel.background if self.sourceChannel.getDevice().subtractBackgroundActive() else self.sourceChannel.value
                if self.active and self.device.isOn() and self.inputChannel.getDevice().isOn() and not np.isnan(self.sourceChannel.value):
                    # self.print(f'stepPID {self.device.isOn()} {self.inputChannel.name} {self.inputChannel.value} {self.inputChannel.getDevice().isOn()} {self.sourceChannel.name} {self.sourceChannel.value} {self.pid.components}', flag=PRINT.DEBUG)
                    self.inputChannel.value = self.pid(self.sourceChannel.value)
            except RuntimeError as e:
                self.print(f'Resetting. Source channel {self.output} or {self.input} may have been lost: {e}', flag=PRINT.ERROR)
                self.connectSource()

        def monitorChanged(self):
            pass

        def updateSetpoint(self):
            if self.pid is not None:
                self.pid.setpoint = self.value

        def updateSampleTime(self):
            if self.pid is not None:
                self.pid.sample_time = self.sample_time

        def updatePID(self):
            if self.pid is not None:
                self.pid.tunings = self.p, self.i, self.d

        def onDelete(self):
            super().onDelete()
            self.removeEvents()

        def removeEvents(self):
            if self.sourceChannel is not None:
                if self.stepPID in self.sourceChannel.getParameterByName(self.VALUE).extraEvents:
                    self.sourceChannel.getParameterByName(self.VALUE).extraEvents.remove(self.stepPID)
                if self.sourceChannel.useMonitors and self.stepPID in self.sourceChannel.getParameterByName(self.MONITOR).extraEvents:
                    self.sourceChannel.getParameterByName(self.MONITOR).extraEvents.remove(self.stepPID)

        def getDefaultChannel(self):
            channel = super().getDefaultChannel()
            channel.pop(Channel.EQUATION)
            channel.pop(Channel.ACTIVE)
            channel.pop(Channel.REAL)
            channel.pop(Channel.COLOR)
            channel[self.VALUE][Parameter.HEADER] = 'Setpoint   ' # channels can have different types of parameters and units
            channel[self.VALUE][Parameter.EVENT] = self.updateSetpoint
            channel[self.UNIT] = parameterDict(value='', widgetType=Parameter.TYPE.LABEL, attr='unit', header='Unit   ', indicator=True)
            channel[self.OUTPUT] = parameterDict(value='Output', widgetType=Parameter.TYPE.TEXT, attr='output', event=lambda: self.connectSource(),
                                                 toolTip='Output channel', header='Controlled')
            channel[self.OUTPUTDEVICE] = parameterDict(value=False, widgetType=Parameter.TYPE.BOOL, advanced=False,
                                                 toolTip='Output device.', header='')
            channel[self.INPUT ] = parameterDict(value='Input',  widgetType=Parameter.TYPE.TEXT, attr='input', event=lambda: self.connectSource(),
                                                 toolTip='Input channel', header='Controlling')
            channel[self.INPUTDEVICE] = parameterDict(value=False, widgetType=Parameter.TYPE.BOOL, advanced=False,
                                                 toolTip='Input device.', header='')
            channel[self.ACTIVE ] = parameterDict(value=False, widgetType=Parameter.TYPE.BOOL, attr='active', toolTip='Activate PID control.')
            channel[self.PROPORTIONAL] = parameterDict(value=1, widgetType=Parameter.TYPE.FLOAT, advanced=True, attr='p', header='P        ',
                                                       event=lambda: self.updatePID(), toolTip='Proportional')
            channel[self.INTEGRAL    ] = parameterDict(value=1, widgetType=Parameter.TYPE.FLOAT, advanced=True, attr='i', header='I        ',
                                                       event=lambda: self.updatePID(), toolTip='Integral')
            channel[self.DERIVATIVE  ] = parameterDict(value=1, widgetType=Parameter.TYPE.FLOAT, advanced=True, attr='d', header='D        ',
                                                       event=lambda: self.updatePID(), toolTip='Derivative')
            channel[self.SAMPLETIME  ] = parameterDict(value=10, widgetType=Parameter.TYPE.FLOAT, advanced=True, attr='sample_time',
                                                       header='Time   ', event=lambda: self.updateSampleTime(), toolTip='Sample time in s')
            channel[self.NOTES  ] = parameterDict(value='', widgetType=Parameter.TYPE.LABEL, advanced=True, attr='notes', indicator=True)
            return channel

        def setDisplayedParameters(self):
            super().setDisplayedParameters()
            self.displayedParameters.remove(self.ENABLED)
            self.displayedParameters.remove(self.EQUATION)
            self.displayedParameters.remove(self.REAL)
            self.displayedParameters.remove(self.COLOR)
            self.insertDisplayedParameter(self.ACTIVE, before=self.NAME)
            self.insertDisplayedParameter(self.UNIT, before=self.SCALING)
            self.insertDisplayedParameter(self.OUTPUTDEVICE, before=self.SCALING)
            self.insertDisplayedParameter(self.OUTPUT, before=self.SCALING)
            self.insertDisplayedParameter(self.INPUTDEVICE, before=self.SCALING)
            self.insertDisplayedParameter(self.INPUT, before=self.SCALING)
            self.insertDisplayedParameter(self.PROPORTIONAL, before=self.SCALING)
            self.insertDisplayedParameter(self.INTEGRAL, before=self.SCALING)
            self.insertDisplayedParameter(self.DERIVATIVE, before=self.SCALING)
            self.insertDisplayedParameter(self.SAMPLETIME, before=self.SCALING)
            self.insertDisplayedParameter(self.NOTES, before=self.SCALING)

        def tempParameters(self):
            return super().tempParameters() + [self.NOTES, self.OUTPUTDEVICE, self.INPUTDEVICE]

        def initGUI(self, item):
            super().initGUI(item)
            active = self.getParameterByName(self.ACTIVE)
            value = active.value
            active.widget = ToolButton()
            active.applyWidget()
            active.check.setMaximumHeight(active.rowHeight) # default too high
            active.check.setText(self.ACTIVE.title())
            active.check.setMinimumWidth(5)
            active.check.setCheckable(True)
            active.value = value
            for DEVICE in [self.OUTPUTDEVICE, self.INPUTDEVICE]:
                device = self.getParameterByName(DEVICE)
                device.widget = QPushButton()
                device.widget.setStyleSheet('QPushButton{border:none;}')
                device.applyWidget()

    channelType = PIDChannel

    def __init__(self, **kwargs):
        self.useOnOffLogic = True
        self.useDisplays = False
        self.useMonitors = True
        super().__init__(**kwargs)

    def afterFinalizeInit(self):
        super().afterFinalizeInit()
        self.connectAllSources(update=True)

    def loadConfiguration(self, file=None, default=False, append=False):
        super().loadConfiguration(file, default, append=append)
        if not self.pluginManager.loading:
            self.connectAllSources(update=True)

    def loadData(self, file, _show=True):
        self.pluginManager.Text.setText('Import channels from file explicitly.', True)

    def getChannels(self):
        return [channel for channel in self.channels if channel.sourceChannel is not None]

    def moveChannel(self, up):
        newChannel = super().moveChannel(up)
        if newChannel is not None:
            newChannel.connectSource()

    def duplicateChannel(self):
        newChannel = super().duplicateChannel()
        if newChannel is not None:
            newChannel.connectSource()

    def connectAllSources(self, update=False):
        for channel in self.channels:
            if channel.sourceChannel is None or channel.inputChannel is None or update:
                channel.connectSource()
            else: # only reconnect (disconnect) if the reference has become invalid
                try:
                    channel.sourceChannel.value # testing access to a parameter that depends on sourceChannel with no internal fallback
                    channel.inputChannel.value # testing access to a parameter that depends on inputChannel with no internal fallback
                except RuntimeError as e:
                    self.print(f'Source channel {channel.output} or {channel.input} may have been lost: {e} Attempt reconnecting.', flag=PRINT.WARNING)
                    channel.connectSource()

    def reconnectSource(self, name):
        for channel in self.channels:
            if channel.input == name or channel.output == name:
                self.print(f'Source channel {channel.output} or {channel.input} may have been lost. Attempt reconnecting.', flag=PRINT.WARNING)
                channel.connectSource()
