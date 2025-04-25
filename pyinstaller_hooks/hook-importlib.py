# add all modules that might be used by plugins but are not imported at packaging time  # noqa: N999
# when adding a module here, it should probably also be added to autodoc_mock_imports in docs\conf.py
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
