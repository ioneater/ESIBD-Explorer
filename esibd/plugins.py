""" This module contains only :class:`plugins<esibd.plugins.Plugin>` and plugin templates.
The user controls generally have a large amount of logic integrated and can act as an intelligent database.
This avoids complex and error prone synchronization between redundant data in the UI and a separate database.
Every parameter should only exist in one unique location at run time."""
# Separating the logic from the PyQt specific UI elements may be required in the future,
# but only if there are practical and relevant advantages that outweigh the drawbacks of managing syncronization."""

import sys
import os
import io
import ast
import itertools
from itertools import islice
from pathlib import Path
from threading import Thread, Timer, current_thread, main_thread
from typing import List
import timeit
import time
import inspect
import subprocess
from datetime import datetime
import configparser
import h5py
import numpy as np
from scipy.ndimage import uniform_filter1d
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
                            QFileDialog, QInputDialog, QComboBox, QSpinBox, QCheckBox, QToolButton)
from PyQt6.QtGui import QFont, QKeySequence, QShortcut, QColor, QIcon, QImage, QAction, QTextCursor
from PyQt6.QtCore import Qt, QUrl, QSize, QLoggingCategory, pyqtSignal, QObject, QTimer
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6 import QtCore
import esibd.core as EsibdCore
import esibd.const as EsibdConst
from esibd.core import INOUT, Parameter, PluginManager, parameterDict, DynamicNp, PRINT, Channel, MetaChannel
from esibd.const import * # pylint: disable = wildcard-import, unused-wildcard-import
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
    name : str          = "" # specify in child class mandatory
    """A unique name that will be used in the graphic user interface.
       Plugins can be accessed directly from the :ref:`sec:console` using their name."""
    documentation : str = None # specify in child class
    """The plugin documentation used in the internal about dialog in the :ref:`sec:browser`.
    If None, the doc string *__doc__* will be used instead.
    """
    version : str       = "" # specify in child class mandatory
    """The version of the plugin. Plugins are independent programs that
        require independent versioning and documentation."""
    optional : bool     = True # specify in child to prenvent user from disabling this plugin
    """Defines if the user can deactivate the plugin in the :class:`~esibd.core.PluginManager` user interface."""
    supportedVersion : str = str(PROGRAM_VERSION)
    """By default the current program version is used. You can
       define a fixed version and future program versions will
       state that they are incompatible with this plugin. This can be used to
       prompt developers to update and test their plugins before
       distributing them for a more recent program version."""
    dependencyPath = Path('') # will be set when plugin is loaded. dependencies can be in the same folder as the plugin file or subfolders therein
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
       stored next to the plugin file or in subfolders relative to its location."""
    pluginManager : EsibdCore.PluginManager
    """A reference to the central :class:`~esibd.core.PluginManager`."""
    dock : EsibdCore.BetterDockWidget
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

    def __init__(self, pluginManager=None, dependencyPath=None):
        super().__init__()
        if pluginManager is not None:
            self.pluginManager = pluginManager # provide access to other plugins through pluginmanager
        self.display = None # may be added by child class
        self._loading = 0
        self.labelAnnotation = None
        self.dock = None
        self.fig = None
        self.axes = []
        self.canvas = None
        self.navToolBar = None
        self.copyAction = None
        self.initializedGUI = False
        self.initializedDock = False # visible in GUI, some plugins will only appear when needed to dispay specific content
        if dependencyPath is not None:
            self.dependencyPath = dependencyPath
        self.dataClipboardIcon = self.makeCoreIcon('clipboard-paste-document-text.png')
        self.imageClipboardIcon = self.makeCoreIcon('clipboard-paste-image.png')

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
        Timer(0, self.runTestParallel).start()

    def testControl(self, control, value, delay=0):
        """Changes control states and triggers corresponding events."""
        self.print(f'Testing {control.objectName()}')
        if hasattr(control, 'signalComm'):
            control.signalComm.setValueFromThreadSignal.emit(value)
        if isinstance(control, QAction):
            control.triggered.emit(value) # c.isChecked()
        elif isinstance(control, QComboBox):
            control.currentIndexChanged.emit(value) # c.currentIndex()
        elif isinstance(control, (QLineEdit)):
            control.editingFinished.emit()
        elif isinstance(control, (QSpinBox)):
            control.valueChanged.emit(value)
            control.editingFinished.emit()
        elif isinstance(control, (QCheckBox)):
            control.stateChanged.emit(value) # c.isChecked()
        elif isinstance(control, (QToolButton)):
            control.clicked.emit()
        elif isinstance(control, (pg.ColorButton)):
            control.sigColorChanged.emit(control)
        else:
            self.print(f'No test implemented for class {type(control)}')
        time.sleep(delay)

    def runTestParallel(self):
        """Runs a series of tests by changing values of selected controls and triggering the corresponding events.
        Extend to add more plugin specific tests.

        :return: Returns True if the plugin is initialized and further tests can be executed.
        :rtype: bool
        """
        if self.initializedDock:
            self.print(f'Started testing for plugin {self.name}.')
            self.testControl(self.aboutAction, True, 1)
            # ... add sequence of spaced events to trigger and test all functionality
            return True
        return False

    def addToolbarStretch(self):
        self.stretchAction = QAction() # dummy to allow adding actions in front of stretch later on
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
        # hirarchy: self -> mainDisplayLayout -> mainDisplayWidget -> mainLayout
        # mainDisplayLayout and mainDisplayWidget only exist to enable conversion into a dockarea
        # mainLayout contains the actual content
        self.print('Plugin.initGUI', PRINT.DEBUG)
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
        self.print('Plugin.finalizeInit', PRINT.DEBUG)
        self.addToolbarStretch()
        self.aboutAction = self.addAction(self.about if aboutFunc is None else aboutFunc, f'About {self.name}', self.makeCoreIcon('help_large.png'))
        self.floatAction = self.addStateAction(self.setFloat, 'Float.', self.makeCoreIcon('application.png'), 'Dock.', self.makeCoreIcon('applications.png')
                            # , attr='floating' cannot use same attribute for multiple instances of same class # https://stackoverflow.com/questions/1325673/how-to-add-property-to-a-class-dynamically
                            )
        if self.pluginType in [PluginManager.TYPE.DISPLAY, PluginManager.TYPE.LIVEDISPLAY] and not self == self.pluginManager.Browser:
            self.closeAction = self.addAction(self.closeUserGUI, 'Close.', self.makeCoreIcon('close.png'))
        QApplication.processEvents() # required to allow adding dock to tab before self.dock.toggleTitleBar()
        self.dock.toggleTitleBar() # will show titleBarLabel only if not tabbed or floating
        self.updateTheme()
        self.loading = False
        # extend or overwrite to add code that should be executed after all other plugins have been initialized, e.g. modifications of other plugins

    def initDock(self):
        """Initializes the :class:`~esibd.core.BetterDockWidget`."""
        if not self.initializedDock:
            self.dock = EsibdCore.BetterDockWidget(self)

    def provideDock(self):
        """Adds existing :attr:`~esibd.plugins.Plugin.dock` to UI at position defined by :attr:`esibd.plugins.Plugin.pluginType`."""
        self.print('provideDock', PRINT.DEBUG)
        mw = self.pluginManager.mainWindow
        if not self.initializedDock:
            self.loading = True
            self.initGUI()
            self.initDock()
            self.print('provideDock', PRINT.DEBUG)
            if self.pluginType == PluginManager.TYPE.DEVICEMGR: # should be loaded before any other plugin
                mw.splitDockWidget(self.pluginManager.topDock, self.dock, Qt.Orientation.Vertical) # below topDock
            elif self.pluginType == PluginManager.TYPE.LIVEDISPLAY:
                liveDisplays = self.pluginManager.DeviceManager.getActiveLiveDisplays()
                if len(liveDisplays) == 0:
                    mw.splitDockWidget(self.pluginManager.topDock, self.dock, Qt.Orientation.Vertical) # below topDock
                else:
                    mw.tabifyDockWidget(liveDisplays[-1].dock, self.dock) # add to other live displays
                    if len(liveDisplays) == 1:
                        QApplication.processEvents()
                        liveDisplays[0].dock.toggleTitleBar() # tabstate changing for fist one when second one added
            elif self.pluginType in [PluginManager.TYPE.INPUTDEVICE, PluginManager.TYPE.OUTPUTDEVICE, PluginManager.TYPE.CONTROL, PluginManager.TYPE.SCAN]:
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
            self.print('initializedDock = True', PRINT.DEBUG)
            QApplication.processEvents() # break down expensive initialization to allow update splash screens while loading
            self.loading = False
            return True # dock has been created
        return False # dock already exists

    def raiseDock(self, _show=True):
        """Raises :attr:`dock<esibd.plugins.Plugin.dock>` if _show is True."""
        if _show:
            QTimer.singleShot(0, self.dock.raise_) # give time for UI to draw before raising the dock
        # self.loading = False

    def requiredPlugin(self, name):
        """Displays error message if required plugin is not available."""
        if not hasattr(self.pluginManager, name):
            self.print(f'Plugin {name} required for {self.name}', PRINT.ERROR)
            # raise ModuleNotFoundError(f'Error: Plugin {name} required for {self.name}.')

    def addAction(self, func=None, toolTip='', icon=None, before=None):
        """Adds a simple Action to the toolBar.

        :param func: The function triggered by the action, defaults to None
        :type func: method, optional
        :param toolTip: The toolTip of the action, defaults to ''
        :type toolTip: str, optional
        :param icon: The icon of the action, defaults to None
        :type icon: :class:`~esibd.core.BetterIcon`, optional
        :param before: The existing action before which the new action will be placed, defaults to None. If None, the new action will be added to the end.
        :type before: :class:`~esibd.core.Action`, optional
        :return: The new Action
        :rtype: :class:`~esibd.core.Action`
        """
        # first arguments of func have to be "self" and "checked".
        # If you do not need "checked" use "lambda : func()" instead of func as argument to this function to prevent your parameters from being overwritten
        if isinstance(icon, str):
            icon=self.makeIcon(icon)
        a = EsibdCore.Action(icon, toolTip, self) # icon, toolTip, parent
        a.triggered.connect(func)
        a.setObjectName(f"{self.name}/toolTip: {toolTip.strip('.')}")
        if before is None:
            self.titleBar.addAction(a)
        else:
            self.titleBar.insertAction(before, a)
        return a

    def addStateAction(self, func=None, toolTipFalse='', iconFalse=None, toolTipTrue='', iconTrue=None, before=None, attr=None, restore=True, default='false'):
        """Adds an action with can be toggled between two states, each having a
        dedicated tooltip and icon.

        :param func: The function triggered by the stateAction, defaults to None
        :type func: method, optional
        :param toolTipFalse: The toolTip of the stateAction if state is False, defaults to ''
        :type toolTipFalse: str, optional
        :param iconFalse: The icon of the stateAction if state is False, defaults to None
        :type iconFalse: :class:`~esibd.core.BetterIcon`, optional
        :param toolTipTrue: The toolTip of the stateAction if state is True, defaults to ''
        :type toolTipTrue: str, optional
        :param iconTrue: The icon of the stateAction if state is True, defaults to None
        :type iconTrue: :class:`~esibd.core.BetterIcon`, optional
        :param before: An existing action or stateAction before which the new action will be placed, defaults to None.
            If None, the new stateAction will be added to the end.
        :type before: :class:`~esibd.core.Action`, optional
        :param attr: Enables direct access to the state of the stateAction using self.attr, defaults to None
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
                                     iconTrue=iconTrue, func=func, before=before, attr=attr, restore=restore, default=default)

    def addMultiStateAction(self, func=None, states=None, before=None, attr=None, restore=True, default=0):
        """Adds an action with can be toggled between two states, each having a
        dedicated tooltip and icon.

        :param func: The function triggered by the stateAction, defaults to None
        :type func: method, optional
        :param states: The list of states the control can represent, defaults to a list of empty states
        :type states: List[:class:`~esibd.core.MultiState`], optional
        :param before: An existing action or stateAction before which the new action will be placed, defaults to None.
            If None, the new stateAction will be added to the end.
        :type before: :class:`~esibd.core.Action`, optional
        :param attr: Enables direct access to the state of the stateAction using self.attr, defaults to None
        :type attr: str, optional
        :param restore: If True state will be restored when the program is restarted, defaults to True
        :type restore: bool, optional
        :param default: Index of default state, defaults to 0
        :type default: int, optional
        :return: The new StateAction
        :rtype: :class:`~esibd.core.StateAction`

        """
        # Using wrapper allows to pass parentPlugin implicitly and keep signature consistent.
        return EsibdCore.MultiStateAction(parentPlugin=self, states=states, func=func, before=before, attr=attr, restore=restore, default=default)

    def toggleTitleBar(self):
        """Adjusts the title bar layout and :attr:`~esibd.plugins.Plugin.titleBarLabel` depending on the state of the :attr:`~esibd.plugins.Plugin.dock` (tabbed, floating, ...).
        Extend to make sure toggleTitleBar is called for dependent plugins.
        """
        self.dock.toggleTitleBar()

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
        return any(file.name.endswith(s) for s in self.previewFileTypes)

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
        v = self.requireGroup(f, INFO)
        for key, value in infoDict(self.name).items():
            v.attrs[key] = value

    def requireGroup(self, g, name):
        """Replaces require_group from h5py, and adds support for track_order."""
        if name in g:
            return g[name]
        else:
            return g.create_group(name=name, track_order=True)

    def expandTree(self, tree):
        # expand all categories
        it = QTreeWidgetItemIterator(tree, QTreeWidgetItemIterator.IteratorFlag.HasChildren)
        while it.value():
            it.value().setExpanded(True)
            it +=1

    def about(self):
        """Displays the about dialog of the plugin using the :ref:`sec:browser`."""
        self.pluginManager.Browser.setAbout(self, f'About {self.name}', f"""
            <p>{self.documentation if self.documentation is not None else self.__doc__}<br></p>
            <p>Supported files: {', '.join(self.getSupportedFiles())}<br>
            Supported version: {self.supportedVersion}<br></p>"""
            + # add programmer info in testmode, otherwise only show user info
            (f"""<p>Plugin type: {self.pluginType.value}<br>
            Optional: {self.optional}<br>
            Dependency path: {self.dependencyPath.resolve()}<br></p>"""
            if getTestMode() else '')
            )

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
        self.navToolBar = EsibdCore.ThemedNavigationToolbar(self.canvas, parentPlugin=self, dark=getDarkMode()) # keep reference in order to reset navigation
        for action in self.navToolBar.actions()[:-1]: # last action is empty and undocumented
            if hasattr(self,'stretchAction'):
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
            except ValueError:
                pass # might have been deleted already
        self.labelAnnotation = ax.annotate(text=label, xy=(.98,.98), fontsize=fontsize, xycoords='axes fraction', textcoords='axes fraction',
                                        ha='right', va='top', bbox=dict(boxstyle='square, pad=.2', fc=plt.rcParams['axes.facecolor'], ec='none'), clip_on=True)
        QApplication.processEvents() # trigger paint to get width
        labelWidth = self.labelAnnotation.get_window_extent(renderer=ax.get_figure().canvas.get_renderer()).width
        axisWidth = ax.get_window_extent().transformed(ax.get_figure().dpi_scale_trans.inverted()).width*ax.get_figure().dpi*.9
        self.labelAnnotation.set_size(min(max(fontsize / labelWidth * axisWidth, 1), 10))
        # ax.plot([0.8, 1], [0.95, 0.95], transform=ax.transAxes, color='green') # workaround for label vs legend clash not working
        # https://stackoverflow.com/questions/57328170/draw-a-line-with-matplotlib-using-the-axis-coordinate-system
        if hasattr(ax,'cursor'): # cursor position changes after adding label... -> restore
            ax.cursor.updatePosition()
        ax.figure.canvas.draw_idle()

    def removeAnnotations(self, ax):
        for ann in [child for child in ax.get_children() if isinstance(child, mpl.text.Annotation)]:#[self.seAnnArrow, self.seAnnFile, self.seAnnFWHM]:
            ann.remove()

    def getIcon(self):
        """Gets the plugin icon. Overwrite to introduce custom icons.
        Consider using a themed icon that works in dark and light modes.

        :return: Icon
        :rtype: :class:`~esibd.core.BetterIcon`
        """
        # e.g. return self.darkIcon if getDarkMode() else self.lightIcon
        return self.makeCoreIcon('document.png')

    def makeCoreIcon(self, file):
        """Returns an icon based on a filename. Looks for files in the internal media folder.

        :param file: Icon file name.
        :type file: str
        :return: Icon
        :rtype: :class:`~esibd.core.BetterIcon`
        """
        return EsibdCore.BetterIcon(internalMediaPath / file)

    def makeIcon(self, file):
        """Returns an icon based on a filename. Looks for files in the :meth:`~esibd.plugins.Plugin.dependencyPath`.

        :param file: Icon file name.
        :type file: str
        :return: Icon
        :rtype: :class:`~esibd.core.BetterIcon`
        """
        return EsibdCore.BetterIcon(str(self.dependencyPath / file))

    def updateTheme(self):
        """Changes between dark and light themes. Most
        controls should update automatically as the color pallet is changed.
        Only update the remaining controls using style sheets.
        Extend to adjust colors to app theme.
        """
        if self.fig is not None and not self.loading and (self.scan is None or self.scan.file is not None):
            self.initFig()
            self.plot()
        if hasattr(self,'navToolBar') and self.navToolBar is not None:
            self.navToolBar.updateNavToolbarTheme(getDarkMode())
        if hasattr(self,'closeAction'):
            self.closeAction.setIcon(self.makeCoreIcon('close_dark.png') if getDarkMode() else self.makeCoreIcon('close_light.png'))
        if hasattr(self,'aboutAction'):
            self.aboutAction.setIcon(self.makeCoreIcon('help_large_dark.png') if getDarkMode() else self.makeCoreIcon('help_large.png'))

    def initFig(self):
        """Will be called when a :ref:`display<sec:displays>` is closed and reopened or the theme
        is changed. Overwrite your figure initialization here to make sure all references are updated correctly."""
        self.fig = None
        self.canvas = None

    def provideFig(self):
        if self.fig is not None and ((
                plt.rcParams['axes.facecolor'] == 'black' and self.fig.get_facecolor() == (1.0, 1.0, 1.0, 1.0)) # should be black but is white
                or (plt.rcParams['axes.facecolor'] == 'white' and self.fig.get_facecolor() == (0.0, 0.0, 0.0, 1.0))): # should be white but is black
            # need to create new fig to change matplotlib style
            plt.close(self.fig)
            self.fig = None
        if self.fig is None:
            self.fig = plt.figure(constrained_layout=True, dpi=getDPI())
            self.makeFigureCanvasWithToolbar(self.fig)
            self.addContentWidget(self.canvas)
        else:
            self.fig.clf() # reuse if possible
            self.fig.set_constrained_layout(True)
            self.fig.set_dpi(getDPI())
        self.axes = []

    def plot(self):
        """If applicable, overwrite with a plugin specific plot method."""

    def copyClipboard(self):
        """Copy matplotlib figure to clipboard."""
        buf = io.BytesIO()
        limits = []
        if getDarkMode() and not getClipboardTheme():
            # use default light theme for clipboard
            with mpl.style.context('default'):
                for ax in self.axes:
                    limits.append((ax.get_xlim(), ax.get_ylim()))
                self.initFig()
                self.plot()
                for i, ax in enumerate(self.axes):
                    ax.set_xlim(limits[i][0])
                    ax.set_ylim(limits[i][1])
                self.canvas.draw_idle()
                QApplication.processEvents()
                self.fig.savefig(buf, format='png', bbox_inches='tight', dpi=getDPI())
        else:
            self.fig.savefig(buf, format='png', bbox_inches='tight', dpi=getDPI())
        if getDarkMode() and not getClipboardTheme():
            # restore dark theme for use inside app
            self.initFig()
            self.plot()
            for i, ax in enumerate(self.axes):
                ax.set_xlim(limits[i][0])
                ax.set_ylim(limits[i][1])
            self.canvas.draw_idle()
        QApplication.clipboard().setImage(QImage.fromData(buf.getvalue()))
        buf.close()

    def copyLineDataClipboard(self, line):
        if line is not None:
            text = ''
            for x, y in zip(line.get_xdata(), line.get_ydata()): #np.array(self.msline.get_data()).transpose():
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
        if hasattr(self,'fig'):
            plt.close(self.fig)
        self.fig = None
        self.canvas = None
        self.titleBar = None
        self.initializedGUI = False
        self.initializedDock = False

########################## pyqtgraph Displays #########################################

