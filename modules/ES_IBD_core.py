"""This module contains internally used constants, functions and classes
Generally all objects that are used accross multiple modules should be defined here to avoid circular imports and keep things consistent.
Whenever it is possible to make definitions only locally where they are needed, this is preferred. Keep this file as compact as possible.
This helps to keep things consistent and avoid errors to typos in strings etc.
In principle, different versions of this file could be used for localization
For now, English is the only supported language and use of hard coded error messages etc. in other files is tolerated if they are unique."""

import io
import time
from threading import Thread
from pathlib import Path
from datetime import datetime
from enum import Enum
import keyboard as kb
import matplotlib.pyplot as plt # pylint: disable = unused-import # need to import to access mpl.axes.Axes
import matplotlib as mpl
from matplotlib.widgets import Cursor
from matplotlib.backend_bases import MouseButton,MouseEvent
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas,NavigationToolbar2QT as NavigationToolbar
import pyqtgraph as pg
from PyQt6.QtWidgets import (QApplication,QVBoxLayout,QSizePolicy,QHBoxLayout,QWidget,QGridLayout,QTreeWidgetItem,
                            QPushButton,QSpacerItem,QComboBox,QDoubleSpinBox,QSpinBox,QLineEdit,QLabel,QCheckBox,QAbstractSpinBox)
from PyQt6.QtCore import Qt,QSettings,pyqtSignal,QObject
from PyQt6.QtGui import QIcon,QImage
import numpy as np
from pyqtgraph.dockarea import Dock,DockArea
from asteval import Interpreter
aeval = Interpreter()

# General field
COMPANY_NAME = 'ES-IBD LAB'
PROGRAM_NAME = 'ES-IBD Explorer'
PROGRAM = 'Program'
VERSION_MAYOR = 0
VERSION_MINOR = 5
VERSION = 'Version'
INFO = 'Info'
TIMESTAMP = 'Time'

def infoDict(name):
    return {PROGRAM : PROGRAM_NAME, VERSION : f'{VERSION_MAYOR}.{VERSION_MINOR}', 'NAME' : name, TIMESTAMP : datetime.now().strftime('%Y-%m-%d %H:%M')}

# file types
FILE_INI    = '.ini'
FILE_H5     = '.h5'
FILE_PDF    = '.pdf'

# file type filters

