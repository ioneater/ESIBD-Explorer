"""Functions in this file will generally require direct access to UI elements as well as data structures.
Note this will be imported in ES_IBD_Explorer so that it is equivalent to defining the methods there directly.
This allows to keep the bare UI initialization separated from the more meaningful methods."""

import numpy as np
import pyqtgraph as pg
import pyqtgraph.opengl as gl
from Bio.PDB import PDBParser
from PyQt6.QtWidgets import QSlider, QHBoxLayout
from PyQt6.QtGui import QPalette
from PyQt6.QtCore import Qt
from esibd.core import MZCalculator, PluginManager, getDarkMode
from esibd.plugins import Plugin

#################################### General UI Classes #########################################

def providePlugins():
    return [MS, LINE, PDB, HOLO]

class MS(Plugin):
    """The MS plugin allows to display simple mass spectra. Clicking on peaks
    in a charge state series while holding down the Ctrl key provides a
    quick estimate of charge state and mass, based on minimizing the standard
    deviation of the mass as a function of possible charge states. The
    detailed results are shown in the graph, and help to evaluate the
    quality of the estimate. In most cases you will need to create your own version of this plugin
    that is inheriting from the built-in version and redefines how data is
    loaded for your specific data format. See :ref:`sec:plugin_system` for more information."""
    documentation = """The MS plugin allows to display simple mass spectra. Clicking on peaks
    in a charge state series while holding down the Ctrl key provides a
    quick estimate of charge state and mass, based on minimizing the standard
    deviation of the mass as a function of possible charge states. The
    detailed results are shown in the graph, and help to evaluate the
    quality of the estimate."""

    name = 'MS'
    version = '1.0'
    pluginType = PluginManager.TYPE.DISPLAY
    previewFileTypes = ['.txt']

    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.file = None
        self.x = self.y = None
        self.paperAction = None
        self.dataClipboardIcon = self.makeIcon('clipboard-paste-document-text.png')

    def getIcon(self):
        return self.makeIcon('ms_dark.png' if getDarkMode() else 'ms_light.png')

    def initGUI(self):
        self.mzCalc = MZCalculator(parentPlugin=self)
        super().initGUI()
        self.initFig()

    def initFig(self):
        self.provideFig()
        self.axes.append(self.fig.add_subplot(111))
        self.mzCalc.setAxis(self.axes[0]) # update axis but reuse picked positions until reset explicitly
        self.canvas.mpl_connect('button_press_event', self.mzCalc.msOnClick)
        self.msLine = None # self.axes[0].plot([],[])[0] # dummy plot

    def provideDock(self):
        if super().provideDock():
            self.finalizeInit()

    def finalizeInit(self, aboutFunc=None):
        super().finalizeInit(aboutFunc)
        self.copyAction = self.addAction(self.copyClipboard, 'Image to Clipboard.', icon=self.imageClipboardIcon, before=self.aboutAction)
        self.dataAction = self.addAction(lambda : self.copyLineDataClipboard(line=self.msLine), 'Data to Clipboard.', icon=self.dataClipboardIcon, before=self.copyAction)
        self.paperAction = self.addStateAction(func=self.plot, toolTipFalse='Plot in paper style.', iconFalse=self.makeIcon('percent_dark.png' if getDarkMode() else 'percent_light.png'),
                                               toolTipTrue='Plot in normal style.', iconTrue=self.getIcon(), before=self.dataAction, attr='usePaperStyle')

    def runTestParallel(self):
        if self.initializedDock:
            self.raiseDock(True)
            self.testControl(self.copyAction, True, 1)
            self.testControl(self.dataAction, True, 1)
            self.testControl(self.paperAction, not self.usePaperStyle, 1)
        super().runTestParallel()

    def supportsFile(self, file):
        if super().supportsFile(file):
            first_line = ''
            try:
                with open(file, encoding=self.UTF8) as _file:
                    first_line = _file.readline()
            except UnicodeDecodeError:
                return False
                # self.print(f'could not decode first line of file {file}: {e}', PRINT.ERROR)
            if 'spectrum' in first_line.lower(): # mass spectrum
                return True
        return False

    def loadData(self, file, _show=True):
        self.provideDock()
        self.file = file
        self.mzCalc.clear()
        self.x, self.y = np.loadtxt(self.file, skiprows=10, usecols=[0, 1], unpack=True)
        self.plot()
        self.raiseDock(_show)

    def plot(self):
        """plots MS data"""
        self.axes[0].clear()
        self.axes[0].set_xlabel('m/z (Th)')
        if self.usePaperStyle:
            self.axes[0].spines['right'].set_visible(False)
            self.axes[0].spines['top'].set_visible(False)
            self.msLine = self.axes[0].plot(self.x, self.map_percent(self.x, min(self.x), max(self.x), self.smooth(self.y, 10)), color=QPalette().text().color().name())[0]
            self.axes[0].set_ylabel('')
            self.axes[0].set_ylim([1, 100+2])
            self.axes[0].set_yticks([1, 50, 100])
            self.axes[0].set_yticklabels(['0','%','100'])
        else:
            self.axes[0].set_ylabel('Intensity')
            self.msLine = self.axes[0].plot(self.x, self.y)[0]
            self.axes[0].ticklabel_format(axis='y', style='sci', scilimits=(0, 0)) # use shared exponent for short y labels, even for smaller numbers

        self.axes[0].set_autoscale_on(True)
        self.axes[0].relim()
        self.axes[0].autoscale_view(True, True, False)
        self.setLabelMargin(self.axes[0], 0.15)
        self.navToolBar.update() # reset history for zooming and home view
        self.canvas.get_default_filename = lambda: self.file.with_suffix('.pdf') # set up save file dialog
        self.mzCalc.update_mass_to_charge()
        self.labelPlot(self.axes[0], ' ' if self.usePaperStyle else self.file.name)

    def find_nearest(self, array, value):
        array = np.asarray(array)
        idx = (np.abs(array - value)).argmin()
        return array[idx]

    def map_percent(self, x, x_min, x_max, y):
        x_min_i=np.where(x == self.find_nearest(x, x_min))[0]
        x_min_i=np.min(x_min_i) if x_min_i.shape[0] > 0 else 0
        x_max_i=np.where(x == self.find_nearest(x, x_max))[0]
        x_max_i=np.max(x_max_i) if x_max_i.shape[0] > 0 else x.shape[0]
        y_sub=y[x_min_i:x_max_i]
        return (y-np.min(y))/np.max(y_sub-np.min(y_sub))*100

    def smooth(self, y, box_pts):
        box = np.ones(box_pts)/box_pts
        y_smooth = np.convolve(y, box, mode='same')
        return y_smooth

    def updateTheme(self):
        super().updateTheme()
        if self.paperAction is not None:
            self.paperAction.iconFalse = self.makeIcon('percent_dark.png' if getDarkMode() else 'percent_light.png')
            self.paperAction.iconTrue = self.getIcon()
            self.paperAction.updateIcon(self.usePaperStyle)

