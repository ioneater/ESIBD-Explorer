"""ESIBD Explorer: A comprehensive data acquisition and analysis tool for Electrospray Ion-Beam Deposition experiments and beyond."""

import sys
import os
import ctypes
import matplotlib as mpl
from PyQt6.QtQuick import QQuickWindow, QSGRendererInterface
from PyQt6.QtWidgets import QApplication, QMainWindow
from PyQt6.QtGui import QIcon, QAction
from PyQt6.QtCore import pyqtSignal, QSharedMemory, QTimer
from PyQt6.QtWebEngineWidgets import QWebEngineView
import Esibd.EsibdCore as EsibdCore

mpl.use('Qt5Agg')
mpl.rcParams['savefig.format']  = 'pdf' # make pdf default export format
mpl.rcParams['savefig.bbox']  = 'tight' # trim white space by default (also when saving from toolBar)

class EsibdExplorer(QMainWindow):
    r"""Contains minimal code to start, initialize, and close the program.
    All high level logic is provided by 
    :mod:`~Esibd.EsibdCore`, 
    :mod:`~Esibd.EsibdPlugins` and additional
    :class:`plugins<Esibd.EsibdPlugins.Plugin>`.
    """

    loadPluginsSignal = pyqtSignal()

    def __init__(self):
        """Sets up basic user interface and triggers loading of plugins."""
        super().__init__()
        if EsibdCore.useWebEngine:
            dummy = QWebEngineView(parent=self) # switch to GL compatibility mode https://stackoverflow.com/questions/77031792/how-to-avoid-white-flash-when-initializing-qwebengineview
            dummy.setHtml('dummy')
            dummy.deleteLater()
        self.restoreUiState()
        self.setWindowIcon(QIcon(EsibdCore.ICON_EXPLORER))
        self.setWindowTitle(EsibdCore.PROGRAM_NAME)
        self.actionFull_Screen = QAction()
        self.actionFull_Screen.triggered.connect(self.toggleFullscreen)
        self.actionFull_Screen.setShortcut('F11')
        self.addAction(self.actionFull_Screen) # action only works when added to a widget
        self.maximized  = False
        self.loadPluginsSignal.connect(self.loadPlugins)
        QTimer.singleShot(0, self.loadPluginsSignal.emit) # let event loop start before loading plugins

    def loadPlugins(self):
        """Loads :class:`plugins<Esibd.EsibdPlugins.Plugin>` in main thread."""
        self.pluginManager = EsibdCore.PluginManager()
        self.pluginManager.loadPlugins()

    def toggleFullscreen(self):
        """Toggles full screen mode."""
        if self.isFullScreen(): # return to previous view
            self.showMaximized() if self.maximized else self.showNormal() # pylint: disable = expression-not-assigned
        else: # goFullscreen
            self.maximized = self.isMaximized() # workaround for bug https://github.com/qutebrowser/qutebrowser/issues/2778
            self.showFullScreen()

    def restoreUiState(self):
        """Restores size and location of main window."""
        try:
            self.restoreGeometry(EsibdCore.qSet.value(EsibdCore.GEOMETRY, self.saveGeometry()))
            # Note that the state on startup will not include dynamic displays which open only as needed. Thus the state cannot be restored.
            # self.mainWindow.restoreState(qSet.value(self.WINDOWSTATE, self.mainWindow.saveState()))
            # NOTE: need to restore before starting event loop to avoid Unable to set geometry warning
        except TypeError as e:
            print(f'Could not restore window state: {e}')
            self.resize(800, 400)
            self.saveUiState()

    def saveUiState(self):
        """Saves size and location of main window."""
        EsibdCore.qSet.setValue(EsibdCore.GEOMETRY, self.saveGeometry())
        # qSet.setValue(GEOMETRY, self.mainWindow.geometry())
        # qSet.setValue(self.WINDOWSTATE, self.mainWindow.saveState())

    def closeEvent(self, event):
        """Triggers :class:`~Esibd.EsibdCore.PluginManager` to close all plugins and all related communication."""
        if not self.pluginManager.loading and (not any([ld.recording for ld in self.pluginManager.DeviceManager.getActiveLiveDisplays()])
                or EsibdCore.CloseDialog(prompt='Acquisition is still running. Do you really want to close?').exec()):
            self.pluginManager.closePlugins()
            app.quit() # pylint: disable=used-before-assignment # assigned in __name__ == '__main__'
            event.accept() # let the window close
        else:
            event.ignore() # keep running

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--enable-logging --log-level=1"
    appStr = f'{EsibdCore.PROGRAM_NAME} {EsibdCore.VERSION_MAYOR}.{EsibdCore.VERSION_MINOR}'
    if sys.platform == 'win32':
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(appStr)
    QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.OpenGL) # https://forum.qt.io/topic/130881/potential-qquickwidget-broken-on-qt6-2/4
    shared = QSharedMemory(appStr)
    if not shared.create(512, QSharedMemory.AccessMode.ReadWrite):
        print(f"Can't start more than one instance of {appStr}.")
        sys.exit(0)
    app.mainWindow = EsibdExplorer()
    app.mainWindow.show()
    sys.exit(app.exec())
