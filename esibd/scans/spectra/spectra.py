import itertools
import time
from typing import TYPE_CHECKING

import h5py
import numpy as np

from esibd.core import INOUT, MetaChannel, MultiState, getDarkMode, plotting
from esibd.scans import Beam

if TYPE_CHECKING:
    from esibd.plugins import Plugin


def providePlugins() -> list['Plugin']:
    """Return list of provided plugins. Indicates that this module provides plugins."""
    return [Spectra]


class Spectra(Beam):
    """Extend Beam scan to plot the data in the form of multiple spectra instead of a single 2D plot.

    The spectra can be plotted stacked (Y axis represents value of Y input channel and data of display channel is normalized.)
    or overlaid (Y axis represents data of display channel and value of Y input channels are indicated in a legend).
    In addition, the average of all spectra can be displayed.
    If you want to remeasure the same spectrum several times,
    consider defining a dummy channel that can be used as an index.
    """

    # * by inheriting from Beam, this creates another independent instance which allows the user to use both at the same time.
    # This allows for a more flexible use compared to adding these features as options to Beam directly.
    # It also serves as an example for how to inherit from scans that can help users to make their own versions.
    # As this is backwards compatible with files saved by Beam scan, it is possible to disable Beam scan if you want to make sure Spectra scan is opening the file.

    name = 'Spectra'
    version = '1.0'
    iconFile = 'stacked.png'
    LEFTRIGHT = 'X'
    UPDOWN = 'Y'

    class Display(Beam.Display):
        """Displays data for Spectra scan."""

        plotModeAction = None
        averageAction = None

        def __init__(self, scan, **kwargs) -> None:
            super(Beam.Display, self).__init__(scan, **kwargs)
            self.lines = None

        def finalizeInit(self) -> None:
            self.mouseActive = False
            super().finalizeInit()
            self.averageAction = self.addStateAction(toolTipFalse='Show average.', toolTipTrue='Hide average.', iconFalse=self.scan.getIcon(),  # defined in updateTheme
                                                        before=self.copyAction, event=lambda: (self.initFig(), self.scan.plot(update=False, done=True)), attr='average')
            self.plotModeAction = self.addMultiStateAction(states=[MultiState('stacked', 'Overlay plots.', self.scan.makeIcon('overlay.png')),
                                                               MultiState('overlay', 'Contour plot.', self.scan.makeIcon('beam.png')),
                                                               MultiState('contour', 'Stack plots.', self.scan.makeIcon('stacked.png'))], before=self.copyAction,
                                                        event=lambda: (self.initFig(), self.scan.plot(update=False, done=True)), attr='plotMode')
            self.updateTheme()  # set icons
            self.initFig()  # axes aspect or plotMode may have changed

        def initFig(self) -> None:
            if self.plotModeAction is None:
                return
            self.lines = None
            if self.plotModeAction.state == self.plotModeAction.labels.contour:
                super().initFig()
                return
            super(Beam.Display, self).initFig()
            self.axes.append(self.fig.add_subplot(111))
            if not self.axesAspectAction.state:  # use qSet directly in case control is not yet initialized
                self.axes[0].set_aspect('equal', adjustable='box')

        def updateTheme(self) -> None:
            if self.averageAction is not None:
                self.averageAction.iconFalse = self.scan.makeIcon('average_dark.png' if getDarkMode() else 'average_light.png')
                self.averageAction.iconTrue = self.averageAction.iconFalse
                self.averageAction.updateIcon(self.averageAction.state)
            return super().updateTheme()

    def __init__(self, **kwargs) -> None:
        super(Beam, self).__init__(**kwargs)
        self.useDisplayChannel = True
        self.previewFileTypes.append('beam.h5')

    def initScan(self) -> None:
        self.toggleDisplay(visible=True)
        self.display.lines = None
        return super().initScan()

    def loadDataInternal(self) -> None:
        self.display.lines = None
        if self.file.name.endswith('beam.h5'):
            with h5py.File(self.file, 'r') as h5file:
                group = h5file[self.pluginManager.Beam.name]  # only modification needed to open beam files. data structure is identical
                input_group = group[self.INPUTCHANNELS]
                for name, data in input_group.items():
                    self.inputChannels.append(MetaChannel(parentPlugin=self, name=name, recordingData=data[:], unit=data.attrs[self.UNIT], inout=INOUT.IN))
                output_group = group[self.OUTPUTCHANNELS]
                for name, data in output_group.items():
                    self.addOutputChannel(name=name, unit=data.attrs[self.UNIT], recordingData=data[:])
        else:
            super(Beam, self).loadDataInternal()

    @plotting
    def plot(self, update=False, done=True, **kwargs) -> None:  # pylint:disable=unused-argument  # noqa: C901, PLR0912
        # timing test with 50 data points: update True: 33 ms, update False: 120 ms

        if self.display.plotModeAction.state == self.display.plotModeAction.labels.contour:
            super().plot(update=update, done=done, **kwargs)
            return
        if self.loading or len(self.outputChannels) == 0:
            return

        x = np.linspace(self.inputChannels[0].getRecordingData()[0], self.inputChannels[0].getRecordingData()[-1], len(self.inputChannels[0].getRecordingData()))
        y = np.linspace(self.inputChannels[1].getRecordingData()[0], self.inputChannels[1].getRecordingData()[-1], len(self.inputChannels[1].getRecordingData()))
        if self.display.lines is None:
            self.display.axes[0].clear()
            self.display.lines = []  # dummy plots
            for i in range(len(self.outputChannels[self.getOutputIndex()].getRecordingData())):
                if self.display.plotModeAction.state == self.display.plotModeAction.labels.stacked:
                    self.display.lines.append(self.display.axes[0].plot([], [])[0])
                else:  # self.display.plotModeAction.labels.overlay
                    self.display.lines.append(self.display.axes[0].plot([], [], label=y[i])[0])
            if self.display.averageAction.state:
                if self.display.plotModeAction.state == self.display.plotModeAction.labels.stacked:
                    self.display.lines.append(self.display.axes[0].plot([], [], linewidth=4)[0])
                else:  # self.display.plotModeAction.labels.overlay
                    self.display.lines.append(self.display.axes[0].plot([], [], label='avg', linewidth=4)[0])
            if self.display.plotModeAction.state == self.display.plotModeAction.labels.overlay:
                legend = self.display.axes[0].legend(loc='best', prop={'size': 10}, frameon=False)
                legend.set_in_layout(False)

        if not update:
            self.display.axes[0].set_xlabel(f'{self.inputChannels[0].name} ({self.inputChannels[0].unit})')
            self.display.axes[0].set_ylabel(f'{self.inputChannels[1].name} ({self.inputChannels[1].unit})')
        for i, z in enumerate(self.outputChannels[self.getOutputIndex()].getRecordingData()):
            if self.display.plotModeAction.state == self.display.plotModeAction.labels.stacked:
                z_offset = None
                if np.abs(z.max() - z.min()) != 0:
                    z_normalized = z / (np.abs(z.max() - z.min())) * np.abs(y[1] - y[0])
                    z_offset = z_normalized + y[i] - z_normalized[0]
                self.display.lines[i].set_data(x, z_offset if z_offset is not None else z)
            else:  # self.display.plotModeAction.labels.overlay
                self.display.lines[i].set_data(x, z)
        if self.display.averageAction.state:
            z = np.mean(self.outputChannels[self.getOutputIndex()].getRecordingData(), 0)
            if self.display.plotModeAction.state == self.display.plotModeAction.labels.stacked:
                if np.abs(z.max() - z.min()) != 0:
                    z = z / (np.abs(z.max() - z.min())) * np.abs(y[1] - y[0])
                self.display.lines[-1].set_data(x, z + y[-1] + y[1] - y[0] - z[0])
            else:  # self.display.plotModeAction.labels.overlay
                self.display.lines[-1].set_data(x, z)

        self.display.axes[0].relim()  # adjust to data
        self.setLabelMargin(self.display.axes[0], 0.15)
        self.updateToolBar(update=update)
        if len(self.outputChannels) > 0:
            self.labelPlot(self.display.axes[0], f'{self.outputChannels[self.getOutputIndex()].name} from {self.file.name}')
        else:
            self.labelPlot(self.display.axes[0], self.file.name)

    def run(self, recording) -> None:
        # definition of steps updated to scan along x instead of y axis.
        steps = [steps_1d[::-1] for steps_1d in list(itertools.product(*[i.getRecordingData() for i in [self.inputChannels[1], self.inputChannels[0]]]))]
        self.print(f'Starting scan M{self.pluginManager.Settings.measurementNumber:03}. Estimated time: {self.scantime}')
        for i, step in enumerate(steps):  # scan over all steps
            waitLong = False
            for j, inputChannel in enumerate(self.inputChannels):
                if not waitLong and abs(inputChannel.value - step[j]) > self.largestep:
                    waitLong = True
                inputChannel.updateValueSignal.emit(step[j])
            time.sleep(((self.waitLong if waitLong else self.wait) + self.average) / 1000)  # if step is larger than threshold use longer wait time
            for output in self.outputChannels:
                # 2D scan
                # definition updated to scan along x instead of y axis.
                output.recordingData[i // len(self.inputChannels[0].getRecordingData()), i % len(self.inputChannels[0].getRecordingData())] = np.mean(output.getValues(
                    subtractBackground=output.getDevice().subtractBackgroundActive(), length=self.measurementsPerStep))
            if i == len(steps) - 1 or not recording():  # last step
                for inputChannel in self.inputChannels:
                    inputChannel.updateValueSignal.emit(inputChannel.initialValue)
                time.sleep(.5)  # allow time to reset to initial value before saving
                self.signalComm.scanUpdateSignal.emit(True)  # update graph and save data  # noqa: FBT003
                self.signalComm.updateRecordingSignal.emit(False)  # noqa: FBT003
                break  # in case this is last step
            self.signalComm.scanUpdateSignal.emit(False)  # update graph  # noqa: FBT003

    def pythonPlotCode(self) -> str:
        return f"""# add your custom plot code here

_interpolate = False  # set to True to interpolate data
varAxesAspect = False  # set to True to use variable axes aspect ratio
average = False  # set to True to display an average spectrum
plotMode = 'stacked'  # 'stacked', 'overlay', or 'contour'  # select the representation of your data

from mpl_toolkits.axes_grid1 import make_axes_locatable
from scipy import interpolate

fig = plt.figure(num='{self.name} plot', constrained_layout=True)
ax = fig.add_subplot(111)
if not varAxesAspect:
    ax.set_aspect('equal', adjustable='box')

def getMeshgrid(scaling=1):
    return np.meshgrid(*[np.linspace(i.recordingData[0], i.recordingData[-1], len(i.recordingData) if scaling == 1 else
    min(len(i.recordingData)*scaling, 50)) for i in inputChannels])

ax.set_xlabel(f'{{inputChannels[0].name}} ({{inputChannels[0].unit}})')
ax.set_ylabel(f'{{inputChannels[1].name}} ({{inputChannels[1].unit}})')

if plotMode == 'contour':
    divider = make_axes_locatable(ax)
    cont = None
    cax = divider.append_axes("right", size="5%", pad=0.15)
    x, y = getMeshgrid()
    z = outputChannels[output_index].recordingData.ravel()

    if _interpolate:
        rbf = interpolate.Rbf(x.ravel(), y.ravel(), outputChannels[output_index].recordingData.ravel())
        xi, yi = getMeshgrid(2)  # interpolation coordinates, scaling of 1 much faster than 2 and seems to be sufficient
        zi = rbf(xi, yi)
        cont = ax.contourf(xi, yi, zi, levels=100, cmap='afmhot')  # contour with interpolation
    else:
        cont = ax.pcolormesh(x, y, outputChannels[output_index].recordingData, cmap='afmhot')  # contour without interpolation
    cbar = fig.colorbar(cont, cax=cax)  # match axis and color bar size  # , format='%d'
    cbar.ax.set_title(outputChannels[0].unit)
else:
    x = np.linspace(inputChannels[0].recordingData[0], inputChannels[0].recordingData[-1], len(inputChannels[0].recordingData))
    y = np.linspace(inputChannels[1].recordingData[0], inputChannels[1].recordingData[-1], len(inputChannels[1].recordingData))
    for i, z in enumerate(outputChannels[output_index].recordingData):
        if plotMode == 'stacked':
            if np.abs(z.max()-z.min()) != 0:
                z = z/(np.abs(z.max()-z.min()))*np.abs(y[1]-y[0])
            ax.plot(x, z + y[i] - z[0])
        else:  # 'overlay'
            ax.plot(x, z, label=y[i])
    if average:
        z = np.mean(outputChannels[output_index].recordingData, 0)
        if plotMode == 'stacked':
            if np.abs(z.max()-z.min()) != 0:
                z = z/(np.abs(z.max()-z.min()))*np.abs(y[1]-y[0])
            ax.plot(x, z + y[-1] + y[1]-y[0] - z[0], linewidth=4)
        else:  # 'overlay'
            ax.plot(x, z, label='avg', linewidth=4)
    if plotMode == 'overlay':
        legend = ax.legend(loc='best', prop={{'size': 10}}, frameon=False)
        legend.set_in_layout(False)
fig.show()
        """  # noqa: S608