class ESIBD_GUI(QWidget):
    """Abstracts basic GUI code for devices scans and other high level UI elements.
    """

    LOAD    = 'Load'
    SAVE    = 'Save'
    IMPORT  = 'Import'
    EXPORT  = 'Export'
    UTF8    = 'utf-8'
    FILTER_INI_H5 = 'INI or H5 File (*.ini *.h5)'

    class GuiSignalCommunicate(QObject):
        labelPlotSignal = pyqtSignal(mpl.axes.Axes ,str)

    def __init__(self,name,esibdWindow = None):
        super().__init__()
        # self.esibdWindow = esibdWindow # access to main program via this reference, should not be available to all child classes
        # ideally no reference or only references to the minimal required parts should be passed, depending on the specific requirements of the child class
        self.name = name
        self.displayTab = None # may be added by child class
        self.suffixes = [] # may be added by child class
        self.qSet = QSettings(COMPANY_NAME,PROGRAM_NAME)
        self.dockArea = None
        self.loading = False
        self.guiSignalComm = self.GuiSignalCommunicate()
        self.guiSignalComm.labelPlotSignal.connect(self.delayedLabelPlot)
        self.labelAnnotation = None
        if esibdWindow is not None:
            # allow to execute esibdPrint without storing explicit reference to esibdWindow
            self.print = lambda string : esibdWindow.esibdPrint(string) # pylint: disable = unnecessary-lambda #, need lambda to avoid saving reference to esibdWindow
            self.printFromThread = lambda string : esibdWindow.signalComm.printFromThreadSignal.emit(string) # pylint: disable = unnecessary-lambda
        self.initUi()

    def initUi(self):
        """Initialize your custom user interface"""
        # hirarchy: self -> mainDisplayLayout -> mainDisplayWidget -> mainLayout
        # self is a widget that can be added to a Tabwidget
        # mainDisplayLayout and mainDisplayWidget only exist to enable conversion into a dockarea
        # mainLayout contains the actual content

        self.mainDisplayLayout = QVBoxLayout()
        self.setLayout(self.mainDisplayLayout)
        self.mainDisplayLayout.setContentsMargins(0,0,0,0)

        self.mainDisplayWidget = QWidget()
        self.mainDisplayLayout.addWidget(self.mainDisplayWidget)

        self.mainLayout = QVBoxLayout()
        self.mainLayout.setContentsMargins(0,0,0,0)

        self.mainDisplayWidget.setLayout(self.mainLayout)
        self.vertLayout = QVBoxLayout() # contains row(s) with buttons on top and content below
        self.vertLayout.setContentsMargins(0,0,0,0)
        self.vertLayout.setSpacing(0)

        self.mainLayout.addLayout(self.vertLayout)

        self.horLayouts = [] # array of rows with buttons on top
        self.makeDockArea(self.mainDisplayLayout,self.mainDisplayWidget,self.name)

    def makeDockArea(self,layout,widget,label):
        self.dockArea = DockArea()
        layout.addWidget(self.dockArea)
        dock = Dock(label,size=(100,100)) # TODO how to set icon? https://stackoverflow.com/questions/72416759/how-to-define-the-icon-of-a-dock-in-pyqtgraph
        self.dockArea.addDock(dock,'left')
        dock.addWidget(widget)

    def addButton(self,row,index,label='',func=None,toolTip='',checkable=False,layout=None,icon=None):
        lay = layout if layout is not None else self.provideRow(row)
        pb = QPushButton()
        pb.setText(label)
        pb.setToolTip(toolTip)
        if func is not None:
            pb.clicked.connect(func)
        if icon is not None:
            pb.setIcon(QIcon(icon))
        pb.setCheckable(checkable)
        lay.insertWidget(index,pb)
        return pb

    def provideRow(self,row):
        if len(self.horLayouts) -1 < row:
            self.horLayouts.append(QHBoxLayout())
            self.horLayouts[row].setContentsMargins(0,0,0,0)
            self.horLayouts[row].setSpacing(1)
            self.horLayouts[row].addSpacerItem(QSpacerItem(0, 20, QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Ignored))
            # self.horLayouts[row].addStretch()
            self.vertLayout.insertLayout(row,self.horLayouts[row])
        return self.horLayouts[row]

    def addContentWidget(self,cw):
        self.vertLayout.addWidget(cw)

    def addContentLayout(self,lay):
        self.vertLayout.addLayout(lay)

    def supportsFile(self, file):
        return any(file.name.endswith(s) for s in self.suffixes)

    ICON_COPY = 'media/clipboard-paste-image.png'

    def makeFigureCanvasWithToolbar(self,tab,figure):
        """Creates a canvas and toolbar for provided figure."""
        canvas = FigureCanvas(figure)
        toolbar = NavigationToolbar(canvas,self)
        tab.provideRow(0).insertWidget(0,toolbar,2)
        clipboardButton = QPushButton()
        clipboardButton.setToolTip('Copy to Clipboard')
        clipboardButton.setIcon(QIcon(self.ICON_COPY))
        clipboardButton.clicked.connect(lambda : self.copyClipboard()) # pylint: disable = unnecessary-lambda # use lambda to reevaluate at run time, in case copyClipboard has been overwritten
        tab.provideRow(0).insertWidget(1,clipboardButton)
        tab.addContentWidget(canvas)
        return canvas,toolbar

    def labelPlot(self,ax,label):
        Thread(target=self.labelPlotRun, args=(ax,label,)).start()

    def labelPlotRun(self,ax,label):
        if not self.loading: # ignore calls to labelPlot until former calls are processed
            time.sleep(.5) # give canvas time to draw rest before calculating width
            self.loading = True
            self.guiSignalComm.labelPlotSignal.emit(ax,label) # need to run in main thread to access gui elements

    def delayedLabelPlot(self,ax,label):
        """ labels plot to trace back which file it is based on"""
        fontsize = 10
        # call after all other plotting operations are completed for scaling to work properly
        if self.labelAnnotation is not None:
            self.labelAnnotation.remove()
        self.labelAnnotation = ax.annotate(text = label,xy=(.98,.98),fontsize=fontsize,xycoords='axes fraction',textcoords='axes fraction',
                                        ha='right',va='top',bbox=dict(boxstyle='square,pad=.2',fc='w',ec='none'),clip_on=True)
        labelWidth = self.labelAnnotation.get_window_extent(renderer=ax.get_figure().canvas.get_renderer()).width
        axisWidth = ax.get_window_extent().transformed(ax.get_figure().dpi_scale_trans.inverted()).width*ax.get_figure().dpi*.9
        self.labelAnnotation.remove()
        xpos = 1-0.1/ax.get_window_extent().transformed(ax.get_figure().dpi_scale_trans.inverted()).width
        self.labelAnnotation = ax.annotate(text = label,xy=(xpos,.98),fontsize=min(max(fontsize / labelWidth * axisWidth,1),10),xycoords='axes fraction',textcoords='axes fraction',
                                        ha='right',va='top',bbox=dict(boxstyle='square,pad=.2',fc='w',ec='none'),clip_on=True)
        if hasattr(ax,'cursor'): # cursor position changes after adding label... -> restore
            ax.cursor.updatePosition()
        ax.figure.canvas.draw_idle()
        self.loading = False

    def removeAnnotations(self, ax):
        for ann in [child for child in ax.get_children() if isinstance(child,mpl.text.Annotation)]:#[self.seAnnArrow,self.seAnnFile,self.seAnnFWHM]:
            ann.remove()

    def getDPI(self):
        self.qSet.sync()
        return int(self.qSet.value('DPI',100))# need explicit conversion as stored as string

    def getTestmode(self):
        self.qSet.sync()
        return self.qSet.value('Testmode','false') == 'true'

    def copyClipboard(self):
        buf = io.BytesIO()
        self.fig.savefig(buf,format='png',bbox_inches='tight',dpi=self.getDPI())
        QApplication.clipboard().setImage(QImage.fromData(buf.getvalue()))
        buf.close()

    def close(self): # overwrite or extend to save settings, close comminication etc.
        pass

