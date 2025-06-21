"""Starts PyQt event loop."""
import ctypes
import os
import sys
import warnings

import matplotlib as mpl
import matplotlib.backends.backend_pdf  # pylint: disable = unused-import  # required to assure backend is included
from PyQt6.QtCore import QSharedMemory
from PyQt6.QtQuick import QQuickWindow, QSGRendererInterface

from esibd.core import PROGRAM_NAME, Application, EsibdExplorer, MouseInterceptor, SplashScreen, colors

mpl.use('Qt5Agg')
mpl.rcParams['savefig.format'] = 'pdf'  # make pdf default export format
mpl.rcParams['savefig.bbox'] = 'tight'  # trim white space by default (also when saving from toolBar)
mpl.rcParams['savefig.facecolor'] = colors.fg_light
mpl.rcParams['figure.max_open_warning'] = 50  # not uncommon to exceed the default of 20 when using multiple plugins
warnings.filterwarnings('ignore', message='constrained_layout')  # suppress UserWarning: constrained_layout not applied because axes sizes collapsed to zero.
# open bug with clearing shared log axis https://github.com/matplotlib/matplotlib/issues/9970 requires to ignore log-scaled messages
warnings.filterwarnings('ignore', message='Attempted to set non-positive left xlim on a log-scaled axis.\nInvalid limit will be ignored.')
warnings.filterwarnings('ignore', message='Attempt to set non-positive ylim on a log-scaled axis will be ignored.')
warnings.filterwarnings('ignore', message='Data has no positive values, and therefore cannot be log-scaled.')
warnings.filterwarnings('ignore', message='loadtxt: input contained no data:')
warnings.filterwarnings('ignore', message='Covariance of the parameters could not be estimated')
warnings.filterwarnings('ignore', message='overflow encountered in scalar subtract')
warnings.filterwarnings('ignore', message='overflow encountered in scalar add')
warnings.filterwarnings('ignore', message='No artists with labels found to put in legend.')


def main() -> bool:
    """Configure graphics, check for other running instances, and execute the app."""
    app = Application(sys.argv)
    app.setStyle('Fusion')
    os.environ['QTWEBENGINE_CHROMIUM_FLAGS'] = '--enable-logging --log-level=1'
    appStr = f'{PROGRAM_NAME}'  # same string across versions!
    if sys.platform == 'win32':
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(appStr)
    QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.OpenGL)  # https://forum.qt.io/topic/130881/potential-qquickwidget-broken-on-qt6-2/4
    app.sharedAppStr = QSharedMemory(appStr)
    if not app.sharedAppStr.create(512, QSharedMemory.AccessMode.ReadWrite):
        print(f"Can't start more than one instance of {appStr}.")  # noqa: T201
        sys.exit(0)

    app.splashScreen = SplashScreen(app=app)
    app.mainWindow = EsibdExplorer(app=app)
    app.mainWindow.show()
    app.mouseInterceptor = MouseInterceptor(app.mainWindow)
    app.installEventFilter(app.mouseInterceptor)

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
