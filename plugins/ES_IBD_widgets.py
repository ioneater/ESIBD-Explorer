"""Functions in this file will generally require direct access to UI elements as well as data structures.
Note this will be imported in ES_IBD_Explorer so that it is equivalent to defining the methods there directly.
This allows to keep the bare UI initialization separated from the more meaningful methods."""

import subprocess
from pathlib import Path
import configparser
from itertools import islice
import ast
from send2trash import send2trash
import keyboard as kb
import pyperclip
import numpy as np
import h5py
import matplotlib.pyplot as plt
import matplotlib
from matplotlib.backend_bases import MouseButton
from Bio.PDB import PDBParser
from PyQt6.QtWebEngineCore import QWebEngineSettings,QWebEnginePage
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (QTreeWidgetItem,QTreeWidgetItemIterator,QTextBrowser,QLineEdit,
                            QLabel,QMenu,QSizePolicy,QScrollBar,QPlainTextEdit,QTreeWidget,QToolBar,QFileDialog)
from PyQt6.QtGui import QIcon,QPixmap,QFont,QKeySequence,QShortcut
from PyQt6.QtCore import QUrl,Qt,QEvent,QSize,QLoggingCategory
import ES_IBD_core as core
from ES_IBD_core import ESIBD_Parameter,ESIBD_GUI,INOUT

#################################### General UI Classes #########################################


def initialize(esibdWindow):
    esibdWindow.addGUIWidget(esibdWindow.displayTabWidget,ESIBD_WEB_GUI())
    esibdWindow.addGUIWidget(esibdWindow.displayTabWidget,ESIBD_MS_GUI())
    esibdWindow.addGUIWidget(esibdWindow.displayTabWidget,ESIBD_IMAGE_GUI())
    esibdWindow.lineWidget = esibdWindow.addGUIWidget(esibdWindow.displayTabWidget,ESIBD_LINE_GUI())
    esibdWindow.addGUIWidget(esibdWindow.displayTabWidget,ESIBD_PDB_GUI())
    esibdWindow.addGUIWidget(esibdWindow.displayTabWidget,ESIBD_TREE_GUI())
    esibdWindow.textWidget = esibdWindow.addGUIWidget(esibdWindow.displayTabWidget,ESIBD_TEXT_GUI())
    esibdWindow.notesWidget = esibdWindow.addGUIWidget(esibdWindow.displayTabWidget,ESIBD_NOTES_GUI())
    esibdWindow.explorerWidget = esibdWindow.addGUIWidget(esibdWindow.mainTabWidget,ESIBD_EXPLORER_GUI(esibdWindow = esibdWindow))

