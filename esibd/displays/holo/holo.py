"""Functions in this file will generally require direct access to UI elements as well as data structures.
Note this will be imported in ES_IBD_Explorer so that it is equivalent to defining the methods there directly.
This allows to keep the bare UI initialization separated from the more meaningful methods."""

import numpy as np
import pyqtgraph as pg
import pyqtgraph.opengl as gl
from pathlib import Path
from PyQt6.QtWidgets import QSlider, QHBoxLayout
from PyQt6.QtCore import Qt, QTimer
from esibd.core import PluginManager
from esibd.plugins import Plugin


def providePlugins() -> None:
    """Indicates that this module provides plugins. Returns list of provided plugins."""
    return [HOLO]


class HOLO(Plugin):
    """The Holo plugin was designed to display 3D NumPy arrays such as
    holograms from low energy electron holography (LEEH).\ :cite:`longchamp_imaging_2017, ochner_low-energy_2021, ochner_electrospray_2023`
    Interactive 3D surface plots with density thresholds allow for efficient visualization of very large files."""
    documentation = """The Holo plugin was designed to display 3D NumPy arrays such as
    holograms from low energy electron holography (LEEH).
    Interactive 3D surface plots with density thresholds allow for efficient visualization of very large files."""

    name = 'Holo'
    version = '1.0'
    pluginType = PluginManager.TYPE.DISPLAY
    previewFileTypes = ['.npy']
    iconFile = 'holo.png'

    def initGUI(self) -> None:
        """Initialize GUI to display Holograms."""
        super().initGUI()
        self.glAngleView = gl.GLViewWidget()
        self.glAmplitudeView = gl.GLViewWidget()
        hor = QHBoxLayout()
        hor.addWidget(self.glAngleView)
        hor.addWidget(self.glAmplitudeView)

        self.addContentLayout(hor)

        self.angleSlider = QSlider(Qt.Orientation.Horizontal)
        self.angleSlider.valueChanged.connect(lambda: self.value_changed(plotAngle=True))
        self.amplitudeSlider = QSlider(Qt.Orientation.Horizontal)
        self.amplitudeSlider.valueChanged.connect(lambda: self.value_changed(plotAngle=False))
        self.titleBar.addWidget(self.angleSlider)
        self.titleBar.addWidget(self.amplitudeSlider)
        self.angle = None
        self.amplitude = None
        self.plotAngle = None
        self.update_timer = QTimer()
        self.update_timer.setSingleShot(True)
        self.update_timer.timeout.connect(self.drawSurface)

    def provideDock(self) -> None:
        if super().provideDock():
            self.finalizeInit()
            self.afterFinalizeInit()

    def supportsFile(self, file: Path) -> None:
        if super().supportsFile(file):
            data = np.load(file, mmap_mode='r')  # only load header with shape and datatype
            return len(data.shape) == 3 and data.dtype == np.complex128  # only support complex 3D arrays
        return False

    def loadData(self, file, _show=True) -> None:
        self.provideDock()
        data = np.load(file)
        self.angle = np.ascontiguousarray(np.angle(data))  # make c contiguous
        self.amplitude = np.ascontiguousarray(np.abs(data))  # make c contiguous
        self.glAngleView.setCameraPosition(distance=max(self.angle.shape) * 2)
        self.glAmplitudeView.setCameraPosition(distance=max(self.amplitude.shape) * 2)
        self.angleSlider.setValue(10)
        self.amplitudeSlider.setValue(10)
        self.drawSurface(True)
        self.drawSurface(False)
        self.raiseDock(_show)

    def mapSliderToData(self, slider, data):
        """Maps the position of the slider in percent to the corresponding data value.

        :param slider: Slider providing threshold for drawing.
        :type slider: QSlider
        :param data: The data to be mapped.
        :type data: np.ndarray
        :return: Mapped data.
        :rtype: np.ndarray
        """
        return data.min() + slider.value() / 100 * (data.max() - data.min())

    def value_changed(self, plotAngle=True):
        """Triggers delayed plot after slider value change.

        :param plotAngle: True for angle, False for amplitude, defaults to None
        :type plotAngle: bool, optional
        """
        self.plotAngle = plotAngle
        self.update_timer.start(200)
        # QTimer.singleShot(500, lambda: self.drawSurface(plotAngle=plotAngle))

    def drawSurface(self, plotAngle=None):
        """Draws an isosurface at a value defined by the sliders.

        :param plotAngle: True for angle, False for amplitude, defaults to None
        :type plotAngle: bool, optional
        """
        if plotAngle is not None:
            self.plotAngle=plotAngle
        if self.angle is not None:
            if self.plotAngle:
                self.glAngleView.clear()
                verts, faces = pg.isosurface(self.angle, self.mapSliderToData(self.angleSlider, self.angle))
            else:
                self.glAmplitudeView.clear()
                verts, faces = pg.isosurface(self.amplitude, self.mapSliderToData(self.amplitudeSlider, self.amplitude))

            md = gl.MeshData(vertexes=verts, faces=faces)
            faceColors = np.ones((md.faceCount(), 4), dtype=float)
            faceColors[:, 3] = 0.2
            faceColors[:, 2] = np.linspace(0, 1, faceColors.shape[0])
            md.setFaceColors(faceColors)

            m1 = gl.GLMeshItem(meshdata=md, smooth=True, shader='balloon')
            m1.setGLOptions('additive')
            m1.translate(-self.angle.shape[0] / 2, -self.angle.shape[1] / 2, -self.angle.shape[2] / 2)

            if self.plotAngle:
                self.glAngleView.addItem(m1)
            else:
                self.glAmplitudeView.addItem(m1)

    def generatePythonPlotCode(self) -> None:
        return f"""import pyqtgraph as pg
import pyqtgraph.opengl as gl
import numpy as np
import sys
from PyQt6.QtCore import Qt
from PyQt6.QtQuick import QQuickWindow, QSGRendererInterface
from PyQt6.QtWidgets import QApplication, QWidget, QGridLayout, QMainWindow, QSlider

class Foo(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setGeometry(100, 100, 800, 400)
        self.setCentralWidget(QWidget())
        self.lay = QGridLayout()
        self.centralWidget().setLayout(self.lay);
        self.angleSlider = QSlider(Qt.Orientation.Horizontal)
        self.angleSlider.sliderReleased.connect(lambda: self.value_changed(plotAngle=True))
        self.lay.addWidget(self.angleSlider, 0, 0)
        self.amplitudeSlider = QSlider(Qt.Orientation.Horizontal)
        self.amplitudeSlider.sliderReleased.connect(lambda: self.value_changed(plotAngle=False))
        self.lay.addWidget(self.amplitudeSlider, 0, 1)
        self.glAngleView = gl.GLViewWidget()
        self.lay.addWidget(self.glAngleView, 1, 0)
        self.glAmplitudeView = gl.GLViewWidget()
        self.lay.addWidget(self.glAmplitudeView, 1, 1)
        self.init()

    def init(self):
        data = np.load('{self.pluginManager.Explorer.activeFileFullPath.as_posix()}')
        self.angle = np.ascontiguousarray(np.angle(data))  # make c contiguous
        self.amplitude = np.ascontiguousarray(np.abs(data))  # make c contiguous
        self.glAngleView.setCameraPosition(distance=max(self.angle.shape)*2)
        self.glAmplitudeView.setCameraPosition(distance=max(self.amplitude.shape)*2)
        self.angleSlider.setValue(10)
        self.amplitudeSlider.setValue(10)
        self.drawSurface(plotAngle=True )
        self.drawSurface(plotAngle=False)

    def mapSliderToData(self, slider, data):
        return data.min() + slider.value()/100*(data.max() - data.min())

    def value_changed(self, plotAngle=True):
        self.drawSurface(plotAngle=plotAngle)

    def drawSurface(self, plotAngle):
        '''Draws an isosurface at a value defined by the sliders.'''
        if plotAngle:
            self.glAngleView.clear()
            verts, faces = pg.isosurface(self.angle, self.mapSliderToData(self.angleSlider, self.angle))
        else:
            self.glAmplitudeView.clear()
            verts, faces = pg.isosurface(self.amplitude, self.mapSliderToData(self.amplitudeSlider, self.amplitude))

        md = gl.MeshData(vertexes=verts, faces=faces)
        colors = np.ones((md.faceCount(), 4), dtype=float)
        colors[:, 3] = 0.2
        colors[:, 2] = np.linspace(0, 1, colors.shape[0])
        md.setFaceColors(colors)

        m1 = gl.GLMeshItem(meshdata=md, smooth=True, shader='balloon')
        m1.setGLOptions('additive')
        m1.translate(-self.angle.shape[0]/2, -self.angle.shape[1]/2, -self.angle.shape[2]/2)

        if plotAngle:
            self.glAngleView.addItem(m1)
        else:
            self.glAmplitudeView.addItem(m1)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.OpenGL)  # https://forum.qt.io/topic/130881/potential-qquickwidget-broken-on-qt6-2/4
    mainWindow = Foo()
    mainWindow.show()
    sys.exit(app.exec())
"""