class INOUT(Enum):
    IN = 0
    OUT = 1
    BOTH = 2

def require_group(g,name):
    """ replaces require_group from h5py,as this does not support track_order"""
    if name in g:
        return g[name]
    else:
        return g.create_group(name = name,track_order = True)

class dynamicNp():
    """ based on https://stackoverflow.com/questions/7133885/fastest-way-to-grow-a-numpy-numeric-array
    This is an incrementally expanded numpy array that prevents frequent memory allocation while growing.
    """
    def __init__(self,initialData = None,max_size = None):
        self.data = np.zeros((100,)) if initialData is None else initialData
        self.capacity = self.data.shape[0]
        self.size = 0 if initialData is None else initialData.shape[0]
        self.max_size = max_size
    def add(self,x):
        if self.size == self.capacity:
            self.capacity *= 4
            newdata = np.zeros((self.capacity,))
            newdata[:self.size] = self.data
            self.data = newdata
        if self.max_size is not None and self.size == self.max_size: # remove old data as new data is comming in. used to limit ram use
            self.data = np.roll(self.data,-1)
            self.data[self.size-1] = x
        else:
            self.data[self.size] = x
            self.size += 1
    def get(self):
        """returns plain numpy array"""
        return self.data[:self.size]
    # even though this is working on the internal data directly it performs worse than e.g. self.time.get()[self.time.get()>cutoff]
    # def getLarger(self,offset):
    #     """returns plain numpy array"""
    #     return self.data[(np.abs(self.data - offset)).argmin():self.size]

def parameterDict(value,_min = None,_max = None,toolTip = None,items = None,widgetType = None,advanced = False,header = None,
                    widget = None,event = None,internal = False,attr = None):
    """Provides default values for all properties of a parameter"""
    return {ESIBD_Parameter.VALUE : value,ESIBD_Parameter.MIN : _min,ESIBD_Parameter.MAX : _max,ESIBD_Parameter.ADVANCED : advanced,ESIBD_Parameter.HEADER : header,
            ESIBD_Parameter.DEFAULT : value,ESIBD_Parameter.TOOLTIP : toolTip,ESIBD_Parameter.ITEMS : items,ESIBD_Parameter.WIDGETTYPE : widgetType,
            ESIBD_Parameter.WIDGET : widget,ESIBD_Parameter.EVENT : event,ESIBD_Parameter.INTERNAL : internal,ESIBD_Parameter.ATTR : attr}

