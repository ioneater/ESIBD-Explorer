"""Functions in this file will generally require direct access to UI elements as well as data structures.
Note this will be imported in ES_IBD_Explorer so that it is equivalent to defining the methods there directly.
This allows to keep the bare UI initialization separated from the more meaningful methods."""

import numpy as np
from pathlib import Path
from esibd.core import PluginManager
from esibd.plugins import Plugin


def providePlugins() -> None:
    """Indicates that this module provides plugins. Returns list of provided plugins."""
    return [LINE]


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
    iconFile = 'line.png'

    def initGUI(self) -> None:
        self.profile = None
        self.file = None
        super().initGUI()
        self.initFig()

    def initFig(self) -> None:
        self.provideFig()
        self.axes.append(self.fig.add_subplot(111))
        self.line = None

    def provideDock(self) -> None:
        if super().provideDock():
            self.finalizeInit()
            self.afterFinalizeInit()

    def finalizeInit(self, aboutFunc=None) -> None:
        super().finalizeInit(aboutFunc)
        self.copyAction = self.addAction(lambda: self.copyClipboard(), f'{self.name} image to clipboard.', icon=self.imageClipboardIcon, before=self.aboutAction)
        self.dataAction = self.addAction(lambda: self.copyLineDataClipboard(line=self.line), f'{self.name} data to clipboard.', icon=self.dataClipboardIcon, before=self.copyAction)

    def runTestParallel(self) -> None:
        if self.initializedDock:
            self.testControl(self.copyAction, True)
            self.testControl(self.dataAction, True)
        super().runTestParallel()

    def supportsFile(self, file: Path) -> None:
        if super().supportsFile(file):
            first_line = ''  # else text file
            try:
                with open(file, encoding=self.UTF8) as _file:
                    first_line = _file.readline()
            except UnicodeDecodeError:
                return False
            if 'profile' in first_line.lower():  # afm profile
                return True
        return False

    def loadData(self, file, _show=True) -> None:
        """Plots one dimensional data for multiple file types.

        :param file: The file from which to load data.
        :type file: pathlib.Path
        :param _show: True if display should be shown after loading data. Set to False if multiple plugins load file and other plugins have priority. Defaults to True
        :type _show: bool, optional
        """
        self.provideDock()
        if file.name.endswith('.txt'):  # need to implement handling of different files in future
            self.profile = np.loadtxt(file, skiprows=3)
            self.file = file
            self.plot()
        self.raiseDock(_show)

    def plot(self) -> None:
        self.axes[0].clear()
        self.line = self.axes[0].plot(self.profile[:, 0], self.profile[:, 1])[0]
        self.axes[0].set_xlabel('width (m)')
        self.axes[0].set_ylabel('height (m)')
        self.axes[0].autoscale(True)
        self.axes[0].relim()
        self.axes[0].autoscale_view(True, True, False)
        self.setLabelMargin(self.axes[0], 0.15)
        self.canvas.draw_idle()
        self.navToolBar.update()  # reset history for zooming and home view
        self.canvas.get_default_filename = lambda: self.file.with_suffix('.pdf')  # set up save file dialog
        self.labelPlot(self.axes[0], self.file.name)

    def generatePythonPlotCode(self) -> None:
        return f"""import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np

profile = np.loadtxt('{self.pluginManager.Explorer.activeFileFullPath.as_posix()}', skiprows=3)

with mpl.style.context('default'):
    fig = plt.figure(constrained_layout=True)
    ax = fig.add_subplot(111)
    ax.plot(profile[:, 0], profile[:, 1])[0]
    ax.set_xlabel('width (m)')
    ax.set_ylabel('height (m)')
    fig.show()"""