class PDB(Plugin):
    """The PDB plugin allows to display atoms defined in the .pdb and .pdb1
    file formats used by the protein data bank. While the visualization is
    not very sophisticated it may get you started on interacting
    programmatically with those files."""
    documentation = None # use __doc__

    name = 'PDB'
    version = '1.0'
    pluginType = PluginManager.TYPE.DISPLAY
    previewFileTypes = ['.pdb','.pdb1']

    def getIcon(self):
        return self.makeIcon('pdb.png')

    def initGUI(self):
        self.file = None
        self.x = self.y = self.z = None
        super().initGUI()
        self.initFig()

    def initFig(self):
        self.provideFig()
        self.axes.append(self.fig.add_subplot(111, projection='3d'))

    def provideDock(self):
        if super().provideDock():
            self.finalizeInit()

    def get_structure(self, pdb_file): # read PDB file
        structure = PDBParser(QUIET=True).get_structure('', pdb_file)
        XYZ=np.array([atom.get_coord() for atom in structure.get_atoms()])
        return structure, XYZ, XYZ[:, 0], XYZ[:, 1], XYZ[:, 2]

    def loadData(self, file, _show=True):
        self.provideDock()
        self.file = file
        _, _, self.x, self.y, self.z = self.get_structure(file)
        self.plot()
        self.raiseDock(_show)

    def plot(self):
        self.axes[0].clear()
        self.axes[0].scatter(self.x, self.y, self.z, marker='.', s=2)
        self.set_axes_equal(self.axes[0])
        self.axes[0].set_autoscale_on(True)
        self.axes[0].relim()
        self.navToolBar.update() # reset history for zooming and home view
        self.canvas.get_default_filename = lambda: self.file.with_suffix('.pdf') # set up save file dialog
        self.canvas.draw_idle()

    def set_axes_equal(self, ax):
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

class LINE(Plugin):
    """The Line plugin allows to display simple 2D data. It is made to work
    with simple xy text files with a three line header.
    In most cases you will need to create your own version of this plugin
    that is inheriting from the build in version and redefines how data is
    loaded for your specific data format. See :ref:`sec:plugin_system` for more information."""
    documentation = """The Line plugin allows to display simple 2D data. It is made to work
    with simple xy text files with a three line header."""

    name = 'Line'
    version = '1.0'
    pluginType = PluginManager.TYPE.DISPLAY
    previewFileTypes = ['.txt']

    def getIcon(self):
        return self.makeIcon('chart.png')

    def initGUI(self):
        self.profile = None
        self.file = None
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
        self.dataAction = self.addAction(lambda: self.copyLineDataClipboard(line=self.line), 'Data to Clipboard.', icon=self.dataClipboardIcon, before=self.copyAction)

    def runTestParallel(self):
        if self.initializedDock:
            self.raiseDock(True)
            self.testControl(self.copyAction, True, 1)
            self.testControl(self.dataAction, True, 1)
        super().runTestParallel()

    def supportsFile(self, file):
        if super().supportsFile(file):
            first_line = '' # else text file
            try:
                with open(file, encoding=self.UTF8) as _file:
                    first_line = _file.readline()
            except UnicodeDecodeError:
                return False
            if 'profile' in first_line.lower(): # afm profile
                return True
        return False

    def loadData(self, file, _show=True):
        """Plots one dimensional data for multiple file types."""
        self.provideDock()
        if file.name.endswith('.txt'): # need to implement handling of different files in future
            self.profile = np.loadtxt(file, skiprows=3)
            self.file = file
            self.plot()
        self.raiseDock(_show)

    def plot(self):
        self.axes[0].clear()
        self.line = self.axes[0].plot(self.profile[:, 0], self.profile[:, 1])[0]
        self.axes[0].set_xlabel('width (m)')
        self.axes[0].set_ylabel('height (m)')
        self.axes[0].autoscale(True)
        self.axes[0].relim()
        self.axes[0].autoscale_view(True, True, False)
        self.setLabelMargin(self.axes[0], 0.15)
        self.canvas.draw_idle()
        self.navToolBar.update() # reset history for zooming and home view
        self.canvas.get_default_filename = lambda: self.file.with_suffix('.pdf') # set up save file dialog
        self.labelPlot(self.axes[0], self.file.name)

