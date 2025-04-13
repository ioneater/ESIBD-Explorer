"""Functions in this file will generally require direct access to UI elements as well as data structures.
Note this will be imported in ES_IBD_Explorer so that it is equivalent to defining the methods there directly.
This allows to keep the bare UI initialization separated from the more meaningful methods."""

import numpy as np
from Bio.PDB import PDBParser
from esibd.core import PluginManager
from esibd.plugins import Plugin

def providePlugins():
    """Indicates that this module provides plugins. Returns list of provided plugins."""
    return [PDB]

class PDB(Plugin):
    """The PDB plugin allows to display atoms defined in the .pdb and .pdb1
    file formats used by the protein data bank. While the visualization is
    not very sophisticated it may get you started on interacting
    programmatically with those files."""

    name = 'PDB'
    version = '1.0'
    pluginType = PluginManager.TYPE.DISPLAY
    previewFileTypes = ['.pdb','.pdb1']
    iconFile = 'pdb.png'

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
            self.afterFinalizeInit()

    def get_structure(self, pdb_file): # read PDB file
        """Get structure and XYZ coordinates from pdb file.

        :param pdb_file: PDB input file.
        :type pdb_file: pathlib.Path
        :return: PDBParser object, XYZ, X, Y, Z
        :rtype: PDBParser, np.array, np.array, np.array
        """
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
        """Make axes of 3D plot have equal scale so that spheres appear as spheres,
        cubes as cubes, etc..  This is one possible solution to Matplotlib's
        ax.set_aspect('equal') and ax.axis('equal') not working for 3D.

        :param ax: A matplotlib axes.
        :type ax: matplotlib.axes
        """
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

    def generatePythonPlotCode(self):
        return f"""import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from Bio.PDB import PDBParser

def get_structure(pdb_file): # read PDB file
    '''Get structure and XYZ coordinates from pdb file.

    :param pdb_file: PDB input file.
    :type pdb_file: pathlib.Path
    :return: PDBParser object, XYZ, X, Y, Z
    :rtype: PDBParser, np.array, np.array, np.array
    '''
    structure = PDBParser(QUIET=True).get_structure('', pdb_file)
    XYZ=np.array([atom.get_coord() for atom in structure.get_atoms()])
    return structure, XYZ, XYZ[:, 0], XYZ[:, 1], XYZ[:, 2]

def set_axes_equal(ax):
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

_, _, x, y, z = get_structure('{self.pluginManager.Explorer.activeFileFullPath.as_posix()}')

with mpl.style.context('default'):
    fig = plt.figure(constrained_layout=True)
    ax = fig.add_subplot(111, projection='3d')
    ax.scatter(x, y, z, marker='.', s=2)
    set_axes_equal(ax)
    fig.show()"""