class ESIBD_Parameter():
    """General setting including name,value,default,items,and widgetType
    It maps these property to appropriate UI elements"""

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
    TOOLTIP     = 'Tooltip'
    EVENT       = 'Event'
    INTERNAL    = 'Internal'

    # widget keys
    WIDGET      = 'WIDGET'
    WIDGETTYPES = 'WIDGETTYPES'
    WIDGETTYPE  = 'WIDGETTYPE'
    WIDGETLABEL = 'LABEL'
    WIDGETPATH  = 'PATH'
    WIDGETCOMBO = 'COMBO'
    WIDGETINTCOMBO = 'INTCOMBO'
    WIDGETFLOATCOMBO = 'FLOATCOMBO'
    WIDGETTEXT  = 'TEXT'
    WIDGETCOLOR = 'COLOR'
    WIDGETBOOL  = 'BOOL'
    WIDGETINT   = 'INT'
    WIDGETFLOAT = 'FLOAT'

    def __init__(self,esibdWindow,parent,name,default = None,widgetType = None,index = 1,items = None,widget = None,internal = False,
                    tree = None,itemWidget = None,toolTip = None,event = None,_min = None,_max = None):
        self.widgetType = widgetType if widgetType is not None else self.WIDGETLABEL
        self.index = index
        self.print = lambda string : esibdWindow.esibdPrint(string) # pylint: disable = unnecessary-lambda #, need lambda to avoid saving reference to esibdWindow
        self.printFromThread = lambda string : esibdWindow.signalComm.printFromThreadSignal.emit(string)  # pylint: disable = unnecessary-lambda
        self.parent=parent
        self.name = name
        self.toolTip = toolTip
        self.qSet = QSettings(COMPANY_NAME,PROGRAM_NAME)
        self._items = items.split(',') if items is not None else None
        self.tree = tree # None unless the parameter is used for settings
        self.itemWidget = itemWidget # if this is not none,parameter is part of a device channel
        self.widget = widget # None unless widget provided -> can be used to place an interface to a settings anywhere
        self._changedEvent = None
        self.event = event # None unless widget provided -> can be used to place an interface to a settings anywhere
        self.extendedEvent = event # allows to add internal events on top of the explicitly assigned ones
        self.internal = internal # internal settings will not be exported to file but saved using QSetting
        self.check = None
        self.min = _min
        self.max = _max
        self.button = None
        self.spin = None
        self._default = None
        if default is not None:
            self.default = default
        if self.tree is None: # if this is part of a QTreeWidget,applyWidget() should be called after this parameter is added to the tree
            self.applyWidget() # call after everything else is initialized but before setting value

    @property
    def value(self):
        """returns value in correct format,based on widgetType"""
        # use widget even for internal settings, should always be synchronized to allow access via both attribute and qSet
        if self.widgetType == self.WIDGETCOMBO:
            return self.combo.currentText()
        if self.widgetType == self.WIDGETINTCOMBO:
            return int(self.combo.currentText())
        if self.widgetType == self.WIDGETFLOATCOMBO:
            return float(self.combo.currentText())
        elif self.widgetType == self.WIDGETTEXT:
            return self.line.text()
        elif self.widgetType == self.WIDGETINT or self.widgetType == self.WIDGETFLOAT:
            return self.spin.value()
        elif self.widgetType == self.WIDGETBOOL:
            if self.check is not None:
                return self.check.isChecked()
            else:
                return self.button.isChecked()
        elif self.widgetType == self.WIDGETCOLOR:
            return self.colBtn.color()
        elif self.widgetType == self.WIDGETLABEL:
            return self.label.text()
        elif self.widgetType == self.WIDGETPATH:
            return Path(self.label.text())

    @value.setter
    def value(self,value):
        if self.internal:
            self.qSet.sync()
            self.qSet.setValue(self.name,value)
            self.qSet.sync()
        if self.widgetType == self.WIDGETBOOL:
            value = value if isinstance(value,(bool,np.bool_)) else value in ['True','true'] # accepts strings (from ini file or qset) and bools
            if self.check is not None:
                self.check.setChecked(value)
            else:
                self.button.setChecked(value)
        elif self.widgetType == self.WIDGETINT:
            self.spin.setValue(int(value))
        elif self.widgetType == self.WIDGETFLOAT:
            self.spin.setValue(float(value))
        elif self.widgetType == self.WIDGETCOLOR:
            self.colBtn.setColor(value,True)
        elif any(self.widgetType == wType for wType in [self.WIDGETCOMBO,self.WIDGETINTCOMBO,self.WIDGETFLOATCOMBO]):
            i = self.combo.findText(str(value))
            if i == -1:
                self.print(f'Warning: Value {value} not found for {self.name}. Defaulting to {self.combo.itemText(0)}.')
                self.combo.setCurrentIndex(0)
            else:
                self.combo.setCurrentIndex(i)
        elif self.widgetType == self.WIDGETTEXT:
            self.line.setText(str(value)) # input may be of type Path from pathlib -> needs to be converted to str for display in lineedit
        elif self.widgetType == self.WIDGETLABEL or self.widgetType == self.WIDGETPATH:
            self.label.setText(str(value))
            self.label.setToolTip(str(value))
            if self._changedEvent is not None:
                self._changedEvent() # emit here as it is not emitted by the label

    @property
    def default(self):
        return self._default
    @default.setter
    def default(self,default): # casting does not change anything if the value is already supplied in the right type,but will convert strings to correct value if needed
        if self.widgetType == self.WIDGETBOOL:
            self._default = default
        elif self.widgetType == self.WIDGETINT:
            self._default = int(default)
        elif self.widgetType == self.WIDGETFLOAT:
            self._default = float(default)
        else:
            self._default = str(default)

    @property
    def items(self):
        if any(self.widgetType == wType for wType in [self.WIDGETCOMBO,self.WIDGETINTCOMBO,self.WIDGETFLOATCOMBO]):
            return [self.combo.itemText(i) for i in range(self.combo.count())]
        else:
            return ''

    @property
    def changedEvent(self):
        return self._changedEvent
    @changedEvent.setter
    def changedEvent(self,changedEvent):
        self._changedEvent=changedEvent
        if any(self.widgetType == wType for wType in [self.WIDGETCOMBO,self.WIDGETINTCOMBO,self.WIDGETFLOATCOMBO]):
            self.combo.currentIndexChanged.connect(self._changedEvent)
        elif self.widgetType == self.WIDGETTEXT:
            self.line.editingFinished.connect(self._changedEvent)
        elif self.widgetType == self.WIDGETINT or self.widgetType == self.WIDGETFLOAT:
            if self.itemWidget is None:
                self.spin.editingFinished.connect(self._changedEvent) # indipendent settings trigger events only when changed via user interface
            else:
                self.spin.valueChanged.connect(self._changedEvent) # settings in device channels trigger events on every change,not matter if through user interface or software
        elif self.widgetType == self.WIDGETBOOL:
            if isinstance(self.check,QCheckBox):
                self.check.stateChanged.connect(self._changedEvent)
            else: #isinstance(self.check,QToolButton)
                self.check.clicked.connect(self._changedEvent)
        elif self.widgetType == self.WIDGETCOLOR:
            self.colBtn.sigColorChanged.connect(self._changedEvent)
        elif self.widgetType == self.WIDGETLABEL or self.widgetType == self.WIDGETPATH:
            pass # self.label.changeEvent.connect(self._changedEvent) # no change events for labels

    def setToDefault(self):
        self.value = self.default

    def makeDefault(self):
        self.default = self.value

    def applyWidget(self):
        """create UI widget depending on widget type
        Linking dedicated widget if provided
        """
        if any(self.widgetType == wType for wType in [self.WIDGETCOMBO,self.WIDGETINTCOMBO,self.WIDGETFLOATCOMBO]):
            self.combo = self.widget if self.widget is not None else QComboBox()
            if self.widget is not None: # potentially reuse widget with old data!
                self.combo.clear()
            self.combo.wheelEvent = lambda event: None # disable wheel event to avoid accidental change of setting
            for i in [x.strip(' ') for x in self._items]:
                self.combo.insertItem(self.combo.count(),i)
            self.combo.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self.combo.customContextMenuRequested.connect(self.initComboContextMenu)
        elif self.widgetType == self.WIDGETTEXT:
            self.line = self.widget if self.widget is not None else QLineEdit()
        elif self.widgetType == self.WIDGETINT or self.widgetType == self.WIDGETFLOAT:
            self.spin = self.widget if self.widget is not None else QLabviewControlDoubleSpinBox() if self.widgetType == self.WIDGETFLOAT else QLabviewControlSpinBox()
        elif self.widgetType == self.WIDGETBOOL:
            self.check = self.widget if self.widget is not None else QCheckBox()
        elif self.widgetType == self.WIDGETCOLOR:
            self.colBtn = self.widget if self.widget is not None else pg.ColorButton()
        elif self.widgetType == self.WIDGETLABEL or self.widgetType == self.WIDGETPATH:
            self.label = self.widget if self.widget is not None else QLabel()

        if self.spin is not None: # apply limits # no limits by default to avoid unpredictable behaviour.
            if self.min is not None:
                self.spin.setMinimum(self.min)
            if self.max is not None:
                self.spin.setMaximum(self.max)

        if self.tree is not None:
            if self.itemWidget is None:
                self.tree.setItemWidget(self,1,self.getWidget())
            else:
                self.tree.setItemWidget(self.itemWidget,self.index,self.containerize(self.getWidget())) # container required to hide widgets reliable
        if self.extendedEvent is not None:
            self.changedEvent = self.extendedEvent
        elif self.event is not None:
            self.changedEvent = self.event

        self.getWidget().setToolTip(self.toolTip)

    def containerize(self,widget):
        # just hiding widget using setVisible(False) is not reliable due to bug https://bugreports.qt.io/browse/QTBUG-13522
        # use a wrapping container as a workaround https://stackoverflow.com/questions/71707347/how-to-keep-qwidgets-in-qtreewidget-hidden-during-resize?noredirect=1#comment126731693_71707347
        container = QWidget()
        containerLayout = QGridLayout(container)
        containerLayout.setContentsMargins(0,0,0,0)
        # containerLayout.setColumnMinimumWidth(0,0)
        widget.setSizePolicy(QSizePolicy(QSizePolicy.Policy.MinimumExpanding,QSizePolicy.Policy.MinimumExpanding))
        containerLayout.addWidget(widget)
        return container

    def getWidget(self):
        if any(self.widgetType == wType for wType in [self.WIDGETCOMBO,self.WIDGETINTCOMBO,self.WIDGETFLOATCOMBO]):
            return self.combo
        elif self.widgetType == self.WIDGETTEXT:
            return self.line
        elif self.widgetType == self.WIDGETINT or self.widgetType == self.WIDGETFLOAT:
            return self.spin
        elif self.widgetType == self.WIDGETBOOL:
            return self.check if self.check is not None else self.button
        elif self.widgetType == self.WIDGETCOLOR:
            return self.colBtn
        elif self.widgetType == self.WIDGETLABEL or self.widgetType == self.WIDGETPATH:
            return self.label

    def initComboContextMenu(self,pos):
        self.parent.initSettingsContextMenuBase(self,self.combo.mapToGlobal(pos))

    def addItem(self,value):
        # should only be called for WIDGETCOMBO settings
        if self.validateComboInput(value):
            if self.combo.findText(str(value)) == -1: # only add item if not already in list
                self.combo.insertItem(self.combo.count(),str(value))
                self.value = value

    def removeCurrentItem(self):
        if len(self.items) > 1:
            self.combo.removeItem(self.combo.currentIndex())
        else:
            self.print('Warning: List cannot be empty.')

    def editCurrentItem(self,value):
        if self.validateComboInput(value):
            self.combo.setItemText(self.combo.currentIndex(),str(value))

    def validateComboInput(self,value):
        """Validates input for comboboxes"""
        if self.widgetType == self.WIDGETCOMBO:
            return True
        elif self.widgetType == self.WIDGETINTCOMBO:
            try:
                int(value)
                return True
            except ValueError:
                self.print(f'Error: {value} is not an integer!')
        elif self.widgetType == self.WIDGETFLOATCOMBO:
            try:
                float(value)
                return True
            except ValueError:
                self.print(f'Error: {value} is not a float!')
        return False

