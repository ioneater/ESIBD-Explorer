import itertools

import h5py
import numpy as np
from mpl_toolkits.axes_grid1 import make_axes_locatable
from scipy import interpolate

from esibd.core import INOUT, PARAMETERTYPE, PRINT, ControlCursor, MetaChannel, colors, getDarkMode, parameterDict, plotting
from esibd.plugins import Plugin, Scan


def providePlugins() -> list['Plugin']:
    """Return list of provided plugins. Indicates that this module provides plugins."""
    return [Beam]


class Beam(Scan):
    """Scan that records the ion-beam current on one electrode as a function of two voltage channels, typically deflectors.

    The recorded data can be interpolated to
    enhance the visualization. A 1:1 aspect ratio is used by default, but a variable ratio
    can be enabled to maximize use of space. The resulting image is used to identify
    elements like apertures, samples, and detectors. The beam can be moved
    between those elements by clicking and dragging on the image while
    holding down the Ctrl key. Limits can be coupled to have the same step
    size in both directions. Scan limits can be adopted from the figure or
    centered around the current value, e.g., to zoom in and center on a
    specific feature.
    """

    LEFTRIGHT = 'Left-Right'
    UPDOWN = 'Up-Down'
    name = 'Beam'
    version = '1.0'
    iconFile = 'beam.png'

    class Display(Scan.Display):
        """Display for Beam Scan."""

        axesAspectAction = None

        def finalizeInit(self) -> None:
            self.mouseActive = True
            super().finalizeInit()
            self.interpolateAction = self.addStateAction(toolTipFalse='Interpolation on.', iconFalse=self.scan.makeIcon('interpolate_on.png'),
                                                         toolTipTrue='Interpolation off.', iconTrue=self.scan.makeIcon('interpolate_off.png'),
                                                         before=self.copyAction, event=lambda: self.scan.plot(update=False, done=True), attr='interpolate')
            self.axesAspectAction = self.addStateAction(toolTipFalse='Variable axes aspect ratio.', iconFalse=self.scan.getIcon(),
                                                        toolTipTrue='Fixed axes aspect ratio.', iconTrue=self.scan.getIcon(),  # defined in updateTheme
                                                        before=self.copyAction, event=lambda: (self.initFig(), self.scan.plot(update=False, done=True)), attr='varAxesAspect')
            self.updateTheme()  # set icons for axesAspectActions
            self.initFig()  # axis aspect may have changed

        def initFig(self) -> None:
            if self.axesAspectAction is None:
                return
            super().initFig()
            engine = self.fig.get_layout_engine()
            engine.set(rect=(0.05, 0.0, 0.8, 0.9))  # constrained_layout ignores labels on colorbar
            self.axes.append(self.fig.add_subplot(111))
            if not self.axesAspectAction.state:  # use qSet directly in case control is not yet initialized
                self.axes[0].set_aspect('equal', adjustable='box')
            self.canvas.mpl_connect('motion_notify_event', self.mouseEvent)
            self.canvas.mpl_connect('button_press_event', self.mouseEvent)
            self.canvas.mpl_connect('button_release_event', self.mouseEvent)
            self.cont = None
            divider = make_axes_locatable(self.axes[0])
            self.cax = divider.append_axes('right', size='5%', pad=0.15)
            self.cbar = None
            self.axes[-1].cursor = None

        def runTestParallel(self) -> None:
            if self.initializedDock:
                self.testControl(self.interpolateAction, not self.interpolateAction.state, 1)
                self.testControl(self.axesAspectAction, not self.axesAspectAction.state, 1)
            super().runTestParallel()

        def updateTheme(self) -> None:
            if self.axesAspectAction is not None:
                self.axesAspectAction.iconFalse = self.scan.makeIcon('aspect_variable_dark.png' if getDarkMode() else 'aspect_variable.png')
                self.axesAspectAction.iconTrue = self.scan.makeIcon('aspect_fixed_dark.png' if getDarkMode() else 'aspect_fixed.png')
                self.axesAspectAction.updateIcon(self.axesAspectAction.state)
            return super().updateTheme()

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.useDisplayChannel = True
        self.previewFileTypes.append('.S2D.dat')
        self.previewFileTypes.append('.s2d.h5')

    def initGUI(self) -> None:
        super().initGUI()
        self.coupleAction = self.addStateAction(toolTipFalse='Coupled step size.', iconFalse=self.makeIcon('lock-unlock.png'), toolTipTrue='Independent step size.',
                                                     iconTrue=self.makeIcon('lock.png'), before=self.copyAction, attr='coupleStepSize')
        self.limitAction = self.addAction(event=self.useLimits, toolTip='Adopts limits from display', icon='ruler.png')
        self.centerAction = self.addAction(event=self.centerLimits, toolTip='Center limits around current values.', icon=self.makeIcon('ruler-crop.png'), before=self.copyAction)

    def runTestParallel(self) -> None:
        self.testControl(self.coupleAction, self.coupleAction.state)
        self.testControl(self.limitAction, value=True)
        self.testControl(self.centerAction, value=True)
        super().runTestParallel()

    def loadDataInternal(self) -> None:
        """Load data in internal standard format for plotting."""
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
            self.inputChannels.append(MetaChannel(parentPlugin=self,
                                                  name='LR Voltage', recordingData=np.arange(0, 1, 1 / self.outputChannels[0].getRecordingData().shape[1]), unit='V'))
            self.inputChannels.append(MetaChannel(parentPlugin=self,
                                                  name='UD Voltage', recordingData=np.arange(0, 1, 1 / self.outputChannels[0].getRecordingData().shape[0]), unit='V'))
        elif self.file.name.endswith('.s2d.h5'):
            with h5py.File(self.file, 'r') as h5file:
                is03 = h5file[self.VERSION].attrs['VALUE'] == '0.3'  # legacy version 0.3, 0.4 if False
                lr = h5file['S2DSETTINGS']['Left-Right']
                start, stop, step = lr['From'].attrs['VALUE'], lr['To'].attrs['VALUE'], lr['Step'].attrs['VALUE']
                self.inputChannels.append(MetaChannel(parentPlugin=self, name=lr['Channel'].attrs['VALUE'],
                                                       recordingData=np.linspace(start, stop, int(abs(start - stop) / abs(step)) + 1),
                                                        unit='V', inout=INOUT.IN))
                ud = h5file['S2DSETTINGS']['Up-Down']
                start, stop, step = ud['From'].attrs['VALUE'], ud['To'].attrs['VALUE'], ud['Step'].attrs['VALUE']
                self.inputChannels.append(MetaChannel(parentPlugin=self, name=ud['Channel'].attrs['VALUE'],
                                                       recordingData=np.linspace(start, stop, int(abs(start - stop) / abs(step)) + 1),
                                                        unit='V', inout=INOUT.IN))
                output_group = h5file['Current'] if is03 else h5file['OUTPUTS']
                for name, item in output_group.items():
                    self.addOutputChannel(name=name, unit='pA', recordingData=item[:].transpose())
        else:
            super().loadDataInternal()

    @Scan.finished.setter
    def finished(self, finished) -> None:
        Scan.finished.fset(self, finished)
        # disable inputs while scanning
        for direction in [self.LEFTRIGHT, self.UPDOWN]:
            for setting in [self.START, self.STOP, self.STEP, self.CHANNEL]:
                self.settingsMgr.settings[f'{direction}/{setting}'].setEnabled(finished)

    def estimateScanTime(self) -> None:
        if self.LR_from != self.LR_stop and self.UD_from != self.UD_stop:
            steps = list(itertools.product(self.getSteps(self.LR_from, self.LR_stop, self.LR_step), self.getSteps(self.UD_from, self.UD_stop, self.UD_step)))
        else:
            self.print('Limits are equal.', PRINT.WARNING)
            self.scantime = 'n/a'
            return
        seconds = 0  # estimate scan time
        for i in range(len(steps)):
            waitLong = False
            for j in range(len(self.inputChannels)):
                if not waitLong and abs(steps[i - 1][j] - steps[i][j]) > self.largestep:
                    waitLong = True
                    break
            seconds += (self.waitLong if waitLong else self.wait) + self.average
        seconds = round((seconds) / 1000)
        self.scantime = f'{seconds // 60:02d}:{seconds % 60:02d}'

    def centerLimits(self) -> None:
        """Centers scan range around current channel values."""
        channel = self.getChannelByName(self.LR_channel)
        if channel is not None:
            delta = abs(self.LR_stop - self.LR_from) / 2
            self.LR_from = channel.value - delta
            self.LR_stop = channel.value + delta
        else:
            self.print(f'Could not find channel {self.LR_channel}')
        channel = self.getChannelByName(self.UD_channel)
        if channel is not None:
            delta = abs(self.UD_stop - self.UD_from) / 2
            self.UD_from = channel.value - delta
            self.UD_stop = channel.value + delta
        else:
            self.print(f'Could not find channel {self.UD_channel}')

    def updateStep(self, step) -> None:
        """Couples step size if applicable.

        :param step: The new step size.
        :type step: float
        """
        if self.coupleAction.state:
            self.LR_step = step
            self.UD_step = step
        self.estimateScanTime()

    def initScan(self) -> None:
        return (self.addInputChannel(self.LR_channel, self.LR_from, self.LR_stop, self.LR_step) and
        self.addInputChannel(self.UD_channel, self.UD_from, self.UD_stop, self.UD_step) and
         super().initScan())

    def getDefaultSettings(self) -> dict[str, dict]:
        defaultSettings = super().getDefaultSettings()
        defaultSettings[f'{self.LEFTRIGHT}/{self.CHANNEL}'] = parameterDict(value='LA-S-LR', items='LA-S-LR, LC-in-LR, LD-in-LR, LE-in-LR',
                                                                parameterType=PARAMETERTYPE.COMBO, attr='LR_channel')
        defaultSettings[f'{self.LEFTRIGHT}/{self.START}'] = parameterDict(value=-5, parameterType=PARAMETERTYPE.FLOAT, attr='LR_from', event=self.estimateScanTime)
        defaultSettings[f'{self.LEFTRIGHT}/{self.STOP}'] = parameterDict(value=5, parameterType=PARAMETERTYPE.FLOAT, attr='LR_stop', event=self.estimateScanTime)
        defaultSettings[f'{self.LEFTRIGHT}/{self.STEP}'] = parameterDict(value=2, parameterType=PARAMETERTYPE.FLOAT, attr='LR_step', minimum=.1, maximum=10,
                                                                          event=lambda: self.updateStep(self.LR_step))
        defaultSettings[f'{self.UPDOWN}/{self.CHANNEL}'] = parameterDict(value='LA-S-UD', items='LA-S-UD, LC-in-UD, LD-in-UD, LE-in-UD',
                                                                parameterType=PARAMETERTYPE.COMBO, attr='UD_channel')
        defaultSettings[f'{self.UPDOWN}/{self.START}'] = parameterDict(value=-5, parameterType=PARAMETERTYPE.FLOAT, attr='UD_from', event=self.estimateScanTime)
        defaultSettings[f'{self.UPDOWN}/{self.STOP}'] = parameterDict(value=5, parameterType=PARAMETERTYPE.FLOAT, attr='UD_stop', event=self.estimateScanTime)
        defaultSettings[f'{self.UPDOWN}/{self.STEP}'] = parameterDict(value=2, parameterType=PARAMETERTYPE.FLOAT, attr='UD_step', minimum=.1, maximum=10,
                                                                       event=lambda: self.updateStep(self.UD_step))
        return defaultSettings

    def useLimits(self) -> None:
        """Use current display limits as scan limits."""
        if self.display is not None and self.display.initializedDock:
            self.LR_from, self.LR_stop = self.display.axes[0].get_xlim()
            self.UD_from, self.UD_stop = self.display.axes[0].get_ylim()

    @plotting
    def plot(self, update=False, done=True, **kwargs) -> None:  # pylint:disable=unused-argument  # noqa: ARG002
        # timing test with 50 data points: update True: 33 ms, update False: 120 ms
        if self.loading or len(self.outputChannels) == 0:
            return
        x, y = self.getMeshgrid()  # data coordinates
        if update:
            z = self.outputChannels[self.getOutputIndex()].getRecordingData().ravel()
            self.display.cont.set_array(z.ravel())
            self.display.cbar.mappable.set_clim(vmin=np.min(z), vmax=np.max(z))
        else:
            self.display.axes[0].clear()  # only update would be preferred but not yet possible with contourf
            self.display.cax.clear()
            if len(self.outputChannels) > 0:
                self.display.axes[0].set_xlabel(f'{self.inputChannels[0].name} ({self.inputChannels[0].unit})')
                self.display.axes[0].set_ylabel(f'{self.inputChannels[1].name} ({self.inputChannels[1].unit})')
                if done and self.display.interpolateAction.state:
                    rbf = interpolate.Rbf(x.ravel(), y.ravel(), self.outputChannels[self.getOutputIndex()].getRecordingData().ravel())
                    xi, yi = self.getMeshgrid(2)  # interpolation coordinates, scaling of 1 much faster than 2 and seems to be sufficient
                    zi = rbf(xi, yi)
                    self.display.cont = self.display.axes[0].contourf(xi, yi, zi, levels=100, cmap='afmhot')  # contour with interpolation
                else:
                    # contour without interpolation
                    self.display.cont = self.display.axes[0].pcolormesh(x, y, self.outputChannels[self.getOutputIndex()].getRecordingData(), cmap='afmhot')
                # ax=self.display.axes[0] instead of cax -> colorbar using all available height and does not scale to plot
                self.display.cbar = self.display.fig.colorbar(self.display.cont, cax=self.display.cax)  # match axis and color bar size  # , format='%d'
                self.display.cbar.ax.set_title(self.outputChannels[0].unit)
                self.display.axes[-1].cursor = ControlCursor(self.display.axes[-1], colors.highlight)  # has to be initialized last, otherwise axis limits may be affected

        if len(self.outputChannels) > 0 and self.inputChannels[0].sourceChannel is not None and self.inputChannels[1].sourceChannel is not None:
            self.display.axes[-1].cursor.setPosition(self.inputChannels[0].value, self.inputChannels[1].value)
        self.updateToolBar(update=update)
        self.defaultLabelPlot(self.display.axes[0])

    def pythonPlotCode(self) -> str:
        return f"""# add your custom plot code here

_interpolate = False  # set to True to interpolate data
varAxesAspect = False  # set to True to use variable axes aspect ratio

from mpl_toolkits.axes_grid1 import make_axes_locatable
from scipy import interpolate

fig = plt.figure(num='{self.name} plot', constrained_layout=True)
ax = fig.add_subplot(111)
if not varAxesAspect:
    ax.set_aspect('equal', adjustable='box')
divider = make_axes_locatable(ax)
cont = None
cax = divider.append_axes("right", size="5%", pad=0.15)

def getMeshgrid(scaling=1):
    '''Gets a mesh grid of x a coordinates.

    :param scaling: _descCan be used to increase resolution, e.g. when interpolating. Defaults to 1
    :type scaling: int, optional
    :return: The meshgrid.
    :rtype: np.meshgrid
    '''
    return np.meshgrid(*[np.linspace(i.recordingData[0], i.recordingData[-1],
      len(i.recordingData) if scaling == 1 else min(len(i.recordingData)*scaling, 50)) for i in inputChannels])

x, y = getMeshgrid()
z = outputChannels[output_index].recordingData.ravel()
ax.set_xlabel(f'{{inputChannels[0].name}} ({{inputChannels[0].unit}})')
ax.set_ylabel(f'{{inputChannels[1].name}} ({{inputChannels[1].unit}})')

if _interpolate:
    rbf = interpolate.Rbf(x.ravel(), y.ravel(), outputChannels[output_index].recordingData.ravel())
    xi, yi = getMeshgrid(2)  # interpolation coordinates, scaling of 1 much faster than 2 and seems to be sufficient
    zi = rbf(xi, yi)
    cont = ax.contourf(xi, yi, zi, levels=100, cmap='afmhot')  # contour with interpolation
else:
    cont = ax.pcolormesh(x, y, outputChannels[output_index].recordingData, cmap='afmhot')  # contour without interpolation
cbar = fig.colorbar(cont, cax=cax)  # match axis and color bar size  # , format='%d'
cbar.ax.set_title(outputChannels[0].unit)

fig.show()
        """

    def getMeshgrid(self, scaling=1) -> np.meshgrid:
        """Get a mesh grid of x a coordinates.

        :param scaling: _descCan be used to increase resolution, e.g. when interpolating. Defaults to 1
        :type scaling: int, optional
        :return: The meshgrid.
        :rtype: np.meshgrid
        """
        # interpolation with more than 50 x 50 grid points gets slow and does not add much to the quality for typical scans
        return np.meshgrid(*[np.linspace(i.getRecordingData()[0], i.getRecordingData()[-1], len(i.getRecordingData()) if
                                         scaling == 1 else min(len(i.getRecordingData()) * scaling, 50)) for i in self.inputChannels])