class ESIBD_WEB_GUI(ESIBD_GUI):
    """Displays various file types using QWebEngineView"""

    ICON_MANUAL = 'media/address-book-open.png'
    ICON_ABOUT = 'media/book-question.png'
    ICON_BACK = 'media/arrow-180.png'
    ICON_FORWARD = 'media/arrow.png'
    ICON_RELOAD = 'media/arrow-circle-315.png'
    ICON_STOP = 'media/cross.png'

    def __init__(self):
        super().__init__(name = 'Browser')
        web_engine_context_log = QLoggingCategory("qt.webenginecontext")
        web_engine_context_log.setFilterRules("*.info=false")
        self.webEngineView = QWebEngineView()
        self.addContentWidget(self.webEngineView)
        self.suffixes.extend(['.pdf','.html','.svg'])
        self.file = None
        self.webEngineView.settings().setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled,True)
        # self.webEngineView.settings().setAttribute(QWebEngineSettings.WebAttribute.,True)
        self.webEngineView.setUrl(QUrl('https://rauschenbach.chem.ox.ac.uk/'))
        self.webEngineView.loadFinished.connect(self.adjustLocation)

        self.locationEdit = QLineEdit()
        self.locationEdit.setSizePolicy(QSizePolicy.Policy.Expanding, self.locationEdit.sizePolicy().verticalPolicy())
        self.locationEdit.returnPressed.connect(self.loadUrl)
        self.toolBar = QToolBar()
        self.toolBar.setIconSize(QSize(16,16)) # match size of other toolbar elements
        page = self.webEngineView.pageAction(QWebEnginePage.WebAction.Back)
        page.setIcon(QIcon(self.ICON_BACK))
        self.toolBar.addAction(page)
        page = self.webEngineView.pageAction(QWebEnginePage.WebAction.Forward)
        page.setIcon(QIcon(self.ICON_FORWARD))
        self.toolBar.addAction(page)
        page = self.webEngineView.pageAction(QWebEnginePage.WebAction.Reload)
        page.setIcon(QIcon(self.ICON_RELOAD))
        self.toolBar.addAction(page)
        page = self.webEngineView.pageAction(QWebEnginePage.WebAction.Stop)
        page.setIcon(QIcon(self.ICON_STOP))
        self.toolBar.addAction(page)
        self.toolBar.addWidget(self.locationEdit)
        self.provideRow(0).insertWidget(0,self.toolBar, stretch=8)
        self.addButton(0,2,toolTip='Manual',func=self.openManual,icon=self.ICON_MANUAL)
        self.addButton(0,3,toolTip='About',func=self.openAbout,icon=self.ICON_ABOUT)

    def loadData(self,file):
        # overwrite parent
        if file.name.endswith('.html'):
            self.webEngineView.load(QUrl.fromLocalFile(file.as_posix()))
        elif file.name.endswith('.pdf'):
            self.webEngineView.setUrl(QUrl(f'file:///{file.as_posix()}'))
        elif file.name.endswith('.svg'):
            # self.webEngineView.setUrl(QUrl(f'file:///{file.as_posix()}')) # does not scale
            # does not work when using absolute path directly for src. also need to replace empty spaces to get valid url
            self.webEngineView.setHtml(f'<img src={file.name.replace(" ","%20")} width = "100%"/>',
                baseUrl=QUrl.fromLocalFile(file.as_posix().replace(" ","%20")))

    def loadUrl(self):
        self.webEngineView.load(QUrl.fromUserInput(self.locationEdit.text()))

    def adjustLocation(self):
        self.locationEdit.setText(self.webEngineView.url().toString().replace('%5C','/'))

    def openManual(self):
        self.webEngineView.setUrl(QUrl(f"file:///{Path('../manual/ES-IBD_Explorer_Manual.pdf').resolve().as_posix()}"))

    def openAbout(self):
        """Simple dialog displaying program purpose,version,and creations"""
        aboutFile = Path('media/about.html').resolve()
        with open(aboutFile,'w',encoding=self.UTF8) as f:
            f.write(f"""
        <h1>{core.PROGRAM_NAME}</h1>
        <p>{core.PROGRAM_NAME} controls all aspects of an ES-IBD experiment, including ion beam guiding and steering, beam energy analysis, deposition control, and data analysis.<br>
        Using the build-in plugin system, it can be extended to support additional hardware as well as custom controls for data aquisition, analysis, and visualization.<br>
        See the manual for more details.<br><br>
        Present version: {core.VERSION_MAYOR}.{core.VERSION_MINOR}<br>
        Github: <a href='https://github.com/ioneater/ES-IBD_Explorer'>https://github.com/ioneater/ES-IBD_Explorer</a><br>
        Rauschenbach Lab: <a href='https://rauschenbach.chem.ox.ac.uk/'>https://rauschenbach.chem.ox.ac.uk/</a><br>
        Present implementation in Python/PyQt: ioneater <a href='mailto:tim.esser@chem.ox.ac.uk'>tim.esser@chem.ox.ac.uk</a></p>
        Original implementation in LabView: raushi2000 <a href='mailto:stephan.rauschenbach@chem.ox.ac.uk'>stephan.rauschenbach@chem.ox.ac.uk</a><br>
        """)
        self.loadData(Path(aboutFile.as_posix()))

