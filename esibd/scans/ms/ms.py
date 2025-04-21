"""This module contains classes that contain and manage a list of (extended) UI elements.
In addition it contains classes used to manage data acquisition.
Finally it contains classes for data export, and data import."""

import h5py
from esibd.core import (Parameter, INOUT, parameterDict, plotting,
    MetaChannel, MZCalculator)
from esibd.plugins import Scan

def providePlugins() -> None:
    """Indicates that this module provides plugins. Returns list of provided plugins."""
    return [MassSpec]

class MassSpec(Scan):
    """Records mass spectra by recording an output channel as a function of a (calibrated) input channel.
    Left clicking on peaks in a charge state series while holding down the Ctrl key provides a
    quick estimate of charge state and mass, based on minimizing the standard
    deviation of the mass as a function of possible charge states.
    Use Ctrl + right mouse click to reset.
    This can be used as a template or a parent class for a simple one dimensional scan of other properties."""

    name = 'msScan'
    version = '1.1'
    supportedVersion = '0.7'
    iconFile = 'msScan.png'

    class Display(Scan.Display):
        """Display for MassSpec scan."""

        def initGUI(self) -> None:
            self.mzCalc = MZCalculator(parentPlugin=self)
            super().initGUI()
            self.addAction(lambda: self.copyLineDataClipboard(line=self.ms), 'Data to Clipboard.', icon=self.dataClipboardIcon, before=self.copyAction)

        def initFig(self) -> None:
            super().initFig()
            self.axes.append(self.fig.add_subplot(111))
            self.ms  = self.axes[0].plot([], [])[0]  # dummy plot
            self.mzCalc.setAxis(self.axes[0])
            self.canvas.mpl_connect('button_press_event', self.mzCalc.msOnClick)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.useDisplayChannel = True
        self.previewFileTypes.append('ms scan.h5')

    def getDefaultSettings(self) -> None:
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

    def initScan(self) -> None:
        return (self.addInputChannel(self.channel, self._from, self.to, self.step) and super().initScan())

    @plotting
    def plot(self, update=False, done=False, **kwargs):  # pylint:disable=unused-argument
        if len(self.outputs) > 0:
            self.display.ms.set_data(self.inputs[0].getRecordingData(), self.outputs[self.getOutputIndex()].getRecordingData())
            if not update:
                self.display.axes[0].set_ylabel(f'{self.outputs[self.getOutputIndex()].name} ({self.outputs[self.getOutputIndex()].unit})')
                self.display.axes[0].set_xlabel(f'{self.inputs[0].name} ({self.inputs[0].unit})')
        else:  # no data
            self.display.ms.set_data([],[])
        self.display.axes[0].relim()  # adjust to data
        self.setLabelMargin(self.display.axes[0], 0.15)
        self.updateToolBar(update=update)
        self.display.mzCalc.update_mass_to_charge()
        if len(self.outputs) > 0:
            self.labelPlot(self.display.axes[0], f'{self.outputs[self.getOutputIndex()].name} from {self.file.name}')
        else:
            self.labelPlot(self.display.axes[0], self.file.name)

    def pythonPlotCode(self) -> None:
        return """# add your custom plot code here

fig = plt.figure(constrained_layout=True)
ax0 = fig.add_subplot(111)

ax0.plot(inputs[0].recordingData, outputs[output_index].recordingData)
ax0.set_ylabel(f'{outputs[output_index].name} ({outputs[output_index].unit})')
ax0.set_xlabel(f'{inputs[0].name} ({inputs[0].unit})')

fig.show()
"""

    def loadData(self, file, _show=True) -> None:
        super().loadData(file, _show)
        self.display.mzCalc.clear()

    def loadDataInternal(self) -> None:
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
