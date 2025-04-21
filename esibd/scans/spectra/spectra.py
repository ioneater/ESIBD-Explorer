"""This module contains classes that contain and manage a list of (extended) UI elements.
In addition it contains classes used to manage data acquisition.
Finally it contains classes for data export, and data import."""

import time
import itertools
import h5py
import numpy as np
from esibd.core import INOUT, plotting, MetaChannel, getDarkMode, MultiState
from esibd.scans import Beam


def providePlugins() -> None:
    """Indicates that this module provides plugins. Returns list of provided plugins."""
    return [Spectra]


class Spectra(Beam):
    """This scan shares many features of the Beam scan.
    The main difference is that it adds the option to plot the data in the form
    of multiple spectra instead of a single 2D plot.
    The spectra can be plotted stacked (Y axis represents value of Y input channel and data of display channel is normalized.)
    or overlaid (Y axis represents data of display channel and value of Y input channels are indicated in a legend).
    In addition, the average of all spectra can be displayed.
    If you want to remeasure the same spectrum several times,
    consider defining a dummy channel that can be used as an index."""
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

        def __init__(self, scan, **kwargs):
            super(Beam.Display, self).__init__(scan, **kwargs)
            self.lines = None

        def finalizeInit(self, aboutFunc=None) -> None:
            self.mouseActive = False
            super().finalizeInit(aboutFunc)
            self.averageAction = self.addStateAction(toolTipFalse='Show average.',
                                                        toolTipTrue='Hide average.',
                                                        iconFalse=self.scan.getIcon(),  # defined in updateTheme
                                                        before=self.copyAction,
                                                        event=lambda: (self.initFig(), self.scan.plot(update=False, done=True)), attr='average')
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

    def __init__(self, **kwargs):
        super(Beam, self).__init__(**kwargs)
        self.useDisplayChannel = True
        self.previewFileTypes.append('beam.h5')

    def initScan(self) -> None:
        self.toggleDisplay(True)
        self.display.lines = None
        return super().initScan()

    def loadDataInternal(self) -> None:
        self.display.lines = None
        if self.file.name.endswith('beam.h5'):
            with h5py.File(self.file, 'r') as h5file:
                group = h5file[self.pluginManager.Beam.name]  # only modification needed to open beam files. data structure is identical
                input_group = group[self.INPUTCHANNELS]
                for name, data in input_group.items():
                    self.inputs.append(MetaChannel(parentPlugin=self, name=name, recordingData=data[:], unit=data.attrs[self.UNIT], inout=INOUT.IN))
                output_group = group[self.OUTPUTCHANNELS]
                for name, data in output_group.items():
                    self.addOutputChannel(name=name, unit=data.attrs[self.UNIT], recordingData=data[:])
        else:
            return super(Beam, self).loadDataInternal()

    @plotting
    def plot(self, update=False, done=True, **kwargs) -> None:  # pylint:disable=unused-argument
        # timing test with 50 data points: update True: 33 ms, update False: 120 ms

        if self.display.plotModeAction.state == self.display.plotModeAction.labels.contour:
            super().plot(update=update, done=done, **kwargs)
            return
        if self.loading or len(self.outputs) == 0:
            return

        x = np.linspace(self.inputs[0].getRecordingData()[0], self.inputs[0].getRecordingData()[-1], len(self.inputs[0].getRecordingData()))
        y = np.linspace(self.inputs[1].getRecordingData()[0], self.inputs[1].getRecordingData()[-1], len(self.inputs[1].getRecordingData()))
        if self.display.lines is None:
            self.display.axes[0].clear()
            self.display.lines = []  # dummy plots
            for i, z in enumerate(self.outputs[self.getOutputIndex()].getRecordingData()):
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
            self.display.axes[0].set_xlabel(f'{self.inputs[0].name} ({self.inputs[0].unit})')
            self.display.axes[0].set_ylabel(f'{self.inputs[1].name} ({self.inputs[1].unit})')
        for i, z in enumerate(self.outputs[self.getOutputIndex()].getRecordingData()):
            if self.display.plotModeAction.state == self.display.plotModeAction.labels.stacked:
                if np.abs(z.max() - z.min()) != 0:
                    z = z / (np.abs(z.max() - z.min())) * np.abs(y[1] - y[0])
                self.display.lines[i].set_data(x, z + y[i] - z[0])
            else:  # self.display.plotModeAction.labels.overlay
                self.display.lines[i].set_data(x, z)
        if self.display.averageAction.state:
            z = np.mean(self.outputs[self.getOutputIndex()].getRecordingData(), 0)
            if self.display.plotModeAction.state == self.display.plotModeAction.labels.stacked:
                if np.abs(z.max() - z.min()) != 0:
                    z = z / (np.abs(z.max() - z.min())) * np.abs(y[1] - y[0])
                self.display.lines[-1].set_data(x, z + y[-1] + y[1] - y[0] - z[0])
            else:  # self.display.plotModeAction.labels.overlay
                self.display.lines[-1].set_data(x, z)

        self.display.axes[0].relim()  # adjust to data
        self.setLabelMargin(self.display.axes[0], 0.15)
        self.updateToolBar(update=update)
        if len(self.outputs) > 0:
            self.labelPlot(self.display.axes[0], f'{self.outputs[self.getOutputIndex()].name} from {self.file.name}')
        else:
            self.labelPlot(self.display.axes[0], self.file.name)

    def run(self, recording) -> None:
        # definition of steps updated to scan along x instead of y axis.
        steps = [tuple[::-1] for tuple in list(itertools.product(*[i.getRecordingData() for i in [self.inputs[1], self.inputs[0]]]))]
        self.print(f'Starting scan M{self.pluginManager.Settings.measurementNumber:03}. Estimated time: {self.scantime}')
        for i, step in enumerate(steps):  # scan over all steps
            waitLong = False
            for j, _input in enumerate(self.inputs):
                if not waitLong and abs(_input.value - step[j]) > self.largestep:
                    waitLong=True
                _input.updateValueSignal.emit(step[j])
            time.sleep(((self.waitLong if waitLong else self.wait) + self.average) / 1000)  # if step is larger than threshold use longer wait time
            for j, output in enumerate(self.outputs):
                # 2D scan
                # definition updated to scan along x instead of y axis.
                output.recordingData[i // len(self.inputs[0].getRecordingData()), i%len(self.inputs[0].getRecordingData())] = np.mean(output.getValues(
                    subtractBackground=output.getDevice().subtractBackgroundActive(), length=self.measurementsPerStep))
            if i == len(steps) - 1 or not recording():  # last step
                for j, _input in enumerate(self.inputs):
                    _input.updateValueSignal.emit(_input.initialValue)
                time.sleep(.5)  # allow time to reset to initial value before saving
                self.signalComm.scanUpdateSignal.emit(True)  # update graph and save data
                self.signalComm.updateRecordingSignal.emit(False)
                break  # in case this is last step
            else:
                self.signalComm.scanUpdateSignal.emit(False)  # update graph

    def pythonPlotCode(self) -> None:
        return """# add your custom plot code here

_interpolate = False  # set to True to interpolate data
varAxesAspect = False  # set to True to use variable axes aspect ratio
average = False  # set to True to display an average spectrum
plotMode = 'stacked'  # 'stacked', 'overlay', or 'contour'  # select the representation of your data

from mpl_toolkits.axes_grid1 import make_axes_locatable
from scipy import interpolate

fig = plt.figure(constrained_layout=True)
ax = fig.add_subplot(111)
if not varAxesAspect:
    ax.set_aspect('equal', adjustable='box')

def getMeshgrid(scaling=1):
    return np.meshgrid(*[np.linspace(i.recordingData[0], i.recordingData[-1], len(i.recordingData) if scaling == 1 else min(len(i.recordingData)*scaling, 50)) for i in inputs])

ax.set_xlabel(f'{inputs[0].name} ({inputs[0].unit})')
ax.set_ylabel(f'{inputs[1].name} ({inputs[1].unit})')

if plotMode == 'contour':
    divider = make_axes_locatable(ax)
    cont = None
    cax = divider.append_axes("right", size="5%", pad=0.15)
    x, y = getMeshgrid()
    z = outputs[output_index].recordingData.ravel()

    if _interpolate:
        rbf = interpolate.Rbf(x.ravel(), y.ravel(), outputs[output_index].recordingData.ravel())
        xi, yi = getMeshgrid(2)  # interpolation coordinates, scaling of 1 much faster than 2 and seems to be sufficient
        zi = rbf(xi, yi)
        cont = ax.contourf(xi, yi, zi, levels=100, cmap='afmhot')  # contour with interpolation
    else:
        cont = ax.pcolormesh(x, y, outputs[output_index].recordingData, cmap='afmhot')  # contour without interpolation
    cbar = fig.colorbar(cont, cax=cax)  # match axis and color bar size  # , format='%d'
    cbar.ax.set_title(outputs[0].unit)
else:
    x = np.linspace(inputs[0].recordingData[0], inputs[0].recordingData[-1], len(inputs[0].recordingData))
    y = np.linspace(inputs[1].recordingData[0], inputs[1].recordingData[-1], len(inputs[1].recordingData))
    for i, z in enumerate(outputs[output_index].recordingData):
        if plotMode == 'stacked':
            if np.abs(z.max()-z.min()) != 0:
                z = z/(np.abs(z.max()-z.min()))*np.abs(y[1]-y[0])
            ax.plot(x, z + y[i] - z[0])
        else:  # 'overlay'
            ax.plot(x, z, label=y[i])
    if average:
        z = np.mean(outputs[output_index].recordingData, 0)
        if plotMode == 'stacked':
            if np.abs(z.max()-z.min()) != 0:
                z = z/(np.abs(z.max()-z.min()))*np.abs(y[1]-y[0])
            ax.plot(x, z + y[-1] + y[1]-y[0] - z[0], linewidth=4)
        else:  # 'overlay'
            ax.plot(x, z, label='avg', linewidth=4)
    if plotMode == 'overlay':
        legend = ax.legend(loc='best', prop={'size': 10}, frameon=False)
        legend.set_in_layout(False)
fig.show()
        """
