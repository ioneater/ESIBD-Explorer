""" This module contains only UI controls
The controls generally have a large amount of logic integrated and can act as an intelligent database.
This avoids complex and error prone synchronization between redundant data in the UI and a separate database.
Every parameter should only exist in one unique location at run time.
Separating the logic from the PyQt specific UI elements may be required in the future,
but only if there are no practical and relevant advantages that outweigh the drawbacks."""

from pathlib import Path # replaces os.path
import configparser
import numpy as np
from asteval import Interpreter
from PyQt5 import QtSvg
from PyQt5.QtCore import Qt, QSettings, QEvent,QRectF
from PyQt5.QtWidgets import (QTreeWidget,QTreeWidgetItem,QComboBox,QDoubleSpinBox,QSpinBox,QLineEdit,QToolButton,
                            QCheckBox, QHeaderView, QFileDialog, QLabel, QAbstractSpinBox, QSizePolicy)
from PyQt5.QtGui import QColor, QBrush, QPalette, QPainter
import pyqtgraph as pg
import ES_IBD_configuration as conf
import ES_IBD_RBD as RBD
import ES_IBD_ISEG as ISEG
aeval = Interpreter()

########################## Current user interface #################################################

class CurrentConfigItem(QTreeWidgetItem):
    """UI for picoampmeter with integrated functionality"""
    def __init__(self, esibdWindow, parent, ports):
        super().__init__(parent)
        self.parent = parent
        self.esibdWindow = esibdWindow
        self.channel = None

        #enabled
        self.enabledCheckBox =  QCheckBox() #Led(self, shape=Led.rectangle)
        # self.enabledCheckBox.setToolTip('If enabled, be ')
        self.parent.setItemWidget(self,self.parent.indexEnabled,self.esibdWindow.containerize(self.enabledCheckBox))

        #lens
        self.lensLineEdit = QLineEdit()
        self.parent.setItemWidget(self,self.parent.indexLens,self.lensLineEdit)

        #current
        self.currents = None # array of current history. managed by instrument manager to keep timing synchronous
        self.backgrounds = None # array of background history. managed by instrument manager to keep timing synchronous
        self.charges = None # array of charge history. managed by instrument manager to keep timing synchronous
        self.currentSpinBox = QLabviewIndicatorDoubleSpinBox()
        self.currentSpinBox.setToolTip('Current signal')
        self.currentSpinBox.setValue(0)
        self.parent.setItemWidget(self,self.parent.indexCurrent,self.currentSpinBox)

        #background
        self.backgroundSpinBox = QLabviewControlDoubleSpinBox()
        self.backgroundSpinBox.setToolTip('Background signal')
        self.backgroundSpinBox.setValue(0)
        self.parent.setItemWidget(self,self.parent.indexBackground,self.backgroundSpinBox)

        #charge
        self._charge = 0 # store independent of spin box precision
        self.chargeSpinBox = QLabviewIndicatorDoubleSpinBox()
        self.chargeSpinBox.setToolTip('Accumulated charge')
        self.chargeSpinBox.setValue(0)
        self.parent.setItemWidget(self,self.parent.indexCharge,self.chargeSpinBox)

        #display
        self.currentPlotCurve = None
        self.displayCheckBox = QCheckBox()
        self.displayCheckBox.setToolTip('Display in plot')
        self.displayCheckBox.stateChanged.connect(self.updateDisplay)
        self.parent.setItemWidget(self,self.parent.indexDisplay,self.displayCheckBox)

        #equation
        self.equationLineEdit = QLineEdit()
        self.equationLineEdit.setToolTip('Equation is used if device is not real')
        self.equationLineEdit.setMinimumWidth(350)
        f = self.equationLineEdit.font()
        f.setPointSize(6)
        self.equationLineEdit.setFont(f)
        self.parent.setItemWidget(self,self.parent.indexEquation,self.equationLineEdit)

        #real
        self.realCheckBox = QCheckBox()
        self.realCheckBox.stateChanged.connect(self.realChanged)
        self.realCheckBox.setToolTip('If not real, signal will be determined from equation.')
        self.parent.setItemWidget(self,self.parent.indexReal,self.realCheckBox)

        #color
        self.colorButton = pg.ColorButton()
        self.colorButton.sigColorChanged.connect(self.colorHasChanged)
        parent.setItemWidget(self,self.parent.indexColor,self.colorButton)

        #com
        self.comComboBox = QComboBox()
        self.comComboBox.currentIndexChanged.connect(self.restart)
        for port in ports:
            self.comComboBox.insertItem(self.comComboBox.count(),port)
        self.parent.setItemWidget(self,self.parent.indexCOM,self.esibdWindow.containerize(self.comComboBox))

        #name

        #range
        self.rangeComboBox = QComboBox()
        self.rangeComboBox.currentIndexChanged.connect(self.restart) # index matches RBD documentation!
        self.rangeComboBox.insertItem(self.rangeComboBox.count(),'auto')
        self.rangeComboBox.insertItem(self.rangeComboBox.count(),'2 nA')
        self.rangeComboBox.insertItem(self.rangeComboBox.count(),'20 nA')
        self.rangeComboBox.insertItem(self.rangeComboBox.count(),'200 nA')
        self.rangeComboBox.insertItem(self.rangeComboBox.count(),'2 µA')
        self.rangeComboBox.insertItem(self.rangeComboBox.count(),'20 µA')
        self.rangeComboBox.insertItem(self.rangeComboBox.count(),'200 µA')
        self.rangeComboBox.insertItem(self.rangeComboBox.count(),'2 mA')
        parent.setItemWidget(self,self.parent.indexRange,self.esibdWindow.containerize(self.rangeComboBox))

        #average
        self.averageComboBox = QComboBox()
        self.averageComboBox.currentIndexChanged.connect(self.restart)
        for x in ['off','2','4','8','16','32']: # 2**index is used unless 'off'
            self.averageComboBox.insertItem(self.averageComboBox.count(),x)
        parent.setItemWidget(self,self.parent.indexAverage,self.esibdWindow.containerize(self.averageComboBox))

        #bias
        self.biasCheckBox = QCheckBox()
        self.biasCheckBox.stateChanged.connect(self.restart)
        self.biasCheckBox.setToolTip('Internal bias')
        parent.setItemWidget(self,self.parent.indexBias,self.esibdWindow.containerize(self.biasCheckBox))

        #out of range
        self.outOfRangeCheckBox = QCheckBox()
        self.outOfRangeCheckBox.setToolTip('Indicates if signal is out of range')
        self.outOfRangeCheckBox.setCheckable(False)
        self.outOfRangeCheckBox.setChecked(False)
        parent.setItemWidget(self,self.parent.indexOutOfRange,self.esibdWindow.containerize(self.outOfRangeCheckBox))

        #unstable
        self.unstableCheckBox = QCheckBox()
        self.unstableCheckBox.setToolTip('Indicates if signal is out of unstable')
        self.unstableCheckBox.setCheckable(False)
        self.unstableCheckBox.setChecked(False)
        parent.setItemWidget(self,self.parent.indexUnstable,self.esibdWindow.containerize(self.unstableCheckBox))

        #error
        self.setData(self.parent.indexError,Qt.DisplayRole,'')

    @property
    def enabled(self):
        return self.enabledCheckBox.isChecked()
    @enabled.setter
    def enabled(self, enabled = True):
        self.enabledCheckBox.setChecked(enabled)

    @property
    def name(self):
        return self.text(self.parent.indexName)
    @name.setter
    def name(self, name = ''):
        self.setData(self.parent.indexName,Qt.DisplayRole,name)

    @property
    def com(self):
        return self.comComboBox.currentText()
    @com.setter
    def com(self, com):
        self.comComboBox.setCurrentText(com)
        self.restart()

    @property
    def lens(self):
        return self.lensLineEdit.text()
    @lens.setter
    def lens(self, lens):
        self.lensLineEdit.setText(lens)

    @property
    def current(self):
        return self.currentSpinBox.value()
    @current.setter
    def current(self, current):
        self.currentSpinBox.setValue(current)

    @property
    def background(self):
        return self.backgroundSpinBox.value()
    @background.setter
    def background(self, background):
        self.backgroundSpinBox.setValue(background)

    @property
    def charge(self):
        return self._charge
    @charge.setter
    def charge(self, charge):
        self._charge = charge
        self.chargeSpinBox.setValue(charge)

    def getCurrents(self, subtractBackground = True):
        # note that background subtraction only affects what is displayed, the raw signal and background curves are always retained
        return ((self.currents.get() - self.backgrounds.get()) if subtractBackground else self.currents.get())

    def appendCurrent(self,timestep):
        # calculate deposited charge in last timestep for all channels
        # this does not only monitors the sample but also an what lenses charge is lost
        self.currents.add(self.current)
        self.backgrounds.add(self.background)
        chargeIncrement = (self.current-self.background)*timestep/3600 if self.currents.size > 1 else 0
        self.charges.add(chargeIncrement)
        self.charge = self.charge + chargeIncrement # display accumulated charge

    def clearHistory(self):
        #self.esibdWindow.signalComm.printFromThreadSignal.emit('clearHistory')
        self.currents = self.esibdWindow.dynamicNp()
        self.backgrounds = self.esibdWindow.dynamicNp()
        self.charges = self.esibdWindow.dynamicNp()
        self.charge = 0

    def restart(self): # restart if parameters changed while acquiring
        if self.channel is not None and self.channel.acquiring:
            self.channel.init(True)

    @property
    def range(self):
        return self.rangeComboBox.currentText()
    @range.setter
    def range(self, _range):
        self.rangeComboBox.setCurrentText(_range)
        self.restart()

    @property
    def average(self):
        return self.averageComboBox.currentText()
    @average.setter
    def average(self, average):
        self.averageComboBox.setCurrentText(average)
        self.restart()

    @property
    def bias(self):
        return self.biasCheckBox.isChecked()
    @bias.setter
    def bias(self, bias):
        self.biasCheckBox.setChecked(bias)
        self.restart()

    @property
    def display(self):
        return self.displayCheckBox.isChecked()
    @display.setter
    def display(self, display):
        self.displayCheckBox.setChecked(display)

    @property
    def equation(self):
        return self.equationLineEdit.text()
    @equation.setter
    def equation(self, equation):
        self.equationLineEdit.setText(equation)

    @property
    def real(self):
        return self.realCheckBox.isChecked()
    @real.setter
    def real(self, real):
        self.realCheckBox.setChecked(real)
        self.realChanged(real)

    def realChanged(self,real):
        self.enabledCheckBox.setVisible(real)
        self.comComboBox.setVisible(real)
        self.rangeComboBox.setVisible(real)
        self.averageComboBox.setVisible(real)
        self.biasCheckBox.setVisible(real)
        self.outOfRangeCheckBox.setVisible(real)
        self.unstableCheckBox.setVisible(real)

    @property
    def outOfRange(self):
        return self.outOfRangeCheckBox.isChecked()
    @outOfRange.setter
    def outOfRange(self, outOfRange):
        self.outOfRangeCheckBox.setChecked(outOfRange)

    @property
    def unstable(self):
        return self.unstableCheckBox.isChecked()
    @unstable.setter
    def unstable(self, unstable):
        self.unstableCheckBox.setChecked(unstable)

    @property
    def error(self):
        return self.data(self.parent.indexError,Qt.DisplayRole)
    @error.setter
    def error(self, error):
        self.setData(self.parent.indexError,Qt.DisplayRole,error)
        self.setData(self.parent.indexError,Qt.ToolTipRole,error)

    @property
    def color(self):
        """Use light colors to ensure contrast to text and cursor"""
        return self.colorButton.color()
    @color.setter
    def color(self,color):
        self.colorButton.setColor(color,True)
        self.colorHasChanged()

    def colorHasChanged(self):
        """Apply new color to all controls"""
        qb = QBrush(self.color)
        for i in range(self.parent.indexError+1): # use highest index
            self.setBackground(i,qb)
        palette = QPalette()
        palette.setColor(QPalette.Base,self.color)
        self.lensLineEdit     .setPalette(palette)
        self.currentSpinBox   .setPalette(palette)
        self.backgroundSpinBox.setPalette(palette)
        self.chargeSpinBox.setPalette(palette)
        self.equationLineEdit   .setPalette(palette)
        setStyleSheet = f'background: rgb({self.color.red()}, {self.color.green()}, {self.color.blue()})'
        self.comComboBox      .setStyleSheet(setStyleSheet) # not working -> need stylesheet on windows
        self.rangeComboBox    .setStyleSheet(setStyleSheet)
        self.averageComboBox  .setStyleSheet(setStyleSheet)

    def updateDisplay(self):
        if self.currentPlotCurve is not None:
            if self.display:
                self.currentPlotCurve.setPen(pg.mkPen(self.color, width=5))
            else:
                self.currentPlotCurve.setPen(pg.mkPen(None))

    @property
    def dict(self):
        return {conf.NAME : self.name, conf.ENABLED : str(self.enabled), conf.COM : self.com, conf.LENS : self.lens, conf.RANGE : self.range, conf.EQUATION : self.equation,
                conf.AVERAGE : self.average, conf.BIAS : str(self.bias), conf.DISPLAY : str(self.display), conf.REAL : str(self.real), conf.COLOR : self.color.name()}

