"""Functions in this file will generally require direct access to UI elements as well as data structures.
Note this will be imported in ES_IBD_Explorer so that it is equivalent to defining the methods there directly.
This allows to keep the bare UI initialization separated from the more meaningful methods."""

import subprocess
import time
from pathlib import Path
import configparser
from datetime import datetime
import matplotlib
import matplotlib.dates as mdates
import keyboard as kb
import pyperclip
import numpy as np
import h5py
from Bio.PDB import PDBParser
from scipy.stats import binned_statistic
from scipy import optimize, interpolate
from matplotlib.backend_bases import MouseButton
import pyqtgraph as pg
from PyQt5.QtWidgets import (QApplication, QFileDialog, QTreeWidgetItem,QTreeWidgetItemIterator, QGridLayout,
                            QLabel, QHeaderView, QDialog, QVBoxLayout, QInputDialog, QMenu, QWidget, QSizePolicy, QScrollBar)
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtCore import QUrl, QObject, pyqtSignal, pyqtSlot
import ES_IBD_configuration as conf
from ES_IBD_controls import VoltageConfigItem
import ES_IBD_management as management

#################################### General UI Functions #########################################
class func_mixin: # use_mixin in name to avoid linter warnings
    """Mixin allows to extend ES_IBDWindow while keeping content organized in separate file
    http://www.qtrac.eu/pyclassmulti.html
    """

    def displayContent(self):
        """General wrapper for handling of files with different format.
        If a format related to ES-IBD is detected (including backwards compatible formats) the data will be loaded and shown in the corresponding view.
        Handling for a few general formats is implemented as well.
        For text based formats the text is also shown in the Text tab for quick access if needed.
        The actual handling is redirected to dedicated methods."""
        self.textTextBrowser.clear()
        if any(self.activeFile.endswith(txtType) for txtType in ['.txt','.dat','.ter','.cur','.tt','.star','.pdb1','.css','.js','.py','.html','.tex','.ini','.bat']):
            with open(self.activeFileFullPath,encoding=conf.UTF8) as f:
                self.textTextBrowser.insertPlainText(f.read()) # always populate text box but only change to tab if no other display method is available
        elif any(self.activeFile.endswith(imgType) for imgType in ['.hdf5','.h5']):
            with h5py.File(self.activeFileFullPath, 'r') as f:
                self.textTextBrowser.insertPlainText(self.hdfShow(f,0))
        else:
            self.textTextBrowser.insertPlainText('no handler implemented for this file type')
        self.textTextBrowser.verticalScrollBar().triggerAction(QScrollBar.SliderToMinimum)   # scroll to top
        if any(self.activeFile.endswith(imgType) for imgType in ['.txt']):
            first_line = ''
            with open(self.activeFileFullPath,encoding=conf.UTF8) as f:
                first_line = f.readline()
            self.linePlot(resize = True, tag = first_line.lower())
        elif any(self.activeFile.endswith(imgType) for imgType in ['.jpg','.jpeg','.png','.bmp','.gif']):
            self.displayTabWidget.setCurrentIndex(conf.indexImage)
            self.imgImageWidget.setRawPixmap(QPixmap(self.activeFileFullPath.as_posix()))
        elif any(self.activeFile.endswith(imgType) for imgType in ['.html']):
            self.displayTabWidget.setCurrentIndex(conf.indexHtml)
            self.webEngineView.load(QUrl.fromLocalFile(self.activeFileFullPath.as_posix()))
        elif any(self.activeFile.endswith(imgType) for imgType in ['.pdf']):
            self.displayTabWidget.setCurrentIndex(conf.indexHtml)
            self.webEngineView.load(QUrl.fromUserInput(f'{self.PDFJS}?file=file:///{self.activeFileFullPath.as_posix()}'))
            # self.webEngineView.load(QUrl.fromUserInput(f'file:///{self.activeFileFullPath.as_posix()}')) # using internal chromium gives some bugs and limited menu bar
            # self.webEngineView.show()
        elif any(self.activeFile.endswith(imgType) for imgType in [conf.FILE_S2D]):
            self.displayTabWidget.setCurrentIndex(conf.indexS2D)
            self.s2dScanPlot(self.s2dMgr.hdfLoadS2dData(self.activeFileFullPath), filepath = self.activeFileFullPath,done=True)
        elif any(self.activeFile.endswith(imgType) for imgType in ['S2D.dat']):
            self.displayTabWidget.setCurrentIndex(conf.indexS2D)
            self.s2dScanPlot([management.S2dScanData( current = np.flip(np.loadtxt(self.activeFileFullPath.as_posix()),1),name = '')], filepath = self.activeFileFullPath,done=True)
        elif self.activeFile.endswith(conf.FILE_SE): # Energy scan
            self.displayTabWidget.setCurrentIndex(conf.indexSE)
            self.seScanPlot(currents = self.seMgr.hdfLoadSeData(self.activeFileFullPath), filepath = self.activeFileFullPath,done=True)
        elif self.activeFile.endswith('swp.dat'): # Energy scan
            self.displayTabWidget.setCurrentIndex(conf.indexSE)
            self.seScanPlotLegacy()
        elif self.activeFile.endswith(conf.FILE_CUR): # Energy scan
            self.plotCurrentData()
        elif self.activeFile.endswith('.svg'):
            self.displayTabWidget.setCurrentIndex(conf.indexVector)
            self.svgWidget.load(self.activeFileFullPath.as_posix())
        elif self.activeFile.endswith('.pdb1'):
            self.displayTabWidget.setCurrentIndex(conf.indexPdb)
            self.pdbPlot(self.pdbFig.axes[0],self.activeFileFullPath)
            self.pdbCanvas.draw_idle()
            self.pdbFig.tight_layout()
        else:
            self.displayTabWidget.setCurrentIndex(conf.indexText)

    def initExplorerContextMenu(self, pos):
        """Context menu for items in Explorer"""
        self.explorerContextMenu = QMenu(self.rootTreeWidget)
        item = self.rootTreeWidget.itemAt(pos)
        openDirAction = None
        opencontainingDirAction = None
        openFileAction = None
        copyFileNameAction = None
        loadSettingsAction = None
        if item is self.up_itm:
            pass # no context menu
        elif self.getItemFullPath(item).is_dir():
            openDirAction = self.explorerContextMenu.addAction('Open Folder in Explorer')
        else:
            opencontainingDirAction = self.explorerContextMenu.addAction('Open Containing Folder in Explorer')
            openFileAction = self.explorerContextMenu.addAction('Open in External Program')
            copyFileNameAction = self.explorerContextMenu.addAction('Copy File Name to Clipboard')
            if self.activeFile.endswith(conf.FILE_SE):
                loadSettingsAction = self.explorerContextMenu.addAction(conf.LOAD_SE)
            elif self.activeFile.endswith(conf.FILE_S2D):
                loadSettingsAction = self.explorerContextMenu.addAction(conf.LOAD_S2D)
            elif self.activeFile.endswith(conf.FILE_INI):
                confParser = configparser.ConfigParser()
                try:
                    confParser.read(self.activeFileFullPath)
                    fileType = confParser[conf.VERSION][conf.TOOLTIP]
                except KeyError:
                    self.esibdWindow.esibdPrint(f'Could not identify file type of {self.activeFile}')
                if fileType == conf.GENERALSETTINGS:
                    loadSettingsAction = self.explorerContextMenu.addAction(conf.LOAD_GS)
                elif fileType == conf.VOLTAGE:
                    loadSettingsAction = self.explorerContextMenu.addAction(conf.LOAD_VOLTAGE)
                elif fileType == conf.CURRENT:
                    loadSettingsAction = self.explorerContextMenu.addAction(conf.LOAD_CURRENT)

        explorerContextMenuAction = self.explorerContextMenu.exec_(self.rootTreeWidget.mapToGlobal(pos))
        if explorerContextMenuAction is not None:
            if explorerContextMenuAction is opencontainingDirAction:
                subprocess.Popen(f'explorer {self.activeFileFullPath.parent}')
            elif explorerContextMenuAction == openDirAction:
                subprocess.Popen(f'explorer {self.getItemFullPath(item)}')
            elif explorerContextMenuAction == openFileAction:
                subprocess.Popen(f'explorer {self.activeFileFullPath}')
            elif explorerContextMenuAction == copyFileNameAction:
                pyperclip.copy(self.activeFileFullPath.name)
            elif explorerContextMenuAction == loadSettingsAction:
                if loadSettingsAction.text()  == conf.LOAD_SE:
                    self.seMgr.load(self.activeFileFullPath)
                elif loadSettingsAction.text()  == conf.LOAD_S2D:
                    self.s2dMgr.load(self.activeFileFullPath)
                elif loadSettingsAction.text()  == conf.LOAD_GS:
                    self.settingsMgr.load(self.activeFileFullPath)
                elif loadSettingsAction.text()  == conf.LOAD_VOLTAGE:
                    self.voltageConfig.load(self.activeFileFullPath)
                elif loadSettingsAction.text()  == conf.LOAD_CURRENT:
                    self.currentConfig.load(self.activeFileFullPath)

    def initSettingsContextMenu(self, mgr, pos):
        try:
            setting = mgr[mgr.tree.itemAt(pos).fullName]
            self.initSettingsContextMenuBase(setting, mgr.tree.mapToGlobal(pos))
        except KeyError as e: # setting could not be identified
            self.esibdPrint(e)

    def initSettingsContextMenuBase(self, setting, pos):
        """General implementation of context a menu.
        The relevent actions will be chosen based on the type and properties of the setting."""
        settingsContextMenu = QMenu(self.settingsTreeWidget)
        oldValue=setting.value
        if setting.name == conf.SESSIONPATH: # items with no option
            return
        changePathAction = None
        addItemAction = None
        editItemAction = None
        removeItemAction = None
        if setting.name in [conf.DATAPATH, conf.CONFIGPATH]:
            changePathAction = settingsContextMenu.addAction(conf.SELECTPATH)
        elif setting.widget == conf.WIDGETCOMBO:
            addItemAction = settingsContextMenu.addAction(conf.ADDITEM)
            editItemAction = settingsContextMenu.addAction(conf.EDITITEM)
            removeItemAction = settingsContextMenu.addAction(conf.REMOVEITEM)
        setToDefaultAction = settingsContextMenu.addAction(f'Set to Default: {setting.default}')
        makeDefaultAction = settingsContextMenu.addAction('Make Default')
        settingsContextMenuAction = settingsContextMenu.exec_(pos)
        if settingsContextMenuAction is not None: # no option selected (NOTE: if it is None this could trigger a non initialized action which is also None if not tested here)
            if settingsContextMenuAction is setToDefaultAction:
                setting.setToDefault()
            if settingsContextMenuAction is makeDefaultAction:
                setting.makeDefault()
            elif settingsContextMenuAction is changePathAction:
                startPath = Path(self.settingsMgr[conf.DATAPATH].value if setting.name == conf.DATAPATH else self.settingsMgr[conf.CONFIGPATH].value)
                newPath = Path(QFileDialog.getExistingDirectory(self,conf.SELECTPATH,startPath.as_posix(),QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks))
                if newPath != Path('.'): # directory has been selected successfully
                    setting.value = newPath
                    if setting.name == conf.DATAPATH:
                        self.settingsMgr.updateSessionPath()
            elif settingsContextMenuAction is addItemAction:
                text, ok = QInputDialog.getText(self, conf.ADDITEM, conf.ADDITEM)
                if ok and text != '':
                    setting.addItem(text)
            elif settingsContextMenuAction is editItemAction:
                text, ok = QInputDialog.getText(self, conf.EDITITEM, conf.EDITITEM, text = setting.value)
                if ok and text != '':
                    setting.editCurrentItem(text)
            elif settingsContextMenuAction is removeItemAction:
                setting.removeCurrentItem()
            if setting.value != oldValue:
                if setting.name == conf.DATAPATH:
                    self.updateRoot(Path(setting.value))
                elif setting.name == conf.CONFIGPATH:
                    self.settingsMgr.load(conf.settingsFile(self.qSet))

    def treeItemDoubleClicked(self, item, _):
        if item is self.up_itm:
            self.updateRoot(Path(self.root).parent.resolve())
        elif self.getItemFullPath(item).is_dir(): # isdir is true for '..'
            self.updateRoot(self.getItemFullPath(item))
        else: # treeItemDoubleClicked
            subprocess.Popen(f'explorer {self.activeFileFullPath}')

    def rgb2gray(self, rgb):
        return np.dot(rgb[...,:3], [0.299, 0.587, 0.144])

    def getItemFullPath(self, item):
        out = item.text(0) # don't use self.activeFile as it breaks the recursion
        if item.parent():
            out = self.getItemFullPath(item.parent()) / out
        else:
            out = self.root / out
        return out

    def copyClipboard(self):
        i = self.displayTabWidget.currentIndex()
        if i == conf.indexLineQt: # match case statement will be available with python 3.10
            QApplication.clipboard().setPixmap(self.graphPlotWidget.grab())
        elif i == conf.indexLine:
            #self.lineFig.set_size_inches(8, 6, forward = True) # use dimensions as shown by user, may want to standardize later
            #self.lineCanvas.draw_idle()
            QApplication.clipboard().setPixmap(self.lineCanvas.grab())
        elif i == conf.indexS2D:
            QApplication.clipboard().setPixmap(self.s2dCanvas.grab())
        elif i == conf.indexSE:
            QApplication.clipboard().setPixmap(self.seCanvas.grab())
        else:
            pass # no content for clipboard implemented

    def dpiChanged(self):
        if not self.loading:
            self.lineFig.set_dpi(int(self.settingsMgr[conf.DPI].value))
            self.seFig.set_dpi(int(self.settingsMgr[conf.DPI].value))
            self.lineCanvas.resize(self.lineVerticalLayout.sizeHint())
            self.seCanvas.resize(self.seVerticalLayout.sizeHint()) # fix canvas size after DPI change
            # self.displayContent() # add content again to account for dpi dependent change (tight_layout) not working...

    def xChannelChanged(self):
        """Adjust user interface for given x axis, either time or specific voltage channel.
        If a voltage channel is selected, a slider will be displayed to control the voltage corresponding to the x axis of the graph."""
        if not self.loading:
            xChannel = self.voltageConfig.getSelectedChannel()
            if xChannel is not None:
                self.xSlider.setVisible(True)
                self.currentPlotWidget.setAxisItems({'bottom': pg.AxisItem('bottom')}) # , size=5
                self.currentPlotWidget.setLabel('bottom',f'<font size="5">{xChannel.name} Voltage (V)</font>') # has to be after setAxisItems
                self.currentPlotWidget.enableAutoRange(self.currentPlotWidget.getViewBox().XAxis,False)
                self.currentPlotWidget.setXRange(-1,0,padding=0) # bug: XRange is set from 0 to 1 if called with the same parameters -> calling with -1 0 to trigger update
                self.currentPlotWidget.setXRange(xChannel.min,xChannel.max,padding=0)
            else: # default to time
                self.xSlider.setVisible(False)
                self.currentPlotWidget.setAxisItems({'bottom': pg.DateAxisItem()}) # , size=5
                self.currentPlotWidget.setLabel('bottom','<font size="5">Time</font>') # has to be after setAxisItems
                self.currentPlotWidget.enableAutoRange(self.currentPlotWidget.getViewBox().XAxis,True)
            self.currentPlotWidget.getAxis('bottom').setTickFont(self.plotWidgetFont)
            if self.instMgr.acquiring:
                self.plotData()

    def updateX(self, value):
        xChannel = self.voltageConfig.getSelectedChannel()
        if xChannel is not None:
            xChannel.voltage = xChannel.min + value/self.xSlider.maximum()*(xChannel.max - xChannel.min) # map slider range onto voltage range

    @pyqtSlot()
    def resetScanButtons(self):
        self.seScanPushButton.setChecked(False)
        self.s2dScanPushButton.setChecked(False)

    def lineOnClick(self, event):
        if event.button == MouseButton.RIGHT: # reset m/z analysis
            self.mz = np.array([])
            self.intensity = np.array([])
            self.esibdPrint('Reset m/z analysis')
            self.update_mass_to_charge()
        elif event.button == MouseButton.LEFT and kb.is_pressed('ctrl'): # add new value and analyze m/z
            self.mz = np.append(self.mz,event.xdata)
            self.intensity = np.append(self.intensity,event.ydata)
            self.determine_mass_to_charge()

    def determine_mass_to_charge(self):
        """estimates charge states based on m/z values provided by user by minimizing standard deviation of absolute mass within a charge state series.
        Provides standard deviation for neightbouring series to allow for validation of the result."""
        if len(self.mz) > 1: # not enough information for analysis
            sort_indices = self.mz.argsort()
            self.mz = self.mz[sort_indices] # increasing m/z match decreasing charge states
            self.intensity = self.intensity[sort_indices]
            charges=np.arange(100) # for charge state up to 100
            testCount = len(charges)-len(self.mz)
            STD=np.zeros(testCount) # initialize standard deviation
            for i in np.arange(testCount):
                STD[i] = np.std(self.mz*np.flip(charges[i:i+len(self.mz)]))
            self.esibdPrint(f'm/z Analysis for {self.activeFile}:')
            self.esibdPrint(f"{'m/z':10}, {'charge':8}")
            c1 = STD.argmin()
            self.cs = np.flip(charges[c1:c1+len(self.mz)]) # charge states
            for m, c in zip(self.mz, self.cs):
                self.esibdPrint(f'{m:10.2f}, {c:8}')
            mass = np.average(self.mz*charges[c1-1:c1-1+len(self.mz)])
            self.esibdPrint(f'lower mass (Da): {mass:.2f}, std: {STD[c1-1]:.2f}')
            mass = np.average(self.mz*charges[c1:c1+len(self.mz)])
            self.esibdPrint(f'likely mass (Da): {mass:.2f}, std: {STD[c1]:.2f}')
            mass = np.average(self.mz*charges[c1+1:c1+1+len(self.mz)])
            self.esibdPrint(f'higher mass (Da): {mass:.2f}, std: {STD[c1+1]:.2f}')
            self.update_mass_to_charge()

    def update_mass_to_charge(self):
        for ann in [child for child in self.lineAx.get_children() if isinstance(child, matplotlib.text.Annotation)]:#[self.seAnnArrow,self.seAnnFile,self.seAnnFWHM]:
            ann.remove()
        self.labelPlot(self.lineAx, self.activeFile)
        if len(self.mz) > 1:
            for x, y, c in zip(self.mz,self.intensity,self.cs):
                self.lineAx.annotate(text = f'{c}',xy=(x,y),xycoords='data',ha='center')

    def updateRoot(self, newroot):
        self.saveNotes()
        self.root   = newroot
        self.notes  = self.root / conf.NOTESTXT
        self.currentDirLineEdit.setText(newroot.as_posix())
        self.populateTree()
        self.notesTextEdit.clear()
        if self.notes.exists(): # load and display notes if found
            with open(self.notes, encoding = conf.UTF8) as f:
                self.notesTextEdit.insertPlainText(f.read())
            self.notesTextEdit.verticalScrollBar().triggerAction(QScrollBar.SliderToMinimum)   # scroll to top
            self.displayTabWidget.setCurrentIndex(conf.indexNotes)

    def saveNotes(self):
        if self.notes is not None and self.notesTextEdit.toPlainText() != '':
            with open(self.notes,'w', encoding = conf.UTF8) as f:
                f.write(self.notesTextEdit.toPlainText())

    def populateTree(self):
        self.rootTreeWidget.clear()
        # add .. to move up one dir
        self.up_itm = QTreeWidgetItem(self.rootTreeWidget, ['..'])
        self.up_itm.setIcon(0, QIcon(conf.ICON_FOLDER))
        self.load_project_structure(self.root, self.rootTreeWidget, self.filterLineEdit.text()) # populate tree widget

    def goToCurrentSession(self):
        sessionpath = Path(self.settingsMgr[conf.SESSIONPATH].value)
        sessionpath.mkdir(parents=True, exist_ok=True) # create if not already existing
        self.updateRoot(sessionpath)

    def updateCurDirFromLineEdit(self):
        p = Path(self.currentDirLineEdit.text())
        if p.exists():
            self.updateRoot(p)
        else:
            self.esibdPrint(f'Could not find directory: {p}')

    def treeItemClicked(self, item):
        if item is not None and item is not self.up_itm and not self.getItemFullPath(item).is_dir():
            self.activeFile = item.text(0)
            self.activeFileFullPath = self.getItemFullPath(item)
            self.displayContent()
        # else:
            # item.setExpanded(not item.isExpanded()) # already implemented for double click

    def mainTabChanged(self,i):
        if i == conf.indexScan2D:
            self.displayTabWidget.setCurrentIndex(conf.indexS2D)
        elif i == conf.indexScanEnergy:
            self.displayTabWidget.setCurrentIndex(conf.indexSE)

    def aboutDialog(self):
        """Simple dialog displaying program purpose, version, and creations"""
        dlg = QDialog(self)
        dlg.setWindowTitle('About ES-IBD Control')
        lay = QGridLayout()
        lbl = QLabel(
        f"""<p>ES-IBD Control controls all aspects of an ES-IBD experiment, including ion beam guiding and steering, beam energy analysis, deposition control, and data analysis.<br>
        Current version: {conf.VERSION_MAYOR}.{conf.VERSION_MINOR}</p><br>
        Original implementation in LabView: raushi2000 <a href='"'mailto:stephan.rauschenbach@chem.ox.ac.uk'"'>stephan.rauschenbach@chem.ox.ac.uk</a><br>
        Current implementation in Python/PyQt: ioneater <a href='"'mailto:tim.esser@chem.ox.ac.uk'"'>tim.esser@chem.ox.ac.uk</a>
        """
        )
        lbl.setFixedWidth(450)
        lbl.setWordWrap(True)
        lay.addWidget(lbl)
        dlg.setLayout(lay)
        dlg.exec()

    def load_project_structure(self, startpath, tree, _filter, recursionDepth = 4):
        """from https://stackoverflow.com/questions/5144830/how-to-create-folder-view-in-pyqt-inside-main-window
        recursively maps the file structure into the internal explorer
        Note that recursion depth of 4 assures that session data can be accessed from the data path level by exoanding the tree.
        Recursion depth of more than 4 can lead to very long loading times"""
        if recursionDepth == 0: # limit depth to avoid indexing entire storage (can take minutes)
            return
        recursionDepth = recursionDepth - 1
        if startpath.is_dir():
            # List of directories only
            dirlist = [x for x in startpath.iterdir() if (startpath / x).is_dir() and not x.name.startswith('.')]
            # List of files only
            filelist = [x for x in startpath.iterdir() if not (startpath / x).is_dir() and not x.name.startswith('.')]
            for element in dirlist: # add all dirs first, then all files
                path_info = startpath / element
                parent_itm = QTreeWidgetItem(tree, [element.name])
                self.load_project_structure(path_info, parent_itm, _filter, recursionDepth)
                parent_itm.setIcon(0, QIcon(conf.ICON_FOLDER))
            for element in filelist:
                path_info = startpath / element
                # don't add files that do not match _filter
                if _filter == "" or _filter.lower() in element.name.lower():
                    parent_itm = QTreeWidgetItem(tree, [element.name])
                    parent_itm.setIcon(0, QIcon(conf.ICON_DOCUMENT))
        else:
            self.esibdPrint(f'{startpath} is not a valid directory')

    def expandTree(self, tree):
        # expand all categories
        it = QTreeWidgetItemIterator(tree, QTreeWidgetItemIterator.HasChildren)
        while it.value():
            it.value().setExpanded(True)
            it +=1
        # size to content
        tree.header().setSectionResizeMode(QHeaderView.ResizeToContents)

    def containerize(self,widget):
        # just hiding widget using setVisible(False) is not reliable due to bug https://bugreports.qt.io/browse/QTBUG-13522
        # use a wrapping container as a workaround https://stackoverflow.com/questions/71707347/how-to-keep-qwidgets-in-qtreewidget-hidden-during-resize?noredirect=1#comment126731693_71707347
        container = QWidget()
        containerLayout = QVBoxLayout(container)
        containerLayout.setContentsMargins(0, 0, 0, 0)
        widget.setSizePolicy(QSizePolicy(QSizePolicy.MinimumExpanding,
                                                 QSizePolicy.MinimumExpanding))
        containerLayout.addWidget(widget)
        return container

    def hdfShow(self,f, level):
        content=''
        for name, item in f.items():
            #print('   '*level,name)
            if isinstance(item, h5py.Group):
                content += f"{'   '*level}{name}\n"
                for at, v in item.attrs.items():
                    content += f"{'   '*(level+1)}{at}: {repr(v)}\n"
                    #print(f"{'   '*(level+1)}{at}: {v}")
                content += self.hdfShow(item,level+1)
            elif isinstance(item, h5py.Dataset):
                content += f"{'   '*level}{name} Dataset\n"
        return content

    #################################### Current Functions #########################################

    def initCurrent(self):
        self.currentConfig.init(self.sampleCurrentPushButton.isChecked()) # will start sampling when initialization is complete
        self.currentPlotWidget.clear()
        self.currentPlotWidget.addLegend() # before adding plots
        for d in self.currentConfig.devices: # getInitializedDevices() don't know yet which will be initialized -> create all
            d.currentPlotCurve = None

    def sampleCurrent(self):
        if self.sampleCurrentPushButton.isChecked():
            if not self.currentConfig.initialized:
                self.initCurrent()
            else:
                self.currentConfig.startSampling()
            self.instMgr.startAcquisition()
        else:
            self.currentConfig.stopSampling()
            self.instMgr.stopAcquisition()

    @pyqtSlot()
    def plotData(self):
        """Plots the enabled and initialized current channels in the main current plot
            The x axis is either time or a selected voltage channel"""
        xChannel = self.voltageConfig.getSelectedChannel()
        displaytime = self.instMgr.getTime(time.time() - int(self.settingsMgr[conf.DISPLAYTIME].value)*60)

        for device in self.currentConfig.getInitializedDevices():
            if device.currentPlotCurve is None:
                device.currentPlotCurve = self.currentPlotWidget.plot(pen=pg.mkPen((device.color), width=5), name = device.lens) # initialize empty plots
            if device.display:
                if xChannel is not None:
                    x = xChannel.getVoltages(displaytime)
                    y = device.getCurrents(subtractBackground = self.subtractBackgroundCurrentPushButton.isChecked())
                    length = min(x.shape[0],y.shape[0]) # plot minimal available history
                    mean, bin_edges, _ = binned_statistic(x[-length:], y[-length:] ,bins=abs(xChannel.max-xChannel.min)*2,range=(xChannel.min,xChannel.max))
                    device.currentPlotCurve.setData((bin_edges[:-1] + bin_edges[1:]) / 2, mean)
                else:
                    y = device.getCurrents(subtractBackground = self.subtractBackgroundCurrentPushButton.isChecked())
                    length = min(displaytime.shape[0],y.shape[0]) # plot minimal available history
                    device.currentPlotCurve.setData(displaytime[-length:],y[-length:])
            else:
                device.currentPlotCurve.clear()

    def hdfSaveCurrentData(self):
        self.settingsMgr[conf.MEASUREMENTNUMBER].value += 1
        with h5py.File(self.settingsMgr.getMeasurementFileName(conf.FILE_CUR), 'w', track_order = True) as f:
            self.settingsMgr.hdfAddSettingTemplate(f.create_group(conf.VERSION) ,f'{conf.VERSION_MAYOR}.{conf.VERSION_MINOR}', default=None, toolTip = conf.CURRENTDATA)
            f.create_dataset(conf.TIME, data=self.instMgr.time.get(), dtype=np.float64, track_order = True) # need double precision to keep all decimal places
            g = f.create_group(conf.CURRENT, track_order = True)
            for device in self.currentConfig.getInitializedDevices():
                g.create_dataset(device.lens, data=device.currents.get(), dtype='f')
                g.create_dataset(device.lens + '_BG', data=device.backgrounds.get(), dtype='f')
        self.voltageConfig.save(self.settingsMgr.getMeasurementFileName(conf.FILE_INI)) # save corresponding potentials
        self.populateTree()

    def plotCurrentData(self):
        """plotting current data from file"""
        self.lineAx.clear()
        self.lineAx.set_xlabel('Time')
        self.lineAx.set_ylabel('Current (pA)')
        self.labelPlot(self.lineAx, self.activeFile)
        with h5py.File(self.activeFileFullPath, 'r') as f:
            _time = f[conf.TIME][:]
            _time = [datetime.fromtimestamp(float(t)) for t in _time] # convert timestamp to datetime
            g = f[conf.CURRENT]
            for name, item in g.items():
                if '_BG' in name:
                    continue
                else:
                    BG = g[name + '_BG']
                #print(_time,item[:],_time.shape,item[:].shape)
                if self.subtractBackgroundCurrentPushButton.isChecked():
                    self.lineAx.plot(_time,item[:]-BG[:], label = name)
                else:
                    self.lineAx.plot(_time,item[:], label = name)
        self.lineAx.legend(loc = 'upper left')
        self.lineFig.tight_layout()
        self.lineCanvas.draw_idle()
        self.displayTabWidget.setCurrentIndex(conf.indexLine)


    #################################### Voltage Functions #########################################

    @pyqtSlot(VoltageConfigItem,float)
    def updateVoltage(self,channel,voltage): # used to update voltage from external threads
        channel.voltage = voltage

    def voltageON(self):
        if self.voltageConfig.voltageMgr.initialized:
            self.voltageConfig.voltageON(self.voltageOnPushButton.isChecked())
        else:
            self.voltageConfig.init(restart=True)

    #################################### General Plotting Functions ###############################

    def linePlot(self,resize=True, tag = ''):
        """plots all data that can be represented by a simple line plot"""
        # matplotlib
        self.lineAx.clear()
        # pyqt
        self.graphPlotWidget.clear()
        self.graphPlotWidget.addLegend() # call before creating curves

        if conf.SPECTRUM.lower() in tag.lower(): # mass spectrum
            x,y=np.loadtxt(self.activeFileFullPath,skiprows=10,usecols=[0,1],unpack=True)
            line, = self.lineAx.plot([np.min(x),np.max(x)],[np.min(y),np.max(y)])
            self.ddd = self.DataDisplayDownsampler(x,y,self.lineCanvas,line)
            self.lineAx.callbacks.connect('xlim_changed', self.ddd.update)
            self.lineAx.set_xlabel('m/z')
            self.lineAx.set_ylabel('Intensity')
            self.mz = np.array([]) # reset analyis
            self.intensity = np.array([])
            self.graphPlotWidget.setLabel('bottom','m/z')
            self.graphPlotWidget.setLabel('left','Intensity')
            self.graphPlotWidget.plot(x,y, name=self.activeFile)
        elif conf.PROFILE.lower() in tag.lower(): # AFM height profile
            profile=np.loadtxt(self.activeFileFullPath,skiprows=3)
            self.lineAx.plot(profile[:,0],profile[:,1])
            self.lineAx.set_xlabel('width (m)')
            self.lineAx.set_ylabel('height (m)')
            self.graphPlotWidget.setLabel('bottom','width (m)')
            self.graphPlotWidget.setLabel('left','height (m)')
            self.graphPlotWidget.plot(profile, name=self.activeFile)
        elif 'avg fit' in tag.lower(): # GA fitness curve
            datey = lambda x: datetime.strptime(x.decode(conf.UTF8),'%H:%M:%S')
            _time=np.loadtxt(self.activeFileFullPath,skiprows=1,dtype=datetime, usecols=(2),converters = {2: datey} , unpack = True)
            profile=np.loadtxt(self.activeFileFullPath,skiprows=1, usecols=(3,4), unpack = True)
            self.lineAx.plot(_time,profile[0],label = 'avg fitness')
            self.lineAx.plot(_time,profile[1],label = 'best fitness')
            self.lineAx.legend(loc = 'lower right')
            self.lineAx.set_xlabel('Time')
            self.lineAx.set_ylabel('Fitness Voltage (V)')
            # self.graphPlotWidget.setLabel('bottom','Time') # not supported
            # self.graphPlotWidget.setLabel('left','Fitness Voltage (V)')
            # self.graphPlotWidget.plot(profile, name=self.activeFile)
        else: # no handling implemented for this type of textfile
            self.displayTabWidget.setCurrentIndex(conf.indexText)
            return

        self.labelPlot(self.lineAx, self.activeFile)
        if resize:
            self.lineAx.autoscale(True)
            self.lineAx.relim()
            self.lineAx.autoscale_view(True,True,True)
        # else:
        #     lineAx.autoscale(True,axis='y')
        self.lineFig.tight_layout() # after rescaling!
        self.lineCanvas.draw_idle()
        self.lineToolbar.update() # reset history for zooming and home view
        self.lineCanvas.get_default_filename = lambda: self.activeFileFullPath.with_suffix('') # set up save file dialog

        self.graphPlotWidget.disableAutoRange()
        self.graphPlotWidget.enableAutoRange()
        self.displayTabWidget.setCurrentIndex(conf.indexLine)

    def voltagePlot(self):
        """plots all voltages from table"""
        self.lineAx.clear()
        y = [c.voltage for c in self.voltageConfig.channels if c.real]
        labels = [c.name for c in self.voltageConfig.channels if c.real]
        colors = [c.color.name() for c in self.voltageConfig.channels if c.real]
        x = np.arange(len(y))
        self.lineAx.scatter(x,y,marker='.',color = colors)
        self.lineAx.set_ylabel('Potential (V)')
        self.lineAx.set_xticks(x,labels,rotation=30,ha='right',rotation_mode='anchor')
        self.lineFig.tight_layout()
        self.lineCanvas.draw_idle()
        self.displayTabWidget.setCurrentIndex(conf.indexLine)


    def labelPlot(self, ax, label):
        ax.annotate(text = label,xy=(.98,.98),fontsize=8,
            xycoords='axes fraction', textcoords='axes fraction',ha='right',va='top',bbox=dict(boxstyle='square,pad=.2', fc='w', ec='none'),clip_on=True)

    class DataDisplayDownsampler:
        """A class that will downsample the data and recompute when zoomed.
        based on https://matplotlib.org/3.5.0/gallery/event_handling/resample.html
        """
        def __init__(self, xdata, ydata, canvas, line):
            self.origYData = ydata
            self.origXData = xdata
            self.max_points = 2000
            self.delta = xdata[-1] - xdata[0]
            self.canvas = canvas
            self.line = line

        def downsample(self, xstart, xend):
            # get the points in the view range
            mask = (self.origXData > xstart) & (self.origXData < xend)
            # dilate the mask by one to catch the points just outside
            # of the view range to not truncate the line
            mask = np.convolve([1, 1, 1], mask, mode='same').astype(bool)
            # sort out how many points to drop
            ratio = max(np.sum(mask) // self.max_points, 1)

            # mask data
            xdata = self.origXData[mask]
            ydata = self.origYData[mask]

            # downsample data
            xdata = xdata[::ratio]
            ydata = ydata[::ratio]

            # print(f'using {len(ydata)} of {np.sum(mask)} visible points')

            return xdata, ydata

        def update(self, ax):
            # Update the line
            # print('updateing line')
            lims = ax.viewLim
            if abs(lims.width - self.delta) > 1e-8:
                self.delta = lims.width
                xstart, xend = lims.intervalx
                self.line.set_data(*self.downsample(xstart, xend))
                self.canvas.draw_idle()

    #################################### Energy Scan Functions ####################################

    def seScanToogle(self):
        if self.instMgr.acquiring:
            if self.seScanPushButton.isChecked():
                self.seFit.set_data([],[]) #  reset graph
                self.displayTabWidget.setCurrentIndex(conf.indexSE)
                self.seScan = management.SeScan(self)
                self.seScan.start()
            else:
                if self.seScan:
                    self.seScan.acquiring = False
        else:
            self.esibdPrint(f'{conf.NOTE_NOT_ACQUIRING} Cannot start energy scan.')
            self.seScanPushButton.setChecked(False)

    @pyqtSlot(bool)
    def seScanUpdate(self,done=False):
        self.seScanPlot(self.seScan.currents,self.seScan.filename,done)
        if done and len(self.seScan.currents) > 0: # save data
            self.seMgr.save(self.seScan.filename) # save settings
            self.seMgr.hdfAddSeData(self.seScan) # save data to same file
            self.voltageConfig.save(self.settingsMgr.getMeasurementFileName(conf.FILE_INI)) # save corresponding potentials
            self.populateTree()

    def seScanPlotLegacy(self):
        with open(self.activeFileFullPath,'r',encoding = conf.UTF8) as f:
            for i, line in enumerate(f):
                if i == 1:
                    line = (line.replace('S_Exit_Lens','S-Exit')
                    .replace('Sample_Cente','RT_Sample-Center')
                    .replace('SC','RT_Sample-Center')
                    .replace('Sample_End','RT_Sample-End')
                    .replace('SE','RT_Sample-End')
                    .replace('Detector','RT_Detector')
                    .replace('Front_Plate','RT_Front-Plate')
                    .replace('FrontPlate','RT_Front-Plate'))
                    headers = line.split(',')[1:][::2]
        data = np.loadtxt(self.activeFileFullPath,skiprows=4,delimiter=',',unpack=True)
        self.seScanPlot(currents = [management.SeScanData(current = dat, voltage = data[0], name = head.strip()) for head, dat in zip(headers,data[1:][::2])]
                                    , filepath = self.activeFileFullPath,done=True)

    def seScanPlot(self,currents,filepath,done=False):
        """Plots energy scan data including metadata"""
        # use first that matches display setting, use first availible if not found
        displaycurrent = next((c for c in currents if self.seMgr[conf.SE_DISPLAY].value.strip().lower() in c.name.strip().lower()),currents[0])
        ax1 = self.seFig.axes[0]
        ax2 = self.seFig.axes[1]
        ax1.set_ylabel(f'{displaycurrent.name} Current (pA)')
        ax1.set_xlabel(f'{displaycurrent.md.channel} Voltage (V)')
        self.seRaw.set_data(displaycurrent.voltage,displaycurrent.current)
        #(f'{displaycurrent.name} from {filename}')
        y = np.diff(displaycurrent.current)/np.diff(displaycurrent.voltage)
        x = displaycurrent.voltage[:y.shape[0]]+np.diff(displaycurrent.voltage)[0]/2 # use as many data points as needed
        self.seGrad.set_data(x,self.map_percent(-y))
        for ann in [child for child in ax2.get_children() if isinstance(child, matplotlib.text.Annotation)]:#[self.seAnnArrow,self.seAnnFile,self.seAnnFWHM]:
            #if ann is not None:
            ann.remove()
        self.labelPlot(ax2, filepath.name)
        if done:
            try:
                x_fit,y_fit,u,fwhm = self.gaus_fit(x,y,np.mean(x)) # use center as starting guess
                self.seFit.set_data(x_fit,self.map_percent(y_fit))
                self.seAnnArrow = ax2.annotate(text='',xy=(u-fwhm/2.3,50), xycoords='data',xytext=(u+fwhm/2.3,50),textcoords='data',
            	    arrowprops=dict(arrowstyle="<->",color=conf.MYRED),va='center')
                self.seAnnFWHM = ax2.annotate(text=f'center: {u:2.1f} V\nFWHM: {fwhm:2.1f} V',xy=(u-fwhm/1.6,50), xycoords='data',fontsize=10.0,
                    textcoords='data',ha='right',va='center',color=conf.MYRED)
                ax2.set_xlim([u-3*fwhm,u+3*fwhm])
            except RuntimeError as e:
                self.esibdPrint(f'Fit failed with error: {e}')
        ax1.autoscale(True)
        ax1.relim()
        ax2.autoscale(True,axis='x')
        ax2.relim()
        ax1.autoscale_view(True,True,True)
        ax2.autoscale_view(True,True,True)
        self.seFig.tight_layout() # after rescaling!
        self.seCanvas.draw_idle() # Trigger the canvas to update and redraw. / .draw() not working for some reason https://stackoverflow.com/questions/32698501/fast-redrawing-with-pyqt-and-matplotlib
        self.seToolbar.update()
        self.seCanvas.get_default_filename = lambda: filepath.with_suffix('') # set up save file dialog

    def updateSeContent(self): # change display channel
        if self.activeFile is not None and conf.FILE_SE in self.activeFile:
            self.displayContent()

    #################################### 2D Scan Functions #########################################

    def s2dScanToogle(self):
        if self.instMgr.acquiring:
            if self.s2dScanPushButton.isChecked():
                self.displayTabWidget.setCurrentIndex(conf.indexS2D)
                self.s2dScan = management.S2dScan(self)
                self.s2dScan.start()
            else:
                if self.s2dScan:
                    self.s2dScan.acquiring = False
        else:
            self.esibdPrint(f'{conf.NOTE_NOT_ACQUIRING} Cannot start 2D scan.')
            self.s2dScanPushButton.setChecked(False)

    @pyqtSlot(bool)
    def s2dScanUpdate(self,done=False):
        self.s2dScanPlot(self.s2dScan.currents, filepath = self.s2dScan.filename, done = done)
        if done and len(self.s2dScan.currents) > 0: # save data
            self.s2dMgr.save(self.s2dScan.filename) # save settings
            self.s2dMgr.hdfAddS2dData(self.s2dScan)
            self.voltageConfig.save(self.settingsMgr.getMeasurementFileName(conf.FILE_INI)) # save corresponding potentials
            self.populateTree() # refresh to show new file

    def s2dScanPlot(self,currents,filepath,done=False):
        """Plots 2D scan data including metadata"""
        # use first that matches display setting, use first availible if not found
        displaycurrent = next((c for c in currents if self.s2dMgr[conf.S2D_DISPLAY].value.strip().lower() in c.name.strip().lower()),currents[0])
        # pyqt
        self.s2dImv.setImage(displaycurrent.current)
        # matplotlib
        ax = self.s2dFig.axes[0]
        ax.clear() # only update would be preferred but not yet possible with contourf
        if self.s2dCbar is not None:
            self.s2dCbar.remove()
        if self.s2dAnn is not None:
            self.s2dAnn.remove()
        ax.set_xlabel(f'{displaycurrent.md.LR_channel} Voltage (V)')
        ax.set_ylabel(f'{displaycurrent.md.UD_channel} Voltage (V)')
        x, y =  displaycurrent.md.getMgrid() # data coordinates
        if done:
            rbf = interpolate.Rbf(x.ravel(), y.ravel(), displaycurrent.current.ravel())
            xi, yi = displaycurrent.md.getMgrid(2) # interpolation coordinates
            zi = rbf(xi, yi)
            self.s2dCont = ax.contourf(xi, yi, zi, levels=100, cmap = 'afmhot') # contour without interpolation
        else:
            self.s2dCont = ax.pcolormesh(x, y, displaycurrent.current, cmap = 'afmhot')
        # self.s2dScat = ax.scatter(x, y, c=data, marker='x') # , fc='none', ,ec='k'
        self.s2dCbar = self.s2dFig.colorbar(self.s2dCont, ax=ax)
        self.labelPlot(ax, f'{displaycurrent.name} from {filepath.name}')
        self.s2dCanvas.draw_idle()
        self.s2dFig.tight_layout()

    def updateS2dContent(self): # change display channel
        if self.activeFile is not None and conf.FILE_S2D in self.activeFile:
            self.displayContent()

    def s2dLimits(self):
        ax = self.s2dFig.axes[0]
        self.s2dMgr[conf.S2D_LR_FROM].value = ax.get_xlim()[0]
        self.s2dMgr[conf.S2D_LR_TO].value = ax.get_xlim()[1]
        self.s2dMgr[conf.S2D_UD_FROM].value = ax.get_ylim()[0]
        self.s2dMgr[conf.S2D_UD_TO].value = ax.get_ylim()[1]

    def s2dMouseEvent(self,event):  # use mouse to move beam # use ctrl key to avoid this while zoomiong
        if self.mouseMoving and not event.name == 'button_release_event': # dont trigger events until last one has been processed
            return
        else:
            self.mouseMoving = True
            if event.button == MouseButton.LEFT and kb.is_pressed('ctrl') and event.xdata is not None:
                LR_channel = self.voltageConfig.getChannelbyName(self.s2dMgr[conf.S2D_LR_CHANNEL].value)
                UD_channel = self.voltageConfig.getChannelbyName(self.s2dMgr[conf.S2D_UD_CHANNEL].value)
                if LR_channel is not None and UD_channel is not None:
                    LR_channel.voltage = event.xdata
                    UD_channel.voltage = event.ydata
                else:
                    self.esibdPrint('Could not find channel {self.s2dMgr[conf.S2D_LR_CHANNEL].value} or {self.s2dMgr[conf.S2D_UD_CHANNEL].value}')
            self.mouseMoving = False

    #################################### Genetic Algorith (GA) ####################################

    def toogleGA(self):
        if self.instMgr.acquiring:
            if self.optimizeVoltagePushButton.isChecked():
                self.ga = management.GAManager(self)
                self.ga.start()
            else:
                if self.ga:
                    self.ga.optimizing = False
        else:
            self.esibdPrint(f'{conf.NOTE_NOT_ACQUIRING} Cannot start optimization')
            self.optimizeVoltagePushButton.setChecked(False)

    def gaUpdate(self):
        self.voltageConfig.save(self.settingsMgr.getMeasurementFileName(conf.FILE_INI)) # save corresponding potentials




    #################################### Other Functions ##############################################
    ## Consider moving this to separate module if this section grows to more than a few hundred lines of code.
    ###################################################################################################

    def map_percent(self, x):
        # can't map if largest deviation from minimum is 0, i.e. all zero
        return (x-np.min(x))/np.max(x-np.min(x))*100 if np.max(x-np.min(x) > 0) else 0

    def gaussian(self, x, amp1,cen1,sigma1):
        return amp1*(1/(sigma1*(np.sqrt(2*np.pi))))*(np.exp(-((x-cen1)**2)/(2*(sigma1)**2)))

    def gaus_fit(self,x,y,c):
        # Define a gaussian to start with
        amp1 = 100
        sigma1 = 2
        gauss, _ = optimize.curve_fit(self.gaussian, x, y, p0=[amp1, c, sigma1])
        fwhm = round(2.355 * gauss[2], 1) # Calculate FWHM
        x_fine=np.arange(np.min(x), np.max(x),0.05)
        return x_fine,-self.gaussian(x_fine,gauss[0], gauss[1],gauss[2]),gauss[1],fwhm

    def get_structure(self,pdb_file): # read PDB file
        structure = PDBParser(QUIET=True).get_structure('', pdb_file)
        XYZ=np.array([atom.get_coord() for atom in structure.get_atoms()])
        return structure, XYZ, XYZ[:,0], XYZ[:,1], XYZ[:,2]

    def pdbPlot(self,ax,file):
        ax.clear()
        _, _, x, y, z = self.get_structure(file)
        ax.scatter(x, y, z, marker='.', s=1)
        self.set_axes_equal(ax)
        ax.set_autoscale_on(True)
        ax.relim()

    def set_axes_equal(self,ax):
        '''Make axes of 3D plot have equal scale so that spheres appear as spheres,
        cubes as cubes, etc..  This is one possible solution to Matplotlib's
        ax.set_aspect('equal') and ax.axis('equal') not working for 3D.
        Input
          ax: a matplotlib axis, e.g., as output from plt.gca().
        '''
        x_limits = ax.get_xlim3d()
        y_limits = ax.get_ylim3d()
        z_limits = ax.get_zlim3d()
        x_range = abs(x_limits[1] - x_limits[0])
        x_middle = np.mean(x_limits)
        y_range = abs(y_limits[1] - y_limits[0])
        y_middle = np.mean(y_limits)
        z_range = abs(z_limits[1] - z_limits[0])
        z_middle = np.mean(z_limits)
        # The plot bounding box is a sphere in the sense of the infinity
        # norm, hence I call half the max range the plot radius.
        plot_radius = 0.5*max([x_range, y_range, z_range])
        ax.set_xlim3d([x_middle - plot_radius, x_middle + plot_radius])
        ax.set_ylim3d([y_middle - plot_radius, y_middle + plot_radius])
        ax.set_zlim3d([z_middle - plot_radius, z_middle + plot_radius])

    # from https://stackoverflow.com/questions/12090503/listing-available-com-ports-with-python
    # this slows down program start too much -> skip this test and see which ports connect or give an error
    def serial_ports(self):
        """ Lists serial port names
            :raises EnvironmentError:
                On unsupported or unknown platforms
            :returns:
                A list of the serial ports available on the system
        """
        # ports = ['COM%s' % (i + 1) for i in range(20)] # need to increase if ever using more than 20 com ports
        # result = []
        # for port in ports:
            # try:
                # s = serial.Serial(port)
                # s.close()
                # result.append(port)
            # except (OSError, serial.SerialException):
                # pass
        # return result
        return [f'COM{x}' for x in range(3,25)] # need to increase maximum COM port if needed

    class dynamicNp():
        """ based on https://stackoverflow.com/questions/7133885/fastest-way-to-grow-a-numpy-numeric-array
        This is an incrementally expanded numpy array that prevents frequent memory allocation while growing.
        """
        def __init__(self, max_size = None):
            self.data = np.zeros((100,))
            self.capacity = 100
            self.size = 0
            self.max_size = max_size

        def add(self, x):
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

    class SignalCommunicate(QObject): # signals that can be emitted by external threads
        appendDataSignal        = pyqtSignal(float)
        plotDataSignal          = pyqtSignal()
        updateVoltageSignal     = pyqtSignal(VoltageConfigItem,float)
        seScanUpdateSignal      = pyqtSignal(bool)
        s2dScanUpdateSignal     = pyqtSignal(bool)
        gaUpdateSignal          = pyqtSignal()
        printFromThreadSignal   = pyqtSignal(str)
        resetScanButtonsSignal  = pyqtSignal()
        
        