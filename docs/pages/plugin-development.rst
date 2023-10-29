.. _`sec:plugin_system`:

Plugin development
==================

If you are a user of *ESIBD Explorer* you can skip this section. Please
read on if you want to extend the functionality by adding plugins or
adapt the software for a different type of experiment.

The main code does not need to be modified to add support for additional
devices and other features. Instead, you can add :class:`~Esibd.EsibdPlugins.Plugin` that will be
automatically integrated into the user interface. In fact, everything
the user sees in *ESIBD Explorer* is a :class:`~Esibd.EsibdPlugins.Plugin`. This section will discuss
the underlying framework that enables communication between different
devices, scan modes, and other plugins.

To add plugins, all you need to do is prepare a plugin file inside a
sub folder of the user defined :ref:`plugin_path`. A plugin file is a python
script that defines a :meth:`~Esibd.EsibdPlugins.providePlugins` function, which returns one or
multiple :class:`plugins<Esibd.EsibdPlugins.Plugin>`. 
:class:`Plugins<Esibd.EsibdPlugins.Plugin>` can be enabled in the plugin dialog
found in :ref:`sec:Settings` after restarting the software. It is
recommended that your custom plugin classes inherit directly from 
:class:`~Esibd.EsibdPlugins.Plugin`, :class:`~Esibd.EsibdPlugins.Device`, :class:`~Esibd.EsibdPlugins.Scan`, or from one of the other built-in plugins. All built-in :class:`plugins<Esibd.EsibdPlugins.Plugin>` can be imported from :mod:`~Esibd.EsibdPlugins` and the corresponding modules in the *plugins* folder. Many other helpful classes and methods can be imported from :mod:`~Esibd.EsibdCore`.

If you want to do something completely different to the already
implemented functionality, get in touch and see if we can implement a
base class that can be reused for similar projects in the future and keeps your custom plugin code minimal. 

Plugin
------

.. automodule:: Esibd.EsibdPlugins.Plugin
   :noindex:

PluginManager
-------------

.. automodule:: Esibd.EsibdCore.PluginManager
   :noindex:
   
Devices
-------

.. automodule:: Esibd.EsibdPlugins.Device
   :noindex:

Channels
--------

.. automodule:: Esibd.EsibdCore.Channel
   :noindex:

Scan
----

.. automodule:: Esibd.EsibdPlugins.Scan
   :noindex:

DeviceController
----------------

.. automodule:: Esibd.EsibdCore.DeviceController
   :noindex:



        
   