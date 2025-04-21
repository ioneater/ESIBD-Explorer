"""This module contains classes that contain and manage a list of (extended) UI elements.
In addition it contains classes used to manage data acquisition.
Finally it contains classes for data export, and data import."""

import time
from scipy.stats import binned_statistic
from PyQt6.QtWidgets import QSlider  #, QTextEdit  #, QSizePolicy  # QLabel, QMessageBox
from PyQt6.QtCore import Qt
import numpy as np
from esibd.core import Parameter, parameterDict, DynamicNp, plotting
from esibd.plugins import Scan

def providePlugins() -> None:
    """Indicates that this module provides plugins. Returns list of provided plugins."""
    return [Omni]

class Omni(Scan):
    """This is the most basic scan which simply records a number of arbitrary output
    channels as a function of a single arbitrary input channel. When switched to the
    interactive mode, a slider will appear that allows to set the value of
    the input channel manually and independent of the scan settings. This
    may be more intuitive and faster than automated scanning, e.g. when looking for a local maximum."""

    name = 'Omni'
    version = '1.0'
    useDisplayParameter = True
    iconFile = 'omni.png'

    class Display(Scan.Display):
        """Display for Omni scan."""

        def __init__(self, scan, **kwargs):
            super().__init__(scan, **kwargs)
            self.xSlider = None
            self.lines = None

        def initFig(self) -> None:
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
            """Updates the value of the independent variable based on slider value.

            :param value: Slider value.
            :type value: float
            """
            if self.scan.inputs[0].sourceChannel is not None:
                self.scan.inputs[0].value = self.scan._from + value/self.xSlider.maximum()*(self.scan.to - self.scan._from)  # map slider range onto range

        def updateInteractive(self):
            """Adjusts the scan based on the interactive Setting.
            If interactive, a slider is used to change the independent variable in real time."""
            if self.xSlider is not None:
                self.xSlider.setVisible(self.scan.interactive)
                if self.scan.interactive and len(self.scan.inputs) > 0:
                    self.xSlider.setValue(int((self.scan.inputs[0].value - self.scan.inputs[0].min)*
                                              self.xSlider.maximum()/(self.scan.inputs[0].max - self.scan.inputs[0].min)))

    def getDefaultSettings(self) -> None:
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
        """Adjusts the scan based on the interactive Setting."""
        if self.display is not None and self.display.initializedDock:
            self.display.updateInteractive()
        self.estimateScanTime()

    @Scan.finished.setter
    def finished(self, finished):
        Scan.finished.fset(self, finished)
        # disable inputs while scanning
        self.settingsMgr.settings[self.INTERACTIVE].setEnabled(finished)

    def estimateScanTime(self) -> None:
        if self.interactive:
            self.scantime = 'n/a'
        else:
            super().estimateScanTime()

    def initScan(self) -> None:
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

    def loadDataInternal(self) -> None:
        super().loadDataInternal()
        self.display.lines = None

    @plotting
    def plot(self, update=False, done=True, **kwargs) -> None:  # pylint:disable=unused-argument
        if len(self.outputs) > 0:
            if self.display.lines is None:
                self.display.axes[0].clear()
                self.display.lines = []  # dummy plots
                for output in self.outputs:
                    if output.sourceChannel is not None:
                        self.display.lines.append(self.display.axes[0].plot([], [], label=f'{output.name} ({output.unit})', color=output.color)[0])
                    else:
                        self.display.lines.append(self.display.axes[0].plot([], [], label=f'{output.name} ({output.unit})')[0])
                # self.labelPlot(self.display.axes[0], self.file.name)  # text ignored loc='best' https://github.com/matplotlib/matplotlib/issues/23323
                legend = self.display.axes[0].legend(loc='best', prop={'size': 7}, frameon=False)
                legend.set_in_layout(False)
            if not update:
                self.display.axes[0].set_xlabel(f'{self.inputs[0].name} ({self.inputs[0].unit})')
                if self.recording:  # show all data if loaded from file
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
            self.display.axes[0].relim()  # adjust to data
            self.setLabelMargin(self.display.axes[0], 0.15)
        self.updateToolBar(update=update)
        self.labelPlot(self.display.axes[0], self.file.name)

    def pythonPlotCode(self) -> None:
        return """# add your custom plot code here
from scipy.stats import binned_statistic

_interactive = False  # set to True to use histogram
bins = 20  # choose number of bins
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
fig.show()
        """  # similar to staticDisplay

    def run(self, recording) -> None:
        if self.interactive:
            while recording():
                # changing input is done in main thread using slider. Scan is only recording result.
                time.sleep((self.wait+self.average)/1000)  # if step is larger than threshold use longer wait time
                if self.inputs[0].recording:  # get average
                    self.inputs[0].recordingData.add(np.mean(self.inputs[0].getValues(subtractBackground=self.inputs[0].subtractBackgroundActive(), length=self.measurementsPerStep)))
                else:  # use last value
                    self.inputs[0].recordingData.add(self.inputs[0].value)
                for j, output in enumerate(self.outputs):
                    self.outputs[j].recordingData.add(np.mean(output.getValues(subtractBackground=output.subtractBackgroundActive(), length=self.measurementsPerStep)))
                if not recording():  # last step
                    self.signalComm.scanUpdateSignal.emit(True)  # update graph and save data
                    self.signalComm.updateRecordingSignal.emit(False)
                else:
                    self.signalComm.scanUpdateSignal.emit(False)  # update graph
        else:
            steps = self.inputs[0].getRecordingData()
            self.print(f'Starting scan M{self.pluginManager.Settings.measurementNumber:03}. Estimated time: {self.scantime}')
            for i, step in enumerate(steps):  # scan over all steps
                waitLong = False
                if not waitLong and abs(self.inputs[0].value-step) > self.largestep:
                    waitLong=True
                self.inputs[0].updateValueSignal.emit(step)
                time.sleep(((self.waitLong if waitLong else self.wait)+self.average)/1000)  # if step is larger than threshold use longer wait time
                for j, output in enumerate(self.outputs):
                    output.recordingData[i] = np.mean(output.getValues(subtractBackground=output.getDevice().subtractBackgroundActive(), length=self.measurementsPerStep))
                if i == len(steps)-1 or not recording():  # last step
                    self.inputs[0].updateValueSignal.emit(self.inputs[0].initialValue)
                    time.sleep(.5)  # allow time to reset to initial value before saving
                    self.signalComm.scanUpdateSignal.emit(True)  # update graph and save data
                    self.signalComm.updateRecordingSignal.emit(False)
                    break  # in case this is last step
                else:
                    self.signalComm.scanUpdateSignal.emit(False)  # update graph