class ESIBD_MS_GUI(ESIBD_GUI):
    """Displays mass spectra and allows to determine charge states by marking peaks."""
    def __init__(self,**kwargs):
        super().__init__(name = 'MS',**kwargs)
        self.suffixes.extend(['.txt'])
        self.file = None
        self.fig=plt.figure(dpi=self.getDPI())
        self.canvas,self.toolbar = self.makeFigureCanvasWithToolbar(self,self.fig)
        self.canvas.mpl_connect('button_press_event',self.msOnClick)
        self.mz = np.array([]) # array with selected m/z values
        self.cs = None
        self.charges=np.array([]) # for charge state up to 100
        self.maxChargeState = 100 # maximal value for lowest charge state
        self.STD = np.array([]) # array with standard deviations for each charge state
        self.c1 = 0 # charge state of lowest m/z value
        self.intensity = np.array([]) # y value for selected m/z values (for plotting only)
        self.axes=[]
        self.axes.append(self.fig.add_subplot(111))
        self.fig.tight_layout()

    def supportsFile(self, file):
        if super().supportsFile(file):
            first_line = ''
            with open(file,encoding=self.UTF8) as f:
                first_line = f.readline()
            if 'spectrum' in first_line.lower(): # mass spectrum
                return True
        return False

    def loadData(self, file):
        self.file = file
        self.msPlot()

    def msOnClick(self,event):
        if event.button == MouseButton.RIGHT: # reset m/z analysis
            self.mz = np.array([])
            self.intensity = np.array([])
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
            self.charges=np.arange(self.maxChargeState+len(self.mz)) # for charge state up to self.maxChargeState
            self.STD=np.zeros(self.maxChargeState) # initialize standard deviation
            for i in np.arange(self.maxChargeState):
                self.STD[i] = np.std(self.mz*np.flip(self.charges[i:i+len(self.mz)]))
            self.c1 = self.STD.argmin()
            self.cs = np.flip(self.charges[self.c1:self.c1+len(self.mz)]) # charge states
            self.update_mass_to_charge()

    def mass_string(self,offset,label):
        return f'{label} mass (Da): {np.average(self.mz*self.charges[self.c1+offset:self.c1+offset+len(self.mz)]):.2f}, std: {self.STD[self.c1+offset]:.2f}'

    def update_mass_to_charge(self):
        for ann in [child for child in self.axes[0].get_children() if isinstance(child,matplotlib.text.Annotation)]:#[self.seAnnArrow,self.seAnnFile,self.seAnnFWHM]:
            ann.remove()
        if len(self.mz) > 1:
            for x,y,c in zip(self.mz,self.intensity,self.cs):
                self.axes[0].annotate(text = f'{c}',xy=(x,y),xycoords='data',ha='center')
            self.axes[0].annotate(text = f"{self.mass_string(-1,'lower  ')}\n{self.mass_string( 0,'likely  ')}\n{self.mass_string(+1,'higher')}\n"
                                    + '\n'.join([f'mz:{m:10.2f} z:{c:4}' for m,c in zip(self.mz,self.cs)]),
                                xy=(0.02,0.98),xycoords='axes fraction',fontsize=8,ha='left',va='top')
        self.canvas.draw_idle()
        self.labelPlot(self.axes[0],self.file.name)

    def msPlot(self):
        """plots MS data"""
        self.axes[0].clear()
        x,y=np.loadtxt(self.file,skiprows=10,usecols=[0,1],unpack=True)
        self.axes[0].plot(x,y)
        # downsampler slower and more buggy than just using large mass spec data directly
        # ms,= self.axes[0].plot([np.min(x),np.max(x)],[np.min(y),np.max(y)])
        # self.ddd = self.DataDisplayDownsampler(x,y,self.canvas,ms)
        # self.axes[0].callbacks.connect('xlim_changed',self.ddd.update)
        self.axes[0].set_xlabel('m/z')
        self.axes[0].set_ylabel('Intensity')
        self.axes[0].ticklabel_format(axis='y',style='sci',scilimits=(0,0)) # use shared expoent for short y labels,even for smaller numbers
        self.mz = np.array([]) # reset analyis
        self.intensity = np.array([])
        self.fig.tight_layout() # after rescaling!
        self.canvas.draw_idle()
        self.toolbar.update() # reset history for zooming and home view
        self.canvas.get_default_filename = lambda: self.file.with_suffix('') # set up save file dialog
        self.labelPlot(self.axes[0],self.file.name)

    class DataDisplayDownsampler:
        """A class that will downsample the data and recompute when zoomed.
        based on https://matplotlib.org/3.5.0/gallery/event_handling/resample.html
        """
        def __init__(self,xdata,ydata,canvas,line,max_points = 100000):
            self.origYData = ydata
            self.origXData = xdata
            self.max_points = max_points # maximum points used to display. change for your quality/performance needs
            self.delta = xdata[-1] - xdata[0]
            self.canvas = canvas
            self.line = line

        def downsample(self,ax):
            """Reduce number of datapoints while keeping essential plot features"""
            # get the points in the view range
            xmin,xmax = ax.get_xlim()
            ymin,ymax = ax.get_ylim()
            mask = (self.origXData > xmin) & (self.origXData < xmax)
            # dilate the mask by one to catch the points just outside
            # of the view range to not truncate the line
            mask = np.convolve([1,1,1],mask,mode='same').astype(bool)
            # ratio = max(np.sum(mask) // self.max_points,1) # sort out how many points to drop
            # mask data original
            xdata = self.origXData[mask]
            ydata = self.origYData[mask]
            cutoff = abs(0.0001*(ymax-ymin))
            # print('xdata before ',len(xdata),'cutoff: ', cutoff)
            while [abs(ydata[i] - ydata[i-1]) > cutoff for i in range(len(ydata))].count(True) > self.max_points:
                cutoff *= 4
                # print([abs(ydata[i] - ydata[i-1]) > cutoff for i, v in enumerate(ydata)].count(True),self.max_points,cutoff)
            mask = [abs(ydata[i] - ydata[i-1]) > cutoff for i in range(len(ydata))]
            # print('xdata cleaned ',len(xdata[mask]),'cutoff',cutoff)
            return xdata[mask],ydata[mask]

        def update(self,ax):
            # Update the line
            lims = ax.viewLim
            if abs(lims.width - self.delta) > 1e-8:
                self.delta = lims.width
                self.line.set_data(*self.downsample(ax))
                self.canvas.draw_idle()

