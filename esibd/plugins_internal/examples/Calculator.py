import sys
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QGridLayout, QPushButton, QLineEdit
from PyQt6.QtCore import Qt
from esibd.plugins import Plugin
from esibd.core import PluginManager, PRINT
from esibd.plugins_internal.examples.calculator_standalone import Calculator as CalculatorWidget

def providePlugins():
    return [Calculator]

class ExtendedCalculatorWidget(CalculatorWidget):
    """Optionally extend the calculator widget to allow interfacing with other plugins."""

    def __init__(self, parentPlugin):
        self.parentPlugin = parentPlugin
        super().__init__()

    def onButtonClick(self, label):
        channels = self.parentPlugin.pluginManager.DeviceManager.channels()
        channelNames = [channel.name for channel in channels if channel.name != '']
        channelNames.sort(reverse=True, key=len) # avoid replacing a subset of a longer name with a matching shorter name of another channel
        equ = self.display.text()
        for name in channelNames:
            if name in equ:
                channel_equ = next((channel for channel in channels if channel.name == name), None)
                if channel_equ is None:
                    self.parentPlugin.print(f'Could not find channel {name} in equation.', PRINT.WARNING)
                else:
                    equ = equ.replace(channel_equ.name, f'{channel_equ.value}')
        self.display.setText(equ)
        super().onButtonClick(label)

class Calculator(Plugin):
    """The minimal code in "examples/Calculator.py" demonstrates how to integrate an
    external PyQt6 program as a plugin."""

    name = 'Calculator'
    version = '1.0'
    supportedVersion = '0.7'
    pluginType = PluginManager.TYPE.CONTROL
    iconFile = 'calculator.png'

    def initGUI(self):
        """Initialize your custom user interface"""
        super().initGUI()
        self.calculatorWidget = ExtendedCalculatorWidget(parentPlugin=self) # use this to import calculator with interface to other plugins
        # self.calculatorWidget = CalculatorWidget() # use this to import calculator as is
        self.addContentWidget(self.calculatorWidget)
