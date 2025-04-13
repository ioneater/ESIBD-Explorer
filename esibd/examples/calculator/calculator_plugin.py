from esibd.plugins import Plugin
from esibd.core import PluginManager, PRINT
from esibd.examples.calculator.calculator_standalone import Calculator as CalculatorWidget

def providePlugins():
    """Indicates that this module provides plugins. Returns list of provided plugins."""
    return [Calculator]

class Calculator(Plugin):
    """The minimal code in "examples/Calculator.py" demonstrates how to integrate an
    external PyQt6 program as a plugin and interact with other plugins."""

    name = 'Calculator'
    version = '1.0'
    supportedVersion = '0.7'
    pluginType = PluginManager.TYPE.CONTROL
    iconFile = 'calculator.png'

    def initGUI(self):
        """Initialize your custom user interface"""
        super().initGUI()
        self.calculatorWidget = CalculatorWidget() # use this to import calculator as is
        # self.calculatorWidget = ExtendedCalculatorWidget(parentPlugin=self) # use this to import calculator with interface to other plugins
        self.addContentWidget(self.calculatorWidget)

class ExtendedCalculatorWidget(CalculatorWidget):
    """Optionally extend the calculator widget to allow interfacing with other plugins."""

    def __init__(self, parentPlugin):
        self.parentPlugin = parentPlugin
        super().__init__()

    def evaluate(self):
        channels = self.parentPlugin.pluginManager.DeviceManager.channels()
        channelNames = [channel.name for channel in channels if channel.name != '']
        channelNames.sort(reverse=True, key=len) # avoid replacing a subset of a longer name with a matching shorter name of another channel
        equ = self.display.text()
        for name in channelNames:
            if name in equ:
                channel_equ = next((channel for channel in channels if channel.name == name), None)
                self.parentPlugin.print(f'Replacing channel name {name} with value {channel_equ.value-channel_equ.background if channel_equ.useBackgrounds else channel_equ.value}.', flag=PRINT.MESSAGE)
                equ = equ.replace(channel_equ.name, f'{channel_equ.value-channel_equ.background if channel_equ.useBackgrounds else channel_equ.value}')
        self.display.setText(equ)
        super().evaluate()
