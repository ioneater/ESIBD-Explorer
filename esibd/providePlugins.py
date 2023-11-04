"""Defines which plugins are loaded and in what order. 
Only use to replace plugins specified below with extended versions.
Define all other plugins in plugins_internal or a user plugin folder. 
"""

from esibd.plugins import DeviceManager, Console, Browser, Explorer, Notes, Text, Tree
from esibd.extended import ESIBDSettings

def providePlugins():
    """Returns list of :class:`plugins<esibd.plugins.Plugin>` that are available for activation in the :class:`~esibd.core.PluginManager` user interface accessible from :ref:`sec:settings`.

    :return: Plugin list
    :rtype: [:class:`~esibd.plugins.Plugin`]
    """
    # with current docking system first four plugins have to be of type DeviceManager, control, console, display, in this order for correct UI layout!
    return [DeviceManager, ESIBDSettings, Console, Browser, Explorer, Notes, Text, Tree]
