import sys
import time
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import ScalarFormatter
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFontMetrics
from PyQt6.QtWidgets import QTextEdit  # , QSizePolicy  # QLabel, QMessageBox

from esibd.core import INOUT, PARAMETERTYPE, PRINT, DynamicNp, MetaChannel, Parameter, ScanChannel, parameterDict, plotting
from esibd.plugins import Scan

if TYPE_CHECKING:
    from esibd.plugins import Plugin

winsound = None
if sys.platform == 'win32':
    import winsound
else:
    print('Module winsound only available on Windows.')  # noqa: T201


def providePlugins() -> list['Plugin']:
    """Return list of provided plugins. Indicates that this module provides plugins."""
    return [Depo]


class Depo(Scan):
    """Scan that records the sample current and accumulated charge during deposition.

    A target charge and current threshold can be defined and a message will be
    played back when the target has been reached or the current drops below
    the threshold. The time until completion is estimated based on recent data.
    As data analysis is decoupled from data
    acquisition, you can continue to use all other scan modes and
    optimization while the deposition recording is running.
    """

    name = 'Depo'
    version = '1.0'
    CHARGE = 'Charge'
    useDisplayParameter = True
    iconFile = 'depo.png'

    class ScanChannel(ScanChannel):

        def __init__(self, **kwargs) -> None:
            super().__init__(**kwargs)
            self.isChargeChannel = False

        def relayValueEvent(self) -> None:
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

        def initGUI(self, item) -> None:
            super().initGUI(item)
            if self.name.endswith(f'_{Depo.CHARGE}') and self.unit == 'pAh':
                self.isChargeChannel = True
                self.name = self.name.removesuffix(f'_{Depo.CHARGE}')  # change name before connectSource()!

        def connectSource(self) -> None:
            super().connectSource()
            if self.isChargeChannel:
                self.unit = 'pAh'
                self.name += f'_{Depo.CHARGE}'
            if self.sourceChannel is not None and not hasattr(self.sourceChannel, 'resetCharge'):
                # found channel with same name but likely from different device
                super().connectSource()  # running again after changing name -> disconnect
            if self.unit in {'pA', 'pAh'}:
                self.getParameterByName(self.DISPLAY).getWidget().setVisible(False)

    class Display(Scan.Display):
        """Display for Depo scan."""

        class CustomScientificFormatter(ScalarFormatter):
            """Custom formatter that prevents waste of vertical space by offset or scale factor.

            There is still an issue with very large or very small values if log=False.
            In that case the corresponding device should use self.logY = True.
            """

            def __init__(self, *args, log=False, **kwargs) -> None:
                super().__init__(*args, **kwargs)
                self.log = log
                self.set_scientific(True)  # Enable scientific notation
                self.set_useOffset(False)  # Disable the offset/scaling factor above the axis

            def _set_format(self) -> None:
                """Override the default format behavior to suppress scaling."""
                self._useMathText = True
                if self.log:
                    self.format = "%.1e"  # Format ticks in scientific notation (e.g., 1.0e-10)
                else:
                    self.format = "%.1f"  # Format ticks in normal notation

        def initFig(self) -> None:
            super().initFig()
            self.fig.set_constrained_layout_pads(h_pad=-4.0)  # reduce space between axes
            rows = len(self.scan.getExtraUnits()) + 2
            self.axes.append(self.fig.add_subplot(rows, 1, 1))  # current axis
            self.axes.append(self.fig.add_subplot(rows, 1, 2, sharex=self.axes[0]))  # charge axis
            for i, unit in enumerate(self.scan.getExtraUnits()):
                self.axes.append(self.fig.add_subplot(rows, 1, 3 + i, sharex=self.axes[0]))
                self.axes[2 + i].set_ylabel(unit)
            for output in self.scan.outputChannels:
                if output.unit not in {'pA', 'pAh'} and output.unit in self.scan.getExtraUnits():
                    output.line = self.axes[2 + self.scan.getExtraUnits().index(output.unit)].plot([[datetime.now()]], [0], color=output.color, label=output.name)[0]
                    if output.logY:
                        self.axes[2 + self.scan.getExtraUnits().index(output.unit)].set_yscale('log')
                    self.axes[2 + self.scan.getExtraUnits().index(output.unit)].get_yaxis().set_major_formatter(self.CustomScientificFormatter(log=output.logY))
            for i, _ in enumerate(self.scan.getExtraUnits()):
                legend = self.axes[2 + i].legend(loc='best', prop={'size': 6}, frameon=False)
                legend.set_in_layout(False)

            self.currentWarnLine    = self.axes[0].axhline(y=float(self.scan.warnLevel), color=self.scan.MYRED)
            self.depoChargeTarget   = self.axes[1].axhline(y=float(self.scan.target), color=self.scan.MYGREEN)
            if len(self.scan.outputChannels) > 0:
                selected_output = self.scan.outputChannels[self.scan.getOutputIndex()]
                self.currentLine        = self.axes[0].plot([[datetime.now()]], [0], color=selected_output.color)[0]  # need to be initialized with datetime on x axis
                self.chargeLine         = self.axes[1].plot([[datetime.now()]], [0], color=selected_output.color)[0]
                self.chargePredictionLine = self.axes[1].plot([[datetime.now()]], [0], '--', color=selected_output.color)[0]
            for i in range(len(self.axes) - 1):
                self.axes[i].tick_params(axis='x', which='both', bottom=False, labelbottom=False)
            for i in range(len(self.axes)):
                self.addRightAxis(self.axes[i])
            self.axes[0].set_ylabel('pA')
            self.axes[1].set_ylabel('pAh')
            self.axes[-1].set_xlabel(self.TIME)
            self.axes[-1].xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))  # auto formatting will resort to only year if space is limited -> fix format
            self.tilt_xlabels(self.axes[-1])
            self.progressAnnotation = self.axes[1].annotate(text='', xy=(0.02, 0.98), xycoords='axes fraction', fontsize=6, ha='left', va='top',
                                                            bbox={'boxstyle': 'square, pad=.2', 'fc': plt.rcParams['axes.facecolor'], 'ec': 'none'})
            self.updateDepoTarget()

        def updateDepoTarget(self) -> None:
            """Update the deposition target line in the plot."""
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

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.useDisplayChannel = True

    def initGUI(self) -> None:
        super().initGUI()
        self.recordingAction.setToolTip('Toggle deposition.')
        self.depoCheckList = QTextEdit()
        self.depoCheckList.setReadOnly(True)
        self.depoCheckList.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.depoCheckList.setText('Deposition checklist:\n- New session created?\n- Plasma cleaned?\n- Grid in place?\n- Shield closed?\n- Shuttle inserted?\n- Landing energy set?\n'
                                   '- Right polarity?\n- Temperature set?\n- Mass selection on?\n- LN2 ready for transfer?')
        self.depoCheckList.setFixedWidth(QFontMetrics(self.depoCheckList.font()).horizontalAdvance('- LN2 ready for transfer?') + self.depoCheckList.verticalScrollBar().sizeHint().width() + 10)
        self.settingsLayout.addWidget(self.depoCheckList, alignment=Qt.AlignmentFlag.AlignTop)

    def getExtraUnits(self) -> list[str]:
        """Get all units that are not representing a current or a charge."""
        return list({channel.unit for channel in self.outputChannels if channel.unit not in {'pA', 'pAh'} and channel.display})

    def getDefaultSettings(self) -> dict[str, dict]:
        defaultSettings = super().getDefaultSettings()
        defaultSettings.pop(self.WAIT)
        defaultSettings.pop(self.WAITLONG)
        defaultSettings.pop(self.LARGESTEP)
        defaultSettings.pop(self.SCANTIME)
        defaultSettings[self.DISPLAY][Parameter.VALUE] = 'RT_Sample-Center'
        defaultSettings[self.DISPLAY][Parameter.TOOLTIP] = 'Any channel that should be recorded during deposition, including at least one current channel.'
        defaultSettings[self.DISPLAY][Parameter.ITEMS] = 'RT_Sample-Center, RT_Sample-End, C_Shuttle'
        defaultSettings[self.AVERAGE][Parameter.VALUE] = 4000
        defaultSettings[self.INTERVAL]   = parameterDict(value=10000, toolTip='Deposition interval.', parameterType=PARAMETERTYPE.INT,
                                                                minimum=1000, maximum=60000, attr='interval')
        defaultSettings['Target']        = parameterDict(value='15', toolTip='Target coverage in pAh.', items='-20,-15,-10, 10, 15, 20',
                                                                parameterType=PARAMETERTYPE.INTCOMBO, attr='target', event=lambda: self.updateDepoTarget())
        defaultSettings['Warnlevel']     = parameterDict(value='10', toolTip='Warning sound will be played when value drops below this level.', event=lambda: self.updateWarnLevel(),
                                                            items='20, 15, 10, 0, -10, -15, -20', parameterType=PARAMETERTYPE.INTCOMBO, attr='warnLevel')
        defaultSettings['Warn']          = parameterDict(value=False, toolTip='Warning sound will be played when value drops below warnLevel. Disable to Mute.',
                                                            parameterType=PARAMETERTYPE.BOOL, attr='warn')
        defaultSettings['Autoscale']     = parameterDict(value=True, toolTip='Disable y axis autoscale if your data includes outliers, e.g. from pickup spikes.',
                                                            parameterType=PARAMETERTYPE.BOOL, attr='autoscale')
        defaultSettings['Dialog']     = parameterDict(value=True, toolTip='Show check list dialog on start.', parameterType=PARAMETERTYPE.BOOL, attr='dialog')
        return defaultSettings

    def updateDepoTarget(self) -> None:
        """Update the deposition target line in the plot."""
        if self.display is not None and self.display.initializedDock:
            self.display.updateDepoTarget()

    def initScan(self) -> None:
        # overwrite parent
        """Initialize all data and metadata.

        Returns True if initialization successful and scan is ready to start.
        """
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
        if len([output for output in self.outputChannels if output.unit == 'pA']) > 0:  # at least one current channel
            self.inputChannels.append(MetaChannel(parentPlugin=self, name=self.TIME, recordingData=DynamicNp(dtype=np.float64)))
            self.measurementsPerStep = max(int(self.average / self.interval) - 1, 1)
            self.toggleDisplay(True)
            self.display.progressAnnotation.set_text('')
            self.updateFile()
            self.populateDisplayChannel()
            self.display.updateDepoTarget()  # flip axes if needed
            return True
        else:
            self.print('No initialized current output channel found.', PRINT.WARNING)
            return False

    def addOutputChannels(self) -> None:
        for name in self.settingsMgr.settings[self.DISPLAY].items:
            channel = self.addOutputChannel(name=name, recordingData=DynamicNp())
            if hasattr(channel.sourceChannel, 'resetCharge'):
                channel.sourceChannel.resetCharge()
                self.addOutputChannel(name=f'{name}_{self.CHARGE}', unit='pAh', recordingData=DynamicNp())
        self.channelTree.setHeaderLabels([(parameterDict.get(Parameter.HEADER, name.title()))
                                            for name, parameterDict in self.channels[0].getSortedDefaultChannel().items()])
        self.toggleAdvanced(False)

    def populateDisplayChannel(self) -> None:
        # overwrite parent to hide charge channels
        self.loading = True
        self.display.displayComboBox.clear()
        for output in self.outputChannels:
            if output.unit == 'pA':
                self.display.displayComboBox.insertItem(self.display.displayComboBox.count(), output.name)
        self.loading = False
        self.updateDisplayDefault()

    def updateDisplayChannel(self) -> None:
        self.display.initFig()  # need to reinitialize as displayed channels are changing
        super().updateDisplayChannel()

    def updateWarnLevel(self) -> None:
        """Update the warning level line in the plot."""
        if self.display is not None and self.display.currentWarnLine is not None:
            self.display.currentWarnLine.set_ydata([self.warnLevel])
            self.display.canvas.draw_idle()

    MIN_FIT_DATA_POINTS = 10

    @plotting
    def plot(self, update=False, done=True, **kwargs) -> None:  # pylint:disable=unused-argument  # noqa: ARG002
        # timing test with 360 data points (one hour at 0.1 Hz) update True: 75 ms, update False: 135 ms
        if self.loading:
            return
        if len(self.outputChannels) > 0 and len(self.inputChannels) > 0:
            time_axis = self.getData(0, INOUT.IN)
            time_stamp_axis = [datetime.fromtimestamp(float(t)) for t in time_axis]  # convert timestamp to datetime
            charge = []
            for i, output in enumerate(self.outputChannels):
                if i == self.getOutputIndex():
                    self.display.currentLine.set_data(time_stamp_axis, output.getRecordingData())
                elif i == self.getOutputIndex() + 1:
                    charge = output.getRecordingData()
                    self.display.chargeLine.set_data(time_stamp_axis, output.getRecordingData())
                elif output.unit not in {'pA', 'pAh'} and output.display:  # only show current and charge for selected channel
                    if hasattr(output, 'line'):
                        output.line.set_data(time_stamp_axis, output.getRecordingData())
                    else:
                        self.print(f'Line not initialized for channel {output.name}', flag=PRINT.WARNING)
            time_done_str = 'unknown'
            end_str = 'end'
            if len(time_stamp_axis) > self.MIN_FIT_DATA_POINTS or done:  # predict scan based on last 10 data points
                if len(time_stamp_axis) > self.MIN_FIT_DATA_POINTS and update and np.abs(charge[-1]) < np.abs(float(self.target)) and np.abs(charge[-1]) > np.abs(charge[-10]):  # only predict if below target and charge is increasing
                    time_done = datetime.fromtimestamp(float(time_axis[-1] + (time_axis[-1] - time_axis[-10]) / (charge[-1] - charge[-10]) * (float(self.target) - charge[-1])))  # t_t=t_i + dt/dQ * Q_missing
                    self.display.chargePredictionLine.set_data([time_stamp_axis[-1], time_done], [charge[-1], self.target])
                    time_done_str = self.roundDateTime(time_done).strftime('%H:%M')
                    end_str = 'estimated end'
                else:
                    self.display.chargePredictionLine.set_data([[time_stamp_axis[0]]], [0])  # hide at beginning and end of scan or if loaded from file
                if done:
                    time_done_str = self.roundDateTime(datetime.fromtimestamp(float(time_axis[-1]))).strftime('%H:%M')
            if len(time_stamp_axis) > 0:  # predict scan based on last 10 data points
                self.display.progressAnnotation.set_text(f"start: {self.roundDateTime(time_stamp_axis[0]).strftime('%H:%M')}, {end_str}: {time_done_str}\n"
                                        f"{charge[-1] - charge[0]:2.1f} pAh deposited")
        else:  # no data
            self.removeAnnotations(self.display.axes[1])
            self.display.currentLine.set_data([], [])
            self.display.chargeLine .set_data([], [])
        self.display.axes[0].autoscale(True, axis='x')
        self.display.axes[0].relim()
        for i in range(len(self.display.axes)):
            if i > 0:
                self.display.axes[i].autoscale(True)
                self.display.axes[i].relim()
        if self.autoscale:
            self.setLabelMargin(self.display.axes[0], 0.3)
        self.updateToolBar(update=update)
        if len(self.outputChannels) > 0:
            self.labelPlot(self.display.axes[0], f'{self.outputChannels[self.getOutputIndex()].name} from {self.file.name}')
        else:
            self.labelPlot(self.display.axes[0], self.file.name)

    def pythonPlotCode(self) -> str:
        return f"""# add your custom plot code here

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
    return list(set([channel.unit for channel in outputChannels if channel.unit not in ['pA', 'pAh']]))

fig = plt.figure(num='{self.name} plot', constrained_layout=True)
fig.set_constrained_layout_pads(h_pad=-4.0)  # reduce space between axes
rows = len(getExtraUnits()) + 2
axes = []
axes.append(fig.add_subplot(rows, 1, 1))  # current axis
axes[0].set_ylabel('pA')
axes.append(fig.add_subplot(rows, 1, 2, sharex = axes[0]))  # charge axis
axes[1].set_ylabel('pAh')

for i, unit in enumerate(getExtraUnits()):
    axes.append(fig.add_subplot(rows, 1, 3+i, sharex = axes[0]))
    axes[2+i].set_ylabel(unit)

time_axis = inputChannels[0].recordingData
time_stamp_axis = [datetime.fromtimestamp(float(t)) for t in time_axis]  # convert timestamp to datetime
axes[0].plot(time_stamp_axis, outputChannels[output_index].recordingData, color=MYBLUE)[0]
axes[1].plot(time_stamp_axis, outputChannels[output_index+1].recordingData, color=MYBLUE)[0]

for output in outputChannels:
    if output.unit not in ['pA', 'pAh'] and output.unit in getExtraUnits():
        axes[2+getExtraUnits().index(output.unit)].plot(time_stamp_axis, output.recordingData, label=output.name)[0]
        if output.logY:
            axes[2+getExtraUnits().index(output.unit)].set_yscale('log')

for i, unit in enumerate(getExtraUnits()):
    legend = axes[2+i].legend(loc='best', prop={{'size': 6}}, frameon=False)
    legend.set_in_layout(False)

for i in range(len(axes)-1):
    axes[i].tick_params(axis='x', which='both', bottom=False, labelbottom=False)
for i in range(len(axes)):
    addRightAxis(axes[i])
axes[-1].set_xlabel('Time')
axes[-1].xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
tilt_xlabels(axes[-1])

fig.show()

        """

    def roundDateTime(self, interval) -> datetime:
        """Round to nearest minute.

        :param interval: The original time interval.
        :type interval: datetime.datetime
        :return: The rounded time interval.
        :rtype: datetime.datetime
        """
        discard = timedelta(minutes=interval.minute % 1,
                             seconds=interval.second,
                             microseconds=interval.microsecond)
        interval -= discard
        if discard >= timedelta(seconds=30):
            interval += timedelta(minutes=1)
        return interval

    def run(self, recording) -> None:
        while recording():
            time.sleep(self.interval / 1000)
            self.inputChannels[0].recordingData.add(time.time())
            for output in self.outputChannels:
                if output.isChargeChannel:
                    output.recordingData.add(output.sourceChannel.charge)
                else:
                    output.recordingData.add(np.mean(output.getValues(subtractBackground=output.getDevice().subtractBackgroundActive(), length=self.measurementsPerStep)))
            if self.warn and winsound is not None:  # Sound only supported for windows
                if ((np.sign(self.target) == 1 and self.getData(self.getOutputIndex() + 1, INOUT.OUT)[-1] > float(self.target)) or
                              (np.sign(self.target) == -1 and self.getData(self.getOutputIndex() + 1, INOUT.OUT)[-1] < float(self.target))):
                    winsound.PlaySound(str(self.dependencyPath / 'done.wav'), winsound.SND_ASYNC | winsound.SND_ALIAS)
                elif ((np.sign(self.warnLevel) == 1 and self.getData(self.getOutputIndex(), INOUT.OUT)[-1] < float(self.warnLevel)) or
                              (np.sign(self.warnLevel) == -1 and self.getData(self.getOutputIndex(), INOUT.OUT)[-1] > float(self.warnLevel))):
                    winsound.PlaySound(str(self.dependencyPath / 'alarm.wav'), winsound.SND_ASYNC | winsound.SND_ALIAS)
            if recording():  # all but last step
                self.signalComm.scanUpdateSignal.emit(False)  # update graph
        self.signalComm.scanUpdateSignal.emit(True)  # update graph and save data  # placed after while loop to ensure it will be executed