#################################### Settings Item ################################################

class ESIBD_Setting(QTreeWidgetItem,ESIBD_Parameter):
    """ESIBD parameter to be used as general settings with dedicated UI controls instead of being embedded in a device channel.
    Always use keyword arguments to allow forwarding to parent classes.
    """
    def __init__(self,value=None,parentItem=None,**kwargs):
        # use keyword arguments rather than positional to avoid issues with multiple inheritace
        # https://stackoverflow.com/questions/9575409/calling-parent-class-init-with-multiple-inheritance-whats-the-right-way
        # super().__init__()
        super().__init__(**kwargs)
        self.fullName = self.name # will contain path of setting in HDF5 file if applicable
        self.name = Path(self.name).name # only use last element in case its a path
        if self.tree is not None: # some settings may be attached to dedicated controls
            self.parentItem = parentItem
            self.parentItem.addChild(self) # has to be added to parent before widgets can be added!
            self.setData(0,Qt.ItemDataRole.DisplayRole,self.name)
            self.setToolTip(0,self.toolTip)
            self.extendedEvent = self.settingEvent # assign before applyWidget()
            self.applyWidget()
        if self.internal:
            self.value = self.qSet.value(self.name,self.default) # trigger assignment to widget
        else:
            self.value = value # use setter to distinguish data types based on other fields

    def settingEvent(self):
        """Executes internal validation based on setting type.
        Saves parameters to file or qSet to make sure they can be restored even after a crash.
        Finally executes setting specific event if applicable."""
        if not self.parent.loading:
            if self.widgetType == self.WIDGETPATH:
                path = Path(self.value) # validate path and use default if not exists
                if not path.exists():
                    Path(self.default).mkdir(parents=True,exist_ok=True)
                    self.value = Path(self.default)
                    self.print(f'Warning: Could not find path {path.as_posix()}. Defaulting to {self.value.as_posix()}.')
            if self.internal: # save internal parameters to qSet
                self.qSet.sync()
                self.qSet.setValue(self.name,self.value)
                self.qSet.sync()
            else: # save non internal parameters to file
                self.parent.saveSettings(default = True)
            if self.event is not None: # call explicitly assigned event if applicable without causing recursion issue
                self.event()