class StaticDisplay(Plugin):
    """Displays :class:`~esibd.plugins.Device` data from file."""
    pluginType=PluginManager.TYPE.DISPLAY

    def __init__(self, parentPlugin, **kwargs):
        self.parentPlugin = parentPlugin # another Plugin
        self.name = parentPlugin.name
        self.file = None
        self.previewFileTypes = [] # extend in derived classes, define here to avoid cross talk between instances
        super().__init__(**kwargs)

    def initGUI(self):
        """:meta private:"""
        super().initGUI()
        self.legend = None
        self.backgroundAction = None
        self.outputLayout = QVBoxLayout()
        self.plotWidgetFont = QFont()
        self.plotWidgetFont.setPixelSize(15)
        self.staticPlotWidget = EsibdCore.BetterPlotWidget(parent=self)
        self.staticPlotWidget.showGrid(x=True, y=True)
        self.staticPlotWidget.showAxis('top')
        self.staticPlotWidget.getAxis('top').setStyle(showValues=False)
        self.staticPlotWidget.showLabel('top', show=False)
        self.staticPlotWidget.setAxisItems({'right': EsibdCore.SciAxisItem('right')})
        self.staticPlotWidget.setAxisItems({'left': EsibdCore.SciAxisItem('left')})
        self.staticPlotWidget.getAxis('left').setTickFont(self.plotWidgetFont)
        self.staticPlotWidget.getAxis('right').setTickFont(self.plotWidgetFont)
        self.staticPlotWidget.getAxis('bottom').setTickFont(self.plotWidgetFont)
        self.staticPlotWidget.setAxisItems({'bottom': pg.DateAxisItem()})
        self.staticPlotWidget.setLabel('bottom','<font size="5">Time</font>') # has to be after setAxisItems
        self.staticPlotWidget.enableAutoRange(self.staticPlotWidget.getViewBox().XAxis, True)

        self.outputLayout.addWidget(self.staticPlotWidget)
        self.initFig()
        self.addContentLayout(self.outputLayout)
        self.initData()

    def initFig(self):
        """:meta private:"""
        self.fig=plt.figure(constrained_layout=True, dpi=getDPI())
        self.makeFigureCanvasWithToolbar(self.fig)
        self.outputLayout.addWidget(self.canvas)
        self.axes = []
        self.axes.append(self.fig.add_subplot(111))

    def finalizeInit(self, aboutFunc=None):
        """:meta private:"""
        # for a in self.navToolBar.actions()[:-1]: # last action is empty and undocumented
        #     self.titleBar.addAction(a)
        super().finalizeInit(aboutFunc)
        self.copyAction = self.addAction(self.copyClipboard,'Image to Clipboard.', self.imageClipboardIcon, before=self.aboutAction)
        self.plotEfficientAction = self.addStateAction(func=self.togglePlotType, toolTipFalse='Use matplotlib plot.', iconFalse=self.makeCoreIcon('mpl.png'),
                                                       toolTipTrue='Use pyqtgraph plot.', iconTrue=self.makeCoreIcon('pyqt.png'), attr='plotEfficient', before=self.copyAction)
        if self.parentPlugin.useBackgrounds:
            self.backgroundAction = self.addStateAction(toolTipFalse='Subtract background.', iconFalse=self.makeCoreIcon('eraser.png'),
                                                        toolTipTrue='Ignore background.', iconTrue=self.makeCoreIcon('eraser.png'), before=self.plotEfficientAction,
                                                        attr='subtractStaticBackground', func=lambda : self.plot()) # pylint: disable=unnecessary-lambda
        self.togglePlotType()

    def runTestParallel(self):
        """:meta private:"""
        if super().runTestParallel():
            self.testControl(self.copyAction, True, 1)
            self.testControl(self.plotEfficientAction, not self.plotEfficient, 1)
            if self.parentPlugin.useBackgrounds:
                self.testControl(self.backgroundAction, not self.subtractStaticBackground, 1)

    def copyClipboard(self):
        """Extends matplotlib based version to add support for pyqtgraph."""
        if self.plotEfficient: # maptplotlib
            super().copyClipboard()
        else: # pyqt
            if getDarkMode() and not getClipboardTheme():
                qSet.setValue(f'{GENERAL}/{DARKMODE}', 'false')
                self.updateTheme() # use default light theme for clipboard
                QApplication.processEvents()
                QApplication.clipboard().setPixmap(self.staticPlotWidget.grab())
                qSet.setValue(f'{GENERAL}/{DARKMODE}', 'true')
                self.updateTheme() # restore dark theme
            else:
                QApplication.clipboard().setPixmap(self.staticPlotWidget.grab())

    def provideDock(self):
        """:meta private:"""
        if super().provideDock():
            self.finalizeInit(aboutFunc=self.parentPlugin.about)

    def supportsFile(self, file):
        """:meta private:"""
        if super().supportsFile(file):
            return True
        elif self.pluginManager.DeviceManager.supportsFile(file):
            with h5py.File(file,'r') as f:
                return self.name in f
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
        self.staticPlotWidget.setVisible(not self.plotEfficient)
        self.canvas.setHidden(not self.plotEfficient)
        for a in self.navToolBar.actions()[:-1]: # last action is empty and undocumented
            a.setVisible(self.plotEfficient)
        if self.file is not None and len(self.outputs) > 0:
            self.plot(update=True)

    def updateStaticPlot(self):
        # update if channel settings have changed and data is present
        if self.initializedDock and not self.loading and len(self.outputs) > 0:
            self.plot()

    def plot(self, update=False):
        """Plots channels from file, using real channel information (color, linewidth, ...) if available."""
        # as this is only done once we can plot all data without thinning
        if self.plotEfficient:
            self.axes[0].clear()
            self.axes[0].set_xlabel(self.TIME)
            self.tilt_xlabels(self.axes[0])
        else:
            self.staticPlotWidget.clear()
            self.legend = self.staticPlotWidget.addLegend(labelTextColor=colors.fg) # before adding plots

        for o in self.outputs:
            length = min(self.inputs[0].data.shape[0], o.data.shape[0])
            x = self.inputs[0].data[-length:]
            y = self.parentPlugin.convertDataDisplay((o.data-o.background)[:length]
                                           if self.parentPlugin.useBackgrounds and (self.subtractStaticBackground if self.backgroundAction is not None else False)
                                           else o.data[:length])

            if o.channel is None:
                if self.plotEfficient:
                    self.axes[0].plot([datetime.fromtimestamp(float(t)) for t in x], y, label=f'{o.name} ({o.unit})')
                else:
                    self.staticPlotWidget.plot(x, y, name=f'{o.name} ({o.unit})') # initialize empty plots
            elif o.channel.display:
                if o.channel.smooth != 0:
                    y = uniform_filter1d(y, o.channel.smooth)
                if self.plotEfficient:
                    self.axes[0].plot([datetime.fromtimestamp(float(t)) for t in x], y, label=f'{o.channel.name} ({o.channel.device.getUnit()})',
                                      color=o.channel.color, linewidth=o.channel.linewidth/2)
                else:
                    self.staticPlotWidget.plot(x, y, pen=pg.mkPen((o.channel.color), width=o.channel.linewidth), name=f'{o.channel.name} ({o.channel.device.getUnit()})')

        if self.plotEfficient:
            self.setLabelMargin(self.axes[0], 0.15)
            self.navToolBar.update() # reset history for zooming and home view
            self.canvas.get_default_filename = lambda : self.file.with_suffix('.pdf') # set up save file dialog
            self.labelPlot(self.axes[0], self.file.name)
            leg = self.axes[0].legend(loc='best', prop={'size': 7}, frameon=False)
            leg.set_in_layout(False)
        elif update:
            self.staticPlotWidget.autoRange() # required to trigger update

    def initData(self):
        self.inputs, self.outputs = [], []

    def loadDataInternal(self, file):
        """Load data in standard format. Overwrite in derived classes to add support for old file formats."""
        with h5py.File(file,'r') as f:
            if not self.name in f:
                return False
            g=f[self.name]
            if not (Scan.INPUTCHANNELS in g and Scan.OUTPUTCHANNELS in g):
                return False
            self.inputs.append(MetaChannel(name=self.TIME, data=g[Scan.INPUTCHANNELS][self.TIME][:]))
            o = g[Scan.OUTPUTCHANNELS]
            for name, item in o.items():
                if name.endswith('_BG'):
                    self.outputs[-1].background = item[:]
                else:
                    self.outputs.append(MetaChannel(name=name, data=item[:], unit=item.attrs[Scan.UNIT] if Scan.UNIT in item.attrs else '', channel=self.parentPlugin.getChannelByName(name)))
        return True # return True if loading was successful # make sure to follow this pattern when extending!

    def generatePythonPlotCode(self):
        with open(self.pluginManager.Explorer.activeFileFullPath.with_suffix('.py'), 'w', encoding=UTF8) as f:
            f.write(f"""import h5py
import matplotlib.pyplot as plt
from datetime import datetime

inputs, outputs = [], []
class MetaChannel():
    def __init__(self, name, data, initial=None, background=None, unit=''):
        self.name = name
        self.data = data
        self.initial = initial
        self.background = background
        self.unit = unit

with h5py.File('{self.pluginManager.Explorer.activeFileFullPath.as_posix()}','r') as f:
    g = f['{self.parentPlugin.name}']

    inputs.append(MetaChannel(name='Time', data=g['Input Channels']['Time'][:]))

    o = g['Output Channels']
    for name, data in o.items():
        if name.endswith('_BG'):
            outputs[-1].background = data[:]
        else:
            outputs.append(MetaChannel(name=name, data=data[:], units=data.attrs['Unit']))

# replace following with your custom code
subtract_backgrounds = False # switch to True to subtract background signals if available

fig=plt.figure(constrained_layout=True, )
ax = fig.add_subplot(111)
ax.set_xlabel('Time')

for i, o in enumerate(outputs):
    length = min(inputs[0].data.shape[0], o.data.shape[0])
    x = inputs[0].data[-length:]
    y = (o.data-o.background)[:length] if o.background is not None and subtract_backgrounds else o.data[:length]
    ax.plot([datetime.fromtimestamp(float(t)) for t in x], y, label=f'{{o.name}} ({{o.unit}})')

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
        self.staticPlotWidget.xyLabel.setColor(fg)
        if self.legend is not None:
            self.legend.setLabelTextColor(fg)
        self.updateStaticPlot() # triggers update of legend
        if not self.loading:
            self.togglePlotType()

# import pyqtgraph.multiprocess as mp

class LiveDisplay(Plugin):
    """Live displays show the history of measured data over time. The toolbar
    provides icons to initialize, start, pause, stop acquisition, optionally
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
    documentation = """Live displays show the history of measured data over time. The toolbar
    provides icons to initialize, start, pause, stop acquisition, optionally
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

    pluginType=PluginManager.TYPE.LIVEDISPLAY

    def __init__(self, device=None, **kwargs):
        self.device = device # should be a device that will define which channel to plot
        self.name = device.name
        self.dataFileType = f'_{self.name.lower()}.dat.h5'
        self.previewFileTypes = [self.dataFileType]
        self._recording = False
        self.lastPlotTime = time.time()*1000
        self.lagging = 0
        super().__init__(**kwargs)
        self.ICON_PLAY      = self.makeCoreIcon('play.png')
        self.ICON_PAUSE     = self.makeCoreIcon('pause.png')
        self.ICON_STOP      = self.makeCoreIcon('stop.png')
        self.backgroundAction = None
        self.legend = None

    def initGUI(self):
        """:meta private:"""
        super().initGUI()
        self.print('initGUI', PRINT.DEBUG)
        # self.outputLayout = QVBoxLayout()

        # RemoteGraphicsView: cannot find examples using PlotWidget and setAxisItems etc. -> TypeError: can't pickle [...] objects
        # self.remoteView = pg.widgets.RemoteGraphicsView.RemoteGraphicsView()
        # self.livePlotWidget = self.remoteView.pg.PlotWidget()
        # self.livePlotWidget._setProxyOptions(deferGetattr=True)
        # self.remoteView.setCentralItem(self.livePlotWidget)
        # self.outputLayout.addWidget(self.remoteView)

        # multiprocessing_ can't addWidget from separate process. solution to show in separate window is not acceptable
        # proc = mp.QtProcess()
        # rpg = proc._import('pyqtgraph')
        # self.livePlotWidget = rpg.PlotWidget()
        # self.outputLayout.addWidget(self.livePlotWidget)

        # do everything in main thread
        self.livePlotWidget = EsibdCore.BetterPlotWidget(parent=self)#pg.PlotWidget()
        # self.outputLayout.addWidget(self.livePlotWidget)

        # self.addContentLayout(self.outputLayout)
        self.addContentWidget(self.livePlotWidget)

        self.addAction(func=self.device.stop, toolTip='Close communication.', icon=self.ICON_STOP)
        self.addAction(func=self.device.init, toolTip='Initialize communication.', icon=self.makeCoreIcon('rocket-fly.png'))
        self.clearHistoryAction = self.addAction(func=self.device.clearHistory, toolTip='Clear history.', icon=self.makeCoreIcon('clipboard-empty.png'))
        self.clearHistoryAction.setVisible(False) # usually not required as number of datapoints is already limited. only show in advanced mode
        if self.device.useBackgrounds:
            self.backgroundAction = self.addStateAction(toolTipFalse='Subtract background.', iconFalse=self.makeCoreIcon('eraser.png'),
                                                        toolTipTrue='Ignore background.', iconTrue=self.makeCoreIcon('eraser.png'),
                                                        attr='subtractLiveBackground', func=lambda : self.plot(apply=True))
            self.addAction(func=self.device.setBackground, toolTip='Set current value as background.', icon=self.makeCoreIcon('eraser--pencil.png'))
        self.exportAction = self.addAction(func=lambda : self.device.exportOutputData(), toolTip=f'Save visible {self.name} data to current session.', # pylint: disable=unnecessary-lambda
                       icon=self.makeCoreIcon('database-export.png'))
        self.recordingAction = self.addStateAction(self.device.toggleRecording, 'Start data acquisition.', self.ICON_PLAY,'Stop data acquisition.', self.ICON_PAUSE)

        self.livePlotWidget.getPlotItem().setContentsMargins(0, 0, 10, 0) # prevent right axis from being cut off
        self.livePlotWidget.showGrid(x=True, y=True)
        self.livePlotWidget.setMouseEnabled(x=False, y=True) # keep auto pan in x running, use settings to zoom in x
        self.livePlotWidget.showAxis('top')
        self.livePlotWidget.getAxis('top').setStyle(showValues=False)
        self.livePlotWidget.showLabel('top', show=False)
        self.livePlotWidget.setAxisItems({'right': EsibdCore.SciAxisItem('right')})
        self.livePlotWidget.setAxisItems({'left': EsibdCore.SciAxisItem('left')})
        #self.livePlotWidget.setLabel('left','<font size="5">Current (pA)</font>') # no label needed as output channels can have various different units -> use plot labels instead
        self.plotWidgetFont = QFont()
        self.plotWidgetFont.setPixelSize(15)
        self.livePlotWidget.getAxis('left').setTickFont(self.plotWidgetFont)
        self.livePlotWidget.getAxis('right').setTickFont(self.plotWidgetFont)
        self.livePlotWidget.setAxisItems({'bottom': pg.DateAxisItem()}) #, size=5
        self.livePlotWidget.setLabel('bottom','<font size="5">Time</font>') # has to be after setAxisItems
        self.livePlotWidget.enableAutoRange(self.livePlotWidget.getViewBox().XAxis, True)
        self.livePlotWidget.getAxis('bottom').setTickFont(self.plotWidgetFont)
        # self.livePlotWidget.disableAutoRange() # 50 % less CPU usage for about 1000 datapoints. For 10000 and more it does not make a big difference anymore.

        # pg.SignalProxy(self.livePlotWidget.scene().sigMouseMoved, rateLimit=60, slot=self.mouseMoved)

    def finalizeInit(self, aboutFunc=None):
        """:meta private:"""
        super().finalizeInit(aboutFunc)
        self.print('finalizeInit', PRINT.DEBUG)
        self.copyAction = self.addAction(self.copyClipboard,'Image to Clipboard.', self.imageClipboardIcon, before=self.aboutAction)
        self.displayTimeComboBox = EsibdCore.RestoreFloatComboBox(parentPlugin=self, default='2', items='-1, 0.2, 1, 2, 3, 5, 10, 60, 600, 1440', attr='displayTime',
                                                        event=lambda : self.plot(apply=True), _min=.2, _max=3600,
                                                        toolTip='Length of displayed history in min. When -1, all history is shown.')
        self.titleBar.insertWidget(self.copyAction, self.displayTimeComboBox)
        self.plot(apply=True)

    def runTestParallel(self):
        """:meta private:"""
        if super().runTestParallel():
            # init, start, pause, stop acquisition will be tested by instManager
            if self.device.useBackgrounds:
                self.testControl(self.backgroundAction, not self.subtractLiveBackground, 1)
            # self.testControl(self.clearHistoryAction, True, 1) # keep history, test manually for dummy devices if applicable
            self.testControl(self.exportAction, True, 1)

    def copyClipboard(self):
        """Extends matplotlib based version to add support for pyqtgraph."""
        buf = io.BytesIO()
        if getDarkMode() and not getClipboardTheme():
            qSet.setValue(f'{GENERAL}/{DARKMODE}', 'false')
            self.updateTheme() # use default light theme for clipboard
            QApplication.processEvents()
            QApplication.clipboard().setPixmap(self.livePlotWidget.grab())
            qSet.setValue(f'{GENERAL}/{DARKMODE}', 'true')
            self.updateTheme() # restore dark theme
        else:
            QApplication.clipboard().setPixmap(self.livePlotWidget.grab())
        buf.close()

    @property
    def recording(self):
        return self._recording
    @recording.setter
    def recording(self, recording):
        self._recording = recording
        # allow output widgets to react to change if acquisition state
        if self.initializedDock:
            self.recordingAction.state = self.recording

    def updateLivePlot(self):
        if any([c.plotCurve is None or c.plotCurve.getData()[0] is None and c.display for c in self.device.channels]):
            # make full plot to add required plotCurve
            self.plot(apply=True)
            return
        # otherwise toogle visibility is sufficient
        for channel in self.device.channels:
            if channel.display:
                channel.plotCurve.setPen(pg.mkPen(QColor(channel.color), width=int(channel.linewidth)))
                channel.plotCurve.opts['name'] = channel.name
            else:
                channel.plotCurve.setPen(pg.mkPen(None))

    def plot(self, apply=False):
        """Plots the enabled and initialized channels in the main output plot
            The x axis is either time or a selected channel"""
        if not self.initializedDock or not hasattr(self, 'displayTimeComboBox') or self.device.pluginManager.loading or self.pluginManager.Settings.loading or self.device.time.size == 0:
            return # values not yet available
        # flip array to speed up search of most recent datapoints
        # may return None if no value is older than displaytime
        userRange = False
        t = self.device.time.get()
        if self.livePlotWidget.getViewBox().autoRangeEnabled()[0]: # displayTime determines range
            i_min = np.argmin(np.abs(t - (time.time() - float(self.displayTimeComboBox.currentText())*60))) if float(self.displayTimeComboBox.currentText()) != -1 else 0
            i_max = None
            t_length = t.shape[0] - i_min # number of indices within in displaytime before thinning
            # determine by how much to limit number of displayed data points
            n = max(int(t_length/self.pluginManager.DeviceManager.max_display_size), 1) if self.pluginManager.DeviceManager.limit_display_size else 1
            timeAx = self.device.time.get(_min=i_min, n=n)
        else: # range determined by user
            userRange = True # need to update every time as i_min is not changing
            t_min, t_max = self.livePlotWidget.getAxis('bottom').range
            i_min = np.argmin(np.abs(t - t_min))
            i_max = np.argmin(np.abs(t - t_max))
            n = max(int((i_max-i_min)/self.pluginManager.DeviceManager.max_display_size), 1) if self.pluginManager.DeviceManager.limit_display_size else 1
            timeAx = self.device.time.get(_min=i_min, _max=i_max, n=n)
        for channel in (self.device.channels)[::-1]:
            if (channel.enabled or not channel.real) and channel.display:
                if channel.plotCurve is None:
                    channel.plotCurve = self.livePlotWidget.plot(pen=pg.mkPen((channel.color), width=channel.linewidth),
                                                                                            name=f'{channel.name} ({channel.device.getUnit()})') # initialize empty plots
                if apply or np.remainder(i_min, n) == 0 or userRange: # otherwise no update required # need at least 2 datapoints to plot connecting line segement
                    if timeAx.shape[0] > 1:
                        # plotting is very expensive, array manipulation is negligable even with 50000 data points per channel
                        # channel should at any point have as many data points as timeAx (missing bits will be filled with nan as soon as new data comes in)
                        # however, cant exclude that one data point added between definition of timeAx and y
                        y = self.device.convertDataDisplay(channel.getValues(subtractBackground=self.subtractLiveBackground if self.backgroundAction is not None else False,
                                              _min=i_min, _max=i_max, n=n)) # ignore last data point, possibly added after definition of timeAx #, _callSync='off'
                        if any(np.isnan([y[0], y[-1]])):
                            # y.shape[0] == 0 # should never happen as y is nan padded to timeAx.shape[0] which is > 1. It was reported only once and did not reoccur after a simple restart.
                            # cannot draw if only np.nan (e.g. when zooming into old data where a channel did not exist or was not enabled and data was padded with np.nan)
                            channel.plotCurve.clear()
                        else:
                            l = min(timeAx.shape[0], y.shape[0]) # make sure x any y have same shape
                            if channel.smooth != 0:
                                y = uniform_filter1d(y, channel.smooth)
                            channel.plotCurve.setData(timeAx[:l], y[:l])
                    else:
                        channel.plotCurve.clear()
                if apply:
                    self.livePlotWidget.autoRange() # required to trigger update if all plotcurves have been cleared but breaks automatic scaling -> stackoverflow?
                    self.livePlotWidget.enableAutoRange(self.livePlotWidget.getViewBox().XAxis, True)
                    self.livePlotWidget.enableAutoRange(self.livePlotWidget.getViewBox().YAxis, True)
            else:
                if channel.plotCurve is not None:
                    channel.plotCurve.clear()
                    channel.plotCurve = None
        if self.recording:
            # free up resources by limiting data points or stopping acquisition if UI becomes unresponsive
            # NOTE: when GUI thread becomes unresponsive, this function is sometimes delayed and sometimes too fast.
            self.device.interval_meas = int((time.time()*1000-self.lastPlotTime)) if self.lastPlotTime is not None else self.device.interval
            self.device.interval_tolerance = max(50, self.device.interval/10) # larger margin for error if interval is large.
            if abs(self.device.interval_meas - self.device.interval) < self.device.interval_tolerance:
                self.lagging = 0 # reset / ignore temporary lag if interval is within range
            elif self.device.interval_meas > self.device.interval + self.device.interval_tolerance: # increase self.lagging and react if interval is longer than expected
                if self.lagging < 10:
                    self.lagging += 1
                elif self.lagging < 20: # lagging 10 times in a row -> reduce data points
                    if self.lagging == 10:
                        self.pluginManager.DeviceManager.limit_display_size = True
                        self.pluginManager.DeviceManager.max_display_size = 1000
                        self.print(f'Slow GUI detected, limiting number of displayed data points to {self.pluginManager.DeviceManager.max_display_size} per channel.', flag=PRINT.WARNING)
                    self.lagging += 1
                else: # lagging > 19 times in a row -> turn of aquisition
                    if self.lagging == 20:
                        self.pluginManager.DeviceManager.stop()
                        self.print('Slow GUI detected, stopped acquisition. Reduce number of active channels or acquisition interval.'+
                                   ' Identify which plugin(s) is(are) most resource intensive and contact plugin author.', flag=PRINT.WARNING)
                # self.print(self.lagging)
            else:
                # keep self.lagging unchanged. One long interval can be followed by many short intervals when GUI is catching up with events.
                # This might happen due to another part of the program blocking the GUI temporarily or after decreasing max_display_size.
                # This should not trigger a reaction but also should not reset self.lagging as plotting is not yet stable.
                pass
            self.lastPlotTime = time.time()*1000

    def closeUserGUI(self):
        """:meta private:"""
        self.device.showLiveDisplay = False # state is remembered and restored from setting
        # self.remoteView.close() # not using parallelization for now
        super().closeUserGUI()

    def closeGUI(self):
        """:meta private:"""
        self.device.resetPlot() # plotCurve references will be deleted and have to be recreated later if needed
        self.recording = False
        self.legend = None
        self.pluginManager.toggleTitleBarDelayed()
        super().closeGUI()

    def updateTheme(self):
        """:meta private:"""
        super().updateTheme()
        self.livePlotWidget.setBackground(colors.bg)
        fg = colors.fg
        self.livePlotWidget.getAxis('left').setTextPen(fg)
        self.livePlotWidget.getAxis('top').setTextPen(fg)
        self.livePlotWidget.getAxis('right').setTextPen(fg)
        self.livePlotWidget.getAxis('bottom').setTextPen(fg)
        self.livePlotWidget.setLabel('bottom','<font size="5">Time</font>', color=fg) # do not overwrite text!
        self.livePlotWidget.xyLabel.setColor(fg)
        if self.legend is not None:
            self.legend.setLabelTextColor(fg)
            self.device.resetPlot()
            self.plot()

########################## Generic device interface #########################################

class Device(Plugin):
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
    name = 'Device' # overwrite after inheriting
    pluginType = PluginManager.TYPE.INPUTDEVICE
    """ :class:`Devices<esibd.plugins.Device>` are categorized as input or output devices.
    Overwrite with :attr:`~esibd.core.PluginManager.TYPE.OUTPUTDEVICE` after inheriting if applicable."""
    channelType = EsibdCore.Channel
    """Type of :class:`~esibd.core.Channel` used by the device. Overwrite by appropriate type in derived classes."""
    StaticDisplay = StaticDisplay
    """Defined here so that overwriting only affects only instance in device and not all instances.

    :meta private:
    """
    LiveDisplay = LiveDisplay
    """Defined here so that overwriting only affects single instance in device and not all instances.

    :meta private:
    """

    MAXSTORAGE = 'Max storage'
    MAXDATAPOINTS = 'Max data points'
    DISPLAYTIME = 'Display Time'
    LOGGING = 'Logging'
    unit : str = 'unit'
    """Unit used in user interface."""
    staticDisplay : StaticDisplay
    """Internal plugin to display data from file."""
    liveDisplay : LiveDisplay
    """Internal plugin to display data in real time."""
    inout : INOUT
    """Flag specifying if this is an input or output device."""
    channels : List[Channel]
    """List of :class:`channels<esibd.core.Channel>`."""
    useBackgrounds : bool
    """If True, the device implements controls to define and subtract background signals."""

    class SignalCommunicate(QObject): # signals that can be emitted by external threads
        """Object than bundles pyqtSignals for the device"""
        appendDataSignal    = pyqtSignal()
        """Signal that triggers appending of data from channels to history."""
        plotSignal = pyqtSignal()
        """Signal that triggers plotting of history."""

    class ChannelPlot(Plugin):
        """Simplified version of the Line plugin for plotting channels."""

        name = 'Line'
        version = '1.0'
        pluginType = PluginManager.TYPE.DISPLAY

        def __init__(self, device, pluginManager=None, dependencyPath=None):
            super().__init__(pluginManager, dependencyPath)
            self.device = device
            self.name = self.device.name

        def getIcon(self):
            return self.makeIcon('chart.png')

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

        def finalizeInit(self, aboutFunc=None):
            super().finalizeInit(aboutFunc)
            self.copyAction = self.addAction(self.copyClipboard, 'Image to Clipboard.', icon=self.imageClipboardIcon, before=self.aboutAction)

        def runTestParallel(self):
            if super().runTestParallel():
                self.testControl(self.copyAction, True, 1)

        def plot(self):
            """Plots current values from all real :class:`channels<esibd.core.Channel>`."""
            self.axes[0].clear()
            y = [c.value for c in self.device.channels if c.real]
            labels = [c.name for c in self.device.channels if c.real]
            _colors = [c.color for c in self.device.channels if c.real]
            x = np.arange(len(y))
            self.axes[0].scatter(x, y, marker='.', color=_colors)
            self.axes[0].set_ylabel(self.device.unit)
            self.axes[0].set_xticks(x, labels, rotation=30, ha='right', rotation_mode='anchor')
            self.canvas.draw_idle()

    def __init__(self, **kwargs): # Always use keyword arguments to allow forwarding to parent classes.
        super().__init__(**kwargs)
        if self.pluginType == PluginManager.TYPE.INPUTDEVICE:
            self.inout = INOUT.IN
        else:
            self.inout = INOUT.OUT
        self.useBackgrounds = False
        self.channels = []
        self.channelsChanged = False
        self.channelPlot = None
        self.updating = False # Surpress events while channel equations are evaluated
        self.time = DynamicNp(dtype=np.float64)
        self.interval_tolerance = None # how much the acquisitoin interval is allowd to deviate
        self.dataThread = None
        # internal constants
        self.confINI = f'{self.name}.ini' # not a file extension, but complete filename to save and restore configurations
        self.confh5 = f'_{self.name.lower()}.h5'
        self.previewFileTypes = [self.confINI, self.confh5]
        self.changeLog = []
        self.staticDisplay = self.StaticDisplay(parentPlugin=self, **kwargs) # need to initialize to access previewFileTypes
        self.liveDisplay = self.LiveDisplay(device=self, **kwargs)
        self.signalComm = self.SignalCommunicate()
        self.signalComm.appendDataSignal.connect(self.appendData)
        self.signalComm.plotSignal.connect(self.liveDisplay.plot)

    def initGUI(self):
        """:meta private:"""
        super().initGUI()
        self.advancedAction = self.addStateAction(lambda : self.toggleAdvanced(None),'Show advanced options and virtual channels.', self.makeCoreIcon('toolbox.png'),
                                                  'Hide advanced options and virtual channels.', self.makeCoreIcon('toolbox--pencil.png'), attr='advanced')
        self.importAction = self.addAction(lambda : self.loadConfiguration(None),'Import channels and values.', icon=self.makeCoreIcon('blue-folder-import.png'))
        self.exportAction = self.addAction(lambda : self.exportConfiguration(None),'Export channels and values.', icon=self.makeCoreIcon('blue-folder-export.png'))
        self.saveAction = self.addAction(self.saveConfiguration,'Save channels in current session.', icon=self.makeCoreIcon('database-export.png'))
        self.addAction(func=self.init, toolTip='(Re-)initialize device.', icon=self.makeCoreIcon('rocket-fly.png'))
        self.addStateAction(toolTipFalse=f'Show {self.name} live display.', iconFalse=self.makeCoreIcon('system-monitor.png'),
                                              toolTipTrue=f'Hide {self.name} live display.', iconTrue=self.makeCoreIcon('system-monitor--minus.png'),
                                              attr='showLiveDisplay', func=self.toggleLiveDisplay, default='true')
        self.duplicateChannelAction    = self.addAction(func=self.duplicateChannel, toolTip='Insert copy of selected channel.', icon=self.makeCoreIcon('table-insert-row.png'))
        self.deleteChannelAction    = self.addAction(func=self.deleteChannel, toolTip='Delete selected channel.', icon=self.makeCoreIcon('table-delete-row.png'))
        self.moveChannelUpAction    = self.addAction(func=lambda : self.moveChannel(up=True), toolTip='Move selected channel up.', icon=self.makeCoreIcon('table-up.png'))
        self.moveChannelDownAction  = self.addAction(func=lambda : self.moveChannel(up=False), toolTip='Move selected channel down.', icon=self.makeCoreIcon('table-down.png'))
        self.tree = QTreeWidget()
        self.addContentWidget(self.tree)
        self.loadConfiguration(default=True)
        self.estimateStorage()
        if self.inout == INOUT.IN:
            self.addAction(lambda : self.loadValues(None),'Load values only.', before=self.saveAction, icon=self.makeCoreIcon('table-import.png'))
            self.plotAction = self.addAction(self.showChannelPlot,'Plot values.', icon=self.makeCoreIcon('chart.png'))

    def finalizeInit(self, aboutFunc=None):
        """:meta private:"""
        super().finalizeInit(aboutFunc)
        if self.pluginManager.DeviceManager.restoreData:
            self.restoreOutputData()
            self.toggleLiveDisplay()

    def getDefaultSettings(self):
        """ Define device specific settings that will be added to the general settings tab.
        Settings will be generated automatically if not found in the settings file.
        Overwrite and extend as needed."""
        ds = {}
        ds[f'{self.name}/Interval'] = parameterDict(value=10000, _min=100, _max=10000, toolTip=f'Interval for {self.name} in ms.',
                                                                widgetType=Parameter.TYPE.INT, event=self.intervalChanged, attr='interval', instantUpdate=False)
        ds[f'{self.name}/Interval (measured)'] = parameterDict(value=0, internal=True,
        toolTip=f'Measured plot interval for {self.name} in ms.\n If this deviates multiple times in a row, the number of display points will be reduced and eventually acquisition\n'+
                ' will be stopped to ensure the application remains responsive.',
                                                                widgetType=Parameter.TYPE.INT, indicator=True, _min=0, _max=10000, attr='interval_meas')
        ds[f'{self.name}/{self.MAXSTORAGE}'] = parameterDict(value=50, widgetType=Parameter.TYPE.INT, _min=5, _max=500, event=self.estimateStorage,
                                                          toolTip='Maximum amount of storage used to store history in MB.', attr='maxStorage')
        ds[f'{self.name}/{self.MAXDATAPOINTS}'] = parameterDict(value=500000, indicator=True, widgetType=Parameter.TYPE.INT, attr='maxDataPoints',
        toolTip='Maximum number of data points saved per channel, based on max storage. If this is reached, older data will be thinned to allow to keep longer history.')
        ds[f'{self.name}/Logging'] = parameterDict(value=False, toolTip='Show warnings in console. Only use when debugging to keep console uncluttered.',
                                          widgetType=Parameter.TYPE.BOOL, attr='log')
        return ds

    def runTestParallel(self):
        """:meta private:"""
        if super().runTestParallel():
            # Note: ignore repeated line indicating testing of device.name as static and live displays have same name
            if self.staticDisplayActive():
                self.staticDisplay.runTestParallel()
            if self.liveDisplayActive():
                self.liveDisplay.runTestParallel()
            if self.channelPlotActive():
                self.channelPlot.runTestParallel()
            # init, start, pause, stop acquisition will be tested by instManager
            self.testControl(self.advancedAction, True, 1) # keep history, test manually for dummy devices if applicable
            self.testControl(self.saveAction, True, 1)
            self.testControl(self.channels[0].getParameterByName(Channel.SELECT).getWidget(), True, 1)
            # self.testControl(self.moveChannelDownAction, True, 2) # test manually, cant guarantee events are processed in correct order and channel will temporarily point to deleted widgets
            # self.testControl(self.moveChannelUpAction, True, 2)
            # self.testControl(self.duplicateChannelAction, True, 2) # test manually, cant guarantee events are processed in correct order and channel will temporarily point to deleted widgets
            # self.testControl(self.deleteChannelAction, True, 2)
            if self.inout == INOUT.IN:
                self.testControl(self.plotAction, True, 1)
                if hasattr(self,'onAction'):
                    self.testControl(self.onAction, True, 1)

    def intervalChanged(self):
        """Extend to add code to be executed in case the :ref:`acquisition_interval` changes."""
        self.estimateStorage()

    def startAcquisition(self):
        """Extend to start all device related communication."""

    def stopAcquisition(self):
        """Extend to stop all device related communication."""

    def startRecording(self):
        if not self.liveDisplayActive():
            return
        if self.dataThread is not None and self.dataThread.is_alive():
            self.print('Wait for data acquisition thread to complete before restarting acquisition.', PRINT.WARNING)
            self.liveDisplay.recording = False
            self.dataThread.join(timeout=5) # may freeze GUI temporarily but need to be sure old thread is stopped before starting new one
            if self.dataThread.is_alive():
                self.print('Data acquisition thread did not complete. Reset connection manually.', PRINT.ERROR)
                return
        self.resetPlot() # update legend in case channels have changed
        self.liveDisplay.recording = True
        self.liveDisplay.lagging = 0
        self.dataThread = Thread(target=self.runDataThread, args =(lambda : self.liveDisplay.recording,), name=f'{self.name} dataThread')
        self.dataThread.daemon = True # Terminate with main app independent of stop condition
        self.dataThread.start()

    def stop(self):
        """Stops recording and also closes all device communication.
        Extend to add custom code to close device communication."""
        self.stopAcquisition()
        self.liveDisplay.recording = False
        if hasattr(self,'onAction') and self.onAction.state:
            self.onAction.state = False
            self.onAction.triggered.emit()
        if self.pluginManager.closing:
            time.sleep(.1)

    def init(self):
        """Extend device initialization as needed. Note, this inits the device GUI.
        Device communication is initialized by the corresponding :class:`~esibd.core.DeviceController`."""
        self.resetPlot()

    def initialized(self):
        """Extend to indicate when the device is initialized."""
        return False

    def supportsFile(self, file):
        return any(file.name.endswith(suffix) for suffix in (self.getSupportedFiles())) # does not support any files for preview, only when explicitly loading

    def getSupportedFiles(self):
        return self.previewFileTypes+self.staticDisplay.previewFileTypes+self.liveDisplay.previewFileTypes

    def customConfigFile(self, file):
        return self.pluginManager.Settings.configPath / file

    def getChannelByName(self, name):
        """Returns a device specific channel based on its unique name."""
        return next((c for c in self.channels if c.name.strip().lower() == name.strip().lower()), None)

    def getSelectedChannel(self):
        """Returns selected channel. Note, channels can only be selected in advanced mode."""
        return next((c for c in self.channels if c.select), None)

    def setBackground(self):
        """Sets the background based on current channel values.
        Only used by output devices."""
        if self.useBackgrounds:
            for channel in self.channels: # save present signal as background
                # use average of last 10 s if possible
                length = min(int(10000/self.interval),len(channel.getValues(subtractBackground=False)))
                channel.background = np.mean(channel.getValues(subtractBackground=False)[-length:])

    def subtractBackgroundActive(self):
        return self.useBackgrounds and self.liveDisplayActive and self.liveDisplay.subtractLiveBackground

    def estimateStorage(self):
        numChannelsBackgrounds = len(self.channels) * 2 if self.useBackgrounds else len(self.channels)
        self.maxDataPoints = (self.maxStorage * 1024**2 - 8) / (4 * numChannelsBackgrounds)  # including time channel
        totalDays = self.interval / 1000 * self.maxDataPoints / 3600 / 24
        self.pluginManager.Settings.settings[f'{self.name}/{self.MAXDATAPOINTS}'].getWidget().setToolTip(
        f'Using an interval of {self.interval} ms and maximum storage of {self.maxStorage:d} MB allows for\n'+
        f'a history of {totalDays:.2f} days or {self.maxDataPoints} datapoints for {len(self.channels)} channels.\n'+
        'After this time, data thinning will allow to retain even older data, but at lower resolution.')

    def toggleAdvanced(self, advanced=None):
        if advanced is not None:
            self.advanced = advanced
        self.importAction.setVisible(self.advanced)
        self.exportAction.setVisible(self.advanced)
        self.duplicateChannelAction.setVisible(self.advanced)
        self.deleteChannelAction.setVisible(self.advanced)
        self.moveChannelUpAction.setVisible(self.advanced)
        self.moveChannelDownAction.setVisible(self.advanced)
        if self.liveDisplayActive():
            self.liveDisplay.clearHistoryAction.setVisible(self.advanced)
        for i, item in enumerate(self.channels[0].getSortedDefaultChannel().values()):
            if item[Parameter.ADVANCED]:
                self.tree.setColumnHidden(i, not self.advanced)
        if self.inout == INOUT.IN:
            for c in self.channels:
                c.setHidden(not (self.advanced or c.active))
        else: # INOUT.OUT:
            for c in self.channels:
                c.setHidden(not (self.advanced or c.active or c.display))

    def loadConfiguration(self, file=None, default=False):
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
            file = Path(QFileDialog.getOpenFileName(parent=None, caption=self.SELECTFILE, filter=self.FILTER_INI_H5)[0])
        if file != Path('.'):
            self.loading = True
            self.tree.setUpdatesEnabled(False)
            self.tree.setRootIsDecorated(False) # no need to show expander
            if file.suffix == EsibdCore.FILE_INI:
                if file.exists(): # create default if not exist
                    confParser = configparser.ConfigParser()
                    confParser.read(file)
                    if len(confParser.items()) < 3: # minimum: DEFAULT, Info, and one Channel
                        self.print(f'File {file} does not contain valid channels. Repair the file manually or delete it,' +
                                                    ' to trigger generation of a valid default channel on next start.', PRINT.WARNING)
                        self.tree.setHeaderLabels(['No valid channels found. Repair or delete config file.'])
                        self.tree.setUpdatesEnabled(True)
                        self.loading = False
                        return
                    self.updateChannelConfig([i for n, i in confParser.items() if n not in [Parameter.DEFAULT.upper(), EsibdCore.VERSION, EsibdCore.INFO]], file)
                else: # Generate default settings file if file was not found.
                    # To update files with new parameters, simply delete the old file and the new one will be generated.
                    self.print(f'Generating default config file {file}')
                    for i in range(9):
                        self.addChannel(item={Parameter.NAME : f'{self.name}{i+1}'})
                    self.exportConfiguration(file, default=True)
            else: # file.suffix == EsibdCore.FILE_H5:
                with h5py.File(name=file, mode='r', track_order=True) as f:
                    g = f[self.name]
                    items = [{} for _ in range(len(g[Parameter.NAME]))]
                    for i, name in enumerate(g[Parameter.NAME].asstr()):
                        items[i][Parameter.NAME] = name
                    default = self.channelType(device=self, tree=None)
                    for name, parameter in default.getSortedDefaultChannel().items():
                        if name in default.tempParameters():
                            continue # temp parameters are not saved
                        values = None
                        if parameter[Parameter.WIDGETTYPE] in [Parameter.TYPE.INT, Parameter.TYPE.FLOAT]:
                            values = g[name]
                        elif parameter[Parameter.WIDGETTYPE] == Parameter.TYPE.BOOL:
                            values = [str(b) for b in g[name]]
                        else:
                            values = g[name].asstr()
                        for i, v in enumerate(values):
                            items[i][name] = v
                    self.updateChannelConfig(items, file)

            self.tree.setHeaderLabels([(name.title() if dict[Parameter.HEADER] is None else dict[Parameter.HEADER])
                                                    for name, dict in self.channels[0].getSortedDefaultChannel().items()])
            self.tree.header().setStretchLastSection(False)
            self.tree.header().setMinimumSectionSize(0)
            self.tree.header().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
            self.toggleAdvanced(False)
            self.tree.setUpdatesEnabled(True)
            self.loading=False
            self.pluginManager.DeviceManager.globalUpdate(inout=self.inout)
            # if there was a history, it has been invalidated by reinitializing all channels.
            if not self.pluginManager.loading:
                for c in self.channels:
                    c.clearPlotCurve()

    @property
    def LOADVALUES(self):
        return f'Load {self.name} values.'

    def loadValues(self, file = None):
        """Loads values only, instead of entire configuration, for :class:`channels<esibd.core.Channel>` matching in file and current configuraion.
        Channels that exist in the file but not in the current configuration will be ignored.
        Only used by input devices."""
        if file is None: # get file via dialog
            file = Path(QFileDialog.getOpenFileName(parent=None, caption=self.SELECTFILE, filter=self.FILTER_INI_H5)[0])
        if file != Path('.'):
            self.changeLog = [f'Change log for loading values for {self.name} from {file.name}:']
            if file.suffix == EsibdCore.FILE_INI:
                confParser = configparser.ConfigParser()
                confParser.read(file)
                for name, item in confParser.items():
                    if not name in [Parameter.DEFAULT.upper(), EsibdCore.VERSION, EsibdCore.INFO]:
                        self.updateChannelValue(item.get(Parameter.NAME), float(item.get(Parameter.VALUE,'0')))
            else: # FILE_H5
                with h5py.File(name=file, mode='r', track_order=True) as f:
                    g = f[self.name]
                    for n, v in zip(g[Parameter.NAME].asstr(), g[Parameter.VALUE]):
                        self.updateChannelValue(n, v)
            if len(self.changeLog) == 1:
                self.changeLog.append('No changes.')
            self.pluginManager.Text.setText('\n'.join(self.changeLog), False)
            self.print('Values updated. Change log available in Text plugin.')

    def updateChannelValue(self, name, value):
        c = self.getChannelByName(name)
        if c is not None:
            initialVal = c.value
            c.value=value
            if initialVal != c.value: # c.value might be differnt from value due to coerced range
                self.changeLog.append(f'Value of channel {name} changed from {initialVal} to {c.value} {self.unit}.')
        else:
            self.print(f'Could not find channel {name}.', PRINT.WARNING)

    def apply(self, apply=False):
        """Applies :class:`~esibd.core.Channel` values to physical devices. Only used by input :class:`devices<esibd.plugins.Device>`.

        :param apply: If false, only values that have changed since last apply will be updated, defaults to False
        :type apply: bool, optional
        """

    def updateChannelConfig(self, items, file):
        """Scans for changes when loading configuration and displays change log
        before overwriting old channel configuraion.

        :param items: :class:`~esibd.core.Channel` items from file
        :type items: List[:class:`~esibd.core.Channel`]
        :param file: config file
        :type file: pathlib.Path
        """
        # Note: h5diff can be used alternatively to find changes, but the output is not formated in a user friendly way (hard to correlate values with channels).
        if not self.pluginManager.loading:
            self.changeLog = [f'Change log for loading channels for {self.name} from {file.name}:']
            self.changeLog += self.compareItemsConfig(items)[0]
            self.pluginManager.Text.setText('\n'.join(self.changeLog), False) # show changelog
            self.print('Configuration updated. Change log available in Text plugin.')
        # clear and load new channels
        self.channels=[]
        self.tree.clear()
        for item in items:
            self.addChannel(item=item)
            if np.mod(len(self.channels),5) == 0:
                QApplication.processEvents()
                #print(f'{self.name} {len(self.channels)} channels')

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
                    parameter = channel.getParameterByName(name)
                    if name in item and not parameter.equals(item[name]):
                        if parameter.indicator and ignoreIndicators:
                            continue
                        changeLog.append(f'Updating parameter {name} on channel {channel.name} from {parameter.value} to {item[name]}')
        newNames = [item[Parameter.NAME] for item in items]
        for channel in self.channels:
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

    def modifyChannel(self):
        selectedChannel = self.getSelectedChannel()
        if selectedChannel is None:
            self.print('No channel selected.')
        else:
            return selectedChannel
        return None

    def duplicateChannel(self):
        selectedChannel = self.modifyChannel()
        if selectedChannel is not None:
            index=self.channels.index(selectedChannel)
            newChannel = selectedChannel.asDict()
            newChannel[selectedChannel.NAME] = f'{selectedChannel.name}_copy'
            self.addChannel(item=newChannel, index=index + 1)
            self.resetPlot()

    def deleteChannel(self):
        selectedChannel = self.modifyChannel()
        if selectedChannel is not None:
            if len(self.channels) == 1:
                self.print('Need to keep at least one channel.')
                return
            index = self.channels.index(selectedChannel)
            self.channels.pop(index)
            self.tree.takeTopLevelItem(index)
            self.resetPlot()

    def moveChannel(self, up):
        """Moves the channel up or down in the list of channels.

        :param up: Move up if True, else down.
        :type up: bool
        """
        selectedChannel = self.modifyChannel()
        if selectedChannel is not None:
            index = self.channels.index(selectedChannel)
            if index == 0 and up or index == len(self.channels)-1 and not up:
                self.print(f"Cannot move channel further {'up' if up else 'down'}.")
                return
            if self.modifyChannel().device.initialized():
                self.print(f"Stop commuinication for {self.modifyChannel().device.name} to move channel.")
                return
            self.channels.pop(index)
            self.tree.takeTopLevelItem(index)
            oldValues = selectedChannel.values.get()
            if up:
                self.addChannel(item=selectedChannel.asDict(), index=index - 1)
            else:
                self.addChannel(item=selectedChannel.asDict(), index=index + 1)
            if len(oldValues) > 0:
                self.getChannelByName(selectedChannel.name).values = DynamicNp(initialData=oldValues, max_size=self.maxDataPoints)
                self.getChannelByName(selectedChannel.name).value = oldValues[-1]
            self.resetPlot()

    def saveConfiguration(self):
        self.pluginManager.Settings.measurementNumber += 1
        file = self.pluginManager.Settings.getMeasurementFileName(self.confh5)
        self.exportConfiguration(file)
        self.print(f'Saved {file.name}')

    CHANNEL = 'Channel'
    SELECTFILE = 'Select File'

    def exportConfiguration(self, file=None, default=False):
        """Saves an .ini or .h5 file which contains the configuration for this :class:`~esibd.plugins.Device`.
        The .ini file can be easily edited manually with a text editor to add more :class:`channels<esibd.core.Channel>`."""
        if len(self.channels) == 0:
            self.print('No channels found to export.', PRINT.ERROR)
            return
        if default:
            file = self.customConfigFile(self.confINI)
        if file is None: # get file via dialog
            file = Path(QFileDialog.getSaveFileName(parent=None, caption=self.SELECTFILE, filter=self.FILTER_INI_H5)[0])
        if file != Path('.'):
            if file.suffix == FILE_INI:
                confParser = configparser.ConfigParser()
                confParser[INFO] = infoDict(self.name)
                for i, channel in enumerate(self.channels):
                    confParser[f'{self.CHANNEL}_{i:03d}'] = channel.asDict()
                with open(file,'w', encoding=self.UTF8) as configfile:
                    confParser.write(configfile)
            else: # h5
                with h5py.File(file,'a', track_order=True) as f:
                    self.hdfUpdateVersion(f)
                    g = self.requireGroup(f, self.name)
                    for parameter in self.channels[0].asDict():
                        if parameter in g:
                            self.print(f'Ignoring duplicate parameter {parameter}', PRINT.WARNING)
                            continue
                        widgetType = self.channels[0].getParameterByName(parameter).widgetType
                        data = [c.getParameterByName(parameter).value for c in self.channels]
                        dtype = None
                        if widgetType == Parameter.TYPE.INT:
                            dtype = np.int32
                        elif widgetType == Parameter.TYPE.FLOAT:
                            dtype = np.float32
                        elif widgetType == Parameter.TYPE.BOOL:
                            dtype = np.bool8
                        elif widgetType == Parameter.TYPE.COLOR:
                            data = [c.getParameterByName(parameter).value for c in self.channels]
                            dtype = 'S7'
                        else: # widgetType in [Parameter.TYPE.COMBO, Parameter.TYPE.INTCOMBO, Parameter.TYPE.TEXT, Parameter.TYPE.LABEL]:
                            dtype = f'S{len(max([str(d) for d in data], key=len))}' # use length of longest string as fixed length is required
                        g.create_dataset(name=parameter, data=np.asarray(data, dtype=dtype)) # do not save as attributes. very very memory intensive!
        if not self.pluginManager.loading:
            self.pluginManager.Explorer.populateTree()

    def exportOutputData(self, default=False):
        if default:
            t = self.time.get()
            if t.shape[0] == 0:
                return # no data to save
            file = Path(self.pluginManager.Settings.configPath) / self.confh5.strip('_')
        else:
            self.pluginManager.Settings.measurementNumber += 1
            file = self.pluginManager.Settings.getMeasurementFileName(self.liveDisplay.previewFileTypes[0])
        with h5py.File(name=file, mode='w' if default else 'a', track_order=True) as f:
            self.hdfUpdateVersion(f)
            self.appendOutputData(f, default=default)
        self.print(f'Stored data in {file.name}')
        if not default:
            self.pluginManager.DeviceManager.exportConfiguration(file=file) # save corresponding device settings in measurement file
            self.pluginManager.Explorer.populateTree()

    def appendOutputData(self, f, default=False):
        """Appends :class:`~esibd.plugins.Device` data to hdf file."""
        fullRange = True
        g = self.requireGroup(f, self.name) #, track_order=True

        t = self.time.get()
        if not default and t.shape[0] > 0:
            # Only save currently visible data (specific regions of interest).
            # Otherwise history of last few days might be added to files, making it hard to find the region of interest.
            # Complete data can still be exported if needed by displaying entire history before exporting.
            # if default == True: save entire history to default file for restoring on next start
            t_min, t_max = self.liveDisplay.livePlotWidget.getAxis('bottom').range
            i_min = np.argmin(np.abs(t - t_min))
            i_max = np.argmin(np.abs(t - t_max))
            fullRange = False

        i = self.requireGroup(g, Scan.INPUTCHANNELS)
        try:
            i.create_dataset(self.TIME, data=t if fullRange else t[i_min:i_max], dtype=np.float64, track_order=True) # need double precision to keep all decimal places
        except ValueError as e:
            self.print(f'Could not create dataset. If the file already exists, make sure to increase the measurment index and try again. Original error: {e}', PRINT.ERROR)
            return

        o = self.requireGroup(g, Scan.OUTPUTCHANNELS)
        # avoid using getValues() function and use get() to make sure raw data, without background subtraction or unit correction etc. is saved in file
        for channel in self.getActiveChannels():
            if channel.name in o:
                self.print(f'Ignoring duplicate channel {channel.name}', PRINT.WARNING)
                continue
            h = o.create_dataset(channel.name, data=channel.values.get() if fullRange else channel.values.get()[i_min:i_max], dtype='f')
            h.attrs[Scan.UNIT] = self.unit
            if self.useBackgrounds:
                # Note: If data format will be changed in future (ensuring backwards compatibilty), consider saving single 2D sataset with data and background instead. for now, no need
                h = o.create_dataset(channel.name + '_BG', data=channel.backgrounds.get() if fullRange else channel.backgrounds.get()[i_min:i_max], dtype='f')
                h.attrs[Scan.UNIT] = self.unit

    def restoreOutputData(self):
        """Restores data from internal restore file."""
        file = Path(self.pluginManager.Settings.configPath) / self.confh5.strip('_')
        if file.exists():
            with h5py.File(name=file, mode='r', track_order=True) as f:
                if self.name not in f:
                    return
                g = f[self.name]
                if not (Scan.INPUTCHANNELS in g and Scan.OUTPUTCHANNELS in g):
                    return False
                i = g[Scan.INPUTCHANNELS]
                self.time = DynamicNp(initialData=i[self.TIME][:], max_size=self.maxDataPoints, dtype=np.float64)

                o = g[Scan.OUTPUTCHANNELS]
                for name, item in o.items():
                    c = self.getChannelByName(name.strip('_BG'))
                    if c is not None:
                        if name.endswith('_BG'):
                            c.backgrounds = DynamicNp(initialData=item[:], max_size=self.maxDataPoints)
                        else:
                            c.values = DynamicNp(initialData=item[:], max_size=self.maxDataPoints)
            self.print(f'Restored data from {file.name}')

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

    def close(self):
        self.stopAcquisition()
        if self.channelConfigChanged(default=True) or self.channelsChanged:
            self.exportConfiguration(default=True)
        self.exportOutputData(default=True)

    def closeGUI(self):
        """:meta private:"""
        self.toggleLiveDisplay(False)
        self.toggleStaticDisplay(False)
        self.toggleChannelPlot(False)
        super().closeGUI()

    def loadData(self, file, _show=True):
        """:meta private:"""
        if self.liveDisplay.supportsFile(file) or self.staticDisplay.supportsFile(file):
            self.staticDisplay.loadData(file, _show)
        else:
            if self.inout == INOUT.IN:
                self.pluginManager.Text.setText('Load channels or values using right click or import file explicitly.', False)
            else:
                self.pluginManager.Text.setText('Load channels using right click or import file explicitly.', False)

    def getActiveChannels(self):
        return [c for c in self.channels if c.getValues().shape[0] != 0]

    def updateValues(self, N=2, apply=False):
        """Updates channel values based on equations.
        This minimal implementation will not give a warning about circular definitions.
        It will also fail if expressions are nested on more than N levels but N can be increased as needed."""
        # N=2 should however be sufficient for day to day work.
        # More complex algorithms should only be implemented if they are required to solve a practical problem.
        if self.updating or self.pluginManager.closing:
            return
        self.updating = True # prevent recursive call caused by changing values from here
        channels = self.pluginManager.DeviceManager.channels(inout=INOUT.IN) if self.inout == INOUT.IN else self.pluginManager.DeviceManager.channels(inout=INOUT.BOTH)
        for _ in range(N): # go through parsing N times, in case the dependencies are not ordered
            for channel in [c for c in self.channels if not c.active and c.equation != '']: # ignore if no equation defined
                equ = channel.equation
                error = False
                for name in [c.name for c in channels if c.name != '']: # for name in channel names
                    if name in equ:
                        c = next((c for c in channels if c.name == name), None)
                        if c is None:
                            self.print(f'Could not find channel {name} in equation of channel {channel.name}.', PRINT.WARNING)
                            error = True
                        else:
                            equ = equ.replace(c.name, f'{c.value}')
                if error:
                    self.print(f'Could not resolve equation of channel {channel.name}.', PRINT.WARNING)
                else:
                    channel.value = aeval(equ) or 0 # evaluate
        if self.inout == INOUT.IN:
            self.apply(apply)
        self.updating = False

    ######################################## Acquisition ###############################################

    def toggleRecording(self):
        """Toggle recoding of data in :class:`~esibd.plugins.LiveDisplay`."""
        if self.liveDisplayActive():
            if self.liveDisplay.recording:
                self.liveDisplay.recording = False
                self.pluginManager.DeviceManager.stopScans()
            else:
                if not self.initialized():
                    self.init() # will start recording when initialization is complete
                else:
                    self.startAcquisition()
                self.resetPlot()
                self.startRecording()

    def appendData(self):
        # all new entries including time are added in one step to avoid any chance of unequal array sizes
        if self.pluginManager.closing:
            return
        self.updateValues()
        for c in self.channels:
            c.appendValue(self.time.size) # add time after values to make sure value arrays stay alligned with time array
        self.time.add(time.time()) # add time in seconds
        # self.interval_meas = (time.time()-self.time.data[self.time.size-11])*100 if self.time.size > 10 else 0 -> using ploting interval instead
        self.signalComm.plotSignal.emit()

    def clearHistory(self):
        self.resetPlot()
        for c in self.channels:
            c.clearHistory(max_size=self.maxDataPoints)
        self.time = DynamicNp(max_size=self.maxDataPoints, dtype=np.float64)

    def runDataThread(self, recording):
        """Regulartly triggers reading and appending of data.
        This uses the current value of :class:`channels<esibd.core.Channel>` which is updated
        independently by the corresponding :class:`~esibd.core.DeviceController`."""
        while recording():
            # time.sleep precision in low ms range on windows -> will usually be a few ms late
            # e.g. 0.1 will not give a true 10 Hz repetition rate
            # if that becomes important and decreasing the interval to compensate for delay is not sufficient a better method is required
            self.signalComm.appendDataSignal.emit()
            time.sleep(self.interval/1000) # in seconds # wait at end to avoid emitting signal after recording set to False

    def resetPlot(self):
        if self.liveDisplayActive():
            self.liveDisplay.livePlotWidget.clear()
            self.liveDisplay.legend = self.liveDisplay.livePlotWidget.addLegend(labelTextColor=colors.fg) # before adding plots
        for c in self.channels: # getInitializedChannels() don't know yet which will be initialized -> create all
            c.plotCurve = None

    def toggleLiveDisplay(self, visible=None):
        if visible if visible is not None else self.showLiveDisplay:
            self.liveDisplay.provideDock()
            self.liveDisplay.finalizeInit()
            self.liveDisplay.raiseDock(True)
        else:
            if self.liveDisplayActive():
                self.liveDisplay.closeGUI()
            self.pluginManager.toggleTitleBarDelayed()

    def liveDisplayActive(self):
        return self.liveDisplay is not None and self.liveDisplay.initializedDock

    def toggleStaticDisplay(self, visible):
        if visible:
            self.staticDisplay.provideDock()
            self.staticDisplay.raiseDock(True)
        elif self.staticDisplayActive():
            self.staticDisplay.closeGUI()

    def staticDisplayActive(self):
        return self.staticDisplay is not None and self.staticDisplay.initializedDock

    def toggleTitleBar(self):
        """:meta private:"""
        super().toggleTitleBar()
        if self.liveDisplayActive():
            self.liveDisplay.toggleTitleBar()
        if self.staticDisplayActive():
            self.staticDisplay.toggleTitleBar()

    def convertDataDisplay(self, data):
        """Overwrite to apply scaling and offsets to data before it is displayed. Use, e.g., to convert to another unit."""
        return data

    def channelSelection(self, channel=None):
        if channel is not None and channel.select: # only one channel should be selected at all times
            for c in self.channels:
                if c is not channel:
                    c.select = False

    def getUnit(self):
        """Overwrite if you want to change units dynamically."""
        return self.unit

    def channelPlotActive(self):
        return self.channelPlot is not None and self.channelPlot.initializedDock

    def toggleChannelPlot(self, visible):
        if visible:
            if self.channelPlot is None or not self.channelPlot.initializedDock:
                self.channelPlot = self.ChannelPlot(device=self, pluginManager=self.pluginManager, dependencyPath=self.dependencyPath)
                self.channelPlot.provideDock()
        elif self.channelPlot is not None and self.channelPlot.initializedDock:
            self.channelPlot.closeGUI()

    def showChannelPlot(self):
        self.toggleChannelPlot(True)
        self.channelPlot.raiseDock(True)
        self.channelPlot.plot()

    def updateTheme(self):
        """:meta private:"""
        super().updateTheme()
        self.loading = True
        for c in self.channels:
            c.updateColor()
        self.loading = False
        if self.staticDisplayActive():
            self.staticDisplay.updateTheme()
        if self.liveDisplayActive():
            self.liveDisplay.updateTheme()

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

    PARAMETER   = 'Parameter'
    VERSION     = 'Version'
    VALUE       = 'Value'
    UNIT        = 'Unit'
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
    INPUTCHANNELS = 'Input Channels'
    OUTPUTCHANNELS = 'Output Channels'
    SCAN            = 'Scan'
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
    outputs : List[EsibdCore.MetaChannel]
    """List of output :class:`meta channels<esibd.core.MetaChannel>`."""

    class SignalCommunicate(QObject):
        """Object that bundles pyqtSignals."""
        scanUpdateSignal        = pyqtSignal(bool)
        """Signal that triggers update of the figure and, if True is passed, saving of data."""
        updateRecordingSignal   = pyqtSignal(bool)
        """Signal that allows to stop recording from an external thread."""
        saveScanCompleteSignal  = pyqtSignal()
        """Signal that confirms that scan data has been saved and a new scan can be started."""

    class Display(Plugin):
        """Display for base scan. Extend as needed.

        :meta private:
        """
        pluginType=PluginManager.TYPE.DISPLAY

        def __init__(self, scan, **kwargs):
            self.scan = scan
            self.name = self.scan.name
            self.plot = self.scan.plot
            super().__init__(**kwargs)

        def initGUI(self):
            """:meta private:"""
            super().initGUI()
            self.mouseMoving = False
            self.mouseActive = False
            self.initFig()

        def initFig(self):
            self.provideFig()

        def provideDock(self):
            """:meta private:"""
            if super().provideDock():
                self.finalizeInit(aboutFunc=self.scan.about)

        def finalizeInit(self, aboutFunc=None):
            """:meta private:"""
            super().finalizeInit(aboutFunc)
            self.copyAction = self.addAction(self.copyClipboard,'Image to Clipboard.', self.imageClipboardIcon, before=self.aboutAction)
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

        def runTestParallel(self):
            """:meta private:"""
            if super().runTestParallel():
                self.testControl(self.copyAction, True, 1)

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
                        if _input.channel is not None:
                            _input.channel.value = event.xdata if i == 0 else event.ydata # 3D not supported
                        else:
                            self.print(f'Could not find channel {self.scan.inputs[i].name}.')
                    if self.axes[-1].cursor is not None:
                        self.axes[-1].cursor.ondrag(event)
                self.mouseMoving = False

        def closeGUI(self):
            """:meta private:"""
            self.scan.recording = False
            return super().closeGUI()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.getChannelByName = self.pluginManager.DeviceManager.getChannelByName
        self.ICON_PLAY = self.makeCoreIcon('play.png')
        self.ICON_STOP = self.makeCoreIcon('stop.png')
        self._finished  = True
        self.file = None
        self.configINI = f'{self.name}.ini'
        self.previewFileTypes = [self.configINI, f'{self.name.lower()}.h5']
        self.useDisplayChannel = False
        self.measurementsPerStep = 0
        self.display = None
        self.runThread = None
        self.saveThread = None
        self.signalComm = self.SignalCommunicate()
        self.signalComm.scanUpdateSignal.connect(self.scanUpdate)
        self.signalComm.updateRecordingSignal.connect(self.updateRecording)
        self.signalComm.saveScanCompleteSignal.connect(self.saveScanComplete)
        self.init()

    def initGUI(self):
        """:meta private:"""
        self.loading = True
        super().initGUI()
        settingsTreeWidget = QTreeWidget()
        settingsTreeWidget.setHeaderLabels([self.PARAMETER, self.VALUE])
        settingsTreeWidget.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        # size to content prevents manual resize
        settingsTreeWidget.header().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.addContentWidget(settingsTreeWidget)
        self.settingsMgr = SettingsManager(parentPlugin=self, pluginManager=self.pluginManager, name=f'{self.name} Settings', tree=settingsTreeWidget,
                                        defaultFile=self.pluginManager.Settings.configPath / self.configINI)
        self.settingsMgr.addDefaultSettings(plugin=self)
        self.settingsMgr.init()
        self.expandTree(self.settingsMgr.tree)
        self.notes = '' # should always have current notes or no notes

        self.addAction(lambda : self.loadSettings(file=None),'Load settings.', icon=self.makeCoreIcon('blue-folder-import.png'))
        self.addAction(lambda : self.saveSettings(file=None),'Export settings.', icon=self.makeCoreIcon('blue-folder-export.png'))
        self.recordingAction = self.addStateAction(self.toggleRecording,'Start.', self.ICON_PLAY,'Stop.', self.ICON_STOP)
        self.estimateScanTime()
        self.loading = False

    def init(self):
        self.inputs, self.outputs = [], []

    def runTestParallel(self):
        """:meta private:"""
        if super().runTestParallel():
            if self.display is not None:
                self.display.runTestParallel()

    @property
    def recording(self):
        """True if currently recording.
        Set to False to stop recording and save available data."""
        return self.recordingAction.state

    @recording.setter
    def recording(self, recording):
        # make sure to only call from main thread as GUI is affected!
        self.recordingAction.state = recording

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
        self.pluginManager.Settings.measurementNumber += 1
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

    def populateDisplayChannel(self):
        if self.display is not None and self.useDisplayChannel:
            self.loading = True
            self.display.displayComboBox.clear()
            for o in self.outputs: # use channels form current acquisition or from file.
                self.display.displayComboBox.insertItem(self.display.displayComboBox.count(), o.name)
            self.loading = False
            self.updateDisplayDefault()

    def loadSettings(self, file=None, default=False):
        self.settingsMgr.loadSettings(file=file, default=default)
        self.expandTree(self.settingsMgr.tree)
        self.updateDisplayChannel()
        self.estimateScanTime()

    def saveSettings(self, file=None, default=False):
        self.settingsMgr.saveSettings(file=file, default=default)

    def getDefaultSettings(self):
        """:meta private:"""
        # ATTENTION: Changing setting names will cause backwards incompatibility unless handeled explicitly!
        ds = {}
        ds[self.NOTES]  = parameterDict(value='', toolTip='Add specific notes to current scan. Will be reset after scan is saved.', widgetType=Parameter.TYPE.TEXT,
                                        attr='notes')
        ds[self.DISPLAY] = parameterDict(value='RT_Front-Plate', toolTip='Default output channel used when scanning. Other channels defined here will be recorded as well.',
                                         items='RT_Front-Plate, RT_Detector, RT_Sample-Center, RT_Sample-End, LALB-Aperture',
                                         widgetType=Parameter.TYPE.COMBO, attr='displayDefault', event=self.updateDisplayDefault)
            # NOTE: alternatively the wait time could be determined proportional to the step.
            # While this would be technically cleaner and more time efficient,
            # the present implementation is easier to understand and should work well as long as the step sizes do not change too often
        ds[self.WAIT]         = parameterDict(value=500, toolTip='Wait time between small steps in ms.', _min=10, event=self.estimateScanTime,
                                                                        widgetType=Parameter.TYPE.INT, attr='wait')
        ds[self.WAITLONG]     = parameterDict(value=2000, toolTip=f'Wait time between steps larger than {self.LARGESTEP} in ms.', _min=10,
                                                                        widgetType=Parameter.TYPE.INT, attr='waitlong', event=self.estimateScanTime)
        ds[self.LARGESTEP]    = parameterDict(value=2, toolTip='Threshold step size to use longer wait time.', event=self.estimateScanTime,
                                                                        widgetType=Parameter.TYPE.FLOAT, attr='largestep')
        ds[self.AVERAGE]      = parameterDict(value=1000, toolTip='Average time in ms.', widgetType=Parameter.TYPE.INT, attr='average', event=self.estimateScanTime)
        ds[self.SCANTIME]     = parameterDict(value='n/a', toolTip='Estimated scan time.', widgetType=Parameter.TYPE.LABEL, attr='scantime',internal=True,indicator=True)
        return ds

    def getOutputIndex(self):
        """Gets the index of the output channel corresponding to the currently selected display channel. See :attr:`~esibd.plugins.Scan.useDisplayChannel`.
        """
        if self.useDisplayChannel:
            try:
                if self.display.initializedDock:
                    return next((i for i, o in enumerate(self.outputs) if o.name == self.display.displayComboBox.currentText()), 0)
                else:
                    return next((i for i, o in enumerate(self.outputs) if o.name == self.displayDefault), 0)
            except ValueError:
                return 0
        return 0

    def initScan(self):
        """Initializes all data and metadata.
        Returns True if initialization successful and scan is ready to start.
        Will likely need to be adapted for custom scans."""
        lengths = [len(i.data) for i in self.inputs]
        for name in self.settingsMgr.settings[self.DISPLAY].items:
            c = self.getChannelByName(name, inout=INOUT.OUT)
            if c is None:
                self.print(f'Could not find channel {name}.', PRINT.WARNING)
            elif not c.device.initialized():
                self.print(f'{c.device.name} is not initialized.', PRINT.WARNING)
            elif not c.device.liveDisplay.recording:
                self.print(f'{c.device.name} is not recording.', PRINT.WARNING)
            elif not c.enabled and c.real:
                self.print(f'{c.name} is not enabled.', PRINT.WARNING)
            else:
                if len(self.inputs) == 1: # 1D scan
                    data = np.zeros(len(self.inputs[0].data)) # cant reuse same array for all outputs as they would refer to same instance.
                else: # 2D scan, higher dimensions not jet supported
                    data = np.zeros(np.prod(lengths)).reshape(*lengths).transpose()
                    # note np.zeros works better than np.full(len, np.nan) as some plots give unexpected results when given np.nan
                self.outputs.append(MetaChannel(name=c.name, data=data, unit=c.device.unit, channel=c))
        if len(self.outputs) > 0:
            self.measurementsPerStep = max(int((self.average/self.outputs[0].channel.device.interval))-1, 1)
            self.toggleDisplay(True)
            self.updateFile()
            self.populateDisplayChannel()
            return True
        else:
            self.print('No initialized output channel found.', PRINT.WARNING)
            return False

    def estimateScanTime(self):
        """Estimates scan time. Will likely need to be adapted for custom scans."""
        # owerwrite with scan specific estimation if applicable
        if hasattr(self,'_from'):
            # Simple time estimate for scan with single input channel.
            steps = self.getSteps(self._from, self.to, self.step)
            seconds = 0 # estimate scan time
            for i in range(len(steps)): # pylint: disable = consider-using-enumerate
                waitlong = False
                if not waitlong and abs(steps[i-1]-steps[i]) > self.largestep:
                    waitlong=True
                seconds += (self.waitlong if waitlong else self.wait) + self.average
            seconds = round((seconds)/1000)
            self.scantime = f'{seconds//60:02d}:{seconds%60:02d}'
        else:
            self.scantime = 'n/a'

    def saveData(self, file):
        """Writes generic scan data to hdf file."""
        with h5py.File(file,'a', track_order=True) as f:
            # avoid using getValues() function and use get() to make sure raw data, without background subtraction or unit correction etc. is saved in file
            g = self.requireGroup(f, self.name) #, track_order=True

            i = self.requireGroup(g, self.INPUTCHANNELS)
            for j, _input in enumerate(self.inputs):
                try:
                    d = i.create_dataset(name=_input.name, data=self.getData(j, INOUT.IN), track_order=True)
                    d.attrs[self.UNIT] = self.inputs[j].unit
                except ValueError as e:
                    self.print(f'Cannot create dataset for channel {_input.name}: {e}', PRINT.ERROR)

            o = self.requireGroup(g, self.OUTPUTCHANNELS)
            for j, output in enumerate(self.outputs):
                if output.name in o:
                    self.print(f'Ignoring duplicate channel {output.name}', PRINT.WARNING)
                    continue
                try:
                    d = o.create_dataset(name=output.name, data=self.getData(j, INOUT.OUT), track_order=True)
                    d.attrs[self.UNIT] = self.outputs[j].unit
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
                self.init()
                self.loadDataInternal()
                if self.useDisplayChannel:
                    self.populateDisplayChannel() # select default scan channel if available
                self.plot(update=False, done=True) # self.populateDisplayChannel() does not trigger plot while loading
                self.display.raiseDock(_show)
            else:
                self.print('Cannot open file while scanning.', PRINT.WARNING)

    def loadDataInternal(self):
        """Loads data from scan file. Data is stored in scan-neutral format of input and output channels.
        Extend to provide support for previous file formats."""
        with h5py.File(self.file, 'r') as f:
            g = f[self.name]
            i = g[self.INPUTCHANNELS]
            for name, data in i.items():
                self.inputs.append(MetaChannel(name=name, data=data[:], unit=data.attrs[self.UNIT],
                                               channel=self.getChannelByName(name, inout=INOUT.IN)))
            o = g[self.OUTPUTCHANNELS]
            for name, data in o.items():
                self.outputs.append(MetaChannel(name=name, data=data[:], unit=data.attrs[self.UNIT],
                                               channel=self.getChannelByName(name, inout=INOUT.OUT)))

    def generatePythonPlotCode(self):
        """Saves minimal code to create a plot which can be customized by the user."""
        with open(self.pluginManager.Explorer.activeFileFullPath.with_suffix('.py'), 'w', encoding=UTF8) as f:
            f.write(self.pythonLoadCode() + self.pythonPlotCode())

    def pythonLoadCode(self):
        return f"""import h5py
import numpy as np
import matplotlib.pyplot as plt
inputs, outputs = [], []
class MetaChannel():
    def __init__(self, name, data, initial=None, background=None, unit=''):
        self.name = name
        self.data = data
        self.initial = initial
        self.background = background
        self.unit = unit

with h5py.File('{self.pluginManager.Explorer.activeFileFullPath.as_posix()}','r') as f:
    g = f['{self.name}']

    i = g['Input Channels']
    for name, data in i.items():
        inputs.append(MetaChannel(name=name, data=data[:], unit=data.attrs['Unit']))
    o = g['Output Channels']
    for name, data in o.items():
        outputs.append(MetaChannel(name=name, data=data[:], unit=data.attrs['Unit']))

output_index = next((i for i, o in enumerate(outputs) if o.name == '{self.outputs[0].name}'), 0) # select channel to plot

"""

    def pythonPlotCode(self):
        """Defines minimal code to create a plot which can be customized by user.
        Accessible from context menu of scan files.
        Overwrite to add scan specific plot code here."""
        return """# Add your custom plot code here:"""

    def addInputChannel(self, channelName, _from, to, step):
        """Converting channel to generic input data. Returns True if channel is valid for scanning."""
        c = self.getChannelByName(channelName, inout=INOUT.IN)
        if c is None:
            self.print(f'No channel found with name {channelName}.', PRINT.WARNING)
            return False
        else:
            if _from == to:
                self.print('Limits are equal.', PRINT.WARNING)
                return False
            elif not c.device.initialized():
                self.print(f'{c.device.name} is not initialized.', PRINT.WARNING)
                return False
            data = self.getSteps(_from, to, step)
            if len(data) < 3:
                self.print('Not enough steps.', PRINT.WARNING)
                return False
            self.inputs.append(MetaChannel(name=channelName, data=data, initial=c.value, unit=c.device.unit, channel=c))
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
        if inout == INOUT.IN:
            return self.inputs[i].data.get()  if isinstance(self.inputs[i].data,  DynamicNp) else self.inputs[i].data
        else:
            return self.outputs[i].data.get() if isinstance(self.outputs[i].data, DynamicNp) else self.outputs[i].data

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
                    self.runThread = Thread(target=self.run, args =(lambda : self.recording,), name=f'{self.name} runThread')
                    self.runThread.daemon = True
                    self.runThread.start()
                    self.display.raiseDock()
                else:
                    self.recordingAction.state = False
            else:
                self.print('Wait for scan to finish.')
        else:
            self.print('Stopping scan.')

    def scanUpdate(self, done=False):
        self.plot(update=not done, done=done)
        if done: # save data
            self.pluginManager.Explorer.activeFileFullPath = self.file
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
        self.pluginManager.Explorer.populateTree()
        self.notes='' # reset after saved to last scan
        self.finished = True

    def plot(self, update=False, **kwargs): # pylint: disable = unused-argument # use **kwargs to allow child classed to extend the signature
        """Plot showing a current or final state of the scan. Extend to add scan specific plot code.

        :param update: If update is True, only data will be updates, otherwise entire figure will be initialized, defaults to False
        :type update: bool, optional
        """

    def updateToolBar(self, update):
        if len(self.outputs) > 0 and not update:
            self.display.navToolBar.update()
            self.display.canvas.get_default_filename = lambda : self.file.with_suffix('.pdf') # set up save file dialog

    def updateRecording(self, recording):
        # trigger from external thread to assure GUI update happens in main thread
        self.recording = recording

    def run(self, recording):
        """Steps through input values, records output values, and triggers plot update.
        Executed in runThread. Will likely need to be adapted for custom scans."""
        steps = list(itertools.product(*[i.data for i in self.inputs]))
        self.print(f'Starting scan M{self.pluginManager.Settings.measurementNumber:02}. Estimated time: {self.scantime}')
        for i, step in enumerate(steps): # scan over all steps
            waitlong = False
            for j, _input in enumerate(self.inputs):
                if not waitlong and abs(_input.channel.value-step[j]) > self.largestep:
                    waitlong=True
                _input.channel.signalComm.updateValueSignal.emit(step[j])
            time.sleep(((self.waitlong if waitlong else self.wait)+self.average)/1000) # if step is larger than threashold use longer wait time
            for j, o in enumerate(self.outputs):
                if len(self.inputs) == 1: # 1D scan
                    o.data[i] = np.mean(o.channel.getValues(subtractBackground=o.channel.device.subtractBackgroundActive(), length=self.measurementsPerStep))
                else: # 2D scan, higher dimensions not jet supported
                    o.data[i%len(self.inputs[1].data), i//len(self.inputs[1].data)] = np.mean(o.channel.getValues(subtractBackground=o.channel.device.subtractBackgroundActive(),
                                                                                                                  length=self.measurementsPerStep))

            if i == len(steps)-1 or not recording(): # last step
                for j, _input in enumerate(self.inputs):
                    _input.channel.signalComm.updateValueSignal.emit(_input.initial)
                time.sleep(.5) # allow time to reset to initial value before saving
                self.signalComm.scanUpdateSignal.emit(True) # update graph and save data
                self.signalComm.updateRecordingSignal.emit(False)
                break # in case this is last step
            else:
                self.signalComm.scanUpdateSignal.emit(False) # update graph

    def close(self):
        """:meta private:"""
        super().close()
        # if self.initializedDock:
        #     self.settingsMgr.saveSettings(default=True) # scan settings saved immedeately when changed
        if self.recording:
            self.recording = False
            if self.pluginManager.closing:
                time.sleep(.1) # allow for last call in aquisition loop.

    def closeGUI(self):
        """:meta private:"""
        self.toggleDisplay(False)
        super().closeGUI()

    def toggleDisplay(self, visible):
        if visible:
            if self.display is None or not self.display.initializedDock:
                self.display = self.Display(scan=self, pluginManager=self.pluginManager)
                self.display.provideDock()
        elif self.display is not None and self.display.initializedDock:
            self.display.closeGUI()

    def updateTheme(self):
        """:meta private:"""
        super().updateTheme()
        if self.display is not None and self.display.initializedDock:
            self.display.updateTheme()

