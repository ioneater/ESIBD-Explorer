"""This module contains classes that contain and manage a list of (extended) UI elements.
In addition it contains classes used to manage data acquisition.
Finally it contains classes for data export, and data import."""

import time
from datetime import datetime, timedelta
import sys
import itertools
import matplotlib as mpl
import matplotlib.pyplot as plt
from mpl_toolkits.axes_grid1 import make_axes_locatable
import matplotlib.dates as mdates
from matplotlib.ticker import ScalarFormatter
import h5py
from scipy import optimize, interpolate
from scipy.stats import binned_statistic
from asteval import Interpreter
from PyQt6.QtWidgets import QSlider, QLabel, QSizePolicy # , QMessageBox
from PyQt6.QtCore import QObject, Qt
import numpy as np
from esibd.core import (Parameter, INOUT, ControlCursor, parameterDict, DynamicNp, PluginManager, PRINT,
    pyqtSignal, MetaChannel, colors, getDarkMode, dynamicImport, MultiState, MZCalculator, ScanChannel)
from esibd.plugins import Scan
winsound = None
if sys.platform == 'win32':
    import winsound
else:
    print('Module winsound only available on Windows.')
aeval = Interpreter()

def providePlugins():
    return [Beam, Spectra, Energy, Omni, Depo, GA, MassSpec]

