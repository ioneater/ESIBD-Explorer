:tocdepth: 1

Changelog
---------

Latest
======

Added
~~~~~

- Added icon legend in about dialogs.
- Added Calculator plugin as an example of embedding external GUI applications as plugins.
- Running scans will be indicated by icons in the DeviceManager.
- Added lagging indicator in advanced mode of device settings.
- Added option to filter warning and error messages in the Console.

Fixed
~~~~~

- Fixed assignment of values to virtual channels in test mode for several internal plugins.
- Improved colors of displays when copied to clipboard or saved as pdf.
- Renaming of settings is handled like any other setting change.
- Restoring backgrounds after moving channels.

Changed
~~~~~~~

- Improved the definition of the channel properties active and real in the documentation.
- Treating file types not case sensitive.
- New icons for msScan and MS.
- Simplified TIC plugin implementation by inheriting from OMNICONTROL.
- Made layout more stable by preventing moving of Console, Settings, and Browser.
- Some development specific settings are hidden by default and only visible in the advanced mode of the Settings plugin.
- Tolerating more device interval deviation and skipping plotting and data recording if needed to make application more responsive and stable when using close to maximum resources.
- Channel backgrounds are only displayed and used for channels that are enabled, active, and real.
- Scans will warn if scan limits exceed limits of scan channels.

Version 0.7.2 2025-03-02
========================

Added
~~~~~

- Added update information on starting screen.
- Added option to show an overview of all icons (enter Tree.iconOverview() in Console).
- Added Error count setting for devices to stop communication after multiple consecutive errors.
- Added option to record videos of plugins.
- Added option to highlight mouse clicks.
- Added offline installation instructions.
- Added option to run python files from explorer context menu.
- Added options to load all device values from file context menu instead of one device at a time.
- Added option to load all device channels and values from advanced device manager instead of one device at a time.
- Added simple video example to the documentation.

Fixed
~~~~~
- Fixed scaling when copy image to clipboard in live displays.
- Updating linked channels when renaming source channels.
- Dialogs stay on top of all windows.
- Fixed help dialog for displays.

Changed
~~~~~~~
- Using plugin names more consistently in tooltips.
- Using explicit tooltips for linked channels in UCM, PID, and scans.
- Reintroduced start recording and subtractBackground actions for live displays (linked to corresponding action in parent Plugin).

Removed
~~~~~~~
- Removed display time control for device manager (use UCM to see multiple channels with consistent time).

Version 0.7.1 2025-02-08
========================

Added
~~~~~

- Added new icons for UCM, Line, and DeviceManager.
- Added change log to readthedocs.
- Added Linux installation instructions.
- Generalized opening files and storing settings to work on Linux.
- Limiting valid characters for channel names.
- Adding messages emitted during initialization to Console.
- Added itemFile and itemFileDark to simplify specification of icons and show icons in PluginManager
- Added program info to plugins.ini

Changed
~~~~~~~

- Removed checkbox for non optional plugins in plugin dialog.
- Prevent device manager from moving or floating.
- Disable navigation icons in explorer while loading directory to avoid inconsistent behavior.
- Plugin dialog can be accessed while devices are communicating. Communication will only be stopped when reloading plugins.
- Improved formatting of values in .ini files and change logs.
- Prevent loading of channels while recording.
- PICO only loads SDK if user has explicitly enabled this plugin.
- Using dark mode background instead of black for scans.
- Devices only store data regularly if they are actively recording new data.
- Waiting for scans to finish when closing.
- UCM, PID, and Scan channels show background corrected values if applicable.
- Depo scan is using color of selected current channel.

Fixed
~~~~~

- Reconnecting source channels after loading device configuration.
- Fixed error caused by missing console history file.
- Fixed copyClipboard in light theme
- Fixed repeated plotting when loading scans
- Fixed scan channel initialization for Depo Scan.
- Using display parameter for Omni scan.
- Removed display parameter for other scans.
- Implemented proper file handling for UCM and PID.
- Fixed incomplete status messages
- RSPD3303C only sets values for enabled channels.

Version 0.7.0 2025-01-19
========================

This version brings multiple improvements to the user interface and messages. The main new features include the Universal Channel Manager (UCM), PID Plugin, and a channel interface for scans. The data and config file formats remain unchanged. The plugin file format is significantly simplified but requires adjustments (see below) to use old plugins with the current version!

Added
~~~~~