#################################### General UI Classes #########################################

class Browser(Plugin):
    """The Browser is used to display various file formats. In addition, it
    provides access to the program description and documentation. Finally, it shows
    the about content of other plugins when clicking on their respective question mark icons."""

    name = 'Browser'
    version = '1.0'
    optional = False
    pluginType = PluginManager.TYPE.DISPLAY

    previewFileTypes = ['.pdf','.html','.htm','.svg','.wav','.mp3','.ogg'] # ,'.mp4','.avi' only work with codec

    previewFileTypes.extend(['.jpg','.jpeg','.png','.bmp','.gif'])
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

    def getIcon(self):
        """:meta private:"""
        return self.makeCoreIcon('blue-document-text-image.png')

    def initGUI(self):
        """:meta private:"""
        super().initGUI()
        self.webEngineView = QWebEngineView(parent=QApplication.instance().mainWindow)
        # self.webEngineView.page().settings().setUnknownUrlSchemePolicy(QWebEngineSettings.UnknownUrlSchemePolicy.AllowAllUnknownUrlSchemes)
        # self.webEngineView.page().settings().setAttribute(QWebEngineSettings.WebAttribute.AutoLoadImages, True)
        self.webEngineView.settings().setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, True) # required to open local pdfs
        self.webEngineView.loadFinished.connect(self.adjustLocation)

        self.titleBar.setIconSize(QSize(16, 16)) # match size of other titleBar elements
        page = self.webEngineView.pageAction(QWebEnginePage.WebAction.Back)
        page.setIcon(self.ICON_BACK)
        self.titleBar.addAction(page)
        page = self.webEngineView.pageAction(QWebEnginePage.WebAction.Forward)
        page.setIcon(self.ICON_FORWARD)
        self.titleBar.addAction(page)
        page = self.webEngineView.pageAction(QWebEnginePage.WebAction.Reload)
        page.setIcon(self.ICON_RELOAD)
        self.titleBar.addAction(page)
        page = self.webEngineView.pageAction(QWebEnginePage.WebAction.Stop)
        page.setIcon(self.ICON_STOP)
        self.titleBar.addAction(page)
        self.addAction(self.openAbout, 'Home', self.ICON_HOME)
        self.locationEdit = QLineEdit()
        self.locationEdit.setSizePolicy(QSizePolicy.Policy.Expanding, self.locationEdit.sizePolicy().verticalPolicy())
        self.locationEdit.returnPressed.connect(self.loadUrl)
        self.locationEdit.setMaximumHeight(QPushButton().sizeHint().height())
        self.titleBar.addWidget(self.locationEdit)
        self.docAction = self.addAction(self.openDocumentation,'Documentation', self.ICON_MANUAL)
        self.addContentWidget(self.webEngineView)

    def finalizeInit(self, aboutFunc=None):
        """:meta private:"""
        super().finalizeInit(aboutFunc)
        self.stretch.deleteLater()
        self.openAbout()

    def runTestParallel(self):
        """:meta private:"""
        if super().runTestParallel():
            self.testControl(self.docAction, True, 1)

    def loadData(self, file, _show=True):
        """:meta private:"""
        self.provideDock()
        self.file = file
        # overwrite parent
        if any(file.name.endswith(s) for s in ['.html','.htm']):
            self.webEngineView.load(QUrl.fromLocalFile(file.as_posix()))
            # self.webEngineView.setUrl(QUrl(f'file:///{file.as_posix()}'))
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
        self.title = 'Documentation'
        self.loadData(file=(Path(__file__).parent / 'docs/index.html').resolve())

    def openAbout(self):
        """Simple dialog displaying program purpose, version, and creators"""
        self.setHtml(title=f'About {PROGRAM_NAME}', html=f"""
        <h1><img src='{PROGRAM_ICON.resolve()}' width='22'> {PROGRAM_NAME} {PROGRAM_VERSION}</h1>{ABOUTHTML}""")

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
    previewFileTypes = ['.txt','.dat','.ter','.cur','.tt','.log','.py','.star','.pdb1','.css','.js','.html','.tex','.ini','.bat']
    SELECTFILE = 'Select File'

    class SignalCommunicate(QObject):
        setTextSignal = pyqtSignal(str, bool)

    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.signalComm = self.SignalCommunicate()
        self.signalComm.setTextSignal.connect(self.setText)

    def getIcon(self):
        """:meta private:"""
        return self.makeCoreIcon('blue-document-text.png')

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

    def finalizeInit(self, aboutFunc=None):
        """:meta private:"""
        super().finalizeInit(aboutFunc)
        self.addAction(self.saveFile,'Save', icon=self.makeCoreIcon('disk-black.png'), before=self.aboutAction)
        self.wordWrapAction = self.addStateAction(func=self.toggleWordWrap, toolTipFalse='Word wrap on.', iconFalse=self.makeCoreIcon('ui-scroll-pane-text.png'),
                                                  toolTipTrue='Word wrap off.', before=self.aboutAction, attr='wordWrap')
        self.textClipboardAction = self.addAction(lambda: QApplication.clipboard().setText(self.editor.toPlainText()),
                       'Copy text to clipboard.', icon=self.makeCoreIcon('clipboard-paste-document-text.png'), before=self.aboutAction)
        self.toggleWordWrap()

    def runTestParallel(self):
        """:meta private:"""
        if super().runTestParallel():
            self.testControl(self.wordWrapAction, True, 1)
            self.testControl(self.textClipboardAction, True, 1)

    def updateTheme(self):
        """:meta private:"""
        super().updateTheme()
        if not self.pluginManager.loading:
            self.numbers.updateTheme()

    def saveFile(self):
        file = None
        if self.pluginManager.Explorer.activeFileFullPath is not None:
            file = Path(QFileDialog.getSaveFileName(parent=None, caption=self.SELECTFILE, directory=self.pluginManager.Explorer.activeFileFullPath.as_posix())[0])
        else:
            file = Path(QFileDialog.getSaveFileName(parent=None, caption=self.SELECTFILE)[0])
        if file != Path('.'):
            with open(file,'w', encoding=self.UTF8) as f:
                f.write(self.editor.toPlainText())
            self.pluginManager.Explorer.populateTree()

    def loadData(self, file, _show=True):
        """:meta private:"""
        self.provideDock()
        self.editor.clear()
        if any(file.name.endswith(s) for s in self.previewFileTypes):
            try:
                with open(file, encoding=self.UTF8) as f:
                    for line in islice(f, 1000): # dont use f.read() as files could potenitially be very large
                        self.editor.insertPlainText(line) # always populate text box but only change to tab if no other display method is available
            except UnicodeDecodeError as e:
                self.print(f'Cant read file: {e}')
        self.editor.verticalScrollBar().triggerAction(QScrollBar.SliderAction.SliderToMinimum)   # scroll to top
        self.raiseDock(_show)

    def setText(self, text, _show=False):
        self.provideDock()
        self.editor.setPlainText(text)
        tc = self.editor.textCursor()
        tc.setPosition(0)
        self.editor.setTextCursor(tc)
        self.raiseDock(_show)

    def setTextParallel(self, text, _show=False):
        self.signalComm.setTextSignal.emit(text, _show)

    def inspect(self, obj, _filter=None):
        _list = inspect.getmembers(obj)
        if _filter is not None:
            _list = [repr(t) for t in inspect.getmembers(obj) if _filter in repr(t)]
        else:
            _list = [repr(t) for t in inspect.getmembers(obj)]
        self.setText('\n'.join(_list), True)

    def toggleWordWrap(self):
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth if self.wordWrap else QPlainTextEdit.LineWrapMode.NoWrap)