class CurrentConfig(QTreeWidget):
    """Bundles miltiple real and virtual current channels into a single object to handle shared functionality"""
    def __init__(self, esibdWindow):
        super().__init__(esibdWindow)
        self.esibdWindow=esibdWindow
        self.header().setSectionsMovable(False) # keep order fixed to allow use od static indices
        self.qSet = QSettings(conf.COMPANY_NAME, conf.PROGRAM_NAME)
        (self.indexEnabled, self.indexLens, self.indexCurrent, self.indexBackground, self.indexCharge, self.indexDisplay, self.indexEquation, self.indexReal, self.indexColor, self.indexCOM,
        self.indexName, self.indexRange, self.indexAverage, self.indexBias, self.indexOutOfRange, self.indexUnstable, self.indexError) = range(17)
        self.setHeaderLabels(['Enabled','Lens','I (pA)','BG (pA)','C (pAh)','Display','Equation','Real','Color','COM','Device','Range','Average','Bias','OOR','U','Message'])
        #head = self.header().
        #head.setData((self.indexError,Qt.ToolTipRole,'Current (pA)')) # tooltips would be nice here
        self._advanced = False
        self.initialized = False
        self.loading=False
        self.load(conf.currentConfigFile(self.qSet))

    def addDevice(self, name, item):
        "maps dictionary to UI control"
        device = CurrentConfigItem(esibdWindow=self.esibdWindow ,parent=self, ports=self.ports)
        self.devices.append(device)
        self.addTopLevelItem(device) # has to be added before populating

        device.name     = item.get(conf.NAME,name) # should never be empty
        device.enabled  = item.get(conf.ENABLED, 'True') == 'True'
        device.lens     = item.get(conf.LENS, '')
        # device.current # no need to load
        # device.background # no need to load
        # device.charge # no need to load
        device.display  = item.get(conf.DISPLAY, 'True') == 'True'
        device.equation = item.get(conf.EQUATION, '')
        device.real     = item.get(conf.REAL, 'True') == 'True'
        device.color    = QColor(item.get(conf.COLOR,'#ffffff'))
        device.com      = item.get(conf.COM,'COM0')
        device.range    = item.get(conf.RANGE,'auto')
        device.average  = item.get(conf.AVERAGE,'off')
        device.bias     = item.get(conf.BIAS, 'False') == 'True'
        device.channel  = RBD.CurrentChannel(esibdWindow = self.esibdWindow, device = device)

    def getDevicebyLens(self, lens):
        return next((d for d in self.devices if d.lens.strip().lower() == lens.strip().lower()), None)

    def getInitializedDevices(self):
        return [d for d in self.devices if d.enabled and (d.channel.port is not None or self.esibdWindow.testMode or not d.real)]

    def load(self, file = None):
        """loads current channels from file"""
        self.loading=True
        if file is None: # get file via dialog
            file = Path(QFileDialog.getOpenFileName(self.esibdWindow,conf.SELECTFILE,filter = conf.FILTER_INI)[0])
        if file != Path('.'):
            self.setUpdatesEnabled(False)
            self.setRootIsDecorated(False) # no need to show expander
            self.devices    = []
            self.ports      = self.esibdWindow.serial_ports()
            self.clear()
            confParser = configparser.ConfigParser()
            confParser.read(file)
            for name, item in confParser.items():
                if not any(name == key for key in [conf.DEFAULT,conf.VERSION]):
                    self.addDevice(name, item)
            self.header().setStretchLastSection(False)
            self.header().setSectionResizeMode(QHeaderView.ResizeToContents)
            self.advanced = self.advanced
            self.setUpdatesEnabled(True)
        self.loading=False

    def save(self, file = None):
        if file is None: # get file via dialog
            file = Path(QFileDialog.getSaveFileName(self.esibdWindow,conf.SELECTFILE,filter = conf.FILTER_INI)[0])
        if file != Path('.'):
            config = configparser.ConfigParser()
            config[conf.VERSION] = self.esibdWindow.settingsMgr.settingsDict(conf.VERSION,f'{conf.VERSION_MAYOR}.{conf.VERSION_MINOR}',conf.CURRENT,'',conf.WIDGETLABEL,conf.GENERAL)
            for i, device in enumerate(self.devices):
                config[f'CURRENT_{i:03d}'] = device.dict
            with open(file, 'w', encoding = conf.UTF8) as configfile:
                config.write(configfile)

    def init(self, restart = False):
        for device in self.devices:
            device.channel.init(restart)
        self.initialized = True

    def startSampling(self):
        for device in self.devices:
            if device.enabled:
                device.channel.startSampling(interval = int(self.esibdWindow.settingsMgr[conf.DATAINTERVAL].value))

    def stopSampling(self):
        for device in self.devices:
            device.channel.stopSampling()

    def reset(self):
        for device in self.devices:
            device.channel.reset()

    def resetCharge(self):
        for d in self.devices:
            d.charge = 0

    def close(self):
        for device in self.devices:
            device.channel.close()

    def setBackground(self): # make current signal background
        for device in self.devices: # save current signal as background
            device.background = device.current

    @property
    def advanced(self):
        return self._advanced
    @advanced.setter
    def advanced(self, advanced):
        self.setAdvanced(advanced)

    def setAdvanced(self, advanced): # allow to connect to envent
        self._advanced = advanced
        hide = not self._advanced
        self.setColumnHidden(self.indexColor   , hide)
        self.setColumnHidden(self.indexCOM     , hide)
        self.setColumnHidden(self.indexName    , hide)
        self.setColumnHidden(self.indexRange   , hide)
        self.setColumnHidden(self.indexEquation, hide)
        self.setColumnHidden(self.indexAverage , hide)
        self.setColumnHidden(self.indexBias    , hide)


    def updateCurrent(self):
        """updates current based on equations.
        See updateVoltage for documentation of the parsing algorithm."""
        if self.loading: # wait until all devices are complete before applying logic
            return
        N = 2
        for _ in range(N): # go through parsing twice, in case the dependencies are note ordered
            for device in self.devices:
                if not device.real:
                    equ_c = device.equation
                    equ_b = device.equation
                    for d in self.devices:
                        if d.lens != '': # should not happen anyways # note: if c.name is '' replace will add voltage between each character
                            equ_c = equ_c.replace(d.lens,f'{d.current}') # convert equation to math expression
                            equ_b = equ_b.replace(d.lens,f'{d.background}') # convert equation to math expression
                    device.current = aeval(equ_c) or 0 # evaluate
                    device.background = aeval(equ_b) or 0 # evaluate


