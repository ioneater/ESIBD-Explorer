"""This is the main ES-IBD_Explorer module that loads all other dependecies"""

import sys
# import os
# import ctypes
import platform
# from functools import partial
# import inspect
# from datetime import datetime
# import numpy as np
# import matplotlib as mpl
# import matplotlib.pyplot as plt
# import pyqtgraph as pg
# import pyqtgraph.console
# from PyQt5 import uic, QtWebEngineWidgets, sip # pylint: disable=[unused-import] # note QtWebEngineWidgets is required to loadUi, despite the fact that it is marked as "not accessed" by pylint
from PyQt5.QtWidgets import QApplication, QMainWindow, QTreeWidget#, QComboBox, QGridLayout, QSizePolicy, QShortcut
# from PyQt5.QtGui import QGuiApplication, QIcon, QFont,QKeySequence
# from PyQt5.QtCore import QSettings, Qt, pyqtSlot
import ES_IBD_configuration as conf
# import ES_IBD_management as management
from ES_IBD_functions import func_mixin
import ES_IBD_controls as controls
# from custom_device import CustomInputTab


class ES_IBDWindow(QMainWindow,func_mixin):
    def __init__(self):
        super().__init__()

        # item0 = self.settingsDict(conf.DPI,'150','DPI used in ES-IBD Explorer','100,150,200,300,600',conf.WIDGETCOMBO,conf.GENERAL)
        # item1 = self.settingsDict(conf.MEASUREMENTNUMBER,0,'Self incrementing measurement number. Set to 0 to start a new session.','',conf.WIDGETINT,conf.SESSION)
        # item2 = self.settingsDict(conf.SUBSTRATE,'Steel','Choose substrate','Steel,HOPG,Graphene,aCarbon',conf.WIDGETCOMBO,conf.SESSION)
        # tree = QTreeWidget()
        # test0 = controls.esibdSetting(self, tree, 'DPI', item0)
        # test1 = controls.esibdSetting(self, tree, 'DPI', item1)
        # test2 = controls.esibdSetting(self, tree, 'DPI', item2)
        # print('blaa',test0.value)
        # print('blaa',test1.value)
        # print('blaa',test2.value)

        test=controls.ESIBD_Parameter(conf.DPI,'150',conf.WIDGETCOMBO,items='100,150,200,300,600')
        for i in range(test.combo.count()):
            
            print(test.combo.itemText(i))
        print('bla',test.value)

    def settingsDict(self, name, value, tooltip, items, widgetType, category):
        return {conf.NAME : name, conf.VALUE : value, conf.DEFAULT : value, conf.TOOLTIP : tooltip, conf.ITEMS : items, conf.WIDGETTYPE : widgetType, conf.CATEGORY : category}


if __name__ == '__main__':
    app = QApplication(sys.argv)
    #app.setStyle('QtCurve') # default
    if '11' in platform.release():
        app.setStyle('Fusion') # otherwise button statis is not clearly displayed on windows 11

    mainWindow = ES_IBDWindow()

    mainWindow.show()
    sys.exit(app.exec_())
