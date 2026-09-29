# pylint: disable=[missing-module-docstring]  # see class docstrings

import time
from collections.abc import Callable
from threading import Thread
from typing import cast

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QGridLayout, QLineEdit, QTreeWidgetItem

from esibd.core import PLUGINTYPE, CheckBox, LabviewSpinBox, TreeWidget
from esibd.plugins import Plugin


def providePlugins() -> 'list[type[Plugin]]':
    """Indicate that this module provides plugins. Returns list of provided plugins."""
    return [Sequencer]


class Sequencer(Plugin):
    """Run a sequence of commands to create dynamic workflows.

    Each command is executed after a defined delay.
    The plugin provides controls to start the sequence, pause at current step, or stop the sequence.

    Commands may include defining parameters or variables in the Console namespace, which can be accessed by following commands in the sequence.

    Future Features may contain:
    - running loops of subsequences
    - saving and loading sequences
    - running worflows line by line directly from a text file
    - optionally hide all messages from console
    """

    name = 'Sequencer'
    version = '1.0'
    supportedVersion = '1.0'
    pluginType = PLUGINTYPE.CONTROL
    iconFile = 'sequencer.png'
    signalComm: 'SignalCommunicate'

    class SignalCommunicate(Plugin.SignalCommunicate):
        """Bundle pyqtSignals."""

        stopRunningSignal = pyqtSignal()
        """Signal that allows to stop recording from an external thread."""

    def initGUI(self) -> None:
        """Initialize your custom user interface."""
        super().initGUI()
        self.signalComm.stopRunningSignal.connect(self.stopSequence)
        lay = QGridLayout()
        self.tree = TreeWidget()
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels(['Current', 'Delay', 'Command'])
        self.tree.setRootIsDecorated(False)
        lay.addWidget(self.tree)
        self.addContentLayout(lay)
        self.running = False
        self.demoComands = [
            'Browser.previewFileTypes',
            'inspect.getdoc(Settings)',
            'Tree.inspect(Settings)',
            'a = 2+4',
            'b = 2*a+4',
            'b',
            'np.sqrt(b)',
            '# Close valve 32',
            '# Set heater 5 to 10 W',
            '# T = sensor 3 temperature',
            '# More custom commands']
        self.initSequence()

        self.runSequenceAction = self.addStateAction(event=self.runSequence,
                                                   toolTipFalse='Run Sequence', iconFalse=self.makeCoreIcon(file='play.png'),
                                                   toolTipTrue='Pause Sequence', iconTrue=self.makeCoreIcon(file='pause.png'))
        self.stopSequenceAction = self.addAction(event=self.stopSequence,
                                                   toolTip='Stop Sequence', icon=self.makeCoreIcon(file='stop.png'))


    def initSequence(self) -> None:
        """Initialize the sequence of commands.

        TODO Replace with proper import to restore last used sequece.
        """
        for i, command in enumerate(self.demoComands):
            sequenceWidgetItem = QTreeWidgetItem(self.tree.invisibleRootItem())
            checkbox = CheckBox()
            checkbox.setChecked(i == 0)
            checkbox.setToolTip('Indicate current step in sequence.\nWill resume from selected command if paused.\nStop to return to start of sequence.')
            self.tree.setItemWidget(sequenceWidgetItem, 0, checkbox)

            commandDelaySpinBox = LabviewSpinBox()
            commandDelaySpinBox.setValue(1000 if i>0 else 0)
            commandDelaySpinBox.setToolTip('Command delay in ms.')
            self.tree.setItemWidget(sequenceWidgetItem, 1, commandDelaySpinBox)

            commandTextEdit = QLineEdit()
            commandTextEdit.setText(command)
            self.tree.setItemWidget(sequenceWidgetItem, 2, commandTextEdit)

    def runSequence(self) -> None:
        if self.running:
            # Pausing. Do not reset current command selection. Sequence will restart from here.
            self.running = False
        else:
            # start running sequence
            self.running = True
            Thread(target=self.runSequenceFromThread, args=(lambda: self.running,), name='runSequenceFromThread').start()

    def runSequenceFromThread(self, running: Callable) -> None:
        while running():
            if self.tree:
                root = self.tree.invisibleRootItem()
                selectedSequenceWidgetIndex = None
                selectedSequenceWidgetItem = None
                if root:
                    for i, child in enumerate([root.child(j) for j in range(root.childCount())]):
                        if child and self.tree.itemWidget(child, 0) and cast('CheckBox', (self.tree.itemWidget(child, 0))).isChecked():
                            # find currently selected step
                            selectedSequenceWidgetIndex = i
                            selectedSequenceWidgetItem=child
                            break
                    if selectedSequenceWidgetItem and selectedSequenceWidgetIndex is not None:
                        delay = float(cast('LabviewSpinBox', (self.tree.itemWidget(selectedSequenceWidgetItem, 1))).value()) / 1000
                        time.sleep(delay)
                        command = cast('QLineEdit', (self.tree.itemWidget(selectedSequenceWidgetItem, 2))).text()
                        self.pluginManager.Console.execute(command=command)

                        cast('CheckBox', (self.tree.itemWidget(selectedSequenceWidgetItem, 0))).setChecked(False)
                        if selectedSequenceWidgetIndex == root.childCount() -1:
                            # stop and select start of sequence
                            cast('CheckBox', (self.tree.itemWidget(root.child(0), 0))).setChecked(True)
                            self.signalComm.stopRunningSignal.emit()
                            break
                        # select next command in sequence
                        cast('CheckBox', (self.tree.itemWidget(root.child(selectedSequenceWidgetIndex+1), 0))).setChecked(True)

    def stopSequence(self) -> None:
        self.runSequenceAction.state = False
        self.running = False
        if self.tree:
            root = self.tree.invisibleRootItem()
            if root:
                for i, child in enumerate([root.child(j) for j in range(root.childCount())]):
                    if child and self.tree.itemWidget(child, 0):
                        cast('CheckBox', (self.tree.itemWidget(child, 0))).setChecked(i == 0) # only check first command