########################## Voltage user interface #################################################

class VoltageConfigItem(QTreeWidgetItem):
    """UI for single voltage channel with integrated functionality"""

    def __init__(self, esibdWindow, parent):
        super().__init__(parent)
        self.esibdWindow=esibdWindow
        self.parent=parent
        self.voltages = None
        self.palette = QPalette()

        self.lastAppliedVoltage = None # keep track of last value to identify what has changed
        #name
        self.nameLineEdit = QLineEdit()
        self.parent.setItemWidget(self,self.parent.indexName,self.nameLineEdit)

        #voltage
        self.voltageSpinBox = QLabviewControlDoubleSpinBox()
        self.voltageSpinBox.setValue(0)
        self.voltageSpinBox.valueChanged.connect(self.updateVoltage)
        self.parent.setItemWidget(self,self.parent.indexVoltage,self.voltageSpinBox)

        # select
        self.selectPushButton = QToolButton() # QPushButton is too wide
        self.selectPushButton.setText('Select')
        self.selectPushButton.setMinimumWidth(5)
        self.selectPushButton.setCheckable(True)
        self.selectPushButton.setCheckable(True)
        self.selectPushButton.clicked.connect(self.setX)
        self.parent.setItemWidget(self,self.parent.indexSelect,self.selectPushButton)

        #monitor
        self.warningPalette = QPalette()
        self.warningPalette.setColor(QPalette.Base,Qt.red)
        self.monitorSpinBox = QLabviewIndicatorDoubleSpinBox()
        self.monitorSpinBox.setValue(0)
        self.parent.setItemWidget(self,self.parent.indexMonitor,self.esibdWindow.containerize(self.monitorSpinBox))

        #equation
        self.equationLineEdit = QLineEdit()
        self.equationLineEdit.setMinimumWidth(350)
        f = self.equationLineEdit.font()
        f.setPointSize(6)
        self.equationLineEdit.setFont(f)
        self.parent.setItemWidget(self,self.parent.indexEquation,self.equationLineEdit)

        #enabled
        self.enabledCheckBox = QCheckBox()
        self.enabledCheckBox.setToolTip('If enabled, voltage will be applied to channel')
        self.enabledCheckBox.stateChanged.connect(self.enabledChanged)
        self.parent.setItemWidget(self,self.parent.indexEnabled,self.esibdWindow.containerize(self.enabledCheckBox))

        #active
        self.activeCheckBox = QCheckBox()
        self.activeCheckBox.stateChanged.connect(self.activeChanged)
        self.activeCheckBox.setToolTip('If passive, voltage will be determined from equation.')

        self.parent.setItemWidget(self,self.parent.indexActive,self.activeCheckBox)

        #real
        self.realCheckBox = QCheckBox()
        self.realCheckBox.setChecked(True) # to trigger realChanged if loaded a virtual channel
        self.realCheckBox.stateChanged.connect(self.realChanged)
        self.realCheckBox.setToolTip('Set to real for physically exiting channels')
        self.parent.setItemWidget(self,self.parent.indexReal,self.realCheckBox)

        #module
        self.moduleSpinBox = QLabviewControlSpinBox()
        self.moduleSpinBox.setMinimum(-1000) # min/max affect widget size!
        self.moduleSpinBox.setMaximum(+1000)
        self.moduleSpinBox.setValue(0)
        self.parent.setItemWidget(self,self.parent.indexModule,self.esibdWindow.containerize(self.moduleSpinBox))

        #channelID
        self.idSpinBox = QLabviewControlSpinBox()
        self.idSpinBox.setMinimum(-1000)
        self.idSpinBox.setMaximum(+1000)
        self.idSpinBox.setValue(0)
        self.parent.setItemWidget(self,self.parent.indexID,self.esibdWindow.containerize(self.idSpinBox))

        #min
        self.minSpinBox = QLabviewControlSpinBox()
        self.minSpinBox.setMinimum(-100000)
        self.minSpinBox.setMaximum(+100000)
        self.parent.setItemWidget(self,self.parent.indexMin,self.esibdWindow.containerize(self.minSpinBox))

        #max
        self.maxSpinBox = QLabviewControlSpinBox()
        self.maxSpinBox.setMinimum(-100000)
        self.maxSpinBox.setMaximum(+100000)
        self.parent.setItemWidget(self,self.parent.indexMax,self.esibdWindow.containerize(self.maxSpinBox))

        #optimize
        self.optimizeCheckBox = QCheckBox()
        self.optimizeCheckBox.setToolTip('Selected channels will be optimized using GA')
        self.parent.setItemWidget(self,self.parent.indexOpt,self.optimizeCheckBox)

        #color
        self.colorButton = pg.ColorButton()
        self.colorButton.sigColorChanged.connect(self.colorHasChanged)
        self.parent.setItemWidget(self,self.parent.indexColor,self.colorButton)

    @property
    def name(self):
        return self.nameLineEdit.text()
    @name.setter
    def name(self, name):
        self.nameLineEdit.setText(name)

    @property
    def voltage(self):
        return self.voltageSpinBox.value() if self.enabled else 0
    @voltage.setter
    def voltage(self, voltage):
        self.voltageSpinBox.setValue(voltage)

    def setVoltage(self,apply): # this actually sets the voltage on the powersupply!
        if self.real and ((self.voltage != self.lastAppliedVoltage) or apply):
            self.parent.voltageMgr.setVoltage(self)
            self.lastAppliedVoltage = self.voltage

    def updateVoltage(self): # just defined for debugging events
        self.parent.updateVoltage(apply = False)

    def getVoltages(self, xaxis):
        # return section matching x axis
        length = min(len(xaxis), self.voltages.get().shape[0])
        return self.voltages.get()[-length:] # xaxis[-length:],

    def appendVoltage(self):
        self.voltages.add(self.voltage)

    def clearHistory(self):
        self.voltages= self.esibdWindow.dynamicNp(max_size = 600000/int(self.esibdWindow.settingsMgr[conf.DATAINTERVAL].value)) # 600000 only keep last 10 min to save ram

    def setX(self):
        checked = self.selectPushButton.isChecked()
        for c in self.parent.channels:
            c.selectPushButton.setChecked(False)
        self.selectPushButton.setChecked(checked)
        self.esibdWindow.xChannelChanged()

    @property
    def monitor(self):
        return self.monitorSpinBox.value()
    @monitor.setter
    def monitor(self,monitor):
        self.monitorSpinBox.setValue(monitor)
        if self.enabled and self.parent.voltageMgr.monitoring and ((self.parent.ON and abs(self.monitor - self.voltage) > 1) or (not self.parent.ON and abs(self.monitor - 0) > 1)):
            self.monitorSpinBox.setPalette(self.warningPalette) # will alays be triggered when changing voltage -> will reset as soon as voltage is stable.
        else:
            self.monitorSpinBox.setPalette(self.palette)

    @property
    def equation(self):
        return self.equationLineEdit.text()
    @equation.setter
    def equation(self, equation):
        self.equationLineEdit.setText(equation)

    @property
    def enabled(self):
        return self.enabledCheckBox.isChecked()
    @enabled.setter
    def enabled(self, enabled): # change by code
        self.enabledCheckBox.setChecked(enabled)
        self.enabledChanged()

    def enabledChanged(self): # change by user click
        self.parent.updateVoltage()

    @property
    def active(self):
        return self.activeCheckBox.isChecked()
    @active.setter
    def active(self, active):
        self.activeCheckBox.setChecked(active)
        self.activeChanged()

    def activeChanged(self):
        self.colorHasChanged()
        self.parent.updateVoltage()

    @property
    def real(self):
        return self.realCheckBox.isChecked()
    @real.setter
    def real(self, real):
        self.realCheckBox.setChecked(real)
        self.realChanged(real)

    def realChanged(self,real):
        self.enabledCheckBox.setVisible(real)
        self.monitorSpinBox.setVisible(real)
        self.moduleSpinBox.setVisible(real)
        self.idSpinBox.setVisible(real)
        # self.minSpinBox.setVisible(real)
        # self.maxSpinBox.setVisible(real)
        self.parent.updateVoltage()

    @property
    def module(self):
        return self.moduleSpinBox.value()
    @module.setter
    def module(self, module):
        self.moduleSpinBox.setValue(module)

    @property
    def id(self):
        return self.idSpinBox.value()
    @id.setter
    def id(self, _id):
        self.idSpinBox.setValue(_id)

    @property
    def min(self):
        return self.minSpinBox.value()
    @min.setter
    def min(self, _min):
        self.voltageSpinBox.setMinimum(_min)
        self.minSpinBox.setValue(_min)
        self.esibdWindow.xChannelChanged()

    @property
    def max(self):
        return self.maxSpinBox.value()
    @max.setter
    def max(self, _max):
        self.voltageSpinBox.setMaximum(_max)
        self.maxSpinBox.setValue(_max)
        self.esibdWindow.xChannelChanged()

    @property
    def optimize(self):
        return self.optimizeCheckBox.isChecked()
    @optimize.setter
    def optimize(self, optimize):
        self.optimizeCheckBox.setChecked(optimize)

    @property
    def color(self):
        return self.colorButton.color()
    @color.setter
    def color(self, color):
        self.colorButton.setColor(color)
        self.colorHasChanged()

    def colorHasChanged(self):
        """apply new color to all controls"""
        color = self.color if self.active else self.color.darker(115) # indicate passive channels by darker color
        qb = QBrush(color)
        for i in range(self.parent.indexColor+1): # use highest index
            self.setBackground(i,qb)
        self.palette.setColor(QPalette.Base,color)
        self.nameLineEdit       .setPalette(self.palette)
        self.voltageSpinBox     .setPalette(self.palette)
        self.equationLineEdit   .setPalette(self.palette)
        self.moduleSpinBox      .setPalette(self.palette)
        self.idSpinBox          .setPalette(self.palette)
        self.minSpinBox         .setPalette(self.palette)
        self.maxSpinBox         .setPalette(self.palette)
        self.monitorSpinBox     .setPalette(self.palette)
        setStyleSheet = f'background: rgb({self.color.red()}, {self.color.green()}, {self.color.blue()})'
        self.selectPushButton.setStyleSheet(setStyleSheet) # not working -> need stylesheet on windows

    @property
    def dict(self):
        return {conf.NAME : self.name, conf.VOLTAGE : str(self.voltage), conf.ENABLED : str(self.enabled), conf.EQUATION : self.equation,
                conf.ACTIVE : str(self.active), conf.REAL : str(self.real), conf.MODULE : str(self.module), conf.ID : str(self.id),
                conf.MIN : str(self.min), conf.MAX : str(self.max), conf.OPTIMIZE : str(self.optimize), conf.COLOR : self.color.name()}