#################################### Other Custom Widgets #########################################

class QLabviewControlSpinBox(QSpinBox):
    """Implements handling of arrow key events based on curser position as in LabView"""
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.setRange(np.iinfo(np.int32).min,np.iinfo(np.int32).max) # limit explicitly if needed,this seems more useful than the [0,100] default range

    def wheelEvent(self,event):
        event.ignore()

    def stepBy(self,step):
        text=self.lineEdit().text()
        cur = self.lineEdit().cursorPosition()
        pos = len(text)-cur
        if cur==0 and not '-' in text: # left of number
            pos= len(text)-1
        if cur<=1 and '-' in text: # left of number
            pos= len(text)-2
        val=self.value()+1*10**pos*step # use step for sign
        self.setValue(val)

class QLabviewControlDoubleSpinBox(QDoubleSpinBox):
    """Implements handling of arrow key events based on curser position as in LabView"""
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.setRange(-np.inf,np.inf) # limit explicitly if needed,this seems more useful than the [0,100] default range

    def wheelEvent(self,event):
        event.ignore()

    def stepBy(self,step):
        text=self.lineEdit().text()
        cur = self.lineEdit().cursorPosition()
        pos = len(text)-cur
        if pos>=2: # account for .
            pos=pos-1
        if cur==0 and not '-' in text: # left of number
            pos= len(text)-2
        if cur<=1 and '-' in text: # left of number
            pos= len(text)-3
        val=self.value()+0.01*10**pos*step # use step for sign
        self.setValue(val)

