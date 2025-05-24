from pathlib import Path
from typing import TYPE_CHECKING, cast

import numpy as np
from Bio.PDB.PDBParser import PDBParser
from mpl_toolkits.mplot3d.axes3d import Axes3D

from esibd.core import PLUGINTYPE, PRINT
from esibd.plugins import Plugin

if TYPE_CHECKING:
    from Bio.PDB.Structure import Structure


def providePlugins() -> list['type[Plugin]']:
    """Return list of provided plugins. Indicates that this module provides plugins."""
    return [PDB]


class PDB(Plugin):
    """The PDB plugin allows to display atoms defined in the .pdb and .pdb1 file formats used by the protein data bank.

    While the visualization is
    not very sophisticated it may get you started on interacting
    programmatically with those files.
    """

    name = 'PDB'
    version = '1.0'
    pluginType = PLUGINTYPE.DISPLAY
    iconFile = 'pdb.png'

    axes: list[Axes3D]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.previewFileTypes = ['.pdb', '.pdb1']

    def initGUI(self) -> None:
        self.file = Path()
        self._x = self._y = self.z = None
        super().initGUI()
        self.initFig()

    def initFig(self) -> None:
        self.provideFig()
        if self.fig:
            self.axes.append(cast('Axes3D', self.fig.add_subplot(111, projection='3d')))

    def provideDock(self) -> None:
        if super().provideDock():
            self.finalizeInit()
            self.afterFinalizeInit()

    def finalizeInit(self) -> None:
        super().finalizeInit()
        self.copyAction = self.addAction(event=self.copyClipboard, toolTip=f'{self.name} image to clipboard.', icon=self.imageClipboardIcon, before=self.aboutAction)

    def runTestParallel(self) -> None:
        if self.initializedDock:
            self.testControl(self.copyAction, value=True)
            self.testPythonPlotCode(closePopup=True)
        super().runTestParallel()

    def get_structure(self, pdb_file: Path) -> 'tuple[Structure, np.ndarray] | tuple[None, None]':  # read PDB file
        """Get structure and XYZ coordinates from pdb file.

        :param pdb_file: PDB input file.
        :type pdb_file: pathlib.Path
        :return: PDBParser object, XYZ
        :rtype: PDBParser, np.ndarray
        """
        structure = PDBParser(QUIET=True).get_structure('', pdb_file)
        if structure:
            return structure, np.array([atom.get_coord() for atom in structure.get_atoms()])
        return None, None

    def loadData(self, file, showPlugin=True) -> None:
        self.provideDock()
        self.file = file
        _, XYZ = self.get_structure(file)
        if XYZ is not None:
            self._x, self._y, self.z = XYZ[:, 0], XYZ[:, 1], XYZ[:, 2]
            self.plot()
            self.raiseDock(showPlugin)
        else:
            self.print('XYZ is None', flag=PRINT.WARNING)

    def plot(self) -> None:
        self.axes[0].clear()
        if self.x is not None:
            self.axes[0].scatter(self._x, self._y, self.z, marker='.', s=2)  # type: ignore  # noqa: PGH003 # matplotlib type hinting incomplete
        self.set_axes_equal(self.axes[0])
        self.axes[0].set_autoscale_on(True)
        self.axes[0].relim()
        self.navToolBar.update()  # reset history for zooming and home view
        self.canvas.get_default_filename = lambda: self.file.with_suffix('.pdf') if self.file else self.name  # set up save file dialog
        self.canvas.draw_idle()

    def set_axes_equal(self, ax) -> None:
        """Make axes of 3D plot have equal scale so that spheres appear as spheres, cubes as cubes, etc.

        This is one possible solution to Matplotlib's
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
        plot_radius = 0.5 * max([x_range, y_range, z_range])
        ax.set_xlim3d([x_middle - plot_radius, x_middle + plot_radius])
        ax.set_ylim3d([y_middle - plot_radius, y_middle + plot_radius])
        ax.set_zlim3d([z_middle - plot_radius, z_middle + plot_radius])

    def generatePythonPlotCode(self) -> str:
        return f"""import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from Bio.PDB import PDBParser

def get_structure(pdb_file):  # read PDB file
    '''Get structure and XYZ coordinates from pdb file.

    :param pdb_file: PDB input file.
    :type pdb_file: pathlib.Path
    :return: PDBParser object, XYZ
    :rtype: PDBParser, np.ndarray
    '''
    structure = PDBParser(QUIET=True).get_structure('', pdb_file)
    return structure, np.array([atom.get_coord() for atom in structure.get_atoms()])

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

_, XYZ = get_structure('{self.file.as_posix() if self.file else ''}')
x, y, z = XYZ[:, 0], XYZ[:, 1], XYZ[:, 2]

fig = plt.figure(num='{self.name} plot', constrained_layout=True)
ax = fig.add_subplot(111, projection='3d')
ax.scatter(x, y, z, marker='.', s=2)
set_axes_equal(ax)
fig.show()"""
