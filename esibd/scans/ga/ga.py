import time
from datetime import datetime
from typing import TYPE_CHECKING

import numpy as np
from PyQt6.QtCore import QObject

from esibd.core import INOUT, PRINT, DynamicNp, MetaChannel, Parameter, dynamicImport, parameterDict, plotting, pyqtSignal
from esibd.plugins import Scan

if TYPE_CHECKING:
    from esibd.plugins import Plugin


def providePlugins() -> list['Plugin']:
    """Return list of provided plugins. Indicates that this module provides plugins."""
    return [GA]


class GA(Scan):
    r"""Allows to integrate an independently developed genetic algorithm (GA) for automated optimization of signals\ :cite:`esser_cryogenic_2019`.

    Multiple input channels can be selected to be included in the optimization. Make sure to choose safe
    limits for optimized channels and choose appropriate wait and average
    values to get valid feedback. The performance and reliability of the
    optimization depends on the stability and reproducibility of the
    selected output channel. The output channel can be virtual and contain an
    equation that references many other channels. At the end of the optimization the changed
    parameters will be shown in the plugin. The initial parameters can
    always be restored in case the optimization fails.
    """

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
    iconFile = 'GA_light.png'
    iconFileDark = 'GA_dark.png'

    class GASignalCommunicate(QObject):
        updateValuesSignal = pyqtSignal(int, bool)

    class Display(Scan.Display):
        """Display for GA scan."""

        def initFig(self) -> None:
            super().initFig()
            self.axes.append(self.fig.add_subplot(111))
            self.bestLine = self.axes[0].plot([[datetime.now()]], [0], label='best fitness')[0]  # need to be initialized with datetime on x axis
            self.avgLine  = self.axes[0].plot([[datetime.now()]], [0], label='avg fitness')[0]
            legend = self.axes[0].legend(loc='lower right', prop={'size': 10}, frameon=False)
            legend.set_in_layout(False)
            self.axes[0].set_xlabel(self.TIME)
            self.axes[0].set_ylabel('Fitness Value')
            self.tilt_xlabels(self.axes[0])

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.ga = dynamicImport('ga_standalone', self.dependencyPath / 'ga_standalone.py').GA()
        self.gaSignalComm = self.GASignalCommunicate()
        self.gaSignalComm.updateValuesSignal.connect(self.updateValues)
        self.changeLog = []
        self.gaChannel = None

    def initGUI(self) -> None:
        super().initGUI()
        self.recordingAction.setToolTip('Toggle optimization.')
        self.initialAction = self.addStateAction(event=lambda: self.toggleInitial(), toolTipFalse='Switch to initial settings.', iconFalse=self.makeIcon('switch-medium_on.png'),
                                                 toolTipTrue='Switch to optimized settings.', iconTrue=self.makeIcon('switch-medium_off.png'), attr='applyInitialParameters', restore=False)

    def runTestParallel(self) -> None:
        self.testControl(self.initialAction, self.initialAction.state)
        super().runTestParallel()

    def getDefaultSettings(self) -> dict[str, dict]:
        defaultSettings = super().getDefaultSettings()
        defaultSettings.pop(self.WAITLONG)
        defaultSettings.pop(self.LARGESTEP)
        defaultSettings.pop(self.SCANTIME)
        defaultSettings['GA Channel'] = defaultSettings.pop(self.DISPLAY)  # keep display for using displayChannel functionality but modify properties as needed
        defaultSettings['GA Channel'][Parameter.TOOLTIP] = 'Genetic algorithm optimizes on this channel'
        defaultSettings['GA Channel'][Parameter.ITEMS] = 'C_Shuttle, RT_Detector, RT_Sample-Center, RT_Sample-End, LALB-Aperture'
        defaultSettings['Logging'] = parameterDict(value=False, toolTip='Show detailed GA updates in console.', widgetType=Parameter.TYPE.BOOL, attr='log')
        return defaultSettings

    def toggleInitial(self) -> None:
        """Toggles between initial and optimized values."""
        if len(self.outputs) > 0:
            self.gaSignalComm.updateValuesSignal.emit(0, self.initialAction.state)
        else:
            self.initialAction.state = False
            self.print('GA not initialized.')

    def initScan(self) -> None:
        """Start optimization."""
        # overwrite parent
        self.initializing = True
        self.gaChannel = self.getChannelByName(self.displayDefault, inout=INOUT.OUT)
        self.ga.init()  # don't mix up with init method from Scan
        self.ga.maximize(True)
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
                self.ga.optimize(channel.value, channel.min, channel.max, .2, abs(channel.max - channel.min) / 10, channel.name)
            else:
                # add entry but set rate to 0 to prevent value change. Can be activated later.
                self.ga.optimize(channel.value, channel.min, channel.max, 0, abs(channel.max - channel.min) / 10, channel.name)
        self.ga.genesis()
        self.measurementsPerStep = max(int(self.average / self.outputs[self.getOutputIndex()].getDevice().interval) - 1, 1)
        self.updateFile()
        self.ga.file_path(self.file.parent.as_posix())
        self.ga.file_name(self.file.name)
        self.initialAction.state = False
        return True

    def addOutputChannels(self) -> None:
        for channel in self.outputs:
            channel.onDelete()
        if self.channelTree is not None:
            self.channelTree.clear()
        self.addOutputChannel(name=f'{self.displayDefault}', recordingData=DynamicNp())
        if len(self.outputs) > 0:
            self.outputs.append(MetaChannel(parentPlugin=self, name=f'{self.displayDefault}_Avg', recordingData=DynamicNp()))
        self.channelTree.setHeaderLabels([(parameterDict.get(Parameter.HEADER, name.title()))
                                            for name, parameterDict in self.channels[0].getSortedDefaultChannel().items()])
        self.toggleAdvanced()

    @plotting
    def plot(self, update=False, **kwargs) -> None:  # pylint:disable=unused-argument, missing-param-doc  # noqa: ARG002
        """Plot fitness data.

        :param update: Indicates if this is just an incremental update or the final plot (e.g. when loading data from file), defaults to False
        :type update: bool, optional
        """
        # timing test with 160 generations: update True: 25 ms, update False: 37 ms
        if self.loading:
            return
        if len(self.outputs) > 0:
            time_axis = [datetime.fromtimestamp(float(time_axis)) for time_axis in self.getData(0, INOUT.IN)]  # convert timestamp to datetime
            self.display.bestLine.set_data(time_axis, self.getData(0, INOUT.OUT))
            self.display.avgLine.set_data(time_axis, self.getData(1, INOUT.OUT))
        else:  # no data
            self.display.bestLine.set_data([], [])
            self.display.avgLine.set_data([], [])
        self.display.axes[0].autoscale(True, axis='x')
        self.display.axes[0].relim()
        self.display.axes[0].autoscale_view(True, True, False)
        if len(self.getData(0, INOUT.OUT)) > 1:
            self.setLabelMargin(self.display.axes[0], 0.15)
        self.updateToolBar(update=update)
        self.labelPlot(self.display.axes[0], self.file.name)

    def pythonPlotCode(self) -> str:
        return f"""# add your custom plot code here
from datetime import datetime

fig = plt.figure(num='{self.name} plot', constrained_layout=True)
ax0 = fig.add_subplot(111)
ax0.set_xlabel('Time')
ax0.set_ylabel('Fitness Value')
for label in ax0.get_xticklabels(which='major'):
    label.set_ha('right')
    label.set_rotation(30)
time_axis = [datetime.fromtimestamp(float(time_axis)) for time_axis in inputs[0].recordingData]
ax0.plot(time_axis, outputs[0].recordingData, label='best fitness')[0]
ax0.plot(time_axis, outputs[1].recordingData, label='avg fitness')[0]
ax0.legend(loc='lower right', prop={{'size': 10}}, frameon=False)
fig.show()
        """

    def run(self, recording) -> None:
        # first datapoint before optimization
        self.inputs[0].recordingData.add(time.time())
        fitnessStart = np.mean(self.outputs[0].getValues(subtractBackground=self.outputs[0].subtractBackgroundActive(), length=self.measurementsPerStep))
        self.outputs[0].recordingData.add(fitnessStart)
        self.outputs[1].recordingData.add(fitnessStart)
        while recording():
            self.gaSignalComm.updateValuesSignal.emit(-1, False)
            time.sleep((self.wait + self.average) / 1000)
            self.ga.fitness(np.mean(self.outputs[0].getValues(subtractBackground=self.outputs[0].subtractBackgroundActive(), length=self.measurementsPerStep)))
            if self.log:
                self.print(self.ga.step_string().replace('GA: ', ''))
            _, session_saved = self.ga.check_restart()
            if session_saved:
                self.print(f'Session Saved -- Average Fitness: {self.ga.average_fitness():6.2f} Best Fitness: {self.ga.best_fitness():6.2f}')
                self.print(f'Starting Generation {self.ga.current_generation}:')
                self.inputs[0].recordingData.add(time.time())
                self.outputs[0].recordingData.add(self.ga.best_fitness())
                self.outputs[1].recordingData.add(self.ga.average_fitness())
                self.signalComm.scanUpdateSignal.emit(False)
        self.ga.check_restart(True)  # sort population
        self.gaSignalComm.updateValuesSignal.emit(0, False)
        self.signalComm.scanUpdateSignal.emit(True)

    def updateValues(self, index=None, initial=False) -> None:
        """Update all optimized values or restores initial values.

        :param index: Index of being in GA population. -1 is current being. 0 is best after sorting. Defaults to None
        :type index: int, optional
        :param initial: Indicates if initial values should be returned, defaults to False
        :type initial: bool, optional
        """
        # only call in main thread as updates GUI
        self.pluginManager.loading = True  # only update after setting all voltages
        for channel in [channel for channel in self.pluginManager.DeviceManager.channels(inout=INOUT.IN) if channel.optimize]:
            channel.value = self.ga.GAget(channel.name, channel.value, index=index, initial=initial)
        self.pluginManager.loading = False
        self.pluginManager.DeviceManager.globalUpdate(inout=INOUT.IN)

    def saveScanParallel(self, file) -> None:
        self.changeLog = [f'Change log for optimizing channels by {self.name}:']
        for channel in [channel for channel in self.pluginManager.DeviceManager.channels(inout=INOUT.IN) if channel.optimize]:
            parameter = channel.getParameterByName(Parameter.VALUE)
            if not parameter.equals(self.ga.GAget(channel.name, channel.value, initial=True)):
                self.changeLog.append(
    f'Changed value of {channel.name} from {parameter.formatValue(self.ga.GAget(channel.name, channel.value, initial=True))} to '
    f'{parameter.formatValue(self.ga.GAget(channel.name, channel.value, index=0))}.')
        if len(self.changeLog) == 1:
            self.changeLog.append('No changes.')
        self.pluginManager.Text.setTextParallel('\n'.join(self.changeLog))
        self.print('Change log available in Text plugin.')
        super().saveScanParallel(file)
