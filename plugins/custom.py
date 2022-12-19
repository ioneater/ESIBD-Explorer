# pylint: disable=[missing-module-docstring] # only single class in module

from PyQt6.QtWidgets import QGridLayout, QPushButton, QWidget, QDialog, QLabel,QSizePolicy


def initialize(esibdWindow):
    CustomControl(tabWidget=esibdWindow.mainTabWidget)

class CustomControl(QWidget):
    """A custom user control. Add your independent code here to add it to the Configuration and Management tabs"""

    def __init__(self,tabWidget):
        super().__init__()
        self.initUi()
        tabWidget.addTab(self,'Custom')

    def initUi(self):
        """Initialize your custom user interface"""
        lay = QGridLayout(self)
        self.btn = QPushButton()
        lay.addWidget(self.btn)
        self.btn.setText('Click Me!')
        self.btn.setSizePolicy(QSizePolicy.Policy.Fixed,QSizePolicy.Policy.Fixed)
        self.btn.clicked.connect(self.onClick)

    def onClick(self):
        """Execute your custom code"""
        dlg = QDialog(self)
        dlg.setWindowTitle('Custom Dialog')
        lbl = QLabel('This could run your custom code.')
        lay = QGridLayout()
        lay.addWidget(lbl)
        dlg.setLayout(lay)
        dlg.exec()