class VoltageConfig(QTreeWidget):
    """Bundles miltiple real and virtual voltage channels into a single object to handle shared functionality"""
    def __init__(self, esibdWindow=None):
        super().__init__(esibdWindow)
        self.esibdWindow=esibdWindow
        self.header().setSectionsMovable(False) # keep order fixed to allow use od static indices
        self.qSet = QSettings(conf.COMPANY_NAME, conf.PROGRAM_NAME)
        (self.indexSelect, self.indexName, self.indexVoltage, self.indexMonitor, self.indexMin, self.indexMax, self.indexOpt, self.indexEquation, self.indexEnabled, self.indexActive,
        self.indexReal, self.indexModule, self.indexID, self.indexColor) = range(14)
        self.setHeaderLabels(['Select','Name','Voltage (V)','Monitor (V)','Min (V)','Max (V)','Opt','Equation','Enabled','Active','Real','Module','Channel','Color'])
        self._advanced  = False
        self.voltageMgr = None
        self.loading=False
        self.ON = False
        self.load(conf.voltageConfigFile(self.qSet))

    def addChannel(self, name, item):
        "maps dictionary to UI control"
        channel = VoltageConfigItem(self.esibdWindow,self)
        self.channels.append(channel)
        self.addTopLevelItem(channel) # has to be added before populating
        channel.name      = item.get(conf.NAME,name) # name must not be empty
        channel.voltage   = float(item.get(conf.VOLTAGE, '0'))
        channel.equation  = item.get(conf.EQUATION, '')
        channel.enabled   = item.get(conf.ENABLED, 'True') == 'True'
        channel.active    = item.get(conf.ACTIVE, 'True') == 'True'
        channel.real      = item.get(conf.REAL, 'True') == 'True'
        channel.module    = int(item.get(conf.MODULE,'0'))
        channel.id        = int(item.get(conf.ID,'0'))
        channel.min       = int(item.get(conf.MIN,'-250'))
        channel.max       = int(item.get(conf.MAX,'250'))
        channel.optimize  = item.get(conf.OPTIMIZE, 'False') == 'True'
        channel.color     = item.get(conf.COLOR,'#c6c7c8')

    def getChannelbyName(self, name):
        return next((c for c in self.channels if c.name.strip().lower() == name.strip().lower()), None)

    def getSelectedChannel(self):
        return next((c for c in self.channels if c.selectPushButton.isChecked()), None)

    def load(self, file = None):
        """loads voltage channels from file"""
        if file is None: # get file via dialog
            file = Path(QFileDialog.getOpenFileName(self.esibdWindow,conf.SELECTFILE,filter = conf.FILTER_INI)[0])
        if file != Path('.'):
            self.loading=True
            self.setUpdatesEnabled(False)
            self.setRootIsDecorated(False) # no need to show expander
            self.channels=[]
            self.clear()
            confParser = configparser.ConfigParser()
            confParser.read(file)
            for name, item in confParser.items():
                if not any(name == key for key in [conf.DEFAULT,conf.VERSION]):
                    self.addChannel(name,item)
            self.header().setStretchLastSection(False)
            self.header().setSectionResizeMode(QHeaderView.ResizeToContents)
            self.advanced = self.advanced # trigger applying correct state
            self.setUpdatesEnabled(True)

            self.voltageMgr = ISEG.VoltageManager(esibdWindow = self.esibdWindow, parent=self, modules = self.getModules()) # after all channels loaded
            self.loading=False
            self.updateVoltage() # wait until all channels loaded

    def save(self, file = None):
        if file is None: # get file via dialog
            file = Path(QFileDialog.getSaveFileName(self.esibdWindow,conf.SELECTFILE,filter = conf.FILTER_INI)[0])
        if file != Path('.'):
            config = configparser.ConfigParser()
            config[conf.VERSION] = self.esibdWindow.settingsMgr.settingsDict(conf.VERSION,f'{conf.VERSION_MAYOR}.{conf.VERSION_MINOR}',conf.VOLTAGE,'',conf.WIDGETLABEL,conf.GENERAL)
            for i, channel in enumerate(self.channels):
                config[f'VOLTAGE_{i:03d}'] = channel.dict

            with open(file, 'w', encoding = conf.UTF8) as configfile:
                config.write(configfile)

    def getModules(self): # get list of used modules
        return set([channel.module for channel in self.channels])

    def init(self, restart = False):
        self.voltageMgr.init(IP = self.esibdWindow.settingsMgr[conf.ISEGIP].value, port = int(self.esibdWindow.settingsMgr[conf.ISEGPORT].value),restart = restart)

    def close(self):
        self.voltageMgr.close()

    def voltageON(self, ON = False):
        self.ON = ON
        self.voltageMgr.voltageON(ON)

    def updateVoltage(self, apply = False):
        """this minimal implementation will not give a warning about circular definitions
        it will also fail if expressions are nested on more than N levels (N can be increased as needed)
        it should however be sufficient for day to day ESIBD work
        more complex algorithms should only be implemented if they are required to solve a practical problem"""
        if self.loading: # wait until all channels are complete before applying logic
            return
        N = 2
        for _ in range(N): # go through parsing twice, in case the dependencies are note ordered
            for channel in self.channels:
                if not channel.active:
                    equ = channel.equation
                    for c in self.channels:
                        if c.name != '': # should not happen anyways # note: if c.name is '' replace will add voltage between each character
                            equ = equ.replace(c.name,f'{c.voltage}') # convert equation to math expression
                    channel.voltage = aeval(equ) or 0 # evaluate

        for c in self.channels:
            c.setVoltage(apply) # only actually sets voltage if configured and value has changed



    @property
    def advanced(self):
        return self._advanced
    @advanced.setter
    def advanced(self,advanced):
        self.setAdvanced(advanced)

    def setAdvanced(self, advanced): # allow to be connected to event, not possible with setter
        self._advanced = advanced
        hide = not self._advanced
        self.setColumnHidden(self.indexEquation, hide)
        self.setColumnHidden(self.indexEnabled, hide) #if c.real else True keep hidden
        self.setColumnHidden(self.indexActive, hide)
        self.setColumnHidden(self.indexReal, hide)
        self.setColumnHidden(self.indexModule, hide)
        self.setColumnHidden(self.indexID, hide)
        self.setColumnHidden(self.indexMin, hide)
        self.setColumnHidden(self.indexMax, hide)
        self.setColumnHidden(self.indexOpt, hide)
        self.setColumnHidden(self.indexColor, hide)
        for c in self.channels:
            c.setHidden(not self._advanced and not c.active)

#################################### Settings Item ################################################

class esibdSetting(QTreeWidgetItem):
    """General setting including name, value, default, items, and widgetType
    It maps these property to appropriate UI elements"""
    def __init__(self, esibdWindow, tree, name, _dict, parentItem=None, internal = False):
        super().__init__() # init without tree, otherwise they are added before correct parent is identified
        self.esibdWindow=esibdWindow
        self.qSet = QSettings(conf.COMPANY_NAME, conf.PROGRAM_NAME)
        self.tree = tree
        self.category = _dict.get(conf.CATEGORY,conf.CATGENERAL)
        self.fullName = name # will contain path of setting in HDF5 file if applicable
        if parentItem is None: # use category logic used for general settings, else use provided item
            parents = self.tree.findItems(self.category,Qt.MatchFixedString,0)
            if len(parents) > 0:
                self.parentItem = parents[0]
            else:
                self.parentItem = QTreeWidgetItem()
                self.parentItem.setData(0,Qt.DisplayRole,self.category)
                self.tree.addTopLevelItem(self.parentItem)
        else:
            self.parentItem = parentItem
        self.parentItem.addChild(self) # has to be added to parent before widgets can be added!

        self.name = Path(name).name # only use last element in case its a path
        self.setData(0,Qt.DisplayRole,self.name)

        self.applyWidget(_dict)

        self.setToolTip(0, _dict.get(conf.TOOLTIP,''))
        self.internal = internal # internal settings will not be exported to file but saved using QSetting
        self._default = None
        self.default = _dict.get(conf.DEFAULT,'')
        if not internal:
            self.value = _dict.get(conf.VALUE,'') # use setter to distinguish data types based on other fields

    @property
    def value(self):
        """returns value in correct format, based on widget type"""
        if self.internal:
            self.qSet.sync()
            return self.qSet.value(self.name)
        elif self.widget == conf.WIDGETCOMBO:
            return self.combo.currentText()
        elif self.widget == conf.WIDGETTEXT:
            return self.line.text()
        elif self.widget == conf.WIDGETINT or self.widget == conf.WIDGETFLOAT:
            return self.spin.value()
        elif self.widget == conf.WIDGETBOOL:
            return self.check.isChecked()
        elif self.widget == conf.WIDGETCOLOR:
            return None
        elif self.widget == conf.WIDGETLABEL: # self.widget is widgetLabel: # default
            return self.data(1,Qt.DisplayRole)

    @value.setter
    def value(self, value):
        if self.widget == conf.WIDGETBOOL:
            self.check.setChecked(value == 'True')
        elif self.widget == conf.WIDGETINT:
            self.spin.setValue(int(value))
        elif self.widget == conf.WIDGETCOLOR:
            pass
        elif self.widget == conf.WIDGETCOMBO:
            try:
                self.combo.setCurrentIndex(self.combo.findText(value))
            except ValueError as e:
                self.esibdWindow.esibdPrint(f'{value} not found, Error: {e}')
                self.combo.setCurrentIndex(0)
        elif self.widget == conf.WIDGETFLOAT:
            self.spin.setValue(float(value))
        elif self.widget == conf.WIDGETTEXT:
            self.line.setText(str(value)) # input may be of type Path from pathlib -> needs to be converted to str for display in lineedit
        elif self.widget == conf.WIDGETLABEL:
            self.setData(1,Qt.DisplayRole,str(value)) # input may be of type Path from pathlib -> needs to be converted to str for display in lineedit

        if self.internal:
            self.qSet.setValue(self.name,value)
            self.qSet.sync()

    @property
    def default(self):
        return self._default

    @default.setter
    def default(self, default): # casting does not change anything if the value is already supplied in the right type, but will convert strings to correct value if needed
        if self.widget == conf.WIDGETBOOL:
            self._default = default == 'True'
        elif self.widget == conf.WIDGETINT:
            self._default = int(default)
        elif self.widget == conf.WIDGETFLOAT:
            self._default = float(default)
        else: # conf.WIDGETTEXT
            self._default = str(default)

    @property
    def toolTip(self):
        return self.data(0,Qt.ToolTipRole)

    @property
    def items(self):
        if self.widget == conf.WIDGETCOMBO:
            return [self.combo.itemText(i) for i in range(self.combo.count())]
        else:
            return ''

    @property
    def changedEvent(self):
        return self._changedEvent

    @changedEvent.setter
    def changedEvent(self, changedEvent):
        self._changedEvent=changedEvent
        if self.widget == conf.WIDGETCOMBO:
            self.combo.currentIndexChanged.connect(self._changedEvent)
        elif self.widget == conf.WIDGETTEXT:
            self.line.editingFinished.connect(self._changedEvent)
        elif self.widget == conf.WIDGETINT or self.widget == conf.WIDGETFLOAT:
            self.spin.editingFinished.connect(self._changedEvent)
        elif self.widget == conf.WIDGETBOOL:
            self.check.stateChanged.connect(self._changedEvent)
        elif self.widget == conf.WIDGETCOLOR:
            pass
        elif self.widget is conf.WIDGETLABEL:
            pass # cannot easily assign event to specific QTreeViewItem field

    def setToDefault(self):
        self.value = self.default

    def makeDefault(self):
        self.default = self.value

    def applyWidget(self, _dict):
        """create UI widget depending on widget type"""
        self.widget = _dict.get(conf.WIDGET,conf.WIDGETLABEL)
        if self.widget == conf.WIDGETCOMBO:
            self.combo = QComboBox()
            for i in [x.strip(' ') for x in _dict.get(conf.ITEMS,'').split(',')]:
                self.combo.insertItem(self.combo.count(),i)
            self.tree.setItemWidget(self,1,self.combo)
            self.combo.setContextMenuPolicy(Qt.CustomContextMenu)
            self.combo.customContextMenuRequested.connect(self.initComboContextMenu)
        elif self.widget == conf.WIDGETTEXT:
            self.line = QLineEdit()
            self.tree.setItemWidget(self,1,self.line)
        elif self.widget == conf.WIDGETINT or self.widget == conf.WIDGETFLOAT:
            self.spin = QLabviewControlDoubleSpinBox() if self.widget == conf.WIDGETFLOAT else QLabviewControlSpinBox()
            self.tree.setItemWidget(self,1,self.spin)
        elif self.widget == conf.WIDGETBOOL:
            self.check = QCheckBox()
            self.tree.setItemWidget(self,1,self.check)
        elif self.widget == conf.WIDGETCOLOR:
            pass
        else: # self.widget is widgetLabel: # default
            pass

    def initComboContextMenu(self, pos):
        self.esibdWindow.initSettingsContextMenuBase(self, self.combo.mapToGlobal(pos))

    def addItem(self, value): # should only be called for WIDGETCOMBO settings
        self.combo.insertItem(self.combo.count(),value)
        self.value = value

    def removeCurrentItem(self):
        if len(self.items) > 1:
            self.combo.removeItem(self.combo.currentIndex())
        else:
            self.esibdWindow.esibdPrint('List cannot be empty')

    def editCurrentItem(self,value):
        self.combo.setItemText(self.combo.currentIndex(),value)


