""" Defines constants used throughout the package."""

from enum import Enum
import sys
import subprocess
import importlib
import numpy as np
import traceback
from datetime import datetime
from scipy import signal
from functools import wraps
from PyQt6.QtGui import QColor
from PyQt6.QtCore import QSettings
from esibd.config import * # pylint: disable = wildcard-import, unused-wildcard-import  # noqa: F403

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
ICONMODE        = 'Icon mode'
GEOMETRY        = 'GEOMETRY'
SETTINGSWIDTH   = 'SettingsWidth'
SETTINGSHEIGHT  = 'SettingsHeight'
CONSOLEHEIGHT   = 'ConsoleHeight'
INPUTCHANNELS   = 'Input Channels'
OUTPUTCHANNELS  = 'Output Channels'
UNIT            = 'Unit'
SELECTFILE      = 'Select File'
SELECTPATH  = 'Select Path'

# * default paths should not be in software folder as this might not have write access after installation
defaultDataPath   = Path.home() / PROGRAM_NAME / 'data/'
defaultConfigPath = Path.home() / PROGRAM_NAME / 'conf/'
defaultPluginPath = Path.home() / PROGRAM_NAME / 'plugins/'

# file types
FILE_INI = '.ini'
FILE_H5  = '.h5'
FILE_PDF = '.pdf'
FILE_PY  = '.py'

# other
UTF8    = 'utf-8'

qSet = QSettings(COMPANY_NAME, PROGRAM_NAME)

class Colors():
    """Provides dark mode dependent default colors."""

    fg_dark = '#e4e7eb'
    fg_light ='#000000'

    @property
    def fg(self):
        """Foreground color."""
        return self.fg_dark if getDarkMode() else self.fg_light

    bg_dark = '#202124'
    bg_light ='#ffffff'

    @property
    def bg(self):
        """Background color."""
        return self.bg_dark if getDarkMode() else self.bg_light

    @property
    def bgAlt1(self):
        """First alternative background color."""
        return QColor(self.bg).lighter(160).name() if getDarkMode() else QColor(self.bg).darker(105).name()

    @property
    def bgAlt2(self):
        """Second alternative background color."""
        return QColor(self.bg).lighter(200).name() if getDarkMode() else QColor(self.bg).darker(110).name()

    @property
    def highlight(self):
        """Highlight color."""
        return '#8ab4f7' if getDarkMode() else '#8ab4f7'

colors = Colors()

def rgb_to_hex(rgba):
    """Converts colors from rgb to hex.

    :param rgba: RGBA color tuple.
    :type rgba: tuple
    :return: Hex color string.
    :rtype: str
    """
    return "#{:02x}{:02x}{:02x}".format(int(rgba[0] * 255), int(rgba[1] * 255), int(rgba[2] * 255))

class INOUT(Enum):
    """Used to specify if a function affects only input, only output, or all channels."""
    IN = 0
    """Input"""
    OUT = 1
    """Output"""
    BOTH = 2
    """Both input and output."""
    NONE = 3
    """Neither input nor output."""
    ALL = 4
    """Input and output and all others."""

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

def pluginSupported(pluginVersion):
    """Tests if given version is supported by comparing to current program version.

    :param pluginVersion: Version that the plugin supports.
    :type pluginVersion: str
    :return: True if the plugin is supported.
    :rtype: bool
    """
    return version.parse(pluginVersion).major == PROGRAM_VERSION.major and version.parse(pluginVersion).minor == PROGRAM_VERSION.minor

def makeSettingWrapper(name, settingsMgr, docstring=None):
    """Neutral setting wrapper for convenient access to the value of a setting.
    If you need to handle events on value change, link these directly to the events of the corresponding control.

    :param name: The setting name.
    :type name: str
    :param settingsMgr: The SettingsManager of the setting.
    :type settingsMgr: esibd.plugins.SettingsManager
    :param docstring: The docstring used for the attribute, defaults to None
    :type docstring: str, optional
    """
    def getter(self): # pylint: disable=[unused-argument] # self will be passed on when used in class
        return settingsMgr.settings[name].value
    def setter(self, value): # pylint: disable=[unused-argument] # self will be passed on when used in class
        settingsMgr.settings[name].value = value
    return property(getter, setter, doc=docstring)

def makeWrapper(name, docstring=None):
    """Neutral property wrapper for convenient access to the value of a parameter inside a channel.
    If you need to handle events on value change, link these directly to the events of the corresponding control in the finalizeInit method.

    :param name: The parameter name.
    :type name: str
    :param docstring: The docstring used for the attribute, defaults to None
    :type docstring: str, optional
    """
    def getter(self):
        return self.getParameterByName(name).value
    def setter(self, value):
        self.getParameterByName(name).value = value
    return property(getter, setter, doc=docstring)

def makeStateWrapper(stateAction, docstring=None):
    """State wrapper for convenient access to the value of a StateAction.

    :param stateAction: The StateAction.
    :type stateAction: esibd.core.StateAction
    :param docstring: The docstring assigned to the attribute, defaults to None
    :type docstring: str, optional
    """
    def getter(self): # pylint: disable = unused-argument
        return stateAction.state
    def setter(self, state): # pylint: disable = unused-argument
        stateAction.state = state
    return property(getter, setter, doc=docstring)

def dynamicImport(module, path):
    """_summary_

    :param module: module name
    :type module: str
    :param path: module path
    :type path: str
    :return: Module
    :rtype: ModuleType
    """
    spec = importlib.util.spec_from_file_location(module, path)
    Module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(Module)
    return Module

def getShowDebug():
    """Gets the debug mode from :ref:`sec:settings`.

    :return: Debug mode
    :rtype: bool
    """
    return qSet.value(f'{GENERAL}/{DEBUG}', defaultValue='true', type=bool)