class Tree(Plugin):
    """The Tree plugin gives an overview of the content of .py, .hdf5, and
    .h5 files. This includes configuration or scan files and even python source code."""

    name = 'Tree'
    version = '1.0'
    optional = False
    pluginType = PluginManager.TYPE.DISPLAY
    h5previewFileTypes = ['.hdf5','.h5']
    pypreviewFileTypes = ['.py']
    previewFileTypes = h5previewFileTypes + pypreviewFileTypes

    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.ICON_ATTRIBUTE = str(self.dependencyPath / 'blue-document-attribute.png')
        self.ICON_DATASET = str(self.dependencyPath / 'database-medium.png')
        self.ICON_FUNCMET = str(self.dependencyPath / 'block-small.png')
        self.ICON_CLASS =   str(self.dependencyPath / 'application-block.png')
        self.ICON_GROUP =   str(self.dependencyPath / 'folder.png')

    def getIcon(self):
        """:meta private:"""
        return self.makeIcon('blue-document-tree.png')

    def initGUI(self):
        """:meta private:"""
        super().initGUI()
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.addContentWidget(self.tree)

    def provideDock(self):
        """:meta private:"""
        if super().provideDock():
            self.finalizeInit()

    def loadData(self, file, _show=True):
        """:meta private:"""
        self.provideDock()
        self.tree.clear()
        if any(file.name.endswith(s) for s in self.h5previewFileTypes):
            with h5py.File(file,'r', track_order=True) as f:
                self.hdfShow(f, self.tree.invisibleRootItem(), 0)
        else: # self.pypreviewFileTypes
            # """from https://stackoverflow.com/questions/44698193/how-to-get-a-list-of-classes-and-functions-from-a-python-file-without-importing/67840804#67840804"""
            with open(file, encoding=self.UTF8) as file:
                node = ast.parse(file.read())
            functions = [n for n in node.body if isinstance(n,(ast.FunctionDef, ast.AsyncFunctionDef))]
            classes = [n for n in node.body if isinstance(n, ast.ClassDef)]
            for function in functions:
                f = QTreeWidgetItem(self.tree,[function.name])
                f.setIcon(0, QIcon(self.ICON_FUNCMET))
                f.setToolTip(0, ast.get_docstring(function))
                f.setExpanded(True)
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
                g = QTreeWidgetItem(tree,[name])
                g.setIcon(0, QIcon(self.ICON_GROUP))
                if level < 1:
                    g.setExpanded(True)
                for at, v in item.attrs.items():
                    a = QTreeWidgetItem(g,[f'{at}: {v}'])
                    a.setIcon(0, QIcon(self.ICON_ATTRIBUTE))
                self.hdfShow(item, g, level+1)
            elif isinstance(item, h5py.Dataset):
                d = QTreeWidgetItem(tree,[name])
                d.setIcon(0, QIcon(self.ICON_DATASET))

    def pyShow(self, _class, tree, level):
        c = QTreeWidgetItem(tree,[_class.name])
        c.setIcon(0, QIcon(self.ICON_CLASS))
        c.setToolTip(0, ast.get_docstring(_class))
        if level < 1:
            c.setExpanded(True)
        for __class in [n for n in _class.body if isinstance(n, ast.ClassDef)]:
            self.pyShow(__class, c, level+1)
        for method in [n for n in _class.body if isinstance(n, ast.FunctionDef)]:
            m = QTreeWidgetItem(c,[method.name])
            m.setIcon(0, QIcon(self.ICON_FUNCMET))
            m.setToolTip(0, ast.get_docstring(method))

    def inspect(self, obj, _filter=None):
        self.provideDock()
        self.tree.clear()
        for o in [o for o in dir(obj) if not o.startswith('_') and (_filter is None or _filter.lower() in o.lower())]:
            attr = getattr(obj, o)
            if callable(attr):
                d = QTreeWidgetItem(self.tree,[o])
                d.setIcon(0, QIcon(self.ICON_FUNCMET))
                d.setToolTip(0, attr.__doc__)
            else:
                d = QTreeWidgetItem(self.tree,[f'{o}: {attr}'])
                d.setIcon(0, QIcon(self.ICON_ATTRIBUTE))
                d.setToolTip(0, repr(attr))
        self.raiseDock(True)