class QLabviewIndicatorDoubleSpinBox(QDoubleSpinBox):
    """Implements handling of arrow key events based on curser position as in LabView"""
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.setRange(-np.inf,np.inf)
        self.setReadOnly(True)
        self.preciseValue = 0

    def wheelEvent(self,event):
        event.ignore()

############################ Third Party Widgets ##################################################

class ESIBD_Cursor(Cursor):
    """Extending implementation given here
    https://matplotlib.org/3.5.0/gallery/misc/cursor_demo.html
    cursor only moves when dragged
    """
    def __init__(self,ax,**kwargs):
        self.ax = ax
        super().__init__(ax,**kwargs)

    def onmove(self,event):
        pass

    def ondrag(self,event):
        if event.button == MouseButton.LEFT and kb.is_pressed('ctrl') and event.xdata is not None:
            # dir(event)
            super().onmove(event)

    def setPosition(self,x,y):
        """emulated mouse event to set position"""
        [xpix,ypix]=self.ax.transData.transform((x,y))
        event = MouseEvent(name = '',canvas = self.ax.figure.canvas,x=xpix,y=ypix,button = MouseButton.LEFT)
        super().onmove(event)

    def getPosition(self):
        return self.linev.get_data()[0][0], self.lineh.get_data()[1][1]

    def updatePosition(self):
        self.setPosition(*self.getPosition())