#################################### Other Custom Widgets #########################################

class QLabviewControlSpinBox(QSpinBox):
    """Implements handling of arrow key events based on curser position as in LabView"""
    def __init__(self, parent=None):
        super(QLabviewControlSpinBox, self).__init__(parent)
        self.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.setRange(np.iinfo(np.int32).min,np.iinfo(np.int32).max) # limit explicitly if needed, this seems more useful than the [0,100] default range

    def wheelEvent(self, event):
        event.ignore()

    def stepBy(self, step):
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
    def __init__(self, parent=None):
        super(QLabviewControlDoubleSpinBox, self).__init__(parent)
        self.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.setRange(-np.inf,np.inf) # limit explicitly if needed, this seems more useful than the [0,100] default range

    def wheelEvent(self, event):
        event.ignore()

    def stepBy(self, step):
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
    def __init__(self, parent=None):
        super(QLabviewIndicatorDoubleSpinBox, self).__init__(parent)
        self.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.setRange(-np.inf,np.inf)
        self.setReadOnly(True)

    def wheelEvent(self, event):
        event.ignore()

############################ Third Party Widgets ##################################################

class ImageWidget(QLabel):
    """QLabel that keeps aspect ratio
    https://stackoverflow.com/questions/68484199/keep-aspect-ratio-of-image-in-a-qlabel-whilst-resizing-window"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScaledContents(False)
        self.setMinimumSize(1, 1)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.installEventFilter(self)
        self.raw_pixMap = None

    def setRawPixmap(self, a0):
        self.raw_pixMap = a0
        self.setPixmap(self.raw_pixMap.scaled(self.width(), self.height(), Qt.KeepAspectRatio))

    def eventFilter(self, widget, event):
        if event.type() == QEvent.Resize and widget is self and self.raw_pixMap is not None:
            self.setPixmap(self.raw_pixMap.scaled(self.width(), self.height(), Qt.KeepAspectRatio))
            return True
        return super().eventFilter(widget, event)

class SvgWidget(QtSvg.QSvgWidget):
    """https://discuss.python.org/t/pyqt5-qsvgwidget-preserve-aspect-ratio/6122
    revisit link after upgrade to PyQt5"""

    def __init__(self, parent=None):
        super().__init__(parent)
        #self.setScaledContents(False)
        # self.setMinimumSize(1, 1)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        #self.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        #self.installEventFilter(self)

    def paintEvent(self, _):
        renderer = self.renderer()
        if renderer is not None:
            painter = QPainter(self)
            size = renderer.defaultSize()
            ratio = size.height()/size.width()
            length = min(self.width(), self.height())
            renderer.render(painter, QRectF(0, 0, length, ratio * length))
            painter.end()

###################################################################################################