def getDarkMode():
    """Gets the dark mode from :ref:`sec:settings`.

    :return: Dark mode
    :rtype: bool
    """
    return qSet.value(f'{GENERAL}/{DARKMODE}', defaultValue='true', type=bool)

def setDarkMode(darkMode):
    """Sets the dark mode from :ref:`sec:settings`.

    :param darkMode: True if dark mode active.
    :type darkMode: bool
    """
    qSet.setValue(f'{GENERAL}/{DARKMODE}', darkMode)
    # qSet.value(f'{GENERAL}/{DARKMODE}', defaultValue='true', type=bool)

def getClipboardTheme():
    """Gets the dark clipboard mode from :ref:`sec:settings`.

    :return: Dark clipboard mode
    :rtype: bool
    """
    return qSet.value(f'{GENERAL}/{CLIPBOARDTHEME}', defaultValue='true', type=bool)

def getDPI():
    """Gets the DPI from :ref:`sec:settings`.

    :return: DPI
    :rtype: int
    """
    return int(qSet.value(f'{GENERAL}/{DPI}', 100)) # need explicit conversion as stored as string

def getIconMode():
    """Gets the icon mode from :ref:`sec:settings`.

    :return: Icon mode
    :rtype: str
    """
    return qSet.value(f'{GENERAL}/{ICONMODE}', 'Icons')

def getTestMode():
    """Gets the test mode from :ref:`sec:settings`.

    :return: Test mode
    :rtype: bool
    """
    return qSet.value(f'{GENERAL}/{TESTMODE}', defaultValue='false', type=bool)

def infoDict(name):
    """Dictionary with general information, usually used to add this information to exported files.

    :param name: Usually the name of the plugin requesting the infoDict.
    :type name: str
    :return: infoDict
    :rtype: dict
    """
    return {PROGRAM : PROGRAM_NAME, VERSION : str(PROGRAM_VERSION), PLUGIN : name, TIMESTAMP : datetime.now().strftime('%Y-%m-%d %H:%M')}

def validatePath(path, default):
    """Returns a valid path. If the path does not exist, falling back to default. If default does not exist it will be created

    :param path: Valid path
    :type path: pathlib.Path
    :param default: Default path that is returned if path is not valid.
    :type default: pathlib.Path
    :return: Validated path and indication if path has changed during validation.
    :rtype: pathlib.Path, bool
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

def smooth(array, smooth):
    """Smooths a 1D array while keeping edges meaningful.
    This method is robust if array contains np.nan.

    :param array: Array to be smoothed
    :type array: np.array
    :param smooth: With of box used for smoothing
    :type smooth: int
    :return: convolvedArray
    :rtype: np.array
    """
    if len(array) < smooth:
        return array
    smooth = int(np.ceil(smooth / 2.) * 2) # make even
    padding = int(smooth/2)
    win = signal.windows.boxcar(smooth)
    paddedArray = np.concatenate((array[:padding][::-1], array, array[-padding:][::-1])) # pad ends
    convolvedArray = signal.convolve(paddedArray, win, mode='same') / sum(win)
    return convolvedArray[padding:-padding]

def shorten_text(text, max_length = 100):
    """Shortens text e.g. for concise and consistent log file format.

    :param text: Original text.
    :type text: str
    :param max_length: Length after shortening. Defaults to 100
    :type max_length: int, optional
    :return: shortened text
    :rtype: str
    """
    keep_chars = (max_length - 3) // 2
    text = text.replace('\n', '')
    return text if len(text) < max_length else f'{text[:keep_chars]}…{text[-keep_chars:]}'

def synchronized(timeout=5):
    """Decorator to add thread-safety using a lock from the instance.
    Use with @synchronized() or @synchronized(timeout=5).

    :param timeout: Will wait this long for lock to become available. Defaults to 5
    :type timeout: int, optional
    :return: decorator
    :rtype: decorator
    """
    # avoid calling QApplication.processEvents() inside func as it may cause deadlocks
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            # self.print(f'Acquiring lock for {func.__name__}', flag=PRINT.DEBUG)
            with self.lock.acquire_timeout(timeout=timeout, timeoutMessage=f'Cannot acquire lock for {func.__name__} Stack: {"".join(traceback.format_stack()[:-1])}') as lock_acquired: #
                if lock_acquired:
                    # self.print(f'Lock acquired for {func.__name__}', flag=PRINT.DEBUG)
                    result = func(self, *args, **kwargs)
                # self.print(f'Releasing lock for {func.__name__}', flag=PRINT.DEBUG)
                    return result
                return None
        return wrapper
    return decorator

def plotting(func):
    """Decorator that checks for and sets the plotting flag to make sure func is not executed before previous call is processed.
    Only use within a class that contains the plotting flag.
    This is intended for Scans, but might be used elsewhere.

    :param func: function to add the decorator to
    :type func: callable
    :return: decorated function
    :rtype: callable
    """
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        if self.pluginManager.plotting:
            self.print('Skipping plotting as previous request is still being processed.', flag=PRINT.DEBUG)
            self.measureInterval(reset=False) # do not reset but keep track of unresponsiveness
            return
        self.pluginManager.plotting = True
        try:
            return func(self, *args, **kwargs)
        finally:
            self.pluginManager.plotting = False
    return wrapper

def openInDefaultApplication(file):
    """Opens file in system default application for file type.

    :param file: Path to the file to open.
    :type file: str / pathlib.Path
    """
    if sys.platform == 'win32':
        subprocess.Popen(f'explorer {file}')
    else:
        subprocess.Popen(['xdg-open', file])