class Beam(Scan):
    """Scan that records the ion-beam current on one electrode as a function of two voltage
    channels, typically deflectors. The recorded data can be interpolated to
    enhance the visualization. A 1:1 aspect ratio is used by default, but a variable ratio
    can be enabled to maximize use of space. The resulting image is used to identify
    elements like apertures, samples, and detectors. The beam can be moved
    between those elements by clicking and dragging on the image while
    holding down the Ctrl key. Limits can be coupled to have the same step
    size in both directions. Scan limits can be adopted from the figure or
    centered around the current value, e.g., to zoom in and center on a
    specific feature."""
    documentation = None # use __doc__

    LEFTRIGHT = 'Left-Right'
    UPDOWN = 'Up-Down'
    name = 'Beam'
    version = '1.0'
    pluginType = PluginManager.TYPE.SCAN
    iconFile = 'beam.png'

    class Display(Scan.Display):
        """Display for Beam Scan."""

        axesAspectAction = None

        def finalizeInit(self, aboutFunc=None):
            self.mouseActive = True
            super().finalizeInit(aboutFunc)
            self.interpolateAction = self.addStateAction(toolTipFalse='Interpolation on.', iconFalse=self.scan.makeIcon('interpolate_on.png'), toolTipTrue='Interpolation off.',
                                                         iconTrue=self.scan.makeIcon('interpolate_off.png'), before=self.copyAction,
                                                         event=lambda: self.scan.plot(update=False, done=True), attr='interpolate')
            self.axesAspectAction = self.addStateAction(toolTipFalse='Variable axes aspect ratio.',
                                                        toolTipTrue='Fixed axes aspect ratio.',
                                                        iconFalse=self.scan.getIcon(), iconTrue=self.scan.getIcon(), # defined in updateTheme
                                                        before=self.copyAction,
                                                        event=lambda: (self.initFig(), self.scan.plot(update=False, done=True)), attr='varAxesAspect')
            self.updateTheme() # set icons for axesAspectActions
            self.initFig()

        def initFig(self):
            if self.axesAspectAction is None:
                return
            super().initFig()
            engine = self.fig.get_layout_engine()
            engine.set(rect=(0.05, 0.0, 0.8, 0.9)) # constrained_layout ignores labels on colorbar
            self.axes.append(self.fig.add_subplot(111))
            if not self.axesAspectAction.state: # use qSet directly in case control is not yet initialized
                self.axes[0].set_aspect('equal', adjustable='box')
            self.canvas.mpl_connect('motion_notify_event', self.mouseEvent)
            self.canvas.mpl_connect('button_press_event', self.mouseEvent)
            self.canvas.mpl_connect('button_release_event', self.mouseEvent)
            self.cont = None
            divider = make_axes_locatable(self.axes[0])
            self.cax = divider.append_axes("right", size="5%", pad=0.15)
            self.cbar = None
            self.axes[-1].cursor = None

        def runTestParallel(self):
            if self.initializedDock:
                self.raiseDock(True)
                self.testControl(self.interpolateAction, not self.interpolateAction.state, 1)
                self.testControl(self.axesAspectAction, not self.axesAspectAction.state, 1)
            # super().runTestParallel() # handled by scan

        def updateTheme(self):
            if self.axesAspectAction is not None:
                self.axesAspectAction.iconFalse = self.scan.makeIcon('aspect_variable_dark.png' if getDarkMode() else 'aspect_variable.png')
                self.axesAspectAction.iconTrue = self.scan.makeIcon('aspect_fixed_dark.png' if getDarkMode() else 'aspect_fixed.png')
                self.axesAspectAction.updateIcon(self.axesAspectAction.state)
            return super().updateTheme()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.useDisplayChannel = True
        self.previewFileTypes.append('.S2D.dat')
        self.previewFileTypes.append('.s2d.h5')

    def initGUI(self):
        super().initGUI()
        self.coupleAction = self.addStateAction(toolTipFalse='Coupled step size.', iconFalse=self.makeIcon('lock-unlock.png'), toolTipTrue='Independent step size.',
                                                     iconTrue=self.makeIcon('lock.png'), before=self.copyAction, attr='coupleStepSize')
        self.limitAction = self.addAction(event=lambda: self.useLimits(), toolTip='Adopts limits from display', icon='ruler.png')
        self.centerAction = self.addAction(event=lambda: self.centerLimits(), toolTip='Center limits around current values.', icon=self.makeIcon('ruler-crop.png'), before=self.copyAction)

    def runTestParallel(self):
        self.raiseDock(True)
        self.testControl(self.coupleAction, self.coupleAction.state)
        self.testControl(self.limitAction, True)
        self.testControl(self.centerAction, True)
        super().runTestParallel()

    def loadDataInternal(self):
        """Loads data in internal standard format for plotting."""
        if self.file.name.endswith('.S2D.dat'):  # legacy ESIBD Control file
            try:
                data = np.flip(np.loadtxt(self.file).transpose())
            except ValueError as e:
                self.print(f'Loading from {self.file.name} failed: {e}', PRINT.ERROR)
                return
            if data.shape[0] == 0:
                self.print(f'No data found in file {self.file.name}', PRINT.ERROR)
                return
            self.addOutputChannel(name='', unit='pA', recordingData=data)
            self.inputs.append(MetaChannel(parentPlugin=self, name='LR Voltage', recordingData=np.arange(0, 1, 1/self.outputs[0].getRecordingData().shape[1]), unit='V'))
            self.inputs.append(MetaChannel(parentPlugin=self, name='UD Voltage', recordingData=np.arange(0, 1, 1/self.outputs[0].getRecordingData().shape[0]), unit='V'))
        elif self.file.name.endswith('.s2d.h5'):
            with h5py.File(self.file, 'r') as h5file:
                is03 = h5file[self.VERSION].attrs['VALUE'] == '0.3' # legacy version 0.3, 0.4 if false
                lr = h5file['S2DSETTINGS']['Left-Right']
                _from, to, step = lr['From'].attrs['VALUE'], lr['To'].attrs['VALUE'], lr['Step'].attrs['VALUE']
                self.inputs.append(MetaChannel(parentPlugin=self, name=lr['Channel'].attrs['VALUE'], recordingData=np.linspace(_from, to, int(abs(_from-to)/abs(step))+1),
                                               unit='V', inout = INOUT.IN))
                ud = h5file['S2DSETTINGS']['Up-Down']
                _from, to, step = ud['From'].attrs['VALUE'], ud['To'].attrs['VALUE'], ud['Step'].attrs['VALUE']
                self.inputs.append(MetaChannel(parentPlugin=self, name=ud['Channel'].attrs['VALUE'], recordingData=np.linspace(_from, to, int(abs(_from-to)/abs(step))+1),
                                               unit='V', inout = INOUT.IN))
                output_group = h5file['Current'] if is03 else h5file['OUTPUTS']
                for name, item in output_group.items():
                    self.addOutputChannel(name=name, unit='pA', recordingData=item[:].transpose())
        else:
            super().loadDataInternal()

    @Scan.finished.setter
    def finished(self, finished):
        Scan.finished.fset(self, finished)
        # disable inputs while scanning
        for direction in [self.LEFTRIGHT, self.UPDOWN]:
            for setting in [self.FROM, self.TO, self.STEP, self.CHANNEL]:
                self.settingsMgr.settings[f'{direction}/{setting}'].setEnabled(finished)

    def estimateScanTime(self):
        if self.LR_from != self.LR_to and self.UD_from != self.UD_to:
            steps = list(itertools.product(self.getSteps(self.LR_from, self.LR_to, self.LR_step), self.getSteps(self.UD_from, self.UD_to, self.UD_step)))
        else:
            self.print('Limits are equal.', PRINT.WARNING)
            return
        seconds = 0 # estimate scan time
        for i in range(len(steps)):
            waitLong = False
            for j in range(len(self.inputs)):
                if not waitLong and abs(steps[i-1][j]-steps[i][j]) > self.largestep:
                    waitLong = True
                    break
            seconds += (self.waitLong if waitLong else self.wait) + self.average
        seconds = round((seconds)/1000)
        self.scantime = f'{seconds//60:02d}:{seconds%60:02d}'

    def centerLimits(self):
        channel = self.getChannelByName(self.LR_channel)
        if channel is not None:
            delta = abs(self.LR_to-self.LR_from)/2
            self.LR_from = channel.value - delta
            self.LR_to = channel.value + delta
        else:
            self.print(f'Could not find channel {self.LR_channel}')
        channel = self.getChannelByName(self.UD_channel)
        if channel is not None:
            delta = abs(self.UD_to-self.UD_from)/2
            self.UD_from = channel.value - delta
            self.UD_to = channel.value + delta
        else:
            self.print(f'Could not find channel {self.UD_channel}')

    def updateStep(self, step):
        if self.coupleAction.state:
            self.LR_step = step
            self.UD_step = step
        self.estimateScanTime()

    def initScan(self):
        return (self.addInputChannel(self.LR_channel, self.LR_from, self.LR_to, self.LR_step) and
        self.addInputChannel(self.UD_channel, self.UD_from, self.UD_to, self.UD_step) and
         super().initScan())

    def getDefaultSettings(self):
        defaultSettings = super().getDefaultSettings()
        defaultSettings[f'{self.LEFTRIGHT}/{self.CHANNEL}'] = parameterDict(value='LA-S-LR', items='LA-S-LR, LC-in-LR, LD-in-LR, LE-in-LR',
                                                                widgetType=Parameter.TYPE.COMBO, attr='LR_channel')
        defaultSettings[f'{self.LEFTRIGHT}/{self.FROM}']    = parameterDict(value=-5, widgetType=Parameter.TYPE.FLOAT, attr='LR_from', event=lambda: self.estimateScanTime())
        defaultSettings[f'{self.LEFTRIGHT}/{self.TO}']      = parameterDict(value=5, widgetType=Parameter.TYPE.FLOAT, attr='LR_to', event=lambda: self.estimateScanTime())
        defaultSettings[f'{self.LEFTRIGHT}/{self.STEP}']    = parameterDict(value=2, widgetType=Parameter.TYPE.FLOAT, attr='LR_step', _min=.1, _max=10, event=lambda: self.updateStep(self.LR_step))
        defaultSettings[f'{self.UPDOWN}/{self.CHANNEL}']    = parameterDict(value='LA-S-UD', items='LA-S-UD, LC-in-UD, LD-in-UD, LE-in-UD',
                                                                widgetType=Parameter.TYPE.COMBO, attr='UD_channel')
        defaultSettings[f'{self.UPDOWN}/{self.FROM}']       = parameterDict(value=-5, widgetType=Parameter.TYPE.FLOAT, attr='UD_from', event=lambda: self.estimateScanTime())
        defaultSettings[f'{self.UPDOWN}/{self.TO}']         = parameterDict(value=5, widgetType=Parameter.TYPE.FLOAT, attr='UD_to', event=lambda: self.estimateScanTime())
        defaultSettings[f'{self.UPDOWN}/{self.STEP}']       = parameterDict(value=2, widgetType=Parameter.TYPE.FLOAT, attr='UD_step', _min=.1, _max=10, event=lambda: self.updateStep(self.UD_step))
        return defaultSettings

    def useLimits(self):
        if self.display is not None and self.display.initializedDock:
            self.LR_from, self.LR_to = self.display.axes[0].get_xlim()
            self.UD_from, self.UD_to = self.display.axes[0].get_ylim()

    def plot(self, update=False, done=True, **kwargs): # pylint:disable=unused-argument
        """Plots 2D scan data"""
        # timing test with 50 data points: update True: 33 ms, update False: 120 ms
        if self.loading or len(self.outputs) == 0:
            return
        x, y = self.getMeshgrid() # data coordinates
        if update:
            z = self.outputs[self.getOutputIndex()].getRecordingData().ravel()
            self.display.cont.set_array(z.ravel())
            self.display.cbar.mappable.set_clim(vmin=np.min(z), vmax=np.max(z))
        else:
            self.display.axes[0].clear() # only update would be preferred but not yet possible with contourf
            self.display.cax.clear()
            if len(self.outputs) > 0:
                self.display.axes[0].set_xlabel(f'{self.inputs[0].name} ({self.inputs[0].unit})')
                self.display.axes[0].set_ylabel(f'{self.inputs[1].name} ({self.inputs[1].unit})')
                if done and self.display.interpolateAction.state:
                    rbf = interpolate.Rbf(x.ravel(), y.ravel(), self.outputs[self.getOutputIndex()].getRecordingData().ravel())
                    xi, yi = self.getMeshgrid(2) # interpolation coordinates, scaling of 1 much faster than 2 and seems to be sufficient
                    zi = rbf(xi, yi)
                    self.display.cont = self.display.axes[0].contourf(xi, yi, zi, levels=100, cmap='afmhot') # contour with interpolation
                else:
                    self.display.cont = self.display.axes[0].pcolormesh(x, y, self.outputs[self.getOutputIndex()].getRecordingData(), cmap='afmhot') # contour without interpolation
                # ax=self.display.axes[0] instead of cax -> colorbar using all available height and does not scale to plot
                self.display.cbar = self.display.fig.colorbar(self.display.cont, cax=self.display.cax) # match axis and color bar size # , format='%d'
                self.display.cbar.ax.set_title(self.outputs[0].unit)
                self.display.axes[-1].cursor = ControlCursor(self.display.axes[-1], colors.highlight) # has to be initialized last, otherwise axis limits may be affected

        if len(self.outputs) > 0 and self.inputs[0].sourceChannel is not None and self.inputs[1].sourceChannel is not None:
            self.display.axes[-1].cursor.setPosition(self.inputs[0].value, self.inputs[1].value)
        self.updateToolBar(update=update)
        if len(self.outputs) > 0:
            self.labelPlot(self.display.axes[0], f'{self.outputs[self.getOutputIndex()].name} from {self.file.name}')
        else:
            self.labelPlot(self.display.axes[0], self.file.name)

    def pythonPlotCode(self):
        return """# add your custom plot code here

_interpolate = False # set to True to interpolate data
varAxesAspect = False # set to True to use variable axes aspect ratio

from mpl_toolkits.axes_grid1 import make_axes_locatable
from scipy import interpolate

fig = plt.figure(constrained_layout=True)
ax = fig.add_subplot(111)
if not varAxesAspect:
    ax.set_aspect('equal', adjustable='box')
divider = make_axes_locatable(ax)
cont = None
cax = divider.append_axes("right", size="5%", pad=0.15)

def getMeshgrid(scaling=1):
    return np.meshgrid(*[np.linspace(i.recordingData[0], i.recordingData[-1], len(i.recordingData) if scaling == 1 else min(len(i.recordingData)*scaling, 50)) for i in inputs])

x, y = getMeshgrid()
z = outputs[output_index].recordingData.ravel()
ax.set_xlabel(f'{inputs[0].name} ({inputs[0].unit})')
ax.set_ylabel(f'{inputs[1].name} ({inputs[1].unit})')

if _interpolate:
    rbf = interpolate.Rbf(x.ravel(), y.ravel(), outputs[output_index].recordingData.ravel())
    xi, yi = getMeshgrid(2) # interpolation coordinates, scaling of 1 much faster than 2 and seems to be sufficient
    zi = rbf(xi, yi)
    cont = ax.contourf(xi, yi, zi, levels=100, cmap='afmhot') # contour with interpolation
else:
    cont = ax.pcolormesh(x, y, outputs[output_index].recordingData, cmap='afmhot') # contour without interpolation
cbar = fig.colorbar(cont, cax=cax) # match axis and color bar size # , format='%d'
cbar.ax.set_title(outputs[0].unit)

plt.show()
        """

    def getMeshgrid(self, scaling=1):
        # interpolation with more than 50 x 50 grid points gets slow and does not add much to the quality for typical scans
        return np.meshgrid(*[np.linspace(i.getRecordingData()[0], i.getRecordingData()[-1], len(i.getRecordingData()) if scaling == 1 else min(len(i.getRecordingData())*scaling, 50)) for i in self.inputs])

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

        def finalizeInit(self, aboutFunc=None):
            self.mouseActive = False
            super().finalizeInit(aboutFunc)
            self.averageAction = self.addStateAction(toolTipFalse='Show average.',
                                                        toolTipTrue='Hide average.',
                                                        iconFalse=self.scan.getIcon(), # defined in updateTheme
                                                        before=self.copyAction,
                                                        event=lambda: (self.initFig(), self.scan.plot(update=False, done=True)), attr='average')
            self.plotModeAction = self.addMultiStateAction(states=[MultiState('stacked', 'Overlay plots.', self.scan.makeIcon('overlay.png')),
                                                               MultiState('overlay', 'Contour plot.', self.scan.makeIcon('beam.png')),
                                                               MultiState('contour', 'Stack plots.', self.scan.makeIcon('stacked.png'))], before=self.copyAction,
                                                        event=lambda: (self.initFig(), self.scan.plot(update=False, done=True)), attr='plotMode')
            self.updateTheme() # set icons
            self.initFig() # call after finalizeInit completed

        def initFig(self):
            if self.plotModeAction is None:
                return
            self.lines = None
            if self.plotModeAction.state == self.plotModeAction.labels.contour:
                super().initFig()
                return
            super(Beam.Display, self).initFig()
            self.axes.append(self.fig.add_subplot(111))
            if not self.axesAspectAction.state: # use qSet directly in case control is not yet initialized
                self.axes[0].set_aspect('equal', adjustable='box')

        def updateTheme(self):
            if self.averageAction is not None:
                self.averageAction.iconFalse = self.scan.makeIcon('average_dark.png' if getDarkMode() else 'average_light.png')
                self.averageAction.iconTrue = self.averageAction.iconFalse
                self.averageAction.updateIcon(self.averageAction.state)
            return super().updateTheme()

    def __init__(self, **kwargs):
        super(Beam, self).__init__(**kwargs)
        self.useDisplayChannel = True
        self.previewFileTypes.append('beam.h5')

    def initScan(self):
        self.toggleDisplay(True)
        self.display.lines = None
        return super().initScan()

    def loadDataInternal(self):
        self.display.lines = None
        if self.file.name.endswith('beam.h5'):
            with h5py.File(self.file, 'r') as h5file:
                group = h5file[self.pluginManager.Beam.name] # only modification needed to open beam files. data structure is identical
                input_group = group[self.INPUTCHANNELS]
                for name, data in input_group.items():
                    self.inputs.append(MetaChannel(parentPlugin=self, name=name, recordingData=data[:], unit=data.attrs[self.UNIT], inout=INOUT.IN))
                output_group = group[self.OUTPUTCHANNELS]
                for name, data in output_group.items():
                    self.addOutputChannel(name=name, unit=data.attrs[self.UNIT], recordingData=data[:])
        else:
            return super(Beam, self).loadDataInternal()

    def plot(self, update=False, done=True, **kwargs): # pylint:disable=unused-argument
        """Plots 2D scan data"""
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
            self.display.lines = [] # dummy plots
            for i, z in enumerate(self.outputs[self.getOutputIndex()].getRecordingData()):
                if self.display.plotModeAction.state == self.display.plotModeAction.labels.stacked:
                    self.display.lines.append(self.display.axes[0].plot([], [])[0])
                else: # self.display.plotModeAction.labels.overlay
                    self.display.lines.append(self.display.axes[0].plot([], [], label=y[i])[0])
            if self.display.averageAction.state:
                if self.display.plotModeAction.state == self.display.plotModeAction.labels.stacked:
                    self.display.lines.append(self.display.axes[0].plot([], [], linewidth=4)[0])
                else: # self.display.plotModeAction.labels.overlay
                    self.display.lines.append(self.display.axes[0].plot([], [], label='avg', linewidth=4)[0])
            if self.display.plotModeAction.state == self.display.plotModeAction.labels.overlay:
                legend = self.display.axes[0].legend(loc='best', prop={'size': 10}, frameon=False)
                legend.set_in_layout(False)

        if not update:
            self.display.axes[0].set_xlabel(f'{self.inputs[0].name} ({self.inputs[0].unit})')
            self.display.axes[0].set_ylabel(f'{self.inputs[1].name} ({self.inputs[1].unit})')
        for i, z in enumerate(self.outputs[self.getOutputIndex()].getRecordingData()):
            if self.display.plotModeAction.state == self.display.plotModeAction.labels.stacked:
                if np.abs(z.max()-z.min()) != 0:
                    z = z/(np.abs(z.max()-z.min()))*np.abs(y[1]-y[0])
                self.display.lines[i].set_data(x, z + y[i] - z[0])
            else: # self.display.plotModeAction.labels.overlay
                self.display.lines[i].set_data(x, z)
        if self.display.averageAction.state:
            z = np.mean(self.outputs[self.getOutputIndex()].getRecordingData(), 0)
            if self.display.plotModeAction.state == self.display.plotModeAction.labels.stacked:
                if np.abs(z.max()-z.min()) != 0:
                    z = z/(np.abs(z.max()-z.min()))*np.abs(y[1]-y[0])
                self.display.lines[-1].set_data(x, z + y[-1] + y[1]-y[0] - z[0])
            else: # self.display.plotModeAction.labels.overlay
                self.display.lines[-1].set_data(x, z)

        self.display.axes[0].relim() # adjust to data
        self.setLabelMargin(self.display.axes[0], 0.15)
        self.updateToolBar(update=update)
        if len(self.outputs) > 0:
            self.labelPlot(self.display.axes[0], f'{self.outputs[self.getOutputIndex()].name} from {self.file.name}')
        else:
            self.labelPlot(self.display.axes[0], self.file.name)

    def run(self, recording):
        """Steps through input values, records output values, and triggers plot update.
        Executed in runThread. Will likely need to be adapted for custom scans."""
        # definition of steps updated to scan along x instead of y axis.
        steps = [tuple[::-1] for tuple in list(itertools.product(*[i.getRecordingData() for i in [self.inputs[1], self.inputs[0]]]))]
        self.print(f'Starting scan M{self.pluginManager.Settings.measurementNumber:03}. Estimated time: {self.scantime}')
        for i, step in enumerate(steps): # scan over all steps
            waitLong = False
            for j, _input in enumerate(self.inputs):
                if not waitLong and abs(_input.value-step[j]) > self.largestep:
                    waitLong=True
                _input.updateValueSignal.emit(step[j])
            time.sleep(((self.waitLong if waitLong else self.wait)+self.average)/1000) # if step is larger than threshold use longer wait time
            for j, output in enumerate(self.outputs):
                # 2D scan
                # definition updated to scan along x instead of y axis.
                output.recordingData[i//len(self.inputs[0].getRecordingData()), i%len(self.inputs[0].getRecordingData())] = np.mean(output.getValues(
                    subtractBackground=output.getDevice().subtractBackgroundActive(), length=self.measurementsPerStep))
            if i == len(steps)-1 or not recording(): # last step
                for j, _input in enumerate(self.inputs):
                    _input.updateValueSignal.emit(_input.initialValue)
                time.sleep(.5) # allow time to reset to initial value before saving
                self.signalComm.scanUpdateSignal.emit(True) # update graph and save data
                self.signalComm.updateRecordingSignal.emit(False)
                break # in case this is last step
            else:
                self.signalComm.scanUpdateSignal.emit(False) # update graph

    def pythonPlotCode(self):
        return """# add your custom plot code here

_interpolate = False # set to True to interpolate data
varAxesAspect = False # set to True to use variable axes aspect ratio
average = False # set to true to display an average spectrum
plotMode = 'stacked' # 'stacked', 'overlay', or 'contour' # select the representation of your data

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
        xi, yi = getMeshgrid(2) # interpolation coordinates, scaling of 1 much faster than 2 and seems to be sufficient
        zi = rbf(xi, yi)
        cont = ax.contourf(xi, yi, zi, levels=100, cmap='afmhot') # contour with interpolation
    else:
        cont = ax.pcolormesh(x, y, outputs[output_index].recordingData, cmap='afmhot') # contour without interpolation
    cbar = fig.colorbar(cont, cax=cax) # match axis and color bar size # , format='%d'
    cbar.ax.set_title(outputs[0].unit)
else:
    x = np.linspace(inputs[0].recordingData[0], inputs[0].recordingData[-1], len(inputs[0].recordingData))
    y = np.linspace(inputs[1].recordingData[0], inputs[1].recordingData[-1], len(inputs[1].recordingData))
    for i, z in enumerate(outputs[output_index].recordingData):
        if plotMode == 'stacked':
            if np.abs(z.max()-z.min()) != 0:
                z = z/(np.abs(z.max()-z.min()))*np.abs(y[1]-y[0])
            ax.plot(x, z + y[i] - z[0])
        else: # 'overlay'
            ax.plot(x, z, label=y[i])
    if average:
        z = np.mean(outputs[output_index].recordingData, 0)
        if plotMode == 'stacked':
            if np.abs(z.max()-z.min()) != 0:
                z = z/(np.abs(z.max()-z.min()))*np.abs(y[1]-y[0])
            ax.plot(x, z + y[-1] + y[1]-y[0] - z[0], linewidth=4)
        else: # 'overlay'
            ax.plot(x, z, label='avg', linewidth=4)
    if plotMode == 'overlay':
        legend = ax.legend(loc='best', prop={'size': 10}, frameon=False)
        legend.set_in_layout(False)
plt.show()
        """