class Console(Plugin):
    """The console should typically not be needed, unless you are a developer
    or assist in debugging an issue. It is activated from the tool bar of
    the :ref:`sec:settings`. Status messages will be logged here. In addition you can
    also enable writing status messages to a log file, that can be shared
    with a developer for debugging. All features implemented in the user
    interface and more can be accessed directly from this console. Use at
    your own Risk! You can select some commonly used commands directly from
    the combo box to get started."""
    documentation = """The console should typically not be needed, unless you are a developer
    or assist in debugging an issue. It is activated from the tool bar of
    the settings. Status messages will be logged here. In addition you can
    also enable writing status messages to a log file, that can be shared
    with a developer for debugging. All features implemented in the user
    interface and more can be accessed directly from this console. Use at
    your own Risk! You can select some commonly used commands directly from
    the combo box to get started."""

    pluginType = PluginManager.TYPE.CONSOLE
    name = 'Console'
    version = '1.0'
    optional = False
    triggerComboBoxSignal = pyqtSignal(int)

    writeSignal = pyqtSignal(str)

    def getIcon(self):
        """:meta private:"""
        return self.makeCoreIcon('terminal.png')

    def initGUI(self):
        """:meta private:"""
        super().initGUI()
        self.mainDisplayWidget.setMinimumHeight(1) # enable hiding
        self.historyFile = Path(qSet.value(f'{GENERAL}/{CONFIGPATH}', self.pluginManager.Settings.defaultConfigPath)) / 'console_history.bin'
        self.historyFile.touch(exist_ok=True)
        # self.historyFile = open(hf,'w')
        self.mainConsole    = EsibdCore.ThemedConsole(historyFile=self.historyFile)
        self.mainConsole.repl._lastCommandRow = 0 # not checking for None if uninitialized! -> initialize
        self.mainConsole.repl.write(('All features implemented in the user interface and more can be accessed directly from this console.\n'
                                 'You can select some commonly used commands directly from the combobox below.\n'
                                 'Status messages will also be logged here. It is mainly intended for debugging. Use at your own Risk!\n'))
        self.vertLayout.addWidget(self.mainConsole, 1) # https://github.com/pyqtgraph/pyqtgraph/issues/404 # add before hintsTextEdit
        self.commonCommandsComboBox = EsibdCore.CompactComboBox()
        self.commonCommandsComboBox.wheelEvent = lambda event: None
        self.commonCommandsComboBox.addItems([
            "select command",
            "Browser.previewFileTypes # access plugin properties directly using plugin name",
            "ISEG.controller # get device specific hardware manager",
            "RBD.channels # get channels of a device",
            "Energy.display.fig # get specific figure",
            "Tree.inspect(Energy) # show methods and attributes of any object in Tree plugin",
            "Tree.inspect(Energy, _filter='plot') # show methods and attributes of any object in Tree plugin",
            "Text.inspect(Energy) # more detailed methods and attributes",
            "timeit.timeit('Beam.plot(update=True, done=False)', number=100, globals=globals()) # time execution of plotting",
            "chan = DeviceManager.getChannelByName('RT_Frontplate', inout=INOUT.IN) # get specific input channel",
            "chan.asDict() # Returns list of channel parameters and their value.",
            "chan = DeviceManager.getChannelByName('RT_Detector', inout=INOUT.OUT) # get specific output channel",
            "chan.getParameterByName(chan.ENABLED).getWidget().height() # get property of specific channel",
            "param = chan.getParameterByName(chan.ENABLED) # get specific channel parameter",
            "print(param.widgetType, param.value, param.getWidget()) # print parameter properties",
            "chan.getParameterByName(chan.VALUE).getWidget().setStyleSheet('background-color:red;') # test widget styling",
            "[p.getWidget().setStyleSheet('background-color:red;border: 0px;padding: 0px;margin: 0px;') for p in chan.parameters]",
            "PluginManager.showThreads() # show all active threads",
            "# PluginManager.test() # Automated testing of all active plugins. Can take a few minutes.",
            "# PluginManager.closePlugins(reload=True) # resets layout by reloading all plugins"
        ])
        self.commonCommandsComboBox.setMaximumWidth(150)
        self.commonCommandsComboBox.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed)
        self.commonCommandsComboBox.currentIndexChanged.connect(self.commandChanged)
        self.mainConsole.repl.inputLayout.insertWidget(1, self.commonCommandsComboBox)
        self.mainConsole.historyBtn.deleteLater()
        self.mainConsole.exceptionBtn.deleteLater()
        self.triggerComboBoxSignal.connect(self.triggerCombo)
        self.writeSignal.connect(self.write)

    def finalizeInit(self, aboutFunc=None):
        """:meta private:"""
        super().finalizeInit(aboutFunc)
        namespace= {'timeit':timeit, 'EsibdCore':EsibdCore, 'EsibdConst':EsibdConst, 'np':np, 'itertools':itertools, 'plt':plt, 'inspect':inspect, 'INOUT':INOUT, 'qSet':qSet,
                    'Parameter':Parameter, 'QtCore':QtCore, 'Path':Path, 'Qt':Qt, 'PluginManager':self.pluginManager,
                      'datetime':datetime, 'QApplication':QApplication, 'self':QApplication.instance().mainWindow}
        for p in self.pluginManager.plugins: # direct access to plugins
            namespace[p.name] = p
        self.mainConsole.localNamespace=namespace
        self.addStateAction(toolTipFalse='Write to log file.', iconFalse=self.makeCoreIcon('blue-document-list.png'), attr='logging',
                                              toolTipTrue='Disable logging to file.', iconTrue=self.makeCoreIcon('blue-document-medium.png'),
                                              before=self.aboutAction, func=self.toggleLogging)
        self.addAction(toolTip='Open log file.', icon=self.makeCoreIcon('blue-folder-open-document-text.png'), before=self.aboutAction, func=self.pluginManager.logger.openLog)
        # self.addAction(toolTip='dummy', icon=self.makeCoreIcon('block.png'),func=self.pluginManager.Temperature.test, before=self.aboutAction)

    def runTestParallel(self):
        """:meta private:"""
        if super().runTestParallel():
            for i in range(self.commonCommandsComboBox.count()): # test all predefined commands. Make sure critical commands are commented out to avoid reset and testing loop etc.
                if i != 0:
                    self.triggerComboBoxSignal.emit(i) # .testControl(self.commonCommandsComboBox, i, 1)
                    time.sleep(1)

    def triggerCombo(self, i):
        self.commonCommandsComboBox.setCurrentIndex(i)

    def commandChanged(self, _):
        if self.commonCommandsComboBox.currentIndex() != 0:
            self.mainConsole.input.setText(self.commonCommandsComboBox.currentText())
            self.mainConsole.input.execCmd()
            self.commonCommandsComboBox.setCurrentIndex(0)
            self.mainConsole.input.setFocus()

    def write(self, message):
        # writes to integrated console to keep track of message history
        # avoid using self.mainConsole.repl.write() because stdout is already handled by core.Logger
        if self.initializedDock:
            if current_thread() is main_thread():
                self.mainConsole.output.moveCursor(QTextCursor.MoveOperation.End)
                self.mainConsole.output.insertPlainText(message)
                self.mainConsole.scrollToBottom()
            else:
                self.writeSignal.emit(message)

    def toggleVisible(self):
        self.dock.setVisible(self.pluginManager.Settings.showConsole)

    def toggleLogging(self):
        qSet.setValue(LOGGING, self.logging)
        if self.logging:
            self.pluginManager.logger.open()
        else:
            self.pluginManager.logger.close()

    def updateTheme(self):
        """:meta private:"""
        super().updateTheme()
        self.mainConsole.updateTheme()

