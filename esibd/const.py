"""Defines constants used throughout the package."""

import importlib.util
import subprocess  # noqa: S404
import sys
import traceback
from collections.abc import Callable
from datetime import datetime
from enum import Enum
from functools import wraps
from typing import TYPE_CHECKING, TypeVar, Union, cast

import h5py
import numpy as np
from PyQt6.QtCore import QSettings
from PyQt6.QtGui import QColor
from scipy import signal

from esibd.config import *  # pylint: disable = wildcard-import, unused-wildcard-import  # noqa: F403

if TYPE_CHECKING:
    from types import ModuleType

    from esibd.plugins import Plugin, SettingsManager

ParameterType = Union[str, Path, int, float, QColor, bool]  # str | Path | int | float | QColor | bool not compatible with sphinx # noqa: UP007
T = TypeVar('T')

PROGRAM = 'Program'
VERSION = 'Version'
NAME = 'Name'
PLUGIN = 'Plugin'
INFO = 'Info'
TIMESTAMP = 'Time'
GENERAL = 'General'
DATAPATH = 'Data path'
CONFIGPATH = 'Config path'
PLUGINPATH = 'Plugin path'
DEBUG = 'Debug mode'
LOGLEVEL = 'Log level'
DARKMODE = 'Dark mode'
CLIPBOARDTHEME = 'Clipboard theme'
DPI = 'DPI'
TESTMODE = 'Test mode'
ICONMODE = 'Icon mode'
GEOMETRY = 'GEOMETRY'
SETTINGSWIDTH = 'SettingsWidth'
SETTINGSHEIGHT = 'SettingsHeight'
CONSOLEHEIGHT = 'ConsoleHeight'
INPUTCHANNELS = 'Input Channels'
OUTPUTCHANNELS = 'Output Channels'
UNIT = 'Unit'
SELECTFILE = 'Select File'
SELECTPATH = 'Select Path'

# * default paths should not be in software folder as this might not have write access after installation
defaultDataPath = Path.home() / PROGRAM_NAME / 'data/'
defaultConfigPath = Path.home() / PROGRAM_NAME / 'conf/'
defaultPluginPath = Path.home() / PROGRAM_NAME / 'plugins/'

# file types
FILE_INI = '.ini'
FILE_H5 = '.h5'
FILE_PDF = '.pdf'
FILE_PY = '.py'

# other
UTF8 = 'utf-8'

qSet = QSettings(COMPANY_NAME, PROGRAM_NAME)


class Colors:
    """Provides dark mode dependent default colors."""

    fg_dark = '#e4e7eb'
    fg_light = '#000000'

    @property
    def fg(self) -> str:
        """Foreground color."""
        return self.fg_dark if getDarkMode() else self.fg_light

    bg_dark = '#202124'
    bg_light = '#ffffff'

    @property
    def bg(self) -> str:
        """Background color."""
        return self.bg_dark if getDarkMode() else self.bg_light

    @property
    def bgAlt1(self) -> str:
        """First alternative background color."""
        return QColor(self.bg).lighter(160).name() if getDarkMode() else QColor(self.bg).darker(105).name()

    @property
    def bgAlt2(self) -> str:
        """Second alternative background color."""
        return QColor(self.bg).lighter(200).name() if getDarkMode() else QColor(self.bg).darker(110).name()

    @property
    def highlight(self) -> str:
        """Highlight color."""
        return '#8ab4f7'


colors = Colors()


def rgb_to_hex(rgba: tuple[float, float, float, float]) -> str:
    """Convert colors from rgb to hex.

    :param rgba: RGBA color tuple.
    :type rgba: tuple
    :return: Hex color string.
    :rtype: str
    """
    return f'#{int(rgba[0] * 255):02x}{int(rgba[1] * 255):02x}{int(rgba[2] * 255):02x}'


class INOUT(Enum):
    """Specify if a function affects only input, only output, or all Channels."""

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
    """Specify type of message in Plugin.print."""

    EXPLORER = 0
    """Key messages by Explorer"""
    MESSAGE = 1
    """A standard message."""
    WARNING = 2
    """Tag message as warning."""
    ERROR = 3
    """Tag message as error."""
    CONSOLE = 4
    """Tag message as Console input or output."""
    DEBUG = 5
    """Only show if debug flag is enabled."""
    VERBOSE = 6
    """Additional details that would be distracting if not needed for specific test."""
    TRACE = 7
    """All messages, including detailed trace of instrument communication."""