class Energy(Scan):
    """Scan that records the current on one electrode, typically a detector plate, as a
    function of one potential, typically a retarding grid. The display
    shows the measured transmission data, a discrete derivative,
    and a Gaussian fit that reveals beam-energy center and width. The
    potential on the selected channel can be changed by clicking and
    dragging on the image while holding down the Ctrl key."""
    documentation = None # use __doc__

    name = 'Energy'
    version = '1.0'
    pluginType = PluginManager.TYPE.SCAN
    iconFile = 'energy.png'

    class Display(Scan.Display):
        """Display for energy scan."""

        def initGUI(self):
            """Initialize GUI"""
            super().initGUI()
            self.mouseActive = True

        def initFig(self):
            super().initFig()
            self.axes.append(self.fig.add_subplot(111))
            self.axes.append(self.axes[0].twinx()) # creating twin axis
            self.canvas.mpl_connect('motion_notify_event', self.mouseEvent)
            self.canvas.mpl_connect('button_press_event', self.mouseEvent)
            self.canvas.mpl_connect('button_release_event', self.mouseEvent)
            self.axes[0].yaxis.label.set_color(self.scan.MYBLUE)
            self.axes[0].tick_params(axis='y', colors=self.scan.MYBLUE)
            self.axes[1].set_ylabel('-dI/dV (%)')
            self.axes[1].set_ylim([0, 115]) # keep top 15 % for label
            self.axes[1].yaxis.label.set_color(self.scan.MYRED)
            self.axes[1].tick_params(axis='y', colors=self.scan.MYRED)
            self.seRaw  = self.axes[0].plot([],[], marker='.', linestyle='None', color=self.scan.MYBLUE, label='.')[0] # dummy plot
            self.seGrad = self.axes[1].plot([],[], marker='.', linestyle='None', color=self.scan.MYRED)[0] # dummy plot
            self.seFit  = self.axes[1].plot([],[], color=self.scan.MYRED)[0] # dummy plot
            self.axes[-1].cursor = None

    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.useDisplayChannel = True
        self.previewFileTypes.append('.swp.dat')
        self.previewFileTypes.append('.swp.h5')

    def loadDataInternal(self):
        """Loads data in internal standard format for plotting."""
        if self.file.name.endswith('.swp.dat'): # legacy ESIBD Control file
            headers = []
            with open(self.file, 'r', encoding=self.UTF8) as dataFile:
                dataFile.readline()
                headers = dataFile.readline().split(',')[1:][::2] # read names from second line
            try:
                data = np.loadtxt(self.file, skiprows=4, delimiter=',', unpack=True)
            except ValueError as e:
                self.print(f'Loading from {self.file.name} failed: {e}', PRINT.ERROR)
                return
            if data.shape[0] == 0:
                self.print(f'No data found in file {self.file.name}.', PRINT.ERROR)
                return
            self.inputs.append(MetaChannel(parentPlugin=self, name='Voltage', recordingData=data[0], unit='V'))
            for name, dat in zip(headers, data[1:][::2]):
                self.addOutputChannel(name=name.strip(), unit='pA', recordingData=dat)
        elif self.file.name.endswith('.swp.h5'):
            with h5py.File(self.file, 'r') as h5file:
                is03 = h5file[self.VERSION].attrs['VALUE'] == '0.3' # legacy version 0.3, 0.4 if false
                self.inputs.append(MetaChannel(parentPlugin=self, name=h5file['SESETTINGS']['Channel'].attrs['VALUE'], recordingData=h5file['Voltage'][:] if is03 else h5file['INPUT'][:],
                                               unit='V', inout=INOUT.IN))
                output_group = h5file['Current'] if is03 else h5file['OUTPUTS']
                for name, item in output_group.items():
                    self.addOutputChannel(name=name, unit='pA', recordingData=item[:])
        else:
            super().loadDataInternal()

    def getDefaultSettings(self):
        defaultSettings = super().getDefaultSettings()
        defaultSettings[self.WAIT][Parameter.VALUE] = 2000
        defaultSettings[self.CHANNEL] = parameterDict(value='RT_Grid', toolTip='Electrode that is swept through.', items='RT_Grid, RT_Sample-Center, RT_Sample-End',
                                                                      widgetType=Parameter.TYPE.COMBO, attr='channel')
        defaultSettings[self.FROM]    = parameterDict(value=-10, widgetType=Parameter.TYPE.FLOAT, attr='_from', event=lambda: self.estimateScanTime())
        defaultSettings[self.TO]      = parameterDict(value=-5, widgetType=Parameter.TYPE.FLOAT, attr='to', event=lambda: self.estimateScanTime())
        defaultSettings[self.STEP]    = parameterDict(value=.2, widgetType=Parameter.TYPE.FLOAT, attr='step', _min=.1, _max=10, event=lambda: self.estimateScanTime())
        return defaultSettings

    def initScan(self):
        return (self.addInputChannel(self.channel, self._from, self.to, self.step) and super().initScan())

    def map_percent(self, x):
        """Maps any range on range 0 to 100."""
        # can't map if largest deviation from minimum is 0, i.e. all zero
        # has to return a sequence as matplotlib now expects sequences for set_x(y)data
        return (x-np.min(x))/np.max(x-np.min(x))*100 if np.max(x-np.min(x)) > 0 else [0]

    def plot(self, update=False, done=True, **kwargs):  # pylint:disable=unused-argument
        """Plots energy scan data including metadata"""
        # use first that matches display setting, use first available if not found
        # timing test with 20 data points: update True: 30 ms, update False: 48 ms
        if len(self.outputs) > 0:
            y = np.diff(self.outputs[self.getOutputIndex()].getRecordingData())/np.diff(self.inputs[0].getRecordingData())
            x = self.inputs[0].getRecordingData()[:y.shape[0]]+np.diff(self.inputs[0].getRecordingData())[0]/2 # use as many data points as needed
            if update: # only update data
                self.display.seRaw.set_data(self.inputs[0].getRecordingData(), self.outputs[self.getOutputIndex()].getRecordingData())
                self.display.seGrad.set_data(x, self.map_percent(-y))
            else:
                self.removeAnnotations(self.display.axes[1])
                if len(self.outputs) > 0:
                    self.display.axes[0].set_xlim(self.inputs[0].getRecordingData()[0], self.inputs[0].getRecordingData()[-1])
                    self.display.axes[0].set_ylabel(f'{self.outputs[self.getOutputIndex()].name} {self.outputs[self.getOutputIndex()].unit}')
                    self.display.axes[0].set_xlabel(f'{self.inputs[0].name} ({self.inputs[0].unit})')
                    self.display.seRaw.set_data(self.inputs[0].getRecordingData(), self.outputs[self.getOutputIndex()].getRecordingData())
                    self.display.seFit.set_data([],[]) # init
                    self.display.seGrad.set_data(x, self.map_percent(-y))
                    for ann in [child for child in self.display.axes[1].get_children() if isinstance(child, mpl.text.Annotation)]:
                        ann.remove()
                    if done:
                        try:
                            x_fit, y_fit, expected_value, fwhm = self.gauss_fit(x, y, np.mean(x)) # use center as starting guess
                            if self.inputs[0].getRecordingData()[0] <= expected_value <= self.inputs[0].getRecordingData()[-1]:
                                self.display.seFit.set_data(x_fit, self.map_percent(y_fit))
                                self.display.axes[1].annotate(text='', xy=(expected_value-fwhm/2.3, 50), xycoords='data', xytext=(expected_value+fwhm/2.3, 50), textcoords='data',
                        	        arrowprops=dict(arrowstyle="<->", color=self.MYRED), va='center')
                                self.display.axes[1].annotate(text=f'center: {expected_value:2.1f} V\nFWHM: {fwhm:2.1f} V', xy=(expected_value-fwhm/1.6, 50), xycoords='data', fontsize=10.0,
                                    textcoords='data', ha='right', va='center', color=self.MYRED)
                                #self.display.axes[1].set_xlim([u-3*fwhm, u+3*fwhm]) # can screw up x range if fit fails
                            else:
                                self.print('Fitted mean outside data range. Ignore fit.', PRINT.ERROR)
                        except (RuntimeError, ValueError) as e:
                            self.print(f'Fit failed with error: {e}')
                    self.display.axes[-1].cursor = ControlCursor(self.display.axes[-1], colors.highlight, horizOn=False) # has to be initialized last, otherwise axis limits may be affected
                else: # no data
                    self.display.seRaw.set_data([],[])
                    self.display.seFit.set_data([],[])
                    self.display.seGrad.set_data([],[])
            self.display.axes[0].relim() # adjust to data
            self.setLabelMargin(self.display.axes[0], 0.15)
        if len(self.outputs) > 0 and self.inputs[0].sourceChannel is not None:
            self.display.axes[-1].cursor.setPosition(self.inputs[0].value, 0)
        self.updateToolBar(update=update)
        if len(self.outputs) > 0:
            self.labelPlot(self.display.axes[0], f'{self.outputs[self.getOutputIndex()].name} from {self.file.name}')
        else:
            self.labelPlot(self.display.axes[0], self.file.name)

    def pythonPlotCode(self):
        return """# add your custom plot code here

MYBLUE='#1f77b4'
MYRED='#d62728'

from scipy import optimize

def map_percent(x):
    return (x-np.min(x))/np.max(x-np.min(x))*100 if np.max(x-np.min(x) > 0) else 0

def gaussian(x, amp1, cen1, sigma1):
    return amp1*(1/(sigma1*(np.sqrt(2*np.pi))))*(np.exp(-((x-cen1)**2)/(2*(sigma1)**2)))

def gauss_fit(x, y, c):
    amp1 = 100
    sigma1 = 2
    gauss, *_ = optimize.curve_fit(gaussian, x, y, p0=[amp1, c, sigma1])
    fwhm = round(2.355 * gauss[2], 1) # Calculate FWHM
    x_fine=np.arange(np.min(x), np.max(x), 0.05)
    return x_fine,-gaussian(x_fine, gauss[0], gauss[1], gauss[2]), gauss[1], fwhm

fig = plt.figure(constrained_layout=True)
ax0 = fig.add_subplot(111)
ax1 = ax0.twinx()
ax0.yaxis.label.set_color(MYBLUE)
ax0.tick_params(axis='y', colors=MYBLUE)
ax1.set_ylabel('-dI/dV (%)')
ax1.yaxis.label.set_color(MYRED)
ax1.tick_params(axis='y', colors=MYRED)

y = np.diff(outputs[output_index].recordingData)/np.diff(inputs[0].recordingData)
x = inputs[0].recordingData[:y.shape[0]]+np.diff(inputs[0].recordingData)[0]/2

ax0.set_xlim(inputs[0].recordingData[0], inputs[0].recordingData[-1])
ax0.set_ylabel(f'{outputs[output_index].name} ({outputs[output_index].unit})')
ax0.set_xlabel(f'{inputs[0].name} ({inputs[0].unit})')

ax0.plot(inputs[0].recordingData, outputs[output_index].recordingData, marker='.', linestyle='None', color=MYBLUE, label='.')[0]
ax1.plot(x, map_percent(-y), marker='.', linestyle='None', color=MYRED)[0]

try:
    x_fit, y_fit, expected_value, fwhm = gauss_fit(x, y, np.mean(x))
    if inputs[0].recordingData[0] <= expected_value <= inputs[0].recordingData[-1]:
        ax1.plot(x_fit, map_percent(y_fit), color=MYRED)[0]
        ax1.annotate(text='', xy=(expected_value-fwhm/2.3, 50), xycoords='data', xytext=(expected_value+fwhm/2.3, 50), textcoords='data',
	        arrowprops=dict(arrowstyle="<->", color=MYRED), va='center')
        ax1.annotate(text=f'center: {expected_value:2.1f} V\\nFWHM: {fwhm:2.1f} V', xy=(expected_value-fwhm/1.6, 50), xycoords='data', fontsize=10.0,
            textcoords='data', ha='right', va='center', color=MYRED)
    else:
        print('Fitted mean outside data range. Ignore fit.')
except RuntimeError as e:
    print(f'Fit failed with error: {e}')

plt.show()
        """

    def gaussian(self, x, amp1, cen1, sigma1):
        return amp1*(1/(sigma1*(np.sqrt(2*np.pi))))*(np.exp(-((x-cen1)**2)/(2*(sigma1)**2)))

    def gauss_fit(self, x, y, c):
        # Define a gaussian to start with
        amp1 = 100
        sigma1 = 2
        gauss, *_ = optimize.curve_fit(self.gaussian, x, y, p0=[amp1, c, sigma1])
        fwhm = round(2.355 * gauss[2], 1) # Calculate FWHM
        x_fine=np.arange(np.min(x), np.max(x), 0.05)
        return x_fine,-self.gaussian(x_fine, gauss[0], gauss[1], gauss[2]), gauss[1], fwhm