class SettingsManager(Plugin):
    """Bundles multiple :class:`settings<esibd.core.Setting>` into a single object to handle shared functionality."""

    # useful Console prompts for debugging:
    # tree = QTreeWidget()
    # Settings.vertLayout.addWidget(tree)
    # q = QTreeWidgetItem()
    # tree.invisibleRootItem().addChild(q)
    # tree.setItemWidget(q,1,QCheckBox())

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
            self.initSettingsContextMenuBase(self.settings[self.tree.itemAt(pos).fullName], self.tree.mapToGlobal(pos))
        except KeyError as e: # setting could not be identified
            self.print(e)

    ADDITEM     = 'Add Item'
    EDITITEM    = 'Edit Item'
    REMOVEITEM  = 'Remove Item'
    SELECTPATH  = 'Select Path'
    SELECTFILE  = 'Select File'
    SETTINGS    = 'Settings'

    def initSettingsContextMenuBase(self, setting, pos):
        """General implementation of a context menu.
        The relevent actions will be chosen based on the type and properties of the :class:`~esibd.core.Setting`."""
        settingsContextMenu = QMenu(self.tree)
        changePathAction = None
        addItemAction = None
        editItemAction = None
        removeItemAction = None
        copyClipboardAction = None
        setToDefaultAction = None
        makeDefaultAction = None
        if setting.widgetType == Parameter.TYPE.PATH:
            changePathAction = settingsContextMenu.addAction(self.SELECTPATH)
        elif (setting.widgetType in [Parameter.TYPE.COMBO, Parameter.TYPE.INTCOMBO, Parameter.TYPE.FLOATCOMBO]
                and not isinstance(setting.parent, Channel)):
            # Channels are part of Devices which define items centrally
            addItemAction = settingsContextMenu.addAction(self.ADDITEM)
            editItemAction = settingsContextMenu.addAction(self.EDITITEM)
            removeItemAction = settingsContextMenu.addAction(self.REMOVEITEM)
        if not isinstance(setting.parent, Channel):
            if setting.widgetType == Parameter.TYPE.LABEL:
                copyClipboardAction = settingsContextMenu.addAction('Copy to clipboard.')
            else:
                setToDefaultAction = settingsContextMenu.addAction(f'Set to Default: {setting.default}')
                makeDefaultAction = settingsContextMenu.addAction('Make Default')
        settingsContextMenuAction = settingsContextMenu.exec(pos)
        if settingsContextMenuAction is not None: # no option selected (NOTE: if it is None this could trigger a non initialized action which is also None if not tested here)
            if settingsContextMenuAction is copyClipboardAction:
                pyperclip.copy(setting.value)
            if settingsContextMenuAction is setToDefaultAction:
                setting.setToDefault()
            if settingsContextMenuAction is makeDefaultAction:
                setting.makeDefault()
            elif settingsContextMenuAction is changePathAction:
                startPath = setting.value
                newPath = Path(QFileDialog.getExistingDirectory(self.pluginManager.mainWindow, self.SELECTPATH, startPath.as_posix(),
                                                                QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontResolveSymlinks))
                if newPath != Path('.'): # directory has been selected successfully
                    setting.value = newPath
            elif settingsContextMenuAction is addItemAction:
                text, ok = QInputDialog.getText(self, self.ADDITEM, self.ADDITEM)
                if ok and text != '':
                    setting.addItem(text)
            elif settingsContextMenuAction is editItemAction:
                text, ok = QInputDialog.getText(self, self.EDITITEM, self.EDITITEM, text=str(setting.value))
                if ok and text != '':
                    setting.editCurrentItem(text)
            elif settingsContextMenuAction is removeItemAction:
                setting.removeCurrentItem()

    def init(self):
        # call this after creating the instance, as the instance is required during initialization
        # call after all defaultSettings have been added!
        self.loadSettings(default=True)
        # QTimer.singleShot(100, lambda : self.tree.setColumnWidth(0, 200))

    def loadSettings(self, file=None, default=False):
        """Loads settings from hdf or ini file."""
        self.loading = True
        if default:
            file = self.defaultFile
        if file is None: # get file via dialog
            file = Path(QFileDialog.getOpenFileName(parent=self.pluginManager.mainWindow, caption=self.SELECTFILE,
                                                    directory=self.pluginManager.Settings.configPath.as_posix(), filter=self.FILTER_INI_H5)[0])
        if file == Path('.'):
            return
        useFile = False
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
                if not default[Parameter.INTERNAL] and useFile and not name in confParser:
                    self.print(f'Using default value {default[Parameter.VALUE]} for setting {name}.')
                items.append(EsibdCore.parameterDict(name=name,
                    value=confParser[name][Parameter.VALUE] if useFile and name in confParser and Parameter.VALUE in confParser[name] else default[Parameter.VALUE],
                    default=confParser[name][Parameter.DEFAULT] if useFile and name in confParser and Parameter.DEFAULT in confParser[name] else default[Parameter.DEFAULT],
                    items=confParser[name][Parameter.ITEMS] if useFile and name in confParser and Parameter.ITEMS in confParser[name] else default[Parameter.ITEMS],
                    _min=default[Parameter.MIN], _max=default[Parameter.MAX],
                    internal=default[Parameter.INTERNAL] if Parameter.INTERNAL in default else False,
                    indicator=default[Parameter.INDICATOR] if Parameter.INDICATOR in default else False,
                    instantUpdate=default[Parameter.INSTANTUPDATE] if Parameter.INSTANTUPDATE in default else True,
                    toolTip=default[Parameter.TOOLTIP],
                    tree=self.tree if default[Parameter.WIDGET] is None else None,
                    widgetType=default[Parameter.WIDGETTYPE], widget=default[Parameter.WIDGET],
                    event=default[Parameter.EVENT]))
            self.updateSettings(items, file)
        else:
            with h5py.File(file,'r' if file.exists() else 'w') as f:
                if self.parentPlugin.name == self.SETTINGS:
                    g = f[self.parentPlugin.name]
                    useFile = True
                elif self.parentPlugin.name in f and self.SETTINGS in f[self.parentPlugin.name]:
                    g = f[self.parentPlugin.name][self.SETTINGS]
                    useFile = True
                for name, default in self.defaultSettings.items():
                    if useFile and not name in g:
                        self.print(f'Using default value {default[Parameter.VALUE]} for setting {name}.')
                    items.append(EsibdCore.parameterDict(name=name,
                            value=g[name].attrs[Parameter.VALUE] if useFile and name in g and Parameter.VALUE in g[name].attrs else default[Parameter.VALUE],
                            default=g[name].attrs[Parameter.DEFAULT] if useFile and name in g and Parameter.DEFAULT in g[name].attrs else default[Parameter.DEFAULT],
                            items=g[name].attrs[Parameter.ITEMS] if useFile and name in g and Parameter.ITEMS in g[name].attrs else default[Parameter.ITEMS],
                            _min=default[Parameter.MIN], _max=default[Parameter.MAX],
                            internal=default[Parameter.INTERNAL] if Parameter.INTERNAL in default else False,
                            indicator=default[Parameter.INDICATOR] if Parameter.INDICATOR in default else False,
                            instantUpdate=default[Parameter.INSTANTUPDATE] if Parameter.INSTANTUPDATE in default else True,
                            toolTip=default[Parameter.TOOLTIP],
                            tree=self.tree if default[Parameter.WIDGET] is None else None, # dont use tree if widget is provided independently
                            widgetType=default[Parameter.WIDGETTYPE], widget=default[Parameter.WIDGET],
                            event=default[Parameter.EVENT]))
            self.updateSettings(items, file)
        if not useFile: # create default if not exist
            self.print(f'Adding default settings in {file.name} for {self.parentPlugin.name}.')
            self.saveSettings(file=file)
        # self.expandTree(self.tree)
        self.tree.collapseAll() # only session should be expanded by default
        self.tree.expandItem(self.tree.topLevelItem(1))
        self.loading = False

    def updateSettings(self, items, file):
        """Scans for changes and shows change log before overwriting old channel configuraion."""
        # Note: h5diff can be used alternatively to find changes, but the output is not formated in a user friendly way (hard to correlate values with channels).
        if not self.pluginManager.loading:
            self.changeLog = [f'Change log for loading {self.name} from {file.name}:']
            for item in items:
                if item[Parameter.NAME] in self.settings:
                    if not item[Parameter.INTERNAL]:
                        s = self.settings[item[Parameter.NAME]]
                        if not s.equals(item[Parameter.VALUE]):
                            self.changeLog.append(f'Updating setting {s.fullName} from {s.value} to {item[Parameter.VALUE]}')
                else:
                    self.changeLog.append(f'Adding setting {item[Parameter.NAME]}')
            newNames = [item[Parameter.NAME] for item in items]
            for s in self.settings.values():
                if s.fullName not in newNames:
                    self.changeLog.append(f'Removing setting {s.fullName}')
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
                            items=item[Parameter.ITEMS], _min=item[Parameter.MIN], _max=item[Parameter.MAX], internal=item[Parameter.INTERNAL],
                            indicator=item[Parameter.INDICATOR], instantUpdate=item[Parameter.INSTANTUPDATE], toolTip=item[Parameter.TOOLTIP],
                            tree=item[Parameter.TREE], widgetType=item[Parameter.WIDGETTYPE], widget=item[Parameter.WIDGET], event=item[Parameter.EVENT],
                            parentItem=self.hdfRequireParentItem(item[Parameter.NAME], self.tree.invisibleRootItem()))

    def hdfRequireParentItem(self, name, parentItem):
        names = name.split('/')
        if len(names) > 1: # only ensure parents are there. last widget will be created as an Setting
            for n in name.split('/')[:-1]:
                children = [parentItem.child(i) for i in range(parentItem.childCount())] # list of existing children
                children_text = [c.text(0) for c in children]
                if n in children_text: # reuse existing
                    parentItem = parentItem.child(children_text.index(n))
                else:
                    parentItem = QTreeWidgetItem(parentItem,[n])
        return parentItem

    def saveSettings(self, file=None, default=False): # public method
        """Saves settings to hdf or ini file."""
        if default:
            file = self.defaultFile
        if file is None: # get file via dialog
            file = Path(QFileDialog.getSaveFileName(parent=self.pluginManager.mainWindow, caption=self.SELECTFILE,
                                                    directory=self.pluginManager.Settings.configPath.as_posix(), filter=self.FILTER_INI_H5)[0])
        if file == Path('.'):
            return
        if file.suffix == FILE_INI:
            # load and update content. Keep settings of currently used plugins untouched as they may be needed in when these plugins are enabled in the future
            config = configparser.ConfigParser()
            if file.exists():
                config.read(file)
            config[INFO] = infoDict(self.name)
            for name, default in self.defaultSettings.items():
                if not name in [Parameter.DEFAULT.upper(), VERSION] and not self.settings[name].internal:
                    if not name in config:
                        config[name] = {}
                    config[name][Parameter.VALUE]     = str(self.settings[name].value)
                    config[name][Parameter.DEFAULT]   = str(self.settings[name].default)
                    if default[Parameter.WIDGETTYPE] in [Parameter.TYPE.COMBO, Parameter.TYPE.INTCOMBO, Parameter.TYPE.FLOATCOMBO]:
                        config[name][Parameter.ITEMS] = ','.join(self.settings[name].items)
            with open(file,'w', encoding=self.UTF8) as configfile:
                config.write(configfile)
        else:
            with h5py.File(file,'w' if default else 'a', track_order=True) as f: # will update if exist, otherwise create
                h5py.get_config().track_order = True
                self.hdfUpdateVersion(f)
                if self.parentPlugin.name == self.SETTINGS:
                    g = self.requireGroup(f, self.parentPlugin.name)
                else:
                    p = self.requireGroup(f, self.parentPlugin.name)
                    g = self.requireGroup(p, self.SETTINGS)
                for name, default in self.defaultSettings.items():
                    if not name in [Parameter.DEFAULT.upper(), VERSION] and not self.settings[name].internal:
                        self.hdfSaveSettig(g, name, default)

    def hdfSaveSettig(self, g, name, default):
        for n in name.split('/'):
            g = self.requireGroup(g, n)
        g.attrs[Parameter.VALUE]        = self.settings[name].value
        g.attrs[Parameter.DEFAULT]      = self.settings[name].default
        if default[Parameter.WIDGETTYPE] in [Parameter.TYPE.COMBO, Parameter.TYPE.INTCOMBO, Parameter.TYPE.FLOATCOMBO]:
            g.attrs[Parameter.ITEMS]    = ','.join(self.settings[name].items)

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
    # NOTE: default paths should not be in softwarefolder as this might not have write access after installation
    defaultConfigPath = Path.home() / PROGRAM_NAME / 'conf/' # use user home dir by default
    defaultPluginPath = Path.home() / PROGRAM_NAME / 'plugins/'

    def __init__(self, pluginManager, **kwargs):
        self.tree = QTreeWidget() # Note. If settings will become closable in the future, tree will need to be recreated when it reopens
        self.tree.setHeaderLabels(['Parameter','Value'])
        self.tree.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        # size to content prevents manual resize
        self.tree.header().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.confINI = f'{self.name}.ini'
        self.loadGeneralSettings = f'Load {PROGRAM_NAME} settings.'
        super().__init__(parentPlugin=self, tree=self.tree,
                         defaultFile=Path(qSet.value(f'{GENERAL}/{CONFIGPATH}', self.defaultConfigPath)) / self.confINI, pluginManager=pluginManager, **kwargs)
        self.previewFileTypes = [self.confINI]

    def getIcon(self):
        """:meta private:"""
        return self.makeCoreIcon('gear.png')

    def initGUI(self):
        """:meta private:"""
        super().initGUI()
        self.addContentWidget(self.tree)
        self.addAction(lambda : self.loadSettings(None),'Load Settings.', icon=self.makeCoreIcon('blue-folder-import.png'))
        self.addAction(lambda : self.saveSettings(None),'Export Settings.', icon=self.makeCoreIcon('blue-folder-export.png'))
        self.addAction(self.pluginManager.managePlugins,'Manage Plugins.', icon=self.makeCoreIcon('block--pencil.png'))
        if hasattr(self.pluginManager, 'Console'):
            self.addStateAction(func=self.pluginManager.Console.toggleVisible, toolTipFalse='Show Console.', iconFalse=self.makeCoreIcon('terminal.png'),
                                                 toolTipTrue='Hide Console.', iconTrue=self.makeCoreIcon('terminal--minus.png'), attr='showConsole')

    def init(self):
        """Call externaly to init all internal settings and those of all other plugins."""
        self.addDefaultSettings(plugin=self) # make settings available via self.attr
        super().init() # call first time to only load internal settings to enable validation of datapath
        self.settings[f'{GENERAL}/{DATAPATH}']._changedEvent() # validate path before first use

        for p in self.pluginManager.plugins:
            if hasattr(p,'getDefaultSettings') and not isinstance(p, Scan):
                # only if plugin has specified settings that are not handled by separate settingsMgr within the plugin
                self.addDefaultSettings(plugin=p)
        super().init() # call again to load all settings from all other plugins
        self.settings[f'{self.SESSION}/{self.MEASUREMENTNUMBER}']._valueChanged = False # make sure sessionpath is not updated after restoring session number

    def finalizeInit(self, aboutFunc=None):
        """:meta private:"""
        super().finalizeInit(aboutFunc)
        self.requiredPlugin('DeviceManager')
        self.requiredPlugin('Explorer')

    def loadData(self, file, _show=False):
        """:meta private:"""
        return # nothing to do, content will be handled by Text plugin

    SESSION             = 'Session'
    MEASUREMENTNUMBER   = 'Measurement number'
    SESSIONPATH         = 'Session path'

    def getDefaultSettings(self):
        """Defines general default settings"""
        ds = {}
        ds[f'{GENERAL}/{DATAPATH}']=parameterDict(value=Path.home() / PROGRAM_NAME / 'data/',
                                        widgetType=Parameter.TYPE.PATH, internal=True, event=self.updateDataPath, attr='dataPath')
        ds[f'{GENERAL}/{CONFIGPATH}']=parameterDict(value=self.defaultConfigPath,
                                        widgetType=Parameter.TYPE.PATH, internal=True, event=self.updateConfigPath, attr='configPath')
        ds[f'{GENERAL}/{PLUGINPATH}']=parameterDict(value=self.defaultPluginPath,
                                        widgetType=Parameter.TYPE.PATH, internal=True, event=self.updatePluginPath, attr='pluginPath')
        # validate config path before loading settings from file
        path = Path(qSet.value(f'{GENERAL}/{CONFIGPATH}', self.defaultConfigPath)) # validate path and use default if not exists
        if not path.exists():
            Path(self.defaultConfigPath).mkdir(parents=True, exist_ok=True)
            qSet.setValue(f'{GENERAL}/{CONFIGPATH}', self.defaultConfigPath)
            self.defaultFile = Path(qSet.value(f'{GENERAL}/{CONFIGPATH}', self.defaultConfigPath)) / self.confINI
            self.print(f'Could not find path {path.as_posix()}. Defaulting to {self.defaultFile.parent.as_posix()}.', PRINT.WARNING)
        # access using getDPI()
        ds[f'{GENERAL}/{DPI}']                    = parameterDict(value='100', toolTip='DPI used for graphs.', internal=True, event=self.updateDPI,
                                                                items='100, 150, 200, 300', widgetType=Parameter.TYPE.INTCOMBO)
        # access using getTestMode()
        ds[f'{GENERAL}/{TESTMODE}']               = parameterDict(value=True, toolTip='Devices will fake communication in Testmode!', widgetType=Parameter.TYPE.BOOL,
                                    event=lambda : self.pluginManager.DeviceManager.initDevices() # pylint: disable=unnecessary-lambda # needed to delay execution until initialized
                                    , internal=True)
        ds[f'{GENERAL}/{DEBUG}']                  = parameterDict(value=False, toolTip='Show debug messages.', internal=True, widgetType=Parameter.TYPE.BOOL)
        ds[f'{GENERAL}/{DARKMODE}']               = parameterDict(value=True, toolTip='Use dark mode.', internal=True, event=self.pluginManager.updateTheme,
                                                                widgetType=Parameter.TYPE.BOOL)
        ds[f'{GENERAL}/{CLIPBOARDTHEME}']          = parameterDict(value=True, toolTip='Use current theme when copying graphs to clipboard. Disable to always use light theme.',
                                                                internal=True, widgetType=Parameter.TYPE.BOOL)
        ds[f'{self.SESSION}/{self.MEASUREMENTNUMBER}'] = parameterDict(value=0, toolTip='Self incrementing measurement number. Set to 0 to start a new session.',
                                                                widgetType=Parameter.TYPE.INT,
                                                                instantUpdate=False, # only trigger event when changed by user!
                                                                event=lambda : self.updateSessionPath(self.measurementNumber), attr='measurementNumber')
        ds[f'{self.SESSION}/{self.SESSIONPATH}']   = parameterDict(value='', toolTip='Path for storing session data. Relative to data path.',
                                                                widgetType=Parameter.TYPE.LABEL, attr='sessionPath')
        return ds

    def loadSettings(self, file=None, default=False):
        if self.pluginManager.DeviceManager.recording:
            if EsibdCore.CloseDialog(title='Stop acquisition?', ok='Stop acquisition', prompt='Acquisition is still running. Stop acquisition before loading settings!').exec():
                self.pluginManager.DeviceManager.stop()
                # settings necessary for acquistions will temporarily be unavailable during loading
            else:
                return
        super().loadSettings(file=file, default=default)

    def updateDataPath(self):
        if not self.pluginManager.loading:
            self.updateSessionPath()
            self.pluginManager.Explorer.updateRoot(self.dataPath)

    def updateConfigPath(self): # load settings from new conf path
        self.defaultFile = self.configPath / self.confINI
        if not self.pluginManager.loading:
            splash = EsibdCore.SplashScreen()
            splash.show()
            self.loadSettings(self.defaultFile)
            QApplication.processEvents()
            self.pluginManager.DeviceManager.restoreConfiguration()
            splash.close()

    def updatePluginPath(self):
        if EsibdCore.CloseDialog(title='Restart now', ok='Restart now.', prompt='Plugins will be updated on next restart.').exec():
            self.pluginManager.closePlugins(reload=True)

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
        for w in self.pluginManager.plugins:
            if hasattr(w,'fig') and w.fig is not None:
                w.fig.set_dpi(self.dpi)

    def getMeasurementFileName(self, extension):
        fullSessionPath = Path(*[self.dataPath, self.sessionPath])
        fullSessionPath.mkdir(parents=True, exist_ok=True) # create if not already existing
        return fullSessionPath / f'{fullSessionPath.name}_{self.measurementNumber:03d}{extension}'

    def componentInputValidation(self, c):
        illegal_characters = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
        return ''.join(char if char not in illegal_characters else '_' for char in c)

    def pathInputValidation(self, path):
        return Path(*[self.componentInputValidation(c) for c in path.parts])

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

    class SignalCommunicate(QObject):
        """Object that bundles pyqtSignals."""
        storeSignal = pyqtSignal()
        """Signal that triggers storage of device data."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.dataThread = None
        self._recording = False
        self.ICON_PLAY  = self.makeCoreIcon('play.png')
        self.ICON_PAUSE = self.makeCoreIcon('pause.png')
        self.ICON_STOP  = self.makeCoreIcon('stop.png')
        self.signalComm = self.SignalCommunicate()
        self.signalComm.storeSignal.connect(self.store)

    def getIcon(self):
        """:meta private:"""
        return self.makeCoreIcon('current.png')

    def initGUI(self):
        """:meta private:"""
        super().initGUI()
        self.stopAction = self.addAction(func=lambda : self.stop(manual=True), toolTip='Close all communication.', icon=self.ICON_STOP)
        self.addAction(func=self.initDevices, toolTip='Initialize all communication.', icon=self.makeCoreIcon('rocket-fly.png'))
        # lambda needed to avoid "checked" parameter passed by QAction
        self.exportAction = self.addAction(func=lambda : self.exportOutputData(), toolTip='Save all visible history to current session.', icon=self.makeCoreIcon('database-export.png')) # pylint: disable=unnecessary-lambda
        self.recordingAction = self.addStateAction(func=self.toggleRecording, toolTipFalse='Start all data acquisition.',
                                                iconFalse=self.ICON_PLAY, toolTipTrue='Stop all data acquisition.', iconTrue=self.ICON_PAUSE)

    def initDock(self):
        """:meta private:"""
        super().initDock()
        self.dock.setMaximumHeight(22) # GUI will only consist of titleBar

    def finalizeInit(self, aboutFunc=None):
        """:meta private:"""
        self.requiredPlugin('Settings')
        self.globalUpdate(True)
        if hasattr(self.pluginManager, 'Settings') and self.pluginManager.Settings.sessionPath == '': # keep existing session path when restarting
            self.pluginManager.Settings.updateSessionPath()
        super().finalizeInit(aboutFunc)
        self.displayTimeComboBox = EsibdCore.RestoreFloatComboBox(parentPlugin=self, default='2', items='-1, 0.2, 1, 2, 3, 5, 10, 60, 600, 1440', attr='displayTime',
                                                        event=self.updateDisplayTime, _min=.2, _max=3600,
                                                        toolTip='Length of displayed history in min. When -1, all history is shown.')
        self.titleBar.insertWidget(self.aboutAction, self.displayTimeComboBox)
        if hasattr(self, 'titleBarLabel'):
            self.titleBarLabel.deleteLater()
            self.titleBarLabel = None
        self.dock.toggleTitleBar() # Label not needed for DeviceManager
        self.timer = QTimer()
        self.timer.timeout.connect(self.store)
        self.timer.setInterval(3600000) # every 1 hour
        self.timer.start()

    def runTestParallel(self):
        """:meta private:"""
        if super().runTestParallel():
            self.testControl(self.recordingAction, True, 1)
            self.testControl(self.exportAction, True, 2)
            for d in self.getDevices():
                if hasattr(d,'onAction'):
                    self.testControl(d.onAction, True, 1)
            for s in self.pluginManager.getPluginsByType(PluginManager.TYPE.SCAN):
                self.print(f'Starting scan {s.name}.')
                self.testControl(s.recordingAction, True, 0)
            time.sleep(10) # allow for scans to finish before testing next plugin
            self.print('Stopping acquisition, collection, and scans.')
            self.testControl(self.stopAction, True, 1)
            self.print('Stopping acquisition, collection, and scans sent.')
            time.sleep(5) # allow for scans to stop and save data before triggering more events

    @property
    def recording(self):
        recoding = [ld.recording for ld in self.pluginManager.DeviceManager.getActiveLiveDisplays()]
        recoding.append(self._recording)
        return any(recoding)
    @recording.setter
    def recording(self, recording):
        self._recording = recording
        # allow output widgets to react to change if acquisition state
        self.recordingAction.state = recording

    def loadData(self, file, _show=True):
        """:meta private:"""
        for d in self.getDevices():
            d.loadData(file, _show)

    ########################## Inout Output Access #################################################

    def channels(self, inout=INOUT.BOTH): # flat list of all channels
        # 15% slower than using cached channels but avoids need to maintain cashed lists when removing and adding channels
        return [y for x in [device.channels for device in self.getDevices(inout)] for y in x]

    def getChannelByName(self, name, inout=INOUT.BOTH):
        """Get channel based on unique name and type.

        :param name: Unique channel name.
        :type name: str
        :param inout: Type of channel, defaults to :attr:`~esibd.const.INOUT.BOTH`
        :type inout: :attr:`~esibd.const.INOUT`, optional
        :return: The requested channel.
        :rtype: :class:`~esibd.core.Channel`
        """
        return next((c for c in self.channels(inout) if c.name.strip().lower() == name.strip().lower()), None)

    def getInitializedOutputChannels(self):
        return [y for x in [device.getInitializedChannels() for device in self.getOutputs()] for y in x]

    def getDevices(self, inout=INOUT.BOTH):
        if inout == INOUT.BOTH:
            return self.getInputs() + self.getOutputs()
        elif inout == INOUT.IN:
            return self.getInputs()
        else: # inout == INOUT.OUT:
            return self.getOutputs()

    def getInputs(self):
        return self.pluginManager.getPluginsByType(EsibdCore.PluginManager.TYPE.INPUTDEVICE)

    def getOutputs(self):
        return self.pluginManager.getPluginsByType(EsibdCore.PluginManager.TYPE.OUTPUTDEVICE)

    def getActiveLiveDisplays(self):
        return [d.liveDisplay for d in self.getDevices() if d.liveDisplayActive()]

    def getActiveStaticDisplays(self):
        return [d.staticDisplay for d in self.getDevices() if d.staticDisplayActive()]

    DISPLAYTIME = 'Display Time'

    def getDefaultSettings(self):
        """:meta private:"""
        ds = super().getDefaultSettings()
        ds['Acquisition/Max display points'] = parameterDict(value=2000, toolTip='Maximum number of data points per channel used for plotting. Decrease if plotting is limiting performance.',
                                                                event=lambda : self.livePlot(apply=True), widgetType=Parameter.TYPE.INT, _min=100, _max=100000, attr='max_display_size')
        ds['Acquisition/Limit display points'] = parameterDict(value=True, toolTip="Number of displayed datapoints will be limited to 'Max display points'", widgetType=Parameter.TYPE.BOOL,
                                                               event=lambda : self.livePlot(apply=True), attr='limit_display_size')
        ds['Acquisition/Restore data'] = parameterDict(value=True, toolTip='Enable to store and restore data for all devices.',
                                                        widgetType=Parameter.TYPE.BOOL, attr='restoreData')
        return ds

    def restoreConfiguration(self):
        for d in self.getDevices():
            d.loadConfiguration(default=True)
            QApplication.processEvents()
        for s in self.pluginManager.getPluginsByType(PluginManager.TYPE.SCAN):
            s.loadSettings(default=True)
            QApplication.processEvents()

    def resetPlot(self):
        for d in self.getDevices():
            d.resetPlot()

    def livePlot(self, apply=False):
        for liveDisplay in self.getActiveLiveDisplays():
            liveDisplay.plot(apply)

    def updateLivePlot(self):
        for liveDisplay in self.getActiveLiveDisplays():
            liveDisplay.updateLivePlot()

    def stopRecording(self):
        if EsibdCore.CloseDialog(title='Stop all recording?', ok='Stop all recording', prompt='Stop recording on all devices? Active scans will be stopped.').exec():
            self.recording = False
            for liveDisplay in self.getActiveLiveDisplays():
                liveDisplay.recording = False
            self.stopScans()
        elif self.recording:
            self.recordingAction.state = self.recording

    def stop(self, manual=False):
        """Close all communication

        :param manual: Indicates if triggered by user, defaults to False
        :type manual: bool, optional
        """
        if not manual or self.pluginManager.testing or EsibdCore.CloseDialog(title='Close all communication?', ok='Close all communication', prompt='Close communication with all devices?').exec():
            self.recording = False
            for d in self.getDevices():
                d.stop()
            self.stopScans()

    def stopScans(self):
        for s in self.pluginManager.getPluginsByType(PluginManager.TYPE.SCAN):
            s.recording = False # stop all running scans

    def exportOutputData(self, file=None):
        self.pluginManager.Settings.measurementNumber += 1
        if file is None:
            file = self.pluginManager.Settings.getMeasurementFileName(self.previewFileTypes[0])
        with h5py.File(name=file, mode=('a'), track_order=True) as f:
            self.hdfUpdateVersion(f)
            for liveDisplay in self.getActiveLiveDisplays():
                liveDisplay.device.appendOutputData(f)
        self.exportConfiguration(file=file) # save corresponding device settings in measurement file
        self.print(f'Saved {file.name}')
        self.pluginManager.Explorer.populateTree()

    def updateStaticPlot(self):
        for staticDisplay in self.getActiveStaticDisplays():
            staticDisplay.updateStaticPlot()

    def updateDisplayTime(self):
        if hasattr(self, 'displayTimeComboBox'): # ignore while initializing
            for liveDisplay in self.getActiveLiveDisplays():
                liveDisplay.displayTimeComboBox.setCurrentText(self.displayTimeComboBox.currentText())

    def exportConfiguration(self, file=None, default=False, inout=INOUT.BOTH):
        for d in self.getDevices(inout):
            d.exportConfiguration(file=file, default=default)

    def initDevices(self, inout=INOUT.BOTH):
        for d in self.getDevices(inout):
            d.init()

    def globalUpdate(self, apply=False, inout=INOUT.BOTH):
        # wait until all channels are complete before applying logic. will be called again when loading completed
        if any([device.loading for device in self.getDevices(inout)]) or self.pluginManager.loading:
            return
        if inout in [INOUT.BOTH, INOUT.IN]:
            for d in self.getInputs():
                d.updateValues(apply=apply)
        if inout in [INOUT.BOTH, INOUT.OUT]:
            for d in self.getOutputs():
                d.updateValues()

    def store(self):
        """Regularly stores device settings and data to minimize loss in the event of a program crash.
        Make sure that no GUI elements are accessed when running from parallel thread!"""
        # NOTE: deamon=True is not used to prevent the unlikely case where the thread is terminated halve way through because the program is closing.
        if self.restoreData:
            for d in self.getDevices():
                Thread(target=d.exportConfiguration, kwargs={'default':True}, name=f'{d.name} exportConfigurationThread').start()
                Thread(target=d.exportOutputData, kwargs={'default':True}, name=f'{d.name} exportOutputDataThread').start()
            # for s in self.pluginManager.getPluginsByType(PluginManager.TYPE.SCAN): # scan settings already saved when changed
            #     Thread(target=s.settingsMgr.saveSettings, kwargs={'default':True}).start()
             # Settings already saved when changed
            # Thread(target=self.pluginManager.Settings.saveSettings, kwargs={'default':True}).start()

    def toggleRecording(self):
        """Toggle recording of data."""
        if self.recording:
            self.stopRecording()
        else:
            # check for duplicate channel names before starting all devices. Note that the same name can occur once as and input and once as an output.
            for inout, put in zip([INOUT.IN, INOUT.OUT],['input','output']):
                seen = set()
                dupes = [x for x in [c.name for c in self.channels(inout=inout)] if x in seen or seen.add(x)]
                if len(dupes) > 0:
                    self.print(f"The following {put} channel names have been used more than once: {', '.join(dupes)}", PRINT.WARNING)
            for d in self.getDevices():
                if d.liveDisplayActive():
                    d.liveDisplay.recording = False
                    d.toggleRecording()
                else:
                    d.init()
            self.recording = True

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

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def getIcon(self):
        """:meta private:"""
        return self.makeCoreIcon('sticky-note--pencil.png')

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
        """Addes current notes to existing file """
        if default:
            self.file = file / 'notes.txt'
            if self.editor.toPlainText() != '':
                with open(self.file,'w', encoding = self.UTF8) as f:
                    f.write(self.editor.toPlainText())
        elif file.name.endswith(FILE_H5):
            with h5py.File(file, 'a', track_order=True) as f:
                h5py.get_config().track_order = True
                g = self.requireGroup(f, self.name)
                g.attrs[Parameter.VALUE] = self.editor.toPlainText()

    def loadData(self, file, _show=True):
        """:meta private:"""
        self.provideDock()
        self.editor.clear()
        self.file = file / 'notes.txt'
        if self.file.exists(): # load and display notes if found
            with open(self.file, encoding=self.UTF8) as f:
                self.editor.insertPlainText(f.read())
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
    order numbers. In combination with the :ref:`sec:notes` plugin, you can add comments to
    each component that will be displayed automatically as soon as you
    enter the corresponding folder."""

    name='Explorer'
    version = '1.0'
    pluginType = PluginManager.TYPE.CONTROL
    previewFileTypes = ['.lnk']
    SELECTPATH          = 'Select Path'
    optional = False

    displayContentSignal = pyqtSignal()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.ICON_FOLDER         = self.makeCoreIcon('folder.png')
        self.ICON_HOME           = self.makeCoreIcon('home.png')
        self.ICON_SESSION        = self.makeCoreIcon('book-open-bookmark.png')
        self.ICON_DOCUMENT       = self.makeCoreIcon('document.png')
        self.ICON_BACKWARD       = self.makeCoreIcon('arrow-180')
        self.ICON_FORWARD        = self.makeCoreIcon('arrow.png')
        self.ICON_UP             = self.makeCoreIcon('arrow-090.png')
        self.ICON_BACKWARD_GRAY  = self.makeCoreIcon('arrow_gray-180')
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

    def getIcon(self):
        """:meta private:"""
        return self.makeCoreIcon('folder.png')

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

        self.backAction = self.addAction(self.backward,'Backward', icon=self.ICON_BACKWARD)
        self.forwardAction = self.addAction(self.forward,'Forward', icon=self.ICON_FORWARD)
        self.upAction = self.addAction(self.up,'Up', icon=self.ICON_UP)
        self.refreshAction = self.addAction(lambda : self.populateTree(clear=False),'Refresh', icon=self.ICON_REFRESH)
        self.dataPathAction = self.addAction(self.goToDataPath,'Go to data path.', icon=self.ICON_HOME)

        self.currentDirLineEdit = QLineEdit()
        self.currentDirLineEdit.returnPressed.connect(self.updateCurDirFromLineEdit)
        self.currentDirLineEdit.setMinimumWidth(50)
        self.currentDirLineEdit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.titleBar.addWidget(self.currentDirLineEdit)

        self.browseAction = self.addAction(self.browseDir,'Select folder.', icon=self.ICON_BROWSE)
        self.sessionAction = self.addAction(self.goToCurrentSession,'Go to current session.', icon=self.ICON_SESSION)

        self.filterLineEdit = QLineEdit()
        self.filterLineEdit.setMaximumWidth(100)
        self.filterLineEdit.setMinimumWidth(50)
        self.filterLineEdit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.filterLineEdit.textChanged.connect(lambda : self.populateTree(clear=False))
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
        if super().runTestParallel():
            self.testControl(self.sessionAction, True, .4)
            self.testControl(self.upAction, True, .4)
            self.testControl(self.backAction, True, .4)
            self.testControl(self.forwardAction, True, .4)
            self.testControl(self.dataPathAction, True, .4)
            self.testControl(self.refreshAction, True, .4)
            testDir = self.pluginManager.Settings.dataPath / 'test_files'
            if testDir.exists():
                for file in testDir.iterdir():
                    if not file.is_dir():
                        self.print(f'Loading file {file}.')
                        self.activeFileFullPath = file
                        self.displayContentSignal.emit() # call displayContent in main thread
                        time.sleep(1)

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

    def initExplorerContextMenu(self, pos):
        """Context menu for items in Explorer"""
        item = self.tree.itemAt(pos)
        if item is None:
            return
        openDirAction = None
        opencontainingDirAction = None
        openFileAction = None
        deleteFileAction = None
        copyFileNameAction = None
        copyFolderNameAction = None
        copyPlotCodeAction = None
        loadValuesActions = []
        loadSettingsActions = []
        explorerContextMenu = QMenu(self.tree)
        if self.getItemFullPath(item).is_dir(): # actions for folders
            openDirAction = explorerContextMenu.addAction('Open folder in file explorer.')
            deleteFileAction = explorerContextMenu.addAction('Move folder to recyle bin.')
            copyFolderNameAction = explorerContextMenu.addAction('Copy folder name to clipboard.')
        else:
            opencontainingDirAction = explorerContextMenu.addAction('Open containing folder in file explorer.')
            openFileAction = explorerContextMenu.addAction('Open with default program.')
            copyFileNameAction = explorerContextMenu.addAction('Copy file name to clipboard.')
            deleteFileAction = explorerContextMenu.addAction('Move to recyle bin.')

            if self.activeFileFullPath.suffix == FILE_H5:
                try:
                    with h5py.File(name=self.activeFileFullPath, mode='r') as f:
                        for device in self.pluginManager.DeviceManager.getDevices():
                            if device.name in f and device.pluginType == PluginManager.TYPE.INPUTDEVICE:
                                loadValuesActions.append(explorerContextMenu.addAction(device.LOADVALUES))
                        for w in self.pluginManager.getMainPlugins():
                            if w.pluginType == PluginManager.TYPE.SCAN and w.name in f: # not used very frequenty for devices -> only show for scans
                                loadSettingsActions.append(explorerContextMenu.addAction(self.LOADSETTINGS(w)))
                except OSError:
                    self.print(f'Could not identify file type of {self.activeFileFullPath.name}', PRINT.ERROR)

                for device in self.pluginManager.DeviceManager.getDevices():
                    if device.liveDisplay.supportsFile(self.activeFileFullPath):
                        copyPlotCodeAction = explorerContextMenu.addAction(f'Generate {device.name} plot file.')
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
                else: # no exeption
                    if fileType == self.pluginManager.Settings.name:
                        loadSettingsActions.append(explorerContextMenu.addAction(self.pluginManager.Settings.loadGeneralSettings))
                    else:
                        for device in self.pluginManager.DeviceManager.getDevices(inout = INOUT.IN):
                            if device.name == fileType:
                                loadValuesActions.append(explorerContextMenu.addAction(device.LOADVALUES))

        explorerContextMenuAction = explorerContextMenu.exec(self.tree.mapToGlobal(pos))
        if explorerContextMenuAction is not None:
            if explorerContextMenuAction is opencontainingDirAction:
                subprocess.Popen(f'explorer {self.activeFileFullPath.parent}')
            elif explorerContextMenuAction is openDirAction:
                subprocess.Popen(f'explorer {self.getItemFullPath(item)}')
            elif explorerContextMenuAction is openFileAction:
                subprocess.Popen(f'explorer {self.activeFileFullPath}')
            elif explorerContextMenuAction is copyFileNameAction:
                pyperclip.copy(self.activeFileFullPath.name)
            elif explorerContextMenuAction is copyFolderNameAction:
                pyperclip.copy(self.getItemFullPath(item).name)
            elif explorerContextMenuAction is deleteFileAction:
                send2trash(self.tree.selectedItems()[0].path_info)
                self.populateTree(clear=False)
            elif explorerContextMenuAction is copyPlotCodeAction:
                for device in self.pluginManager.DeviceManager.getDevices():
                    if device.liveDisplay.supportsFile(self.activeFileFullPath):
                        device.staticDisplay.generatePythonPlotCode()
                        self.populateTree(clear=False)
                for scan in self.pluginManager.getPluginsByType(PluginManager.TYPE.SCAN):
                    if scan.supportsFile(self.activeFileFullPath):
                        scan.generatePythonPlotCode()
                        self.populateTree(clear=False)
                        break # only use first match
            elif explorerContextMenuAction in loadSettingsActions:
                for w in self.pluginManager.getMainPlugins():
                    if explorerContextMenuAction.text() == self.LOADSETTINGS(w):
                        w.loadSettings(file=self.activeFileFullPath)
            if explorerContextMenuAction in loadValuesActions:
                if explorerContextMenuAction.text() == self.pluginManager.Settings.loadGeneralSettings:
                    self.pluginManager.Settings.loadSettings(file=self.activeFileFullPath)
                else:
                    for device in self.pluginManager.DeviceManager.getDevices(inout=INOUT.IN):
                        if explorerContextMenuAction.text() == device.LOADVALUES:
                            device.loadValues(self.activeFileFullPath)

    def treeItemDoubleClicked(self, item, _):
        if self.getItemFullPath(item).is_dir():
            self.updateRoot(self.getItemFullPath(item), addHistory=True)
        else: # treeItemDoubleClicked
            subprocess.Popen(f'explorer {self.activeFileFullPath}')

    def getItemFullPath(self, item):
        out = item.text(0)
        if item.parent():
            out = self.getItemFullPath(item.parent()) / out
        else:
            out = self.root / out
        return out

    def up(self):
        newroot = Path(self.root).parent.resolve()
        self.updateRoot(newroot, addHistory=True)

    def forward(self):
        self.indexHistory = min(self.indexHistory + 1, len(self.history)-1)
        self.updateRoot(self.history[self.indexHistory])

    def backward(self):
        self.indexHistory = max(self.indexHistory - 1, 0)
        self.updateRoot(self.history[self.indexHistory])

    def updateRoot(self, newroot, addHistory = False, loading=False):
        self.rootChanging(self.root, newroot)
        self.root = Path(newroot)
        if addHistory:
            del self.history[self.indexHistory+1:] # remove voided forward options
            self.history.append(self.root)
            self.indexHistory = len(self.history)-1
        self.currentDirLineEdit.setText(self.root.as_posix())
        if not loading:
            self.populateTree(clear = True)

    def populateTree(self, clear=False):
        """Populates or updates filetree."""
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

        self.load_project_structure(startpath=self.root, tree=self.tree.invisibleRootItem(), _filter=self.filterLineEdit.text(), clear=clear) # populate tree widget

        it = QTreeWidgetItemIterator(self.tree, QTreeWidgetItemIterator.IteratorFlag.HasChildren)
        while it.value():
            if it.value().isExpanded():
                self.load_project_structure(startpath=it.value().path_info, tree=it.value(), _filter=self.filterLineEdit.text(), clear=clear) # populate expanded dirs, independent of recursion depth
            it +=1

    def browseDir(self):
        newPath = Path(QFileDialog.getExistingDirectory(parent=None, caption=self.SELECTPATH, directory=self.root.as_posix(),
                                                        options=QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontResolveSymlinks))
        if newPath != Path('.'):
            self.updateRoot(newPath, addHistory=True)

    def goToCurrentSession(self):
        fullSessionPath = Path(*[self.pluginManager.Settings.dataPath, self.pluginManager.Settings.sessionPath])
        fullSessionPath.mkdir(parents=True, exist_ok=True) # create if not already existing
        self.updateRoot(fullSessionPath, addHistory=True)

    def goToDataPath(self):
        self.updateRoot(self.pluginManager.Settings.dataPath, addHistory=True)

    def updateCurDirFromLineEdit(self):
        p = Path(self.currentDirLineEdit.text())
        if p.exists():
            self.updateRoot(p, addHistory=True)
        else:
            self.print(f'Could not find directory: {p}', PRINT.ERROR)

    def treeItemClicked(self, item):
        if item is not None and not self.getItemFullPath(item).is_dir():
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

        handled = False
        for p in [p for p in self.pluginManager.plugins if p.supportsFile(self.activeFileFullPath)]:
            p.loadData(file=self.activeFileFullPath, _show=not handled) # after widget is visible to make sure it is drawn properly
            handled = True # display first widget that supports file (others like tree or text come later and are optional)

        if not handled:
            m = f'No preview available for this type of {self.activeFileFullPath.suffix} file. Consider activating, implementing, or requesting a plugin.'
            self.print(m)
            self.pluginManager.Text.setText(m, True)

    def load_project_structure(self, startpath, tree, _filter, recursionDepth=2, clear=False):
        """from https://stackoverflow.com/questions/5144830/how-to-create-folder-view-in-pyqt-inside-main-window
        recursively maps the file structure into the internal explorer
        Note that recursion depth of 2 assures fast indexing. Deeper levels will be indexed as they are expanded.
        Data from multiple sessions can be accessed from the data path level by exoanding the tree.
        Recursion depth of more than 2 can lead to very long loading times"""
        QApplication.processEvents()
        if recursionDepth == 0: # limit depth to avoid indexing entire storage (can take minutes)
            return
        recursionDepth = recursionDepth - 1
        if startpath.is_dir():
            # List of directories only
            dirlist = []
            for x in startpath.iterdir():
                try:
                    if (startpath / x).is_dir() and not any(x.name.startswith(sym) for sym in ['.','$']):
                        [y for y in (startpath / x).iterdir()] # pylint: disable = expression-not-assigned # raises PermissionError if access is denied, need to use iterator to trigger access
                        dirlist.append(x)
                except PermissionError as e:
                    self.print(f'{e}')
                    continue # skip directories that we cannot access
            # List of files only
            filelist = [x for x in startpath.iterdir() if not (startpath / x).is_dir() and not x.name.startswith('.')]

            children = [tree.child(i) for i in range(tree.childCount())] # list of existing children
            children_text = [c.text(0) for c in children]
            for element in dirlist: # add all dirs first, then all files
                path_info = startpath / element
                if element.name in children_text: # reuse existing
                    parent_itm = tree.child(children_text.index(element.name))
                else: # add new
                    parent_itm = QTreeWidgetItem(tree,[element.name])
                    parent_itm.path_info = path_info
                    parent_itm.setIcon(0, self.ICON_FOLDER)
                self.load_project_structure(startpath=path_info, tree=parent_itm, _filter=_filter, recursionDepth=recursionDepth, clear=clear)
            for element in [element for element in filelist if ((_filter is None or _filter == "" or _filter.lower() in element.name.lower()) and not element.name in children_text)]:
                # don't add files that do not match _filter and only add elements that do not exist already
                if clear: # add all items alphabetically
                    parent_itm = QTreeWidgetItem(tree,[element.name])
                else: # insert new items at alphabetially correct position
                    parent_itm = QTreeWidgetItem(None,[element.name])
                    index = next((children_text.index(c) for c in children_text if c > element.name), len(children_text))
                    tree.insertChild(index, parent_itm)
                    children_text.insert(index,element.name)
                parent_itm.path_info = startpath / element
                parent_itm.setIcon(0, self.getFileIcon(element))
            for child in children:
                if not (startpath / child.text(0)).exists():
                    tree.removeChild(child) # remove if does not exist anymore
                if (startpath / child.text(0)).is_file() and _filter is not None and _filter != "" and not _filter.lower() in child.text(0).lower():
                    tree.removeChild(child) # remove files if tehy do not match filter
        else:
            self.print(f'{startpath} is not a valid directory', PRINT.ERROR)

    def getFileIcon(self, file):
        p = next((p for p in self.pluginManager.plugins if p.supportsFile(file)), None)
        if p is not None:
            return p.getIcon()
        else:
            return self.ICON_DOCUMENT

    def expandDir(self, _dir):
        self.load_project_structure(startpath=_dir.path_info, tree=_dir, _filter=self.filterLineEdit.text())
        _dir.setExpanded(True)

    def rootChanging(self, oldRoot, newRoot):
        if hasattr(self.pluginManager,'Notes'):
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