class HOLO(Plugin):
    """The Holo plugin was designed to display 3D NumPy arrays such as
    holograms from low energy electron holography (LEEH).\ :cite:`longchamp_imaging_2017, ochner_low-energy_2021, ochner_electrospray_2023`
    Interactive 3D surface plots with density thresholds allow for efficient visualization of very large files."""
    documentation = """The Holo plugin was designed to display 3D NumPy arrays such as
    holograms from low energy electron holography (LEEH).
    Interactive 3D surface plots with density thresholds allow for efficient visualization of very large files."""

    name = 'Holo'
    version = '1.0'
    pluginType = PluginManager.TYPE.DISPLAY
    previewFileTypes = ['.npy']

    def getIcon(self):
        return self.makeIcon('holo.png')

    def initGUI(self):
        """Initialize GUI to display Holograms."""
        super().initGUI()
        self.glAngleView = gl.GLViewWidget()
        self.glAmplitudeView = gl.GLViewWidget()
        hor = QHBoxLayout()
        hor.addWidget(self.glAngleView)
        hor.addWidget(self.glAmplitudeView)

        self.addContentLayout(hor)

        self.angleSlider = QSlider(Qt.Orientation.Horizontal)
        self.angleSlider.sliderReleased.connect(lambda : self.value_changed(angle=True))
        self.amplitudeSlider = QSlider(Qt.Orientation.Horizontal)
        self.amplitudeSlider.sliderReleased.connect(lambda : self.value_changed(angle=False))
        self.titleBar.addWidget(self.angleSlider)
        self.titleBar.addWidget(self.amplitudeSlider)
        self.angle = None
        self.amplitude = None

    def provideDock(self):
        if super().provideDock():
            self.finalizeInit()

    def value_changed(self, angle=True):
        self.drawSurface(angle=angle)

    def supportsFile(self, file):
        if super().supportsFile(file):
            data = np.load(file, mmap_mode='r') # only load header with shape and datatype
            return len(data.shape) == 3 and data.dtype == np.complex128 # only support complex 3D arrays
        return False

    def loadData(self, file, _show=True):
        self.provideDock()
        data = np.load(file)
        self.angle = np.ascontiguousarray(np.angle(data)) # make c contiguous
        self.amplitude = np.ascontiguousarray(np.abs(data)) # make c contiguous
        self.glAngleView.setCameraPosition(distance=max(self.angle.shape)*2)
        self.glAmplitudeView.setCameraPosition(distance=max(self.amplitude.shape)*2)
        self.angleSlider.setValue(10)
        self.amplitudeSlider.setValue(10)
        self.drawSurface(True)
        self.drawSurface(False)
        self.raiseDock(_show)

    def mapSliderToData(self, slider, data):
        return data.min() + slider.value()/100*(data.max() - data.min())

    def drawSurface(self, angle=True):
        """Draws an isosurface at a value defined by the sliders."""
        if self.angle is not None:
            if angle:
                self.glAngleView.clear()
                verts, faces = pg.isosurface(self.angle, self.mapSliderToData(self.angleSlider, self.angle))
            else:
                self.glAmplitudeView.clear()
                verts, faces = pg.isosurface(self.amplitude, self.mapSliderToData(self.amplitudeSlider, self.amplitude))

            md = gl.MeshData(vertexes=verts, faces=faces)
            colors = np.ones((md.faceCount(), 4), dtype=float)
            colors[:, 3] = 0.2
            colors[:, 2] = np.linspace(0, 1, colors.shape[0])
            md.setFaceColors(colors)

            m1 = gl.GLMeshItem(meshdata=md, smooth=True, shader='balloon')
            m1.setGLOptions('additive')
            m1.translate(-self.angle.shape[0]/2, -self.angle.shape[1]/2, -self.angle.shape[2]/2)

            if angle:
                self.glAngleView.addItem(m1)
            else:
                self.glAmplitudeView.addItem(m1)