class Omni(Scan):
    """This is the most basic scan which simply records a number of arbitrary output
    channels as a function of a single arbitrary input channel. When switched to the
    interactive mode, a slider will appear that allows to set the value of
    the input channel manually and independent of the scan settings. This
    may be more intuitive and faster than automated scanning, e.g. when looking for a local maximum."""
    documentation = None # use __doc__

    name = 'Omni'
    version = '1.0'
    pluginType = PluginManager.TYPE.SCAN
    useDisplayParameter = True
    iconFile = 'omni.png'

    class Display(Scan.Display):
        """Display for energy scan."""

        def __init__(self, scan, **kwargs):
            super().__init__(scan, **kwargs)
            self.xSlider = None
            self.lines = None

        def initFig(self):
            super().initFig()
            self.lines = None
            self.axes = []
            self.axes.append(self.fig.add_subplot(111))
            if self.xSlider is not None:
                self.xSlider.deleteLater()
            self.xSlider = QSlider(Qt.Orientation.Horizontal)
            self.vertLayout.addWidget(self.xSlider)
            self.xSlider.valueChanged.connect(self.updateX)
            self.updateInteractive()

        def updateX(self, value):
            if self.scan.inputs[0].sourceChannel is not None:
                self.scan.inputs[0].value = self.scan._from + value/self.xSlider.maximum()*(self.scan.to - self.scan._from) # map slider range onto range

        def updateInteractive(self):
            if self.xSlider is not None:
                self.xSlider.setVisible(self.scan.interactive)
                if self.scan.interactive and len(self.scan.inputs) > 0:
                    self.xSlider.setValue(int((self.scan.inputs[0].value - self.scan.inputs[0].min)*
                                              self.xSlider.maximum()/(self.scan.inputs[0].max - self.scan.inputs[0].min)))

    def getDefaultSettings(self):
        defaultSettings = super().getDefaultSettings()
        defaultSettings[self.WAIT][Parameter.VALUE] = 2000
        defaultSettings[self.CHANNEL] = parameterDict(value='RT_Grid', toolTip='Electrode that is swept through', items='RT_Grid, RT_Sample-Center, RT_Sample-End',
                                                                      widgetType=Parameter.TYPE.COMBO, attr='channel')
        defaultSettings[self.FROM]    = parameterDict(value=-10, widgetType=Parameter.TYPE.FLOAT, attr='_from', event=lambda: self.estimateScanTime())
        defaultSettings[self.TO]      = parameterDict(value=-5, widgetType=Parameter.TYPE.FLOAT, attr='to', event=lambda: self.estimateScanTime())
        defaultSettings[self.STEP]    = parameterDict(value=.2, widgetType=Parameter.TYPE.FLOAT, attr='step', _min=.1, _max=10, event=lambda: self.estimateScanTime())
        self.BINS = 'Bins'
        defaultSettings[self.BINS]    = parameterDict(value=20, widgetType=Parameter.TYPE.INT, _min=10, _max=200, attr='bins')
        self.INTERACTIVE = 'Interactive'
        defaultSettings[self.INTERACTIVE]    = parameterDict(value=False, widgetType=Parameter.TYPE.BOOL,
        toolTip='Use the slider to define channel value in interactive mode.\nUse short wait and average when possible to get fast feedback.\nStop scan when done.',
                                                attr='interactive', event=lambda: self.updateInteractive())
        return defaultSettings

    def updateInteractive(self):
        if self.display is not None and self.display.initializedDock:
            self.display.updateInteractive()
        self.estimateScanTime()

    @Scan.finished.setter
    def finished(self, finished):
        Scan.finished.fset(self, finished)
        # disable inputs while scanning
        self.settingsMgr.settings[self.INTERACTIVE].setEnabled(finished)

    def estimateScanTime(self):
        if self.interactive:
            self.scantime = 'n/a'
        else:
            super().estimateScanTime()

    def initScan(self):
        if (self.addInputChannel(self.channel, self._from, self.to, self.step) and super().initScan()):
            self.toggleDisplay(True)
            self.display.lines = None
            self.display.updateInteractive()
            if self.interactive:
                self.inputs[0].recordingData = DynamicNp()
                for output in self.outputs:
                    output.recordingData = DynamicNp()
            return True
        return False

    def loadDataInternal(self):
        super().loadDataInternal()
        self.display.lines = None

    def plot(self, update=False, done=True, **kwargs):  # pylint:disable=unused-argument
        """Plots omni scan data."""
        if len(self.outputs) > 0:
            if self.display.lines is None:
                self.display.axes[0].clear()
                self.display.lines = [] # dummy plots
                for output in self.outputs:
                    if output.sourceChannel is not None:
                        self.display.lines.append(self.display.axes[0].plot([], [], label=f'{output.name} ({output.unit})', color=output.color)[0])
                    else:
                        self.display.lines.append(self.display.axes[0].plot([], [], label=f'{output.name} ({output.unit})')[0])
                # self.labelPlot(self.display.axes[0], self.file.name) # text ignored loc='best' https://github.com/matplotlib/matplotlib/issues/23323
                legend = self.display.axes[0].legend(loc='best', prop={'size': 7}, frameon=False)
                legend.set_in_layout(False)
            if not update:
                self.display.axes[0].set_xlabel(f'{self.inputs[0].name} ({self.inputs[0].unit})')
                if self.recording: # show all data if loaded from file
                    self.display.axes[0].set_xlim(self._from, self.to)
            if self.interactive:
                for i, output in enumerate(self.outputs):
                    if output.display:
                        x = self.inputs[0].getRecordingData()
                        y = output.getRecordingData()
                        mean, bin_edges, _ = binned_statistic(x, y, bins=self.bins, range=(int(self._from), int(self.to)))
                        self.display.lines[i].set_data((bin_edges[:-1] + bin_edges[1:]) / 2, mean)
                    else:
                        self.display.lines[i].set_data([], [])
            else:
                for i, output in enumerate(self.outputs):
                    if output.display:
                        self.display.lines[i].set_data(self.inputs[0].getRecordingData(), output.getRecordingData())
                    else:
                        self.display.lines[i].set_data([], [])
            self.display.axes[0].relim() # adjust to data
            self.setLabelMargin(self.display.axes[0], 0.15)
        self.updateToolBar(update=update)
        self.labelPlot(self.display.axes[0], self.file.name)

    def pythonPlotCode(self):
        return """# add your custom plot code here
from scipy.stats import binned_statistic

_interactive = False # set to True to use histogram
bins = 20 # choose number of bins
_from   = min(inputs[0].recordingData)
to      = max(inputs[0].recordingData)

fig = plt.figure(constrained_layout=True)
ax0 = fig.add_subplot(111)
ax0.set_xlabel(f'{inputs[0].name} ({inputs[0].unit})')
for output in outputs:
    if _interactive:
        mean, bin_edges, _ = binned_statistic(inputs[0].recordingData, output.recordingData, bins=bins, range=(int(_from), int(to)))
        ax0.plot((bin_edges[:-1] + bin_edges[1:]) / 2, mean, label=f'{output.name} ({output.unit})')
    else:
        ax0.plot(inputs[0].recordingData, output.recordingData, label=f'{output.name} ({output.unit})')
ax0.legend(loc='best', prop={'size': 7}, frameon=False)
plt.show()
        """ # similar to staticDisplay

    def run(self, recording):
        if self.interactive:
            while recording():
                # changing input is done in main thread using slider. Scan is only recording result.
                time.sleep((self.wait+self.average)/1000) # if step is larger than threshold use longer wait time
                if self.inputs[0].recording: # get average
                    self.inputs[0].recordingData.add(np.mean(self.inputs[0].getValues(subtractBackground=self.inputs[0].subtractBackgroundActive(), length=self.measurementsPerStep)))
                else: # use last value
                    self.inputs[0].recordingData.add(self.inputs[0].value)
                for j, output in enumerate(self.outputs):
                    self.outputs[j].recordingData.add(np.mean(output.getValues(subtractBackground=output.subtractBackgroundActive(), length=self.measurementsPerStep)))
                if not recording(): # last step
                    self.signalComm.scanUpdateSignal.emit(True) # update graph and save data
                    self.signalComm.updateRecordingSignal.emit(False)
                else:
                    self.signalComm.scanUpdateSignal.emit(False) # update graph
        else:
            steps = self.inputs[0].getRecordingData()
            self.print(f'Starting scan M{self.pluginManager.Settings.measurementNumber:03}. Estimated time: {self.scantime}')
            for i, step in enumerate(steps): # scan over all steps
                waitLong = False
                if not waitLong and abs(self.inputs[0].value-step) > self.largestep:
                    waitLong=True
                self.inputs[0].updateValueSignal.emit(step)
                time.sleep(((self.waitLong if waitLong else self.wait)+self.average)/1000) # if step is larger than threshold use longer wait time
                for j, output in enumerate(self.outputs):
                    output.recordingData[i] = np.mean(output.getValues(subtractBackground=output.getDevice().subtractBackgroundActive(), length=self.measurementsPerStep))
                if i == len(steps)-1 or not recording(): # last step
                    self.inputs[0].updateValueSignal.emit(self.inputs[0].initialValue)
                    time.sleep(.5) # allow time to reset to initial value before saving
                    self.signalComm.scanUpdateSignal.emit(True) # update graph and save data
                    self.signalComm.updateRecordingSignal.emit(False)
                    break # in case this is last step
                else:
                    self.signalComm.scanUpdateSignal.emit(False) # update graph

