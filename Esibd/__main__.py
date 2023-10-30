"""ESIBD Explorer: A comprehensive data acquisition and analysis tool for Electrospray Ion-Beam Deposition experiments and beyond."""

import sys
import os
import ctypes
import matplotlib as mpl
from PyQt6.QtQuick import QQuickWindow, QSGRendererInterface
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import  QSharedMemory
# from PyQt6.QtWebEngineWidgets import QWebEngineView
import Esibd.EsibdCore as EsibdCore

mpl.use('Qt5Agg')
mpl.rcParams['savefig.format']  = 'pdf' # make pdf default export format
mpl.rcParams['savefig.bbox']  = 'tight' # trim white space by default (also when saving from toolBar)

def main():
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
    app.mainWindow = EsibdCore.EsibdExplorer()
    app.mainWindow.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
