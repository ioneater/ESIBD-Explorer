# add all modules that might be used by plugins but are not imported at packaging time  # noqa: N999
# when adding a module here, it should probably also be added to autodoc_mock_imports in docs\conf.py

from PyInstaller.utils.hooks import collect_submodules

hiddenimports = [
'socket',
'serial',
'mpl_toolkits.axes_grid1',
'winsound',
'pyqtgraph.opengl',
'Bio.PDB',
'openpyxl',
'python-pptx',
'lakeshore',
'pyvisa',
'nidaqmx',
'picosdk',
'picosdk.usbPT104',
'picosdk.functions',
'pfeiffer_vacuum_protocol']
hiddenimports += collect_submodules('scipy')

# The whole standard library: a plugin may import any of it at run time, and PyInstaller collects only
# what Explorer itself imports. A plugin that reads a TOML file with tomllib, which Explorer never
# imports, failed with ModuleNotFoundError in the executable.
import importlib.util  # noqa: E402
import sys  # noqa: E402

_NOT_FOR_PLUGINS = {'test', 'idlelib', 'turtledemo', 'lib2to3', 'ensurepip', 'venv', 'pydoc_data', 'antigravity', 'this'}
for _name in sorted(sys.stdlib_module_names):
    if _name.startswith('_') or _name in _NOT_FOR_PLUGINS or importlib.util.find_spec(_name) is None:
        continue
    hiddenimports += collect_submodules(_name, filter=lambda name: '.test' not in name and '.tests' not in name)