class ESIBD_PDB_GUI(ESIBD_GUI):
    """Displays coordinates from PDB files in 3D."""
    def __init__(self,**kwargs):
        super().__init__(name = 'PDB',**kwargs)
        self.suffixes.extend(['.pdb','.pdb1'])

        self.fig=plt.figure(dpi=self.getDPI())
        self.canvas,self.toolbar = self.makeFigureCanvasWithToolbar(self,self.fig)
        self.axes = []
        self.axes.append(self.fig.add_subplot(111,projection='3d'))
        self.fig.tight_layout()

    def get_structure(self,pdb_file): # read PDB file
        structure = PDBParser(QUIET=True).get_structure('',pdb_file)
        XYZ=np.array([atom.get_coord() for atom in structure.get_atoms()])
        return structure,XYZ,XYZ[:,0],XYZ[:,1],XYZ[:,2]

    def loadData(self,file):
        self.axes[0].clear()
        _,_,x,y,z = self.get_structure(file)
        self.axes[0].scatter(x,y,z,marker='.',s=1)
        self.set_axes_equal(self.axes[0])
        self.axes[0].set_autoscale_on(True)
        self.axes[0].relim()
        self.toolbar.update() # reset history for zooming and home view
        self.canvas.get_default_filename = lambda: file.with_suffix('') # set up save file dialog
        self.canvas.draw_idle()
        self.fig.tight_layout()

    def set_axes_equal(self,ax):
        '''Make axes of 3D plot have equal scale so that spheres appear as spheres,
        cubes as cubes,etc..  This is one possible solution to Matplotlib's
        ax.set_aspect('equal') and ax.axis('equal') not working for 3D.
        Input
          ax: a matplotlib axis,e.g.,as output from plt.gca().
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
        # norm,hence I call half the max range the plot radius.
        plot_radius = 0.5*max([x_range,y_range,z_range])
        ax.set_xlim3d([x_middle - plot_radius,x_middle + plot_radius])
        ax.set_ylim3d([y_middle - plot_radius,y_middle + plot_radius])
        ax.set_zlim3d([z_middle - plot_radius,z_middle + plot_radius])

class ESIBD_LINE_GUI(ESIBD_GUI):
    """Displays 1D plots for selected files."""
    def __init__(self,**kwargs):
        super().__init__(name = '1D',**kwargs)
        self.suffixes = ['.txt']
        self.fig=plt.figure(dpi=self.getDPI())
        self.canvas,self.toolbar = self.makeFigureCanvasWithToolbar(self,self.fig)
        self.axes = []
        self.axes.append(self.fig.add_subplot(111))
        self.fig.tight_layout()

    def supportsFile(self, file):
        if super().supportsFile(file):
            first_line = '' # else text file
            with open(file,encoding=self.UTF8) as f:
                first_line = f.readline()
            if 'profile' in first_line.lower(): # mass spectrum
                return True
        return False

    def loadData(self,file):
        """Plots one dimensional data for multiple file types."""
        self.axes[0].clear()
        if file.name.endswith('.txt'): # need to implement handling of different files in future
            profile=np.loadtxt(file,skiprows=3)
            self.axes[0].plot(profile[:,0],profile[:,1])
            self.axes[0].set_xlabel('width (m)')
            self.axes[0].set_ylabel('height (m)')
            self.axes[0].autoscale(True)
            self.axes[0].relim()
            self.axes[0].autoscale_view(True,True,True)
        self.fig.tight_layout() # after rescaling!
        self.canvas.draw_idle()
        self.toolbar.update() # reset history for zooming and home view
        self.canvas.get_default_filename = lambda: file.with_suffix('') # set up save file dialog
        self.labelPlot(self.axes[0],file.name)

class ESIBD_IMAGE_GUI(ESIBD_GUI):
    """Displays mass spectra and allows to determine charge states by marking peaks."""
    def __init__(self,**kwargs):
        super().__init__(name = 'Image',**kwargs)
        self.suffixes.extend(['.jpg','.jpeg','.png','.bmp','.gif'])
        self.imgImageWidget = self.ImageWidget()
        self.addContentWidget(self.imgImageWidget)

    def loadData(self, file):
        self.imgImageWidget.setRawPixmap(QPixmap(file.as_posix()))

    class ImageWidget(QLabel):
        """QLabel that keeps aspect ratio
        https://stackoverflow.com/questions/68484199/keep-aspect-ratio-of-image-in-a-qlabel-whilst-resizing-window"""
        def __init__(self,parent=None):
            super().__init__(parent)
            self.setScaledContents(False)
            self.setMinimumSize(1,1)
            self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Expanding)
            self.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
            self.installEventFilter(self)
            self.raw_pixMap = None

        def setRawPixmap(self,a0):
            self.raw_pixMap = a0
            self.setPixmap(self.raw_pixMap.scaled(self.width(),self.height(),Qt.AspectRatioMode.KeepAspectRatio))

        def eventFilter(self,widget,event):
            if event.type() == QEvent.Type.Resize and widget is self and self.raw_pixMap is not None:
                self.setPixmap(self.raw_pixMap.scaled(self.width(),self.height(),Qt.AspectRatioMode.KeepAspectRatio))
                return True
            return super().eventFilter(widget,event)

class ESIBD_TEXT_GUI(ESIBD_GUI):
    """Displays orginal or interpreted file content as text."""
    def __init__(self,**kwargs):
        super().__init__(name = 'Text',**kwargs)
        self.suffixes = ['.txt','.dat','.ter','.cur','.tt','.star','.pdb1','.css','.js','.html','.tex','.ini','.bat']
        self.textBrowser = QTextBrowser()
        self.textBrowser.setFont(QFont('Courier',10))
        self.addContentWidget(self.textBrowser)

    def loadData(self, file):
        self.textBrowser.clear()
        if any(file.name.endswith(s) for s in self.suffixes):
            try:
                with open(file,encoding=self.UTF8) as f:
                    for line in islice(f,1000): # dont use f.read() as files could potenitially be very large
                        self.textBrowser.insertPlainText(line) # always populate text box but only change to tab if no other display method is available
            except UnicodeDecodeError as e:
                self.print(f'Cant read file: {e}')
        else:
            self.textBrowser.insertPlainText('No handler implemented for this file type. Consider making a feature request.')
        self.textBrowser.verticalScrollBar().triggerAction(QScrollBar.SliderAction.SliderToMinimum)   # scroll to top

class ESIBD_NOTES_GUI(ESIBD_GUI):
    """Allows to quickly view and edit notes for sessions and all other folders."""
    def __init__(self,**kwargs):
        super().__init__(name = 'Notes',**kwargs)
        self.suffixes = [] # does not accept any files, needs to be called explicity
        self.file = None
        self.textEdit = QPlainTextEdit()
        self.textEdit.setFont(QFont('Courier',10))
        self.addContentWidget(self.textEdit)

    def rootChanging(self, oldRoot, newRoot):
        # save old notes
        if oldRoot is not None:
            self.file = oldRoot / 'notes.txt'
            if self.textEdit.toPlainText() != '':
                with open(self.file,'w',encoding = self.UTF8) as f:
                    f.write(self.textEdit.toPlainText())
        # load new notes
        if newRoot is not None: # None on program closing
            self.textEdit.clear()
            self.file = newRoot / 'notes.txt'
            if self.file.exists(): # load and display notes if found
                with open(self.file,encoding = self.UTF8) as f:
                    self.textEdit.insertPlainText(f.read())
            self.textEdit.verticalScrollBar().triggerAction(QScrollBar.SliderAction.SliderToMinimum)   # scroll to top

class ESIBD_TREE_GUI(ESIBD_GUI):
    """Displays orginal or interpreted file content as tree."""

    ICON_ATTRIBUTE = 'media/blue-document-attribute.png'
    ICON_DATASET = 'media/database-medium.png'
    ICON_FUNCMET = 'media/block-small.png'
    # ICON_CLASS = 'media/blue-document-block.png'
    ICON_CLASS = 'media/application-block.png'
    ICON_GROUP = 'media/folder.png'

    def __init__(self,**kwargs):
        super().__init__(name = 'Tree',**kwargs)
        self.h5Suffixes = ['.hdf5','.h5']
        self.pySuffixes = ['.py']
        self.suffixes = self.h5Suffixes + self.pySuffixes
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.addContentWidget(self.tree)

    def loadData(self, file):
        """Display file content as tree."""
        self.tree.clear()
        if any(file.name.endswith(s) for s in self.h5Suffixes):
            with h5py.File(file,'r',track_order=True) as f:
                self.hdfShow(f,self.tree.invisibleRootItem(),0)
        else: # self.pySuffixes
            # """from https://stackoverflow.com/questions/44698193/how-to-get-a-list-of-classes-and-functions-from-a-python-file-without-importing/67840804#67840804"""
            with open(file,encoding = self.UTF8) as file:
                node = ast.parse(file.read())
            functions = [n for n in node.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))]
            classes = [n for n in node.body if isinstance(n,ast.ClassDef)]
            for function in functions:
                f = QTreeWidgetItem(self.tree,[function.name])
                f.setIcon(0,QIcon(self.ICON_FUNCMET))
                f.setToolTip(0,ast.get_docstring(function))
                f.setExpanded(True)
            for _class in classes:
                self.pyShow(_class,self.tree,0)

    def hdfShow(self,f,tree,level):
        for name, item in f.items():
            if isinstance(item,h5py.Group):
                g = QTreeWidgetItem(tree,[name])
                g.setIcon(0,QIcon(self.ICON_GROUP))
                if level < 1:
                    g.setExpanded(True)
                for at,v in item.attrs.items():
                    a = QTreeWidgetItem(g,[f'{at}: {v}'])
                    a.setIcon(0,QIcon(self.ICON_ATTRIBUTE))
                self.hdfShow(item,g,level+1)
            elif isinstance(item,h5py.Dataset):
                d = QTreeWidgetItem(tree,[name])
                d.setIcon(0,QIcon(self.ICON_DATASET))

    def pyShow(self,_class,tree,level):
        c = QTreeWidgetItem(tree,[_class.name])
        c.setIcon(0,QIcon(self.ICON_CLASS))
        c.setToolTip(0,ast.get_docstring(_class))
        if level < 1:
            c.setExpanded(True)
        for __class in [n for n in _class.body if isinstance(n,ast.ClassDef)]:
            self.pyShow(__class,c,level+1)
        for method in [n for n in _class.body if isinstance(n,ast.FunctionDef)]:
            m = QTreeWidgetItem(c,[method.name])
            m.setIcon(0,QIcon(self.ICON_FUNCMET))
            m.setToolTip(0,ast.get_docstring(method))

class ESIBD_EXPLORER_GUI(ESIBD_GUI):
    """File manager that is optimized to work with settings and data from devices, scans, and other widgets."""

    ICON_FOLDER = 'media/folder.png'
    ICON_HOME = 'media/home.png'
    ICON_DOCUMENT = 'media/document.png'
    ICON_BACKWARD = 'media/arrow-180'
    ICON_FORWARD = 'media/arrow.png'
    ICON_UP = 'media/arrow-090.png'
    ICON_BACKWARD_GRAY = 'media/arrow_gray-180'
    ICON_FORWARD_GRAY = 'media/arrow_gray.png'
    ICON_UP_GRAY = 'media/arrow_gray-090.png'
    ICON_REFRESH = 'media/arrow-circle-315.png'
    ICON_BROWSE = 'media/folder-horizontal-open.png'
    SELECTPATH  = 'Select Path'

    def __init__(self,esibdWindow,**kwargs):
        super().__init__(name='Explorer',esibdWindow=esibdWindow,**kwargs)
        self.esibdWindow = esibdWindow

        self.suffixes = []
        self.activeFileFullPath = None

        self.history = []
        self.indexHistory = 0

        self.root = None
        self.tree = QTreeWidget()
        self.addContentWidget(self.tree)
        self.tree.currentItemChanged.connect(self.treeItemClicked)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.initExplorerContextMenu)
        self.tree.itemDoubleClicked.connect(self.treeItemDoubleClicked)
        self.tree.itemExpanded.connect(self.expandDir)
        self.tree.setHeaderHidden(True)

        self.provideRow(0).removeItem(self.provideRow(0).itemAt(0)) # remove default spaceritem

        self.backButton = self.addButton(0,0,func=self.backward,toolTip='Backward',icon=self.ICON_BACKWARD)
        self.forwardButton = self.addButton(0,1,func=self.forward,toolTip='Forward',icon=self.ICON_FORWARD)
        self.upButton = self.addButton(0,2,func=self.up,toolTip='Up',icon=self.ICON_UP)
        self.addButton(0,3,func=lambda : self.populateTree(clear=False),toolTip='Refresh',icon=self.ICON_REFRESH)

        self.currentDirLineEdit = QLineEdit()
        self.currentDirLineEdit.returnPressed.connect(self.updateCurDirFromLineEdit)
        self.provideRow(0).insertWidget(4,self.currentDirLineEdit, stretch=8)

        self.addButton(0,5,func=self.browseDir,toolTip='Select folder.',icon=self.ICON_BROWSE)
        self.addButton(0,6,func=self.goToCurrentSession,toolTip='Go to current session.',icon=self.ICON_HOME)

        self.filterLineEdit = QLineEdit()
        self.filterLineEdit.textChanged.connect(lambda : self.populateTree(clear=False))
        self.filterLineEdit.setPlaceholderText('Search')
        self.provideRow(0).insertWidget(7,self.filterLineEdit, stretch=2)

        findShortcut = QShortcut(QKeySequence('Ctrl+F'),self)
        findShortcut.activated.connect(self.filterLineEdit.setFocus)
        self.updateRoot(self.esibdWindow.dataPath,addHistory=True)

    def LOADSETTINGS(self,x):
        return f'Load {x} settings'

    def initExplorerContextMenu(self,pos):
        """Context menu for items in Explorer"""
        item = self.tree.itemAt(pos)
        if item is None:
            return
        openDirAction = None
        opencontainingDirAction = None
        openFileAction = None
        deleteFileAction = None
        copyFileNameAction = None
        loadValuesActions = []
        loadSettingsActions = []
        explorerContextMenu = QMenu(self.tree)
        if self.getItemFullPath(item).is_dir(): # actions for folders
            openDirAction = explorerContextMenu.addAction('Open folder in file explorer.')
            deleteFileAction = explorerContextMenu.addAction('Move folder to recyle bin.')
        else:
            opencontainingDirAction = explorerContextMenu.addAction('Open containing folder in file explorer.')
            openFileAction = explorerContextMenu.addAction('Open with default program.')
            copyFileNameAction = explorerContextMenu.addAction('Copy file name to clipboard.')
            deleteFileAction = explorerContextMenu.addAction('Move to recyle bin.')

            if self.activeFileFullPath.suffix == core.FILE_H5:
                with h5py.File(name = self.activeFileFullPath,mode = 'r') as f:
                    for device in self.esibdWindow.outputWidget.getDevices(inout = INOUT.IN):
                        if device.name in f:
                            loadValuesActions.append(explorerContextMenu.addAction(device.LOADVALUES))
                    for w in self.esibdWindow.getMainWidgets():
                        if w.name in f:
                            loadSettingsActions.append(explorerContextMenu.addAction(self.LOADSETTINGS(w.name)))
            elif self.activeFileFullPath.suffix == core.FILE_INI:
                confParser = configparser.ConfigParser()
                try:
                    confParser.read(self.activeFileFullPath)
                    fileType = confParser[core.INFO][ESIBD_Parameter.NAME]
                except KeyError:
                    self.print(f'Error: Could not identify file type of {self.activeFileFullPath.name}')
                else: # no exeption
                    if fileType == self.esibdWindow.settingsWidget.SETTINGS:
                        loadSettingsActions.append(explorerContextMenu.addAction(self.esibdWindow.settingsWidget.LOAD_GS))
                    else:
                        for device in self.esibdWindow.outputWidget.getDevices(inout = INOUT.IN):
                            if device.name == fileType:
                                loadValuesActions.append(explorerContextMenu.addAction(device.LOADVALUES))

        explorerContextMenuAction = explorerContextMenu.exec(self.tree.mapToGlobal(pos))
        if explorerContextMenuAction is not None:
            if explorerContextMenuAction is opencontainingDirAction:
                subprocess.Popen(f'explorer {self.activeFileFullPath.parent}')
            elif explorerContextMenuAction == openDirAction:
                subprocess.Popen(f'explorer {self.getItemFullPath(item)}')
            elif explorerContextMenuAction == openFileAction:
                subprocess.Popen(f'explorer {self.activeFileFullPath}')
            elif explorerContextMenuAction == copyFileNameAction:
                pyperclip.copy(self.activeFileFullPath.name)
            elif explorerContextMenuAction == deleteFileAction:
                send2trash(self.tree.selectedItems()[0].path_info)
                self.populateTree(clear=False)
            elif explorerContextMenuAction in loadSettingsActions:
                for w in self.esibdWindow.getMainWidgets():
                    if explorerContextMenuAction.text() == self.LOADSETTINGS(w.name):
                        w.loadSettings(file = self.activeFileFullPath)
            if explorerContextMenuAction in loadValuesActions:
                if explorerContextMenuAction.text() == self.esibdWindow.settingsWidget.LOAD_GS:
                    self.esibdWindow.settingsWidget.loadSettings(file = self.activeFileFullPath)
                else:
                    for device in self.esibdWindow.outputWidget.getDevices(inout = INOUT.IN):
                        if explorerContextMenuAction.text() == device.LOADVALUES:
                            device.loadValues(self.activeFileFullPath)

    def treeItemDoubleClicked(self,item,_):
        if self.getItemFullPath(item).is_dir():
            self.updateRoot(self.getItemFullPath(item),addHistory=True)
        else: # treeItemDoubleClicked
            subprocess.Popen(f'explorer {self.activeFileFullPath}')

    def getItemFullPath(self,item):
        out = item.text(0)
        if item.parent():
            out = self.getItemFullPath(item.parent()) / out
        else:
            out = self.root / out
        return out

    def up(self):
        newroot = Path(self.root).parent.resolve()
        self.updateRoot(newroot,addHistory=True)

    def forward(self):
        self.indexHistory = min(self.indexHistory + 1,len(self.history)-1)
        self.updateRoot(self.history[self.indexHistory])

    def backward(self):
        self.indexHistory = max(self.indexHistory - 1,0)
        self.updateRoot(self.history[self.indexHistory])

    def updateRoot(self,newroot,addHistory = False):
        self.esibdWindow.notesWidget.rootChanging(self.root,newroot)
        self.root = Path(newroot)
        if addHistory:
            del self.history[self.indexHistory+1:] # remove voided forward options
            self.history.append(self.root)
            self.indexHistory = len(self.history)-1
        self.currentDirLineEdit.setText(self.root.as_posix())
        self.populateTree(clear = True)

    def populateTree(self, clear=False):
        """Populates or updates filetree."""
        if clear: # otherwise existing tree will be updated (much more efficient)
            self.tree.clear()
        # update navigation arrows
        if self.indexHistory == len(self.history)-1:
            self.forwardButton.setIcon(QIcon(self.ICON_FORWARD_GRAY))
        else:
            self.forwardButton.setIcon(QIcon(self.ICON_FORWARD))
        if self.indexHistory == 0:
            self.backButton.setIcon(QIcon(self.ICON_BACKWARD_GRAY))
        else:
            self.backButton.setIcon(QIcon(self.ICON_BACKWARD))
        if self.root.parent == self.root: # no parent
            self.upButton.setIcon(QIcon(self.ICON_UP_GRAY))
        else:
            self.upButton.setIcon(QIcon(self.ICON_UP))

        self.load_project_structure(startpath = self.root,tree = self.tree.invisibleRootItem(),_filter = self.filterLineEdit.text()) # populate tree widget

        it = QTreeWidgetItemIterator(self.tree,QTreeWidgetItemIterator.IteratorFlag.HasChildren)
        while it.value():
            if it.value().isExpanded():
                self.load_project_structure(startpath = it.value().path_info,tree = it.value(),_filter = self.filterLineEdit.text()) # populate expanded dirs,independent of recursion depth
            #print(it.value().path_info)
            it +=1

    def browseDir(self):
        newPath = Path(QFileDialog.getExistingDirectory(parent=None,caption=self.SELECTPATH,directory=self.root.as_posix(),
                                                        options=QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontResolveSymlinks))
        if newPath != Path('.'):
            self.updateRoot(newPath,addHistory=True)

    def goToCurrentSession(self):
        sessionPath = Path(self.esibdWindow.sessionPath)
        sessionPath.mkdir(parents=True,exist_ok=True) # create if not already existing
        self.updateRoot(sessionPath,addHistory=True)

    def updateCurDirFromLineEdit(self):
        p = Path(self.currentDirLineEdit.text())
        if p.exists():
            self.updateRoot(p,addHistory=True)
        else:
            self.esibdPrint(f'Error: Could not find directory: {p}')

    def treeItemClicked(self,item):
        if item is not None and not self.getItemFullPath(item).is_dir():
            self.activeFileFullPath = self.getItemFullPath(item)
            self.displayContent()
        # else:
            # item.setExpanded(not item.isExpanded()) # already implemented for double click

    def displayContent(self):
        """General wrapper for handling of files with different format.
        If a format related to ES-IBD is detected (including backwards compatible formats) the data will be loaded and shown in the corresponding view.
        Handling for a few general formats is implemented as well.
        For text based formats the text is also shown in the Text tab for quick access if needed.
        The actual handling is redirected to dedicated methods."""

        handeled = False
        for w in [w for w in self.esibdWindow.getAllWidgets() if w.supportsFile(self.activeFileFullPath)]:
            if not handeled: # display first widget that supports file (others like tree or text come later and are optional)
                self.esibdWindow.displayTabWidget.setCurrentWidget(w.displayTab if w.displayTab is not None else w)
                handeled = True
            w.loadData(file = self.activeFileFullPath) # after widget is visible to make sure it is drawn properly

        if not handeled:
            self.esibdWindow.textWidget.loadData(self.activeFileFullPath) # will show file not supported message
            self.esibdWindow.displayTabWidget.setCurrentWidget(self.esibdWindow.textWidget)

    def load_project_structure(self,startpath,tree,_filter,recursionDepth = 2):
        """from https://stackoverflow.com/questions/5144830/how-to-create-folder-view-in-pyqt-inside-main-window
        recursively maps the file structure into the internal explorer
        Note that recursion depth of 2 assures fast indexing. Deeper levels will be indexed as they are expanded.
        Data from multiple sessions can be accessed from the data path level by exoanding the tree.
        Recursion depth of more than 2 can lead to very long loading times"""
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
            for element in dirlist: # add all dirs first,then all files
                path_info = startpath / element
                if element.name in children_text: # reuse existing
                    parent_itm = tree.child(children_text.index(element.name))
                else: # add new
                    parent_itm = QTreeWidgetItem(tree,[element.name])
                    parent_itm.path_info = path_info
                    parent_itm.setIcon(0,QIcon(self.ICON_FOLDER))
                self.load_project_structure(startpath = path_info,tree = parent_itm,_filter = _filter,recursionDepth = recursionDepth)
            for element in filelist:
                path_info = startpath / element
                # don't add files that do not match _filter
                if _filter == "" or _filter.lower() in element.name.lower():
                    if not element.name in children_text: # only add elements that do not exist already
                        parent_itm = QTreeWidgetItem(tree,[element.name])
                        parent_itm.path_info = path_info
                        parent_itm.setIcon(0,QIcon(self.ICON_DOCUMENT))
            for child in children:
                if not (startpath / child.text(0)).exists():
                    tree.removeChild(child) # remove if does not exist anymore
                if (startpath / child.text(0)).is_file() and _filter != "" and not _filter.lower() in child.text(0).lower():
                    tree.removeChild(child) # remove files if tehy do not match filter
        else:
            self.print(f'Error: {startpath} is not a valid directory')

    def expandDir(self,_dir):
        self.load_project_structure(startpath = _dir.path_info,tree = _dir,_filter = self.filterLineEdit.text())
        _dir.setExpanded(True)