class Depo(Scan):
    """Scan that records the sample current and accumulated charge during deposition. A
    target charge and current threshold can be defined and a message will be
    played back when the target has been reached or the current drops below
    the threshold. The time until completion is estimated based on recent data.
    As data analysis is decoupled from data
    acquisition, you can continue to use all other scan modes and
    optimization while the deposition recording is running."""
    documentation = None # use __doc__

    name = 'Depo'
    version = '1.0'
    pluginType = PluginManager.TYPE.SCAN
    CHARGE = 'Charge'
    useDisplayParameter = True
    iconFile = 'depo.png'

    class ScanChannel(ScanChannel):

        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.isChargeChannel = False

        def relayValueEvent(self):
            if self.sourceChannel is not None:
                try:
                    if self.isChargeChannel:
                        self.value = self.sourceChannel.charge
                    elif self.sourceChannel.useMonitors:
                        self.value = self.sourceChannel.monitor
                    else:
                        self.value = self.sourceChannel.value - self.sourceChannel.background if self.sourceChannel.getDevice().subtractBackgroundActive() else self.sourceChannel.value
                except RuntimeError:
                    self.removeEvents()

        def initGUI(self, item):
            super().initGUI(item)
            if self.name.endswith(f'_{Depo.CHARGE}') and self.unit == 'pAh':
                self.isChargeChannel = True
                self.name = self.name.removesuffix(f'_{Depo.CHARGE}') # change name before connectSource()!

        def connectSource(self):
            super().connectSource()
            if self.isChargeChannel:
                self.unit = 'pAh'
                self.name = self.name + f'_{Depo.CHARGE}'
            if self.sourceChannel is not None and not hasattr(self.sourceChannel, 'resetCharge'):
                # found channel with same name but likely from different device
                super().connectSource() # running again after changing name -> disconnect
            if self.unit in ['pA','pAh']:
                self.getParameterByName(self.DISPLAY).getWidget().setVisible(False)

    class Display(Scan.Display):
        """Display for depo scan."""

        class CustomScientificFormatter(ScalarFormatter):
            """custom formatter that prevents waste of vertical space by offset or scale factor.
            There is still an issue with very large or very small values if log=False.
            In that case the corresponding device should use self.logY = True"""
            def __init__(self, log=False, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.log=log
                self.set_scientific(True)  # Enable scientific notation
                self.set_useOffset(False)  # Disable the offset/scaling factor above the axis

            def _set_format(self):
                """Override the default format behavior to suppress scaling."""
                self._useMathText = True
                if self.log:
                    self.format = "%.1e"  # Format ticks in scientific notation (e.g., 1.0e-10)
                else:
                    self.format = "%.1f"  # Format ticks in normal notation

        def initFig(self):
            super().initFig()
            self.fig.set_constrained_layout_pads(h_pad=-4.0) # reduce space between axes
            rows = len(self.scan.getExtraUnits()) + 2
            self.axes.append(self.fig.add_subplot(rows, 1, 1)) # current axis
            self.axes.append(self.fig.add_subplot(rows ,1, 2, sharex = self.axes[0])) # charge axis
            for i, unit in enumerate(self.scan.getExtraUnits()):
                self.axes.append(self.fig.add_subplot(rows, 1, 3+i, sharex = self.axes[0]))
                self.axes[2+i].set_ylabel(unit)
            for output in self.scan.outputs:
                if output.unit not in ['pA', 'pAh'] and output.unit in self.scan.getExtraUnits():
                    output.line = self.axes[2+self.scan.getExtraUnits().index(output.unit)].plot([[datetime.now()]], [0], color=output.color, label=output.name)[0]
                    if output.logY:
                        self.axes[2+self.scan.getExtraUnits().index(output.unit)].set_yscale('log')
                    self.axes[2+self.scan.getExtraUnits().index(output.unit)].get_yaxis().set_major_formatter(self.CustomScientificFormatter(log=output.logY))
                # self.axes[2+i].get_yaxis().set_major_formatter(mpl.ticker.FuncFormatter(lambda x, p: self.scientificNotation(x)))
            for i, unit in enumerate(self.scan.getExtraUnits()):
                legend = self.axes[2+i].legend(loc='best', prop={'size': 6}, frameon=False)
                legend.set_in_layout(False)

            selected_output = self.scan.outputs[self.scan.getOutputIndex()]
            self.currentLine        = self.axes[0].plot([[datetime.now()]],[0], color=selected_output.color)[0] # need to be initialized with datetime on x axis
            self.currentWarnLine    = self.axes[0].axhline(y=float(self.scan.warnLevel), color=self.scan.MYRED)
            self.chargeLine         = self.axes[1].plot([[datetime.now()]],[0], color=selected_output.color)[0]
            self.chargePredictionLine = self.axes[1].plot([[datetime.now()]],[0], '--', color=selected_output.color)[0]
            self.depoChargeTarget   = self.axes[1].axhline(y=float(self.scan.target), color=self.scan.MYGREEN)
            for i in range(len(self.axes)-1):
                self.axes[i].tick_params(axis='x', which='both', bottom=False, labelbottom=False)
            for i in range(len(self.axes)):
                self.addRightAxis(self.axes[i])
            self.axes[0].set_ylabel('pA')
            self.axes[1].set_ylabel('pAh')
            self.axes[-1].set_xlabel(self.TIME)
            self.axes[-1].xaxis.set_major_formatter(mdates.DateFormatter('%H:%M')) # auto formatting will resort to only year if space is limited -> fix format
            self.tilt_xlabels(self.axes[-1])
            self.progressAnnotation = self.axes[1].annotate(text='', xy=(0.02, 0.98), xycoords='axes fraction', fontsize=6, ha='left', va='top',
                                                            bbox=dict(boxstyle='square, pad=.2', fc=plt.rcParams['axes.facecolor'], ec='none'))
            # self.fig.xticks(rotation = 30)

        def updateDepoTarget(self):
            if self.depoChargeTarget is not None:
                self.depoChargeTarget.set_ydata([self.scan.target])
                if np.sign(self.scan.target) == 1:
                    self.axes[0].set_ylim(0, 1)
                    self.axes[1].set_ylim(0, 1)
                else:
                    self.axes[0].set_ylim(1, 0)
                    self.axes[1].set_ylim(1, 0)
                self.axes[0].autoscale(self.scan.autoscale, axis='y')
                self.axes[0].autoscale(True, axis='x')
                self.axes[0].relim()
                self.axes[1].autoscale(True)
                self.axes[1].relim()
                self.canvas.draw_idle()

    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.useDisplayChannel = True

    def initGUI(self):
        super().initGUI()
        self.recordingAction.setToolTip('Toggle deposition.')
        self.depoCheckList = QLabel()
        self.depoCheckList.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        self.depoCheckList.setText('Deposition checklist:\nPlasma cleaned?\nGrid in place?\nShield closed?\nShuttle inserted?\nLanding energy set?\nRight polarity?\nTemperature set?\nMass selection on?\nNitrogen ready for transfer?')
        self.settingsLayout.addWidget(self.depoCheckList, alignment=Qt.AlignmentFlag.AlignTop)

    def getExtraUnits(self):
        return list(set([channel.unit for channel in self.outputs if channel.unit not in ['pA', 'pAh'] and channel.display]))

    def getDefaultSettings(self):
        """Defines settings and default values for DepoScan."""
        defaultSettings = super().getDefaultSettings()
        defaultSettings.pop(self.WAIT)
        defaultSettings.pop(self.WAITLONG)
        defaultSettings.pop(self.LARGESTEP)
        defaultSettings.pop(self.SCANTIME)
        defaultSettings[self.DISPLAY][Parameter.VALUE] = 'RT_Sample-Center'
        defaultSettings[self.DISPLAY][Parameter.TOOLTIP] = 'Any channel that should be recorded during deposition, including at least one current channel.'
        defaultSettings[self.DISPLAY][Parameter.ITEMS] = 'RT_Sample-Center, RT_Sample-End, C_Shuttle'
        defaultSettings[self.AVERAGE][Parameter.VALUE] = 4000
        defaultSettings[self.INTERVAL]   = parameterDict(value=10000, toolTip='Deposition interval.', widgetType=Parameter.TYPE.INT,
                                                                _min=1000, _max=60000, attr='interval')
        defaultSettings['Target']        = parameterDict(value='15', toolTip='Target coverage in pAh.', items='-20,-15,-10, 10, 15, 20',
                                                                widgetType=Parameter.TYPE.INTCOMBO, attr='target', event=lambda: self.updateDepoTarget())
        defaultSettings['Warnlevel']     = parameterDict(value='10', toolTip='Warning sound will be played when value drops below this level.', event=lambda: self.updateWarnLevel(),
                                                            items='20, 15, 10, 0, -10, -15, -20', widgetType=Parameter.TYPE.INTCOMBO, attr='warnLevel')
        defaultSettings['Warn']          = parameterDict(value=False, toolTip='Warning sound will be played when value drops below warnLevel. Disable to Mute.',
                                                            widgetType=Parameter.TYPE.BOOL, attr='warn')
        defaultSettings['Autoscale']     = parameterDict(value=True, toolTip='Disable y axis autoscale if your data includes outliers, e.g. from pickup spikes.',
                                                            widgetType=Parameter.TYPE.BOOL, attr='autoscale')
        defaultSettings['Dialog']     = parameterDict(value=True, toolTip='Show check list dialog on start.', widgetType=Parameter.TYPE.BOOL, attr='dialog')
        return defaultSettings

    def updateDepoTarget(self):
        if self.display is not None and self.display.initializedDock:
            self.display.updateDepoTarget()

    def initScan(self):
        # overwrite parent
        """Initialized all data and metadata.
        Returns True if initialization successful and scan is ready to start."""
        self.initializing = True
        for name in self.settingsMgr.settings[self.DISPLAY].items:
            sourceChannel = self.getChannelByName(name, inout=INOUT.OUT)
            if sourceChannel is None:
                sourceChannel = self.getChannelByName(name, inout=INOUT.IN)
            if sourceChannel is None:
                self.print(f'Could not find channel {name}.', PRINT.WARNING)
            elif not sourceChannel.getDevice().initialized():
                self.print(f'{sourceChannel.getDevice().name} is not initialized.', PRINT.WARNING)
            elif not sourceChannel.acquiring and not sourceChannel.getDevice().recording:
                self.print(f'{sourceChannel.name} is not acquiring.', PRINT.WARNING)
        self.addOutputChannels()
        self.initializing = False
        if len(self.outputs) > 0:
            self.inputs.append(MetaChannel(parentPlugin=self, name=self.TIME, recordingData=DynamicNp(dtype=np.float64)))
            self.measurementsPerStep = max(int((self.average/self.interval))-1, 1)
            self.toggleDisplay(True)
            self.display.progressAnnotation.set_text('')
            self.updateFile()
            self.populateDisplayChannel()
            self.display.updateDepoTarget() # flip axes if needed
            return True
        else:
            self.print('No initialized output channel found.', PRINT.WARNING)
            return False

    def addOutputChannels(self):
        for name in self.settingsMgr.settings[self.DISPLAY].items:
            channel = self.addOutputChannel(name=name, recordingData=DynamicNp())
            if hasattr(channel.sourceChannel, 'resetCharge'):
                channel.sourceChannel.resetCharge()
                self.addOutputChannel(name=f'{name}_{self.CHARGE}', unit='pAh', recordingData=DynamicNp())
        self.channelTree.setHeaderLabels([(name.title() if dict[Parameter.HEADER] is None else dict[Parameter.HEADER])
                                                for name, dict in self.channels[0].getSortedDefaultChannel().items()])
        self.toggleAdvanced(False)

    def loadDataInternal(self):
        super().loadDataInternal()
        self.display.updateDepoTarget() # flip axes if needed before plotting

    def populateDisplayChannel(self):
        # overwrite parent to hide charge channels
        self.loading = True
        self.display.displayComboBox.clear()
        for output in self.outputs:
            if output.unit == 'pA':
                self.display.displayComboBox.insertItem(self.display.displayComboBox.count(), output.name)
        self.loading = False
        self.updateDisplayDefault()

    def updateDisplayChannel(self):
        self.display.initFig() # need to reinitialize as displayed channels are changing
        super().updateDisplayChannel()

    def updateWarnLevel(self):
        if self.display is not None and self.display.currentWarnLine is not None:
            self.display.currentWarnLine.set_ydata([self.warnLevel])
            self.display.canvas.draw_idle()

    def plot(self, update=False, done=True, **kwargs): # pylint:disable=unused-argument
        """Plots depo data"""
        # timing test with 360 data points (one hour at 0.1 Hz) update True: 75 ms, update False: 135 ms
        if self.loading:
            return
        if len(self.outputs) > 0 and len(self.inputs) > 0:
            # self.print('plot', flag=PRINT.DEBUG)
            _timeInt = self.getData(0, INOUT.IN)
            _time = [datetime.fromtimestamp(float(_time)) for _time in _timeInt] # convert timestamp to datetime
            charge = []
            for i, output in enumerate(self.outputs):
                if i == self.getOutputIndex():
                    self.display.currentLine.set_data(_time, output.getRecordingData())
                elif i == self.getOutputIndex() + 1:
                    charge = output.getRecordingData()
                    self.display.chargeLine.set_data(_time, output.getRecordingData())
                elif output.unit not in ['pA', 'pAh'] and output.display: # only show current and charge for selected channel
                    if hasattr(output, 'line'):
                        output.line.set_data(_time, output.getRecordingData())
                    else:
                        self.print(f'Line not initialized for channel {output.name}', flag=PRINT.WARNING)
            time_done_str = 'unknown'
            end_str = 'end'
            if len(_time) > 10 or done: # predict scan based on last 10 data points
                if len(_time) > 10 and update and np.abs(charge[-1]) < np.abs(float(self.target)) and np.abs(charge[-1]) > np.abs(charge[-10]): # only predict if below target and charge is increasing
                    time_done = datetime.fromtimestamp(float(_timeInt[-1] + (_timeInt[-1]-_timeInt[-10])/(charge[-1]-charge[-10])*(float(self.target) - charge[-1]))) # t_t=t_i + dt/dQ * Q_missing
                    self.display.chargePredictionLine.set_data([_time[-1], time_done],[charge[-1], self.target])
                    time_done_str = self.roundDateTime(time_done).strftime('%H:%M')
                    end_str = 'estimated end'
                else:
                    self.display.chargePredictionLine.set_data([[_time[0]]],[0]) # hide at beginning and end of scan or if loaded from file
                if done:
                    time_done_str = self.roundDateTime(datetime.fromtimestamp(float(_timeInt[-1]))).strftime('%H:%M')
            if len(_time) > 0: # predict scan based on last 10 data points
                hh, mm= divmod(int(np.ceil((_timeInt[-1]-_timeInt[0])//60)), 60)
                self.display.progressAnnotation.set_text(f"start: {self.roundDateTime(_time[0]).strftime('%H:%M')}, {end_str}: {time_done_str}\n"
                                        + f"{charge[-1]-charge[0]:2.1f} pAh deposited")
                                        # do not show deposition time as scan time also includes thermalization and ice growth.
                                        # + f"{charge[-1]-charge[0]:2.1f} pAh deposited within " + (f"{hh} h {mm} min" if hh > 0 else f"{mm} min"))
        else: # no data
            self.removeAnnotations(self.display.axes[1])
            self.display.currentLine.set_data([],[])
            self.display.chargeLine .set_data([],[])
        self.display.axes[0].autoscale(True, axis='x')
        self.display.axes[0].relim()
        for i in range(len(self.display.axes)):
            if i > 0:
                self.display.axes[i].autoscale(True)
                self.display.axes[i].relim()
        if self.autoscale:
            self.setLabelMargin(self.display.axes[0], 0.3)
        self.updateToolBar(update=update)
        if len(self.outputs) > 0:
            self.labelPlot(self.display.axes[0], f'{self.outputs[self.getOutputIndex()].name} from {self.file.name}')
        else:
            self.labelPlot(self.display.axes[0], self.file.name)

    def pythonPlotCode(self):
        return """# add your custom plot code here

from datetime import datetime
import matplotlib.dates as mdates

MYBLUE='#1f77b4'

def addRightAxis(ax):
    axr = ax.twinx()
    axr.tick_params(direction="out", right=True)
    axr.sharey(ax)
    if ax.get_yscale() == 'log':
        axr.set_yscale('log')

def tilt_xlabels(ax, rotation=30):
    for label in ax.get_xticklabels(which='major'):
        label.set_ha('right')
        label.set_rotation(rotation)

def getExtraUnits():
    return list(set([channel.unit for channel in outputs if channel.unit not in ['pA', 'pAh']]))

fig = plt.figure(constrained_layout=True)
fig.set_constrained_layout_pads(h_pad=-4.0) # reduce space between axes
rows = len(getExtraUnits()) + 2
axes = []
axes.append(fig.add_subplot(rows, 1, 1)) # current axis
axes[0].set_ylabel('pA')
axes.append(fig.add_subplot(rows ,1, 2, sharex = axes[0])) # charge axis
axes[1].set_ylabel('pAh')

for i, unit in enumerate(getExtraUnits()):
    axes.append(fig.add_subplot(rows, 1, 3+i, sharex = axes[0]))
    axes[2+i].set_ylabel(unit)

_timeInt = inputs[0].recordingData
_time = [datetime.fromtimestamp(float(_time)) for _time in _timeInt] # convert timestamp to datetime
axes[0].plot(_time, outputs[output_index].recordingData, color=MYBLUE)[0]
axes[1].plot(_time, outputs[output_index+1].recordingData, color=MYBLUE)[0]

for output in outputs:
    if output.unit not in ['pA', 'pAh'] and output.unit in getExtraUnits():
        axes[2+getExtraUnits().index(output.unit)].plot(_time, output.recordingData, label=output.name)[0]
        if output.logY:
            axes[2+getExtraUnits().index(output.unit)].set_yscale('log')

for i, unit in enumerate(getExtraUnits()):
    legend = axes[2+i].legend(loc='best', prop={'size': 6}, frameon=False)
    legend.set_in_layout(False)

for i in range(len(axes)-1):
    axes[i].tick_params(axis='x', which='both', bottom=False, labelbottom=False)
for i in range(len(axes)):
    addRightAxis(axes[i])
axes[-1].set_xlabel('Time')
axes[-1].xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
tilt_xlabels(axes[-1])

plt.show()

        """

    def roundDateTime(self, tm):
        """Rounds to nearest minute."""
        discard = timedelta(minutes=tm.minute % 1,
                             seconds=tm.second,
                             microseconds=tm.microsecond)
        tm -= discard
        if discard >= timedelta(seconds=30):
            tm += timedelta(minutes=1)
        return tm

    def run(self, recording):
        while recording():
            time.sleep(self.interval/1000)
            self.inputs[0].recordingData.add(time.time())
            for i, output in enumerate(self.outputs):
                if output.isChargeChannel:
                    output.recordingData.add(output.sourceChannel.charge)
                else:
                    output.recordingData.add(np.mean(output.getValues(subtractBackground=output.getDevice().subtractBackgroundActive(), length=self.measurementsPerStep)))
            if self.warn and winsound is not None: # Sound only supported for windows
                if (np.sign(self.target) == 1 and self.getData(self.getOutputIndex()+1, INOUT.OUT)[-1] > float(self.target) or
                              np.sign(self.target) == -1 and self.getData(self.getOutputIndex()+1, INOUT.OUT)[-1] < float(self.target)):
                    winsound.PlaySound(str(self.dependencyPath / 'done.wav'), winsound.SND_ASYNC | winsound.SND_ALIAS)
                elif (np.sign(self.warnLevel) == 1 and self.getData(self.getOutputIndex(), INOUT.OUT)[-1] < float(self.warnLevel) or
                              np.sign(self.warnLevel) == -1 and self.getData(self.getOutputIndex(), INOUT.OUT)[-1] > float(self.warnLevel)):
                    winsound.PlaySound(str(self.dependencyPath / 'alarm.wav'), winsound.SND_ASYNC | winsound.SND_ALIAS)
            if recording(): # all but last step
                self.signalComm.scanUpdateSignal.emit(False) # update graph
        self.signalComm.scanUpdateSignal.emit(True) # update graph and save data # placed after while loop to ensure it will be executed

class GA(Scan):
    """This plugin allows to integrate an independently developed genetic
    algorithm (GA) for automated optimization of signals.\ :cite:`esser_cryogenic_2019`
    Multiple input channels can be selected to be included in the optimization. Make sure to choose safe
    limits for optimized channels and choose appropriate wait and average
    values to get valid feedback. The performance and reliability of the
    optimization depends on the stability and reproducibility of the
    selected output channel. The output channel can be virtual and contain an
    equation that references many other channels. At the end of the optimization the changed
    parameters will be shown in the plugin. The initial parameters can
    always be restored in case the optimization fails."""
    documentation = """This plugin allows to integrate an independently developed genetic
    algorithm (GA) for automated optimization of signals.
    Multiple input channels can be selected to be included in the optimization. Make sure to choose safe
    limits for optimized channels and choose appropriate wait and average
    values to get valid feedback. The performance and reliability of the
    optimization depends on the stability and reproducibility of the
    selected output channel. The output channel can be virtual and contain an
    equation that references many other channels. At the end of the optimization the changed
    parameters will be shown in the plugin. The initial parameters can
    always be restored in case the optimization fails."""

    name = 'GA'
    version = '1.0'
    pluginType = PluginManager.TYPE.SCAN
    iconFile = 'GA_light.png'
    iconFileDark = 'GA_dark.png'

    class GASignalCommunicate(QObject):
        updateValuesSignal = pyqtSignal(int, bool)

    class Display(Scan.Display):

        def initFig(self):
            super().initFig()
            self.axes.append(self.fig.add_subplot(111))
            self.bestLine = self.axes[0].plot([[datetime.now()]],[0], label='best fitness')[0] # need to be initialized with datetime on x axis
            self.avgLine  = self.axes[0].plot([[datetime.now()]],[0], label='avg fitness')[0]
            legend = self.axes[0].legend(loc='lower right', prop={'size': 10}, frameon=False)
            legend.set_in_layout(False)
            self.axes[0].set_xlabel(self.TIME)
            self.axes[0].set_ylabel('Fitness Value')
            # self.axes[0].margins(y=.1) # not yet supported for individual sides https://stackoverflow.com/questions/49382105/set-different-margins-for-left-and-right-side
            self.tilt_xlabels(self.axes[0])

    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.ga = dynamicImport('GA', self.dependencyPath / 'GA.py').GA()
        self.gaSignalComm = self.GASignalCommunicate()
        self.gaSignalComm.updateValuesSignal.connect(self.updateValues)
        self.changeLog = []
        self.gaChannel = None

    def initGUI(self):
        super().initGUI()
        self.recordingAction.setToolTip('Toggle optimization.')
        self.initialAction = self.addStateAction(event=lambda: self.toggleInitial(), toolTipFalse='Switch to initial settings.', iconFalse=self.makeIcon('switch-medium_on.png'),
                                                 toolTipTrue='Switch to optimized settings.', iconTrue=self.makeIcon('switch-medium_off.png'), attr='applyInitialParameters', restore=False)
    def runTestParallel(self):
        self.raiseDock(True)
        self.testControl(self.initialAction, self.initialAction.state)
        super().runTestParallel()

    def getDefaultSettings(self):
        defaultSettings = super().getDefaultSettings()
        defaultSettings.pop(self.WAITLONG)
        defaultSettings.pop(self.LARGESTEP)
        defaultSettings.pop(self.SCANTIME)
        defaultSettings['GA Channel'] = defaultSettings.pop(self.DISPLAY) # keep display for using displayChannel functionality but modify properties as needed
        defaultSettings['GA Channel'][Parameter.TOOLTIP] = 'Genetic algorithm optimizes on this channel'
        defaultSettings['GA Channel'][Parameter.ITEMS] = 'C_Shuttle, RT_Detector, RT_Sample-Center, RT_Sample-End, LALB-Aperture'
        defaultSettings['Logging'] = parameterDict(value=False, toolTip='Show detailed GA updates in console.', widgetType=Parameter.TYPE.BOOL, attr='log')
        return defaultSettings

    def toggleInitial(self):
        if len(self.outputs) > 0:
            self.gaSignalComm.updateValuesSignal.emit(0, self.initialAction.state)
        else:
            self.initialAction.state = False
            self.print('GA not initialized.')

    def initScan(self):
        """ Start optimization."""
        # overwrite parent
        self.initializing = True
        self.gaChannel = self.getChannelByName(self.displayDefault, inout=INOUT.OUT)
        self.ga.init() # don't mix up with init method from Scan
        self.ga.maximize(True)
        # self.restore(True)
        if self.gaChannel is None:
            self.print(f'Channel {self.displayDefault} not found. Cannot start optimization.', PRINT.WARNING)
            return False
        elif not self.gaChannel.acquiring:
            self.print(f'Channel {self.gaChannel.name} not acquiring. Cannot start optimization.', PRINT.WARNING)
            return False
        else:
            self.inputs.append(MetaChannel(parentPlugin=self, name=self.TIME, recordingData=DynamicNp(dtype=np.float64)))
            self.addOutputChannels()
            self.toggleDisplay(True)
            self.display.axes[0].set_ylabel(self.gaChannel.name)
        self.initializing = False
        for channel in self.pluginManager.DeviceManager.channels(inout=INOUT.IN):
            if channel.optimize:
                self.ga.optimize(channel.value, channel.min, channel.max,.2, abs(channel.max-channel.min)/10, channel.name)
            else:
                self.ga.optimize(channel.value, channel.min, channel.max, 0, abs(channel.max-channel.min)/10, channel.name) # add entry but set rate to 0 to prevent value change. Can be activated later.
        self.ga.genesis()
        self.measurementsPerStep = max(int((self.average/self.outputs[0].getDevice().interval))-1, 1)
        self.updateFile()
        self.ga.file_path(self.file.parent.as_posix())
        self.ga.file_name(self.file.name)
        self.initialAction.state = False
        return True

    def addOutputChannels(self):
        for channel in self.outputs:
            channel.onDelete()
        if self.channelTree is not None:
            self.channelTree.clear()
        self.addOutputChannel(name=f'{self.displayDefault}', recordingData=DynamicNp())
        if len(self.outputs) > 0:
            self.outputs.append(MetaChannel(parentPlugin=self, name=f'{self.displayDefault}_Avg', recordingData=DynamicNp()))
        self.channelTree.setHeaderLabels([(name.title() if dict[Parameter.HEADER] is None else dict[Parameter.HEADER])
                                                    for name, dict in self.channels[0].getSortedDefaultChannel().items()])
        self.toggleAdvanced()

    def plot(self, update=False, **kwargs): # pylint:disable=unused-argument
        """Plots fitness data"""
        # timing test with 160 generations: update True: 25 ms, update False: 37 ms
        if self.loading:
            return
        if len(self.outputs) > 0:
            _time = [datetime.fromtimestamp(float(_time)) for _time in self.getData(0, INOUT.IN)] # convert timestamp to datetime
            self.display.bestLine.set_data(_time, self.getData(0, INOUT.OUT))
            self.display.avgLine.set_data(_time, self.getData(1, INOUT.OUT))
        else: # no data
            self.display.bestLine.set_data([],[])
            self.display.avgLine.set_data([],[])
        self.display.axes[0].autoscale(True, axis='x')
        self.display.axes[0].relim()
        self.display.axes[0].autoscale_view(True, True, False)
        if len(self.getData(0, INOUT.OUT)) > 1:
            self.setLabelMargin(self.display.axes[0], 0.15)
        self.updateToolBar(update=update)
        self.labelPlot(self.display.axes[0], self.file.name)

    def pythonPlotCode(self):
        return """# add your custom plot code here
from datetime import datetime

fig = plt.figure(constrained_layout=True)
ax0 = fig.add_subplot(111)
ax0.set_xlabel('Time')
ax0.set_ylabel('Fitness Value')
for label in ax0.get_xticklabels(which='major'):
    label.set_ha('right')
    label.set_rotation(30)
_time = [datetime.fromtimestamp(float(_time)) for _time in inputs[0].recordingData]
ax0.plot(_time, outputs[0].recordingData, label='best fitness')[0]
ax0.plot(_time, outputs[1].recordingData, label='avg fitness')[0]
ax0.legend(loc='lower right', prop={'size': 10}, frameon=False)
plt.show()
        """

    def run(self, recording):
        """Run GA optimization."""
        #first datapoint before optimization
        self.inputs[0].recordingData.add(time.time())
        fitnessStart = np.mean(self.outputs[0].getValues(subtractBackground=self.outputs[0].subtractBackgroundActive(), length=self.measurementsPerStep))
        self.outputs[0].recordingData.add(fitnessStart)
        self.outputs[1].recordingData.add(fitnessStart)
        while recording():
            self.gaSignalComm.updateValuesSignal.emit(-1, False)
            time.sleep((self.wait+self.average)/1000)
            self.ga.fitness(np.mean(self.outputs[0].getValues(subtractBackground=self.outputs[0].subtractBackgroundActive(), length=self.measurementsPerStep)))
            if self.log:
                self.print(self.ga.step_string().replace('GA: ',''))
            _, session_saved = self.ga.check_restart()
            if session_saved:
                self.print(f'Session Saved -- Average Fitness: {self.ga.average_fitness():6.2f} Best Fitness: {self.ga.best_fitness():6.2f}')
                self.print(f'Starting Generation {self.ga.current_generation}:')
                self.inputs[0].recordingData.add(time.time())
                self.outputs[0].recordingData.add(self.ga.best_fitness())
                self.outputs[1].recordingData.add(self.ga.average_fitness())
                self.signalComm.scanUpdateSignal.emit(False)
        self.ga.check_restart(True) # sort population
        self.gaSignalComm.updateValuesSignal.emit(0, False)
        self.signalComm.scanUpdateSignal.emit(True)

    def updateValues(self, index=None, initial=False):
        # only call in main thread as updates GUI
        self.pluginManager.loading = True # only update after setting all voltages
        for channel in [channel for channel in self.pluginManager.DeviceManager.channels(inout=INOUT.IN) if channel.optimize]:
            channel.value = self.ga.GAget(channel.name, channel.value, index=index, initial=initial)
        self.pluginManager.loading = False
        self.pluginManager.DeviceManager.globalUpdate(inout=INOUT.IN)

    def saveScanParallel(self, file):
        self.changeLog = [f'Change log for optimizing channels by {self.name}:']
        for channel in [channel for channel in self.pluginManager.DeviceManager.channels(inout=INOUT.IN) if channel.optimize]:
            if not channel.getParameterByName(Parameter.VALUE).equals(self.ga.GAget(channel.name, channel.value, initial=True)):
                self.changeLog.append(
    f'Changed value of {channel.name} from {self.ga.GAget(channel.name, channel.value, initial=True)} to {self.ga.GAget(channel.name, channel.value, index=0):6.2f}.')
        if len(self.changeLog) == 1:
            self.changeLog.append('No changes.')
        self.pluginManager.Text.setTextParallel('\n'.join(self.changeLog))
        self.print('Change log available in Text plugin.')
        super().saveScanParallel(file)

class MassSpec(Scan):
    """Records mass spectra by recording an output channel as a function of a (calibrated) input channel.
    Left clicking on peaks in a charge state series while holding down the Ctrl key provides a
    quick estimate of charge state and mass, based on minimizing the standard
    deviation of the mass as a function of possible charge states.
    Use Ctrl + right mouse click to reset.
    This can be used as a template or a parent class for a simple one dimensional scan of other properties."""
    documentation = None # use __doc__

    name = 'msScan'
    version = '1.1'
    supportedVersion = '0.7'
    pluginType = PluginManager.TYPE.SCAN
    iconFile = 'ms_light.png'
    iconFileDark = 'ms_dark.png'

    class Display(Scan.Display):

        def initGUI(self):
            self.mzCalc = MZCalculator(parentPlugin=self)
            super().initGUI()
            self.addAction(lambda: self.copyLineDataClipboard(line=self.ms), 'Data to Clipboard.', icon=self.dataClipboardIcon, before=self.copyAction)

        def initFig(self):
            super().initFig()
            self.axes.append(self.fig.add_subplot(111))
            self.ms  = self.axes[0].plot([], [])[0] # dummy plot
            self.mzCalc.setAxis(self.axes[0])
            self.canvas.mpl_connect('button_press_event', self.mzCalc.msOnClick)

    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.useDisplayChannel = True
        self.previewFileTypes.append('ms scan.h5')

    def getDefaultSettings(self):
        defaultSettings = super().getDefaultSettings()
        defaultSettings[self.DISPLAY][Parameter.VALUE] = 'Detector'
        defaultSettings[self.DISPLAY][Parameter.TOOLTIP] = 'Channel for transmitted signal.'
        defaultSettings[self.DISPLAY][Parameter.ITEMS] = 'Detector, Detector2'
        defaultSettings[self.CHANNEL] = parameterDict(value='AMP_Q1', toolTip='Amplitude that is swept through', items='AMP_Q1, AMP_Q2',
                                                                      widgetType=Parameter.TYPE.COMBO, attr='channel')
        defaultSettings[self.FROM]    = parameterDict(value=50 , widgetType=Parameter.TYPE.FLOAT, attr='_from', event=lambda: self.estimateScanTime())
        defaultSettings[self.TO]      = parameterDict(value=200, widgetType=Parameter.TYPE.FLOAT, attr='to', event=lambda: self.estimateScanTime())
        defaultSettings[self.STEP]    = parameterDict(value=1  , widgetType=Parameter.TYPE.FLOAT, attr='step', _min=.1, _max=10, event=lambda: self.estimateScanTime())
        return defaultSettings

    def initScan(self):
        return (self.addInputChannel(self.channel, self._from, self.to, self.step) and super().initScan())

    def plot(self, update=False, done=False, **kwargs): # pylint:disable=unused-argument
        """Plots mass spectrum including metadata"""

        if len(self.outputs) > 0:
            self.display.ms.set_data(self.inputs[0].getRecordingData(), self.outputs[self.getOutputIndex()].getRecordingData())
            if not update:
                self.display.axes[0].set_ylabel(f'{self.outputs[self.getOutputIndex()].name} ({self.outputs[self.getOutputIndex()].unit})')
                self.display.axes[0].set_xlabel(f'{self.inputs[0].name} ({self.inputs[0].unit})')
        else: # no data
            self.display.ms.set_data([],[])
        self.display.axes[0].relim() # adjust to data
        self.setLabelMargin(self.display.axes[0], 0.15)
        self.updateToolBar(update=update)
        self.display.mzCalc.update_mass_to_charge()
        if len(self.outputs) > 0:
            self.labelPlot(self.display.axes[0], f'{self.outputs[self.getOutputIndex()].name} from {self.file.name}')
        else:
            self.labelPlot(self.display.axes[0], self.file.name)

    def pythonPlotCode(self):
        return """# add your custom plot code here

fig = plt.figure(constrained_layout=True)
ax0 = fig.add_subplot(111)

ax0.plot(inputs[0].recordingData, outputs[output_index].recordingData)
ax0.set_ylabel(f'{outputs[output_index].name} ({outputs[output_index].unit})')
ax0.set_xlabel(f'{inputs[0].name} ({inputs[0].unit})')

plt.show()
"""

    def loadData(self, file, _show=True):
        super().loadData(file, _show)
        self.display.mzCalc.clear()

    def loadDataInternal(self):
        """Loads data in internal standard format for plotting."""
        if self.file.name.endswith('ms scan.h5'):  # legacy file before removing space in plugin name
            with h5py.File(self.file, 'r') as h5file:
                group = h5file['MS Scan']
                input_group = group[self.INPUTCHANNELS]
                for name, data in input_group.items():
                    self.inputs.append(MetaChannel(parentPlugin=self, name=name, recordingData=data[:], unit=data.attrs[self.UNIT], inout=INOUT.IN))
                output_group = group[self.OUTPUTCHANNELS]
                for name, data in output_group.items():
                    self.addOutputChannel(name=name, unit=data.attrs[self.UNIT], recordingData=data[:])
        else:
            super().loadDataInternal()