class PLUGINTYPE(Enum):
    """Each plugin must be of one of the following types to define its location and behavior."""

    CONSOLE = 'Console'
    """The internal Console."""
    CONTROL = 'Generic Control'
    """Any control plugin, will be placed next to Settings, Explorer, Devices, and Scans."""
    INPUTDEVICE = 'Input Device'
    """Device plugin sending user input to hardware."""
    OUTPUTDEVICE = 'Output Device'
    """Device plugin sending hardware output to user."""
    CHANNELMANAGER = 'Channel Manager'
    """A plugin that manages channels which are neither inputs or outputs."""
    DISPLAY = 'Display'
    """Any display plugin, will be places next to scan displays and static displays."""
    LIVEDISPLAY = 'LiveDisplay'
    """Live display associated with a device."""
    SCAN = 'Scan'
    """Scan plugin, will be placed with other controls."""
    DEVICEMGR = 'DeviceManager'
    """Device manager, will be placed below live displays."""
    INTERNAL = 'Internal'
    """A plugin without user interface."""


class PARAMETERTYPE(Enum):
    """Specifies what type of widget should be used to represent the Parameter in the user interface."""

    LABEL = 'LABEL'
    """A label that displays information."""
    PATH = 'PATH'
    """A path to a file or directory."""
    COMBO = 'COMBO'
    """A combobox providing text options."""
    INTCOMBO = 'INTCOMBO'
    """A combobox providing integer options."""
    FLOATCOMBO = 'FLOATCOMBO'
    """A combobox providing floating point options."""
    TEXT = 'TEXT'
    """An editable text field."""
    COLOR = 'COLOR'
    """A ColorButton that allows to select a color."""
    BOOL = 'BOOL'
    """A boolean, represented by a checkbox."""
    INT = 'INT'
    """An integer spinbox."""
    FLOAT = 'FLOAT'
    """A floating point spinbox."""
    EXP = 'EXP'
    """A spinbox with scientific format."""


def pluginSupported(pluginVersion: str) -> bool:
    """Test if given version is supported by comparing to current program version.

    :param pluginVersion: Version that the plugin supports.
    :type pluginVersion: str
    :return: True if the plugin is supported.
    :rtype: bool
    """
    return version.parse(pluginVersion).major == PROGRAM_VERSION.major and version.parse(pluginVersion).minor == PROGRAM_VERSION.minor


def makeSettingWrapper(name: str, settingsMgr: 'SettingsManager', docstring: str = '') -> property:
    """Neutral Setting wrapper for convenient access to the value of a Setting.

    If you need to handle events on value change, link these directly to the events of the corresponding control.

    :param name: The Setting name.
    :type name: str
    :param settingsMgr: The SettingsManager of the Setting.
    :type settingsMgr: esibd.plugins.SettingsManager
    :param docstring: The docstring used for the attribute, defaults to None
    :type docstring: str, optional
    """
    def getter(self) -> ParameterType:  # pylint: disable=[unused-argument]  # self will be passed on when used in class  # noqa: ANN001, ARG001
        return settingsMgr.settings[name].value

    def setter(self, value: ParameterType) -> None:  # pylint: disable=[unused-argument]  # self will be passed on when used in class  # noqa: ANN001, ARG001
        settingsMgr.settings[name].value = value
    return property(getter, setter, doc=docstring)


def makeWrapper(name: str, docstring: str = '') -> property:
    """Neutral property wrapper for convenient access to the value of a Parameter inside a Channel.

    If you need to handle events on value change, link these directly to the events of the corresponding control in the finalizeInit method.

    :param name: The Parameter name.
    :type name: str
    :param docstring: The docstring used for the attribute, defaults to None
    :type docstring: str, optional
    """
    def getter(self) -> ParameterType:  # noqa: ANN001
        return self.getParameterByName(name).value

    def setter(self, value: ParameterType) -> None:  # noqa: ANN001
        self.getParameterByName(name).value = value
    return property(getter, setter, doc=docstring)


def dynamicImport(module: str, path: Path | str) -> 'ModuleType | None':
    """Import a module from the given path at runtime.

    :param module: module name
    :type module: str
    :param path: module path
    :type path: Path | str
    :return: Module
    :rtype: ModuleType
    """
    spec = importlib.util.spec_from_file_location(module, path)
    if spec and spec.loader:
        Module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(Module)
        return Module
    return None


