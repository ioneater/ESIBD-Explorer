""" Defines constants used througout the package."""

from enum import Enum
import importlib
from datetime import datetime
from PyQt6.QtGui import QColor
from PyQt6.QtCore import QSettings
from esibd.config import * # pylint: disable = wildcard-import, unused-wildcard-import

PROGRAM         = 'Program'
VERSION         = 'Version'
NAME            = 'Name'
PLUGIN          = 'Plugin'
INFO            = 'Info'
TIMESTAMP       = 'Time'
GENERAL         = 'General'
LOGGING         = 'Logging'
DATAPATH        = 'Data path'
CONFIGPATH      = 'Config path'
PLUGINPATH      = 'Plugin path'
DEBUG           = 'Debug mode'
DARKMODE        = 'Dark mode'
CLIPBOARDTHEME  = 'Clipboard theme'
DPI             = 'DPI'
TESTMODE        = 'Test mode'
GEOMETRY        = 'GEOMETRY'
SETTINGSWIDTH   = 'SettingsWidth'
SETTINGSHEIGHT  = 'SettingsHeight'
CONSOLEHEIGHT   = 'ConsoleHeight'

# NOTE: default paths should not be in softwarefolder as this might not have write access after installation
defaultDataPath   = Path.home() / PROGRAM_NAME / 'data/'
defaultConfigPath = Path.home() / PROGRAM_NAME / 'conf/'
defaultPluginPath = Path.home() / PROGRAM_NAME / 'plugins/'

# file types
FILE_INI = '.ini'
FILE_H5  = '.h5'
FILE_PDF = '.pdf'

# other
UTF8    = 'utf-8'

qSet = QSettings(COMPANY_NAME, PROGRAM_NAME)

class Colors():
    """Provides dark mode dependent defaul colors."""

    @property
    def fg(self):
        return '#e4e7eb' if getDarkMode() else '#000000'

    @property
    def bg(self):
        return '#202124' if getDarkMode() else '#ffffff'

    @property
    def bgAlt1(self):
        return QColor(self.bg).lighter(160).name() if getDarkMode() else QColor(self.bg).darker(105).name()

    @property
    def bgAlt2(self):
        return QColor(self.bg).lighter(200).name() if getDarkMode() else QColor(self.bg).darker(110).name()

    @property
    def highlight(self):
        return '#8ab4f7' if getDarkMode() else '#0063e6'

colors = Colors()

class INOUT(Enum):
    """Used to specify if a function affects only input, only output, or all channels."""
    IN = 0
    """Input"""
    OUT = 1
    """Output"""
    BOTH = 2
    """Both input and output."""

class PRINT(Enum):
    """Used to specify if a function affects only input, only output, or all channels."""
    MESSAGE = 0
    """A standard message."""
    WARNING = 1
    """Tag message as warning and highlight using color."""
    ERROR = 2
    """Tag message as error and highlight using color."""
    DEBUG = 3
    """Only show if debug flag is enabled."""
    EXPLORER = 4
    """Key messages by Explorer"""

def makeSettingWrapper(name, settingsMgr, docstring=None):
    """ Neutral setting wrapper for convenient access to the value of a setting.
        If you need to handle events on value change, link these directly to the events of the corresponding control.
    """
    def getter(self): # pylint: disable=[unused-argument] # self will be passed on when used in class
        return settingsMgr.settings[name].value
    def setter(self, value): # pylint: disable=[unused-argument] # self will be passed on when used in class
        settingsMgr.settings[name].value = value
    return property(getter, setter, doc=docstring)

def makeWrapper(name, docstring=None):
    """ Neutral property wrapper for convenient access to the value of a parameter inside a channel.
        If you need to handle events on value change, link these directly to the events of the corresponding control in the finalizeInit method.
    """
    def getter(self):
        return self.getParameterByName(name).value
    def setter(self, value):
        self.getParameterByName(name).value = value
    return property(getter, setter, doc=docstring)

def makeStateWrapper(stateAction, docstring=None):
    """State wrapper for convenient access to the value of a StateAction."""
    def getter(self): # pylint: disable = unused-argument
        return stateAction.state
    def setter(self, state): # pylint: disable = unused-argument
        stateAction.state = state
    return property(getter, setter, doc=docstring)

def dynamicImport(module, path):
    spec = importlib.util.spec_from_file_location(module, path)
    Module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(Module)
    return Module

def getShowDebug():
    """Gets the debug mode from :ref:`sec:settings`.

    :return: Debug mode
    :rtype: bool
    """
    return qSet.value(f'{GENERAL}/{DEBUG}', 'true') == 'true'

def getDarkMode():
    """Gets the dark mode from :ref:`sec:settings`.

    :return: Dark mode
    :rtype: bool
    """
    return qSet.value(f'{GENERAL}/{DARKMODE}', 'true') == 'true'

def getClipboardTheme():
    """Gets the dark clipboard mode from :ref:`sec:settings`.

    :return: Dark clipboard mode
    :rtype: bool
    """
    return qSet.value(f'{GENERAL}/{CLIPBOARDTHEME}', 'true') == 'true'

def getDPI():
    """Gets the DPI from :ref:`sec:settings`.

    :return: DPI
    :rtype: int
    """
    return int(qSet.value(f'{GENERAL}/{DPI}', 100))# need explicit conversion as stored as string

def getTestMode():
    """Gets the test mode from :ref:`sec:settings`.

    :return: Test mode
    :rtype: bool
    """
    return qSet.value(f'{GENERAL}/{TESTMODE}', 'false') == 'true'

def infoDict(name):
    return {PROGRAM : PROGRAM_NAME, VERSION : str(PROGRAM_VERSION), PLUGIN : name, TIMESTAMP : datetime.now().strftime('%Y-%m-%d %H:%M')}

def validatePath(path, default):
    """Returns a valid path. If the path does not exist, falling back to default. If default does not exist it will be created
    
    :return: Valid path
    :rtype: Path    
    :return: Indicates if path has changed during validation
    :rtype: bool
    """
    path = Path(path)
    default = Path(default)
    if not path.exists():
        default = Path(default)
        if path == default:
            print(f'Creating {default.as_posix()}.')
        else:
            print(f'Could not find path {path.as_posix()}. Defaulting to {default.as_posix()}.')
        default.mkdir(parents=True, exist_ok=True)
        return default, True
    else:
        return path, False
