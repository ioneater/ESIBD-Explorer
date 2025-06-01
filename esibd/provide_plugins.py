"""Defines which plugins are loaded and in what order.

Only use to replace plugins specified below with extended versions.
Define all other plugins in devices, scans, examples, displays, or a user plugin folder.
"""

from esibd.extended import ESIBDSettings
from esibd.plugins import PID, UCM, Browser, Console, DeviceManager, Explorer, Notes, Plugin, Text, Tree


def providePlugins() -> 'list[type[Plugin]]':
    """Return list of :class:`plugins<esibd.plugins.Plugin>`.

    Plugins are available for activation in the :class:`~esibd.core.PluginManager` user interface accessible from :ref:`sec:settings`.

    :return: Plugin list
    :rtype: [:class:`~esibd.plugins.Plugin`]
    """
    # with current docking system first four plugins have to be of type DeviceManager, control, console, display, in this order for correct UI layout!
    # make sure optional plugins are at the end of this list
    return [DeviceManager, ESIBDSettings, Console, Browser, Explorer, Text, Tree, Notes, UCM, PID]