- Universal Channel Manager (UCM) plugin: This plugin allows to reference arbitrary channels from other devices to create a central list of the most important information. All referenced channels can be controlled from here. The corresponding display allows to see recorded data from multiple devices in one central location. For most users this should result in improved performance and less complexity as the individual device tabs and corresponding displays will rarely be needed once the channels in the UCM are configured.
- PID Plugin: Allows to establish a PID control loop between two arbitrary channels.
- Added option to collapse channels of same color to focus on the most relevant channels.
- Channels now allow to change Line Style and Group for plotting.
- Channels now allow to change Scaling to highlight important channels (and to see them from the other side of the lab!).
- Added channel interface for scans.
- Depo scan can now record data from arbitrary additional channels.
- Added option to inspect the object currently in the Console input.
- Option to use icons instead of labels in tab bars (active by default).
- Live Displays allow to sort plot curves by device, unit, or group (new channel parameter), and arrange them horizontally, vertically, or stacked.
- Added plugins for KEITHLEY 6487, GAA MIPS, NI9263, Pfeiffer Omnicontrol, RSPD3303C, and pico PT-104.
- Added option to generate plot files for displays including MS, Line, PDB, Holo.
- Plugin Manager now shows the supported version of plugins and highlights if they are compatible with the current program or not.

Changed
~~~~~~~

- Plugin format: Much of the functionally has been moved to the base class allowing developers to use standard functionality by using a flag (useMonitors, useDisplays, useBackgrounds, useOnOffLogic) instead of implementing it in the specific plugin file. Some functions have been renamed to be more descriptive and consistent. Most important examples are: stop -> closeCommunication, init -> initializeCommunication, apply -> applyValues. Make sure to compare to build in examples and test your plugins when updating your custom plugins for the current version. Documentation in CustomDevice has been improved to demonstrate and explain the current plugin format.
- Logging is now enabled by default. More informative status, warning, and error messages. A lot more messages in debug mode.
- Using icons for messages, warnings, and errors in status bar, log file, and Console
- Old logs are regularly removed from the log file
- Reorganized internal device plugins in dedicated folders
- Temporary parameters like monitors or other device states are now saved but not restored.
- Parameters that are undefined before communication to the corresponding device is established are set to NaN to emphasize that there is no up to date value available.

Deprecated
~~~~~~~~~~

- Splitting Pressure plugin into dedicated TIC and MAXIGAUGE plugins. If necessary channels can be combined using UCM. Pressure plugin is now deprecated and will be removed in the future.

Fixed
~~~~~

- Replaced deprecated :code:`numpy.bool8` with :code:`numpy.bool_`
- Various minor bug fixes

Performance
~~~~~~~~~~~

- Various performance improvements
- Improved speed and stability of tests. Time is logged during testing if in debug mode.

Version 0.6.18 2024-06-10
=========================

Added
~~~~~

- Tree.inspect now shows values if applicable
- Console restores history of used commands after restart
- Introduced setDisplayDecimals to customize display of floats including scientific notation
- Added variable aspect ratio option for beam scan (varAxesAspect in autogenerated plot file)
- Added new scan mode "Spectra" for a series of 1D spectra based on Beam scan
- Added new UI tool MultiStateAction
- Added dedicated channelPlot to display channel data instead of using Line plugin
- Added msSpectra mode for simple mass spectra
- Added PluginManager.testing flag to avoid interaction of parallel testing thread with UI dialog boxes leading to rare crash during testing

Changed
~~~~~~~

- Communication has to be stopped before channels can be moved (increase stability)
- Default ini files are scanned for changes when closing and only overwritten if necessary
- Using last 10 s instead of last 10 data points to define background signal
- Scans now respect the subtractBackground states defined by the devices of the relevant channels
- Virtual channels do not need to be active to be included in scans

Fixed
~~~~~

- Update to pyqtgraph==0.13.7 after replacing deprecated api

Performance
~~~~~~~~~~~

- Plotting performance improved by reusing figures (figure recreation still needed if theme is changing)

Version 0.6.17 2024-03-18
=========================

Added
~~~~~

- Added popup to show errors while importing plugins (before the Console plugin is ready to display those errors.)
- Added Smooth parameter to all channels to reduce noise using running average.

Changed
~~~~~~~

- Live displays are visible by default
- Test mode active by default
- Stop all communication and recording from DeviceManager, now requires explicit confirmation
- Added warnings for output channels that are not enabled, or their device is not initialized or not recording
- Pressure plugin: init TIC and TPG decoupled so you can use it with only one of them or both.

Removed
~~~~~~~

- Removed explicit save of settings on program termination (settings are saved in real time)

Version 0.6.16 2023-12-17
=========================

First stable release on pipy

Added
~~~~~

- the deposition plugin now shows a checklist for validation before it starts recording
- added option to use dark or light theme when copying graphs to clipboard
- added getting started section in docs
- added PluginManager.showThreads() function for debugging
- added minimal support to restore plugin dimensions after restart
- added exponential temperature change for Temperature plugin in test mode
- added option to reset local settings using python -m esibd.reset

Changed
~~~~~~~

- channels can now only be enabled and disabled in advanced mode
- live displays are now visible by default after initial installation

Fixed
~~~~~

- acquisition is no longer stopped when loading scan or device settings
- added input validation of session path
- fixed issue with autoscaling in static displays

Performance
~~~~~~~~~~~

- increased speed of TIC pressure communication by using correct EOL character

Version 0.6.14 2023-11-07
=========================

First release public on PyPi