def getValidConfigPath() -> Path:
    """Get validated configuration path.

    :return: Validated path and indication if path has changed during validation.
    :rtype: pathlib.Path, bool
    """
    path, changed = validatePath(qSet.value(f'{GENERAL}/{CONFIGPATH}', defaultConfigPath), defaultConfigPath)
    if changed:
        qSet.setValue(f'{GENERAL}/{CONFIGPATH}', path)
    return path


def getValidDataPath() -> Path:
    """Get validated data path.

    :return: Validated path and indication if path has changed during validation.
    :rtype: pathlib.Path, bool
    """
    path, changed = validatePath(qSet.value(f'{GENERAL}/{DATAPATH}', defaultDataPath), defaultDataPath)
    if changed:
        qSet.setValue(f'{GENERAL}/{DATAPATH}', path)
    return path


def getValidPluginPath() -> Path:
    """Get validated plugin path.

    :return: Validated path and indication if path has changed during validation.
    :rtype: pathlib.Path, bool
    """
    path, changed = validatePath(qSet.value(f'{GENERAL}/{PLUGINPATH}', defaultPluginPath), defaultPluginPath)
    if changed:
        qSet.setValue(f'{GENERAL}/{PLUGINPATH}', path)
    return path


def getDebugMode() -> bool:
    """Get the debug mode from :ref:`sec:settings`.

    :return: Debug mode
    :rtype: bool
    """
    return qSet.value(f'{GENERAL}/{DEBUG}', defaultValue=True, type=bool)


def getLogLevel(asString: bool = False) -> int | str:
    """Get the log level from :ref:`sec:settings`.

    :param asString: Indicate if the log level should be returned as a string.
    :type asString: str
    :return: Log level
    :rtype: int | str
    """
    if asString:
        return qSet.value(f'{GENERAL}/{LOGLEVEL}', defaultValue='Basic')
    match qSet.value(f'{GENERAL}/{LOGLEVEL}', defaultValue='Basic'):
        case 'Basic':
            return 0
        case 'Debug':
            return 1
        case 'Verbose':
            return 2
    return 3  # Trace


def getDarkMode() -> bool:
    """Get the dark mode from :ref:`sec:settings`.

    :return: Dark mode
    :rtype: bool
    """
    return qSet.value(f'{GENERAL}/{DARKMODE}', defaultValue=True, type=bool)


def setDarkMode(darkMode: bool) -> None:
    """Set the dark mode from :ref:`sec:settings`.

    :param darkMode: True if dark mode active.
    :type darkMode: bool
    """
    qSet.setValue(f'{GENERAL}/{DARKMODE}', darkMode)


def getClipboardTheme() -> bool:
    """Get the dark clipboard mode from :ref:`sec:settings`.

    :return: Dark clipboard mode
    :rtype: bool
    """
    return qSet.value(f'{GENERAL}/{CLIPBOARDTHEME}', defaultValue=True, type=bool)


def getDPI() -> int:
    """Get the DPI from :ref:`sec:settings`.

    :return: DPI
    :rtype: int
    """
    return int(qSet.value(f'{GENERAL}/{DPI}', 100))  # need explicit conversion as stored as string


def getIconMode() -> str:
    """Get the icon mode from :ref:`sec:settings`.

    :return: Icon mode
    :rtype: str
    """
    return qSet.value(f'{GENERAL}/{ICONMODE}', 'Icons')


def getTestMode() -> bool:
    """Get the test mode from :ref:`sec:settings`.

    :return: Test mode
    :rtype: bool
    """
    return qSet.value(f'{GENERAL}/{TESTMODE}', defaultValue=False, type=bool)


def infoDict(name: str) -> dict[str, str]:
    """Return a dictionary with general information, usually used to add this information to exported files.

    :param name: Usually the name of the plugin requesting the infoDict.
    :type name: str
    :return: infoDict
    :rtype: dict
    """
    return {PROGRAM: PROGRAM_NAME, VERSION: str(PROGRAM_VERSION), PLUGIN: name, TIMESTAMP: datetime.now().strftime('%Y-%m-%d %H:%M')}


def validatePath(path: 'Path | None', default: Path) -> 'tuple[Path, bool]':
    """Return a valid path. If the path does not exist, falling back to default.

    If default does not exist it will be created.

    :param path: Valid path
    :type path: pathlib.Path
    :param default: Default path that is returned if path is not valid.
    :type default: pathlib.Path
    :return: Validated path and indication if path has changed during validation.
    :rtype: pathlib.Path, bool
    """
    if not path or not path.exists():
        default = Path(default)
        if path == default:
            print(f'Creating {default.as_posix()}.')  # noqa: T201
        else:
            print(f'Could not find path {path.as_posix() if path else "None"}. Defaulting to {default.as_posix()}.')  # noqa: T201
        default.mkdir(parents=True, exist_ok=True)
        return default, True
    return path, False


def smooth(array: np.ndarray, smooth: int) -> np.ndarray:
    """Smooth a 1D array while keeping edges meaningful.

    This method is robust if array contains np.nan.

    :param array: Array to be smoothed.
    :type array: np.ndarray
    :param smooth: With of box used for smoothing.
    :type smooth: int
    :return: convolvedArray
    :rtype: np.ndarray
    """
    if len(array) < smooth:
        return array
    smooth = int(np.ceil(smooth / 2.) * 2)  # make even
    padding = int(smooth / 2)
    win = signal.windows.boxcar(smooth)
    paddedArray = np.concatenate((array[:padding][::-1], array, array[-padding:][::-1]))  # pad ends
    convolvedArray = signal.convolve(paddedArray, win, mode='same') / sum(win)
    return convolvedArray[padding:-padding]


def shorten_text(text: str, max_length: int = 100) -> str:
    """Shorten text e.g. for concise and consistent log file format.

    :param text: Original text.
    :type text: str
    :param max_length: Length after shortening. Defaults to 100
    :type max_length: int, optional
    :return: shortened text
    :rtype: str
    """
    keep_chars = (max_length - 1) // 2
    text = text.replace('\n', '')
    return text if len(text) < max_length else f'{text[:keep_chars]}…{text[-keep_chars:]}'


def synchronized(timeout: int = 5) -> Callable:
    """Decorate to add thread-safety using a lock from the instance.

    NOTE: Only works with keyword arguments. Positional arguments apart form self will not be passed on.

    Use with @synchronized() or @synchronized(timeout=5).

    :param timeout: Will wait this long for lock to become available. Defaults to 5
    :type timeout: int, optional
    :return: decorator
    :rtype: decorator
    """
    # avoid calling QApplication.processEvents() inside func as it may cause deadlocks
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(self: 'Plugin', **kwargs) -> 'Callable | None':
            timeoutMessage = f'Cannot acquire lock for {func.__name__}.'
            if cast('int', getLogLevel()) > 0:  # DEBUG, VERBOSE, TRACE
                timeoutMessage += f'\nStack: {"".join(traceback.format_stack()[:-1])}'
            with self.lock.acquire_timeout(timeout=timeout, timeoutMessage=timeoutMessage) as lock_acquired:
                if lock_acquired:
                    self.print(f'Acquired lock for {func.__name__}.', flag=PRINT.VERBOSE)
                    return func(self, **kwargs)
                return None
        return wrapper
    return decorator


def plotting(func: Callable) -> Callable:
    """Decorate to check for and sets the plotting flag to make sure func is not executed before previous call is processed.

    Only use within a class that contains the plotting flag.
    This is intended for Scans, but might be used elsewhere.

    :param func: function to add the decorator to
    :type func: Callable
    :return: decorated function
    :rtype: Callable
    """
    @wraps(func)
    def wrapper(self, *args, **kwargs) -> 'Callable | None':  # noqa: ANN001
        if self.plotting:
            self.print('Skipping plotting as previous request is still being processed.', flag=PRINT.VERBOSE)
            if hasattr(self, 'measureInterval'):
                self.measureInterval(reset=False)  # do not reset but keep track of unresponsiveness
            return None
        self.plotting = True
        try:
            return func(self, *args, **kwargs)
        finally:
            self.plotting = False
    return wrapper


def openInDefaultApplication(file: str | Path) -> None:
    """Open file in system default application for file type.

    :param file: Path to the file to open.
    :type file: str / pathlib.Path
    """
    if sys.platform == 'win32':
        subprocess.Popen(f'explorer {file}')  # noqa: S603
    else:
        subprocess.Popen(['xdg-open', file])  # noqa: S603, S607


def datasetToStrList(dataset: h5py.Dataset) -> list[str]:
    """Convert a h5py string dataset into a list of str.

    :param dataset: The dataset.
    :type dataset: h5py.Dataset
    :return: The list.
    :rtype: list[str]
    """
    return [str(k) for k in dataset.asstr()]
