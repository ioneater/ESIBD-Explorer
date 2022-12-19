"""This module contains classes that contain and manage a list of (extended) UI elements.
In addition it contains classes used to manage data acquisition.
Finally it contains classes for data export,and data import."""

import time
from datetime import datetime,timedelta
import io
import winsound
import h5py
from scipy import optimize,interpolate
import matplotlib as mpl
from mpl_toolkits.axes_grid1 import make_axes_locatable
from asteval import Interpreter
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QSize
from PyQt6.QtGui import QResizeEvent, QImage
import numpy as np
from ES_IBD_core import ESIBD_Parameter,INOUT,ESIBD_Cursor,parameterDict,dynamicNp
from GA import GA
from ES_IBD_controls import ESIBD_Scan
aeval = Interpreter()

def initialize(esibdWindow):
    esibdWindow.addGUIWidget(esibdWindow.mainTabWidget,BeamScan(esibdWindow=esibdWindow))
    esibdWindow.addGUIWidget(esibdWindow.mainTabWidget,EnergyScan(esibdWindow=esibdWindow))
    esibdWindow.addGUIWidget(esibdWindow.mainTabWidget,DepoScan(esibdWindow=esibdWindow))
    esibdWindow.addGUIWidget(esibdWindow.mainTabWidget,GAScan(esibdWindow=esibdWindow))

class BeamScan(ESIBD_Scan):
    """Measures currents as a function of deflector potentials to map beam trajectory."""

    LEFTRIGHT       = 'Left-Right'
    UPDOWN          = 'Up-Down'

    def __init__(self,**kwargs):
        self.LR_from = None # attribute will be overwritten by setting
        self.LR_to = None
        self.UD_from = None
        self.UD_to  = None
        super().__init__(name = 'Beam',**kwargs)
        self.suffixes.append('.S2D.dat')
        self.suffixes.append('.s2d.h5')
        self.addButton(0,3,'Limits',self.useLimits,'Adopts limits from display')
        self.axes.append(self.fig.add_subplot(111))
        self.axes[0].set_aspect('equal',adjustable='box')
        self.canvas.mpl_connect('motion_notify_event',self.mouseEvent)
        self.canvas.mpl_connect('button_press_event',self.mouseEvent)
        self.canvas.mpl_connect('button_release_event',self.mouseEvent)
        self.cont = None
        divider = make_axes_locatable(self.axes[0])
        self.cax = divider.append_axes("right", size="5%", pad=0.15)
        self.cbar = None
        self.mouseActive = True
        self.axes[-1].cursor = None

    S2DSETTINGS = 'S2DSETTINGS'

    def loadDataInternal(self):
        """Loads data in internal standard format for plotting."""
        if self.file.name.endswith('.S2D.dat'):  # legacy ES-IBD Control file
            self.outputChannels.append(None)
            self.outputNames.append('')
            try:
                data = np.flip(np.loadtxt(self.file).transpose())
            except ValueError as e:
                self.print(f'Warning: Error when loading from {self.file.name}: {e}')
                return
            if data.shape[0] == 0:
                self.print(f'Warning: no data found in file {self.file.name}')
                return
            self.outputData.append(data)
            self.outputUnits.append('pA')
            self.inputChannels.append(None)
            self.inputNames.append('LR Voltage')
            self.inputData.append(np.arange(0,1,1/self.outputData[0].shape[1]))
            self.inputUnits.append('V')
            self.inputChannels.append(None)
            self.inputNames.append('UD Voltage')
            self.inputData.append(np.arange(0,1,1/self.outputData[0].shape[0]))
            self.inputUnits.append('V')
        elif self.file.name.endswith('.s2d.h5'):
            with h5py.File(self.file, 'r') as f:
                is03 = f[self.VERSION].attrs['VALUE'] == '0.3' # legacy version 0.3, 0.4 if false
                lr = f[self.S2DSETTINGS]['Left-Right']
                self.inputNames.append(lr['Channel'].attrs['VALUE'])
                self.inputChannels.append(self.esibdWindow.outputWidget.getChannelbyName(self.inputNames[-1],inout = INOUT.IN))
                _from, to, step = lr['From'].attrs['VALUE'], lr['To'].attrs['VALUE'], lr['Step'].attrs['VALUE']
                self.inputData.append(np.linspace(_from,to,int(abs(_from-to)/abs(step))+1))
                self.inputUnits.append('V')
                ud = f[self.S2DSETTINGS]['Up-Down']
                self.inputNames.append(ud['Channel'].attrs['VALUE'])
                self.inputChannels.append(self.esibdWindow.outputWidget.getChannelbyName(self.inputNames[-1],inout = INOUT.IN))
                _from, to, step = ud['From'].attrs['VALUE'], ud['To'].attrs['VALUE'], ud['Step'].attrs['VALUE']
                self.inputData.append(np.linspace(_from,to,int(abs(_from-to)/abs(step))+1))
                self.inputUnits.append('V')
                g = f['Current'] if is03 else f['OUTPUTS']
                for name, item in g.items():
                    self.outputChannels.append(None)
                    self.outputNames.append(name)
                    self.outputData.append(item[:].transpose())
                    self.outputUnits.append('pA')
        else:
            super().loadDataInternal()

    def initScan(self):
        return (self.addInputChannel(self.LR_channel,self.LR_from,self.LR_to,self.LR_step) and
        self.addInputChannel(self.UD_channel,self.UD_from,self.UD_to,self.UD_step) and
         super().initScan())

    def getDefaultSettings(self):
        ds = super().getDefaultSettings()
        ds['Interpolate']      = parameterDict(value = False,widgetType = ESIBD_Parameter.WIDGETBOOL,attr = 'interpolate',event = lambda : self.scanPlot(update=False, done=True))
        ds[f'{self.LEFTRIGHT}/{self.CHANNEL}'] = parameterDict(value = 'LB-S-LR',items = 'LA-S-LR,LB-S-LR,LC-in-LR,LD-in-LR,LE-in-LR',
                                                                widgetType = ESIBD_Parameter.WIDGETCOMBO,attr = 'LR_channel')
        ds[f'{self.LEFTRIGHT}/{self.FROM}']    = parameterDict(value = -5,widgetType = ESIBD_Parameter.WIDGETFLOAT,attr = 'LR_from')
        ds[f'{self.LEFTRIGHT}/{self.TO}']      = parameterDict(value = 5,widgetType = ESIBD_Parameter.WIDGETFLOAT,attr = 'LR_to')
        ds[f'{self.LEFTRIGHT}/{self.STEP}']    = parameterDict(value = 2,widgetType = ESIBD_Parameter.WIDGETFLOAT,attr = 'LR_step',_min = .1,_max = 10)
        ds[f'{self.UPDOWN}/{self.CHANNEL}'] = parameterDict(value = 'LB-S-UD',items = 'LA-S-UD,LB-S-UD,LC-in-UD,LD-in-UD,LE-in-UD',
                                                                widgetType = ESIBD_Parameter.WIDGETCOMBO,attr = 'UD_channel')
        ds[f'{self.UPDOWN}/{self.FROM}']    = parameterDict(value = -5,widgetType = ESIBD_Parameter.WIDGETFLOAT,attr = 'UD_from')
        ds[f'{self.UPDOWN}/{self.TO}']      = parameterDict(value = 5,widgetType = ESIBD_Parameter.WIDGETFLOAT,attr = 'UD_to')
        ds[f'{self.UPDOWN}/{self.STEP}']    = parameterDict(value = 2,widgetType = ESIBD_Parameter.WIDGETFLOAT,attr = 'UD_step',_min = .1,_max = 10)
        return ds

    def useLimits(self):
        self.LR_from,self.LR_to    = self.axes[0].get_xlim()
        self.UD_from,self.UD_to    = self.axes[0].get_ylim()

    def scanPlot(self, update=True, done=False, **kwargs):
        """Plots 2D scan data"""
        # timing test with 50 datapoints: update True: 33 ms, update False: 120 ms
        x,y = self.getMeshgrid() # data coordinates
        if update:
            z = self.outputData[self.getOutputIndex()].ravel()
            self.cont.set_array(z.ravel())
            self.cbar.mappable.set_clim(vmin=np.min(z),vmax=np.max(z))
        else:
            self.axes[0].clear() # only update would be preferred but not yet possible with contourf
            self.cax.clear()
            if len(self.outputData) > 0:
                self.axes[0].set_xlabel(f'{self.inputNames[0]} {self.inputUnits[0]}')
                self.axes[0].set_ylabel(f'{self.inputNames[1]} {self.inputUnits[1]}')
                if done and self.interpolate:
                    rbf = interpolate.Rbf(x.ravel(),y.ravel(),self.outputData[self.getOutputIndex()].ravel())
                    xi,yi = self.getMeshgrid(2) # interpolation coordinates,scaling of 1 much faster than 2 and seems to be sufficient
                    zi = rbf(xi,yi)
                    self.cont = self.axes[0].contourf(xi,yi,zi,levels=100,cmap = 'afmhot') # contour with interpolation
                else:
                    self.cont = self.axes[0].pcolormesh(x,y,self.outputData[self.getOutputIndex()],cmap = 'afmhot') # contour without interpolation
                self.cbar = self.fig.colorbar(self.cont,cax=self.cax) # match axis and color bar size # ,format='%d'
                self.cbar.ax.set_title(self.outputUnits[0])
                self.axes[-1].cursor = ESIBD_Cursor(self.axes[-1]) # has to be initialized last,otherwise axis limits may be affected

        if len(self.outputData) > 0 and self.inputChannels[0] is not None and self.inputChannels[1] is not None:
            self.axes[-1].cursor.setPosition(self.inputChannels[0].value,self.inputChannels[1].value)
        super().scanPlot(update=update)

    def getMeshgrid(self,scaling = 1):
        # interpolation with more than 50 x 50 gridpoints gets slow and does not add much to the quality for typical scans
        return np.meshgrid(*[np.linspace(a[0],a[-1],len(a) if scaling == 1 else min(len(a)*scaling,50)) for a in self.inputData])

class EnergyScan(ESIBD_Scan):
    """Obtains beam energy by scanning transmission as a function of retarding potential."""
    def __init__(self,**kwargs):
        super().__init__(name = 'Energy', **kwargs)
        self.suffixes.append('.swp.dat')
        self.suffixes.append('.swp.h5')
        self.axes.append(self.fig.add_subplot(111))
        self.axes.append(self.axes[0].twinx()) # creating twin axis
        self.fig.tight_layout()
        self.canvas.mpl_connect('motion_notify_event',self.mouseEvent)
        self.canvas.mpl_connect('button_press_event',self.mouseEvent)
        self.canvas.mpl_connect('button_release_event',self.mouseEvent)
        self.axes[0].yaxis.label.set_color(self.MYBLUE)
        self.axes[0].tick_params(axis='y',colors=self.MYBLUE)
        self.axes[1].set_ylabel('-dI/dV (%)')
        self.axes[1].set_ylim([0,112])
        self.axes[1].yaxis.label.set_color(self.MYRED)
        self.axes[1].tick_params(axis='y',colors=self.MYRED)

        self.seRaw  = self.axes[0].plot([],[],marker='.',linestyle = 'None',color=self.MYBLUE,label='.')[0] # dummy plot
        self.seGrad = self.axes[1].plot([],[],marker='.',linestyle = 'None',color=self.MYRED)[0] # dummy plot
        self.seFit  = self.axes[1].plot([],[],color=self.MYRED)[0] # dummy plot
        self.mouseActive = True
        self.axes[-1].cursor = None

    SESETTINGS = 'SESETTINGS'

    def loadDataInternal(self):
        """Loads data in internal standard format for plotting."""
        if self.file.name.endswith('.swp.dat'): # legacy ES-IBD Control file
            headers = []
            with open(self.file,'r',encoding = self.UTF8) as f:
                f.readline()
                headers = f.readline().split(',')[1:][::2] # read names from second line
            try:
                data = np.loadtxt(self.file,skiprows=4,delimiter=',',unpack=True)
            except ValueError as e:
                self.print(f'Warning: Error when loading from {self.file.name}: {e}')
                return
            if data.shape[0] == 0:
                self.print(f'Warning: no data found in file {self.file.name}')
                return
            self.inputChannels.append(None)
            self.inputNames.append('Voltage')
            self.inputData.append(data[0])
            self.inputUnits.append('V')
            for name,dat in zip(headers,data[1:][::2]):
                self.outputChannels.append(None)
                self.outputNames.append(name.strip())
                self.outputData.append(dat)
                self.outputUnits.append('pA')
        elif self.file.name.endswith('.swp.h5'):
            with h5py.File(self.file, 'r') as f:
                is03 = f[self.VERSION].attrs['VALUE'] == '0.3' # legacy version 0.3, 0.4 if false
                self.inputNames.append(f[self.SESETTINGS]['Channel'].attrs['VALUE'])
                self.inputChannels.append(self.esibdWindow.outputWidget.getChannelbyName(self.inputNames[-1],inout = INOUT.IN))
                self.inputData.append(f['Voltage'][:] if is03 else f['INPUT'][:])
                self.inputUnits.append('V')
                g = f['Current'] if is03 else f['OUTPUTS']
                for name, item in g.items():
                    self.outputChannels.append(None)
                    self.outputNames.append(name)
                    self.outputData.append(item[:])
                    self.outputUnits.append('pA')
        else:
            super().loadDataInternal()

    def getDefaultSettings(self):
        ds = super().getDefaultSettings()
        ds[self.CHANNEL] = parameterDict(value = 'RT_Grid',toolTip = 'Electrode that is swept through',items = 'RT_Grid,RT_Sample-Center,RT_Sample-End',
                                                                      widgetType = ESIBD_Parameter.WIDGETCOMBO,attr = 'channel')
        ds[self.FROM]    = parameterDict(value = -10,widgetType = ESIBD_Parameter.WIDGETFLOAT,attr = '_from')
        ds[self.TO]      = parameterDict(value = -5,widgetType = ESIBD_Parameter.WIDGETFLOAT,attr = 'to')
        ds[self.STEP]    = parameterDict(value = .2,widgetType = ESIBD_Parameter.WIDGETFLOAT,attr = 'step',_min = .1,_max = 10)
        return ds

    def initScan(self):
        return (self.addInputChannel(self.channel,self._from,self.to,self.step) and
        super().initScan())

    def map_percent(self,x):
        # can't map if largest deviation from minimum is 0,i.e. all zero
        return (x-np.min(x))/np.max(x-np.min(x))*100 if np.max(x-np.min(x) > 0) else 0

    def copyClipboard(self):
        # overwrite parent to keep fixed aspect ratio
        buf = io.BytesIO()
        self.fig.set_size_inches(6,4) # keep standard dimensions (independent of UI) for consistent look in labbook
        self.fig.savefig(buf,format='png',bbox_inches='tight',dpi=self.getDPI())
        self.canvas.resizeEvent(QResizeEvent(self.canvas.size(),QSize(0,0))) # trigger resize -> rescale to GUI
        QApplication.clipboard().setImage(QImage.fromData(buf.getvalue()))
        buf.close()

    def scanPlot(self, update=True, done=False, **kwargs):
        """Plots energy scan data including metadata"""
        # use first that matches display setting,use first availible if not found
        # timing test with 20 datapoints: update True: 30 ms, update False: 48 ms
        if len(self.outputData) > 0:
            y = np.diff(self.outputData[self.getOutputIndex()])/np.diff(self.inputData[0])
            x = self.inputData[0][:y.shape[0]]+np.diff(self.inputData[0])[0]/2 # use as many data points as needed
        if update: # only update data
            self.seRaw.set_data(self.inputData[0],self.outputData[self.getOutputIndex()])
            self.seGrad.set_data(x,self.map_percent(-y))
        else:
            self.removeAnnotations(self.axes[1])
            if len(self.outputData) > 0:
                self.axes[0].set_xlim(self.inputData[0][0],self.inputData[0][-1])
                self.axes[0].set_ylabel(f'{self.outputNames[self.getOutputIndex()]} {self.outputUnits[self.getOutputIndex()]}')
                self.axes[0].set_xlabel(f'{self.inputNames[0]} {self.inputUnits[0]}')
                self.seRaw.set_data(self.inputData[0],self.outputData[self.getOutputIndex()])
                self.seFit.set_data([],[]) # init
                self.seGrad.set_data(x,self.map_percent(-y))
                for ann in [child for child in self.axes[1].get_children() if isinstance(child,mpl.text.Annotation)]:
                    ann.remove()
                if done:
                    try:
                        x_fit,y_fit,u,fwhm = self.gaus_fit(x,y,np.mean(x)) # use center as starting guess
                        if self.inputData[0][0] <= u <= self.inputData[0][-1]:
                            self.seFit.set_data(x_fit,self.map_percent(y_fit))
                            self.axes[1].annotate(text='',xy=(u-fwhm/2.3,50),xycoords='data',xytext=(u+fwhm/2.3,50),textcoords='data',
                    	        arrowprops=dict(arrowstyle="<->",color=self.MYRED),va='center')
                            self.axes[1].annotate(text=f'center: {u:2.1f} V\nFWHM: {fwhm:2.1f} V',xy=(u-fwhm/1.6,50),xycoords='data',fontsize=10.0,
                                textcoords='data',ha='right',va='center',color=self.MYRED)
                            #self.axes[1].set_xlim([u-3*fwhm,u+3*fwhm]) # can screw up x range if fit fails
                        else:
                            self.print('Warning: Fitted mean outside data range. Ignore fit.')
                    except RuntimeError as e:
                        self.print(f'Fit failed with error: {e}')
                    self.axes[-1].cursor = ESIBD_Cursor(self.axes[-1],horizOn = False) # has to be initialized last,otherwise axis limits may be affected
            else: # no data
                self.seRaw.set_data([],[])
                self.seFit.set_data([],[])
                self.seGrad.set_data([],[])
        self.axes[0].autoscale(True,axis='y') # adjust to data
        self.axes[0].relim() # adjust to data
        if len(self.outputData) > 0 and self.inputChannels[0] is not None:
            self.axes[-1].cursor.setPosition(self.inputChannels[0].value,0)
        super().scanPlot(update=update)

    def gaussian(self,x,amp1,cen1,sigma1):
        return amp1*(1/(sigma1*(np.sqrt(2*np.pi))))*(np.exp(-((x-cen1)**2)/(2*(sigma1)**2)))

    def gaus_fit(self,x,y,c):
        # Define a gaussian to start with
        amp1 = 100
        sigma1 = 2
        gauss, *_ = optimize.curve_fit(self.gaussian,x,y,p0=[amp1,c,sigma1])
        fwhm = round(2.355 * gauss[2],1) # Calculate FWHM
        x_fine=np.arange(np.min(x),np.max(x),0.05)
        return x_fine,-self.gaussian(x_fine,gauss[0],gauss[1],gauss[2]),gauss[1],fwhm

class DepoScan(ESIBD_Scan):
    """Monitors deposited charge over time."""

    CHARGE = 'Charge'

    def __init__(self,**kwargs):
        super().__init__(name='Depo', **kwargs)
        self.scanPushButton.setText('Run')
        self.scanPushButton.setToolTip('Run Deposition.')

        self.axes.append(self.fig.add_subplot(211))
        self.axes.append(self.fig.add_subplot(212,sharex = self.axes[0]))
        self.fig.subplots_adjust(hspace=0.000)
        self.currentLine        = self.fig.axes[0].plot([[datetime.now()]],[0],color=self.MYBLUE)[0] # need to be initialized with datetime on x axis
        self.currentWarnLine    = self.axes[0].axhline(y=float(self.warnlevel),color=self.MYRED)
        self.chargeLine         = self.fig.axes[1].plot([[datetime.now()]],[0],color=self.MYBLUE)[0]
        self.chargePredictionLine = self.fig.axes[1].plot([[datetime.now()]],[0],'--',color=self.MYBLUE)[0]
        self.fig.autofmt_xdate() # rotate labels to avoid overlap https://stackoverflow.com/questions/26700598/matplotlib-showing-x-tick-labels-overlapping
        self.depoChargeTarget   = self.axes[1].axhline(y=float(self.target),color=self.MYGREEN)
        self.axes[0].tick_params(axis='x',which='both',bottom=False,labelbottom=False)
        self.addRightAxis(self.axes[0])
        self.addRightAxis(self.axes[1])
        self.axes[0].set_ylabel('Current (pA)')
        self.axes[1].set_ylabel('Charge (pAh)')
        self.axes[1].set_xlabel('Time')
        self.fig.tight_layout()

    def getDefaultSettings(self):
        """Defines settings and default values for DepoScan."""
        ds = super().getDefaultSettings()
        ds.pop(self.WAIT)
        ds.pop(self.WAITLONG)
        ds.pop(self.LARGESTEP)
        ds[self.DISPLAY][ESIBD_Parameter.VALUE] = 'RT_Sample-Center'
        ds[self.DISPLAY][ESIBD_Parameter.TOOLTIP] = 'Channel of deposition sample.'
        ds[self.DISPLAY][ESIBD_Parameter.ITEMS] = 'RT_Sample-Center,RT_Sample-End,C_Shuttle'
        ds[self.AVERAGE][ESIBD_Parameter.VALUE] = 4000
        ds[self.INTERVAL]   = parameterDict(value = 10000,toolTip = 'Deposition interval',widgetType = ESIBD_Parameter.WIDGETINT,
                                                                _min = 1000,_max = 60000,attr = 'interval')
        ds['Target']     = parameterDict(value = '15',toolTip = 'Target coverage in pAh',items = '-20,-15,-10,10,15,20',
                                                                widgetType = ESIBD_Parameter.WIDGETINTCOMBO,attr = 'target',event = self.updateDepoTarget)
        ds['Warnlevel']  = parameterDict(value = '10',toolTip = 'Warning sound will be played when value drops below this level.',event = self.updateWarnLevel,
                                                            items = '-20,-15,-10,0,10,15,20',widgetType = ESIBD_Parameter.WIDGETINTCOMBO,attr = 'warnlevel')
        ds['Warn']  = parameterDict(value = False,toolTip = 'Warning sound will be played when value drops below warnlevel. Disable to Mute.',
                                                            widgetType = ESIBD_Parameter.WIDGETBOOL,attr = 'warn')
        return ds

    def initScan(self):
        # overwrite parent
        """Initialized all data and metadata.
        Returns True if initialization sucessful and scan is ready to start."""
        self.outputChannels = self.esibdWindow.outputWidget.getInitializedOutputChannels()
        new_list = []
        for item in self.outputChannels:
            new_list.extend([item,item])
        self.outputChannels = new_list
        if len(self.outputChannels) > 0:
            self.inputChannels.append(None)
            self.inputNames.append('Time')
            self.inputUnits.append('')
            self.inputData.append(dynamicNp())
            for i,o in enumerate(self.outputChannels):
                self.outputData.append(dynamicNp())
                if i%2 == 0:
                    self.outputNames.append(f'{o.name}')
                    self.outputUnits.append(o.parent.unit)
                else:
                    self.outputNames.append(f'{o.name}_{self.CHARGE}')
                    self.outputUnits.append('pAh')
            self.measurementsPerStep = max(int((self.average/self.interval))-1,1)
            self.updateFile()
            self.populateDisplayChannel()
            self.updateDepoTarget() # flip axes if needed
            return True
        else:
            self.print(f'{self.name} Scan Warning: No initialized output channel found.')
            return False

    def loadDataInternal(self):
        super().loadDataInternal()
        self.updateDepoTarget() # flip axes if needed before plottin

    def populateDisplayChannel(self):
        # overwrite parent to hide Charge channels
        # super().populateDisplayChannel()
        self.loading = True
        self.displayComboBox.clear()
        for n in self.outputNames:
            if not f'_{self.CHARGE}' in n:
                self.displayComboBox.insertItem(self.displayComboBox.count(),n)
        self.loading = False
        self.updateDisplayDefault()

    def updateDepoTarget(self):
        if self.depoChargeTarget is not None:
            self.depoChargeTarget.set_ydata(self.target)
            if np.sign(self.target) == 1:
                self.axes[0].set_ylim(0,1)
                self.axes[1].set_ylim(0,1)
            else:
                self.axes[0].set_ylim(1,0)
                self.axes[1].set_ylim(1,0)
            self.axes[0].autoscale(True)
            self.axes[0].relim()
            self.axes[1].autoscale(True)
            self.axes[1].relim()
            self.canvas.draw_idle()

    def updateWarnLevel(self):
        if self.currentWarnLine is not None:
            self.currentWarnLine.set_ydata(self.warnlevel)
            self.canvas.draw_idle()

    def scanPlot(self, update=False, done=False, **kwargs):
        """Plots depo data"""
        # timing test with 360 datapoints (one hour at 0.1 Hz) update True: 75 ms, update False: 135 ms
        if self.loading:
            return
        if len(self.outputData) > 0:
            _timeInt = self.getData(0,INOUT.IN)
            _time = [datetime.fromtimestamp(float(t)) for t in _timeInt] # convert timestamp to datetime
            current = self.getData(self.getOutputIndex(),INOUT.OUT)
            charge = self.getData(self.getOutputIndex()+1,INOUT.OUT)
            self.currentLine.set_data(_time,current)
            self.chargeLine .set_data(_time,charge)
            if len(_time) > 10: # predict scan based on last 10 datapoints
                if update and np.abs(charge[-1]) < np.abs(float(self.target)) and np.abs(charge[-1]) > np.abs(charge[-10]): # only predict if below target and charge is increasing
                    time_done = _timeInt[-1] + (_timeInt[-1]-_timeInt[-10])/(charge[-1]-charge[-10])*(float(self.target) - charge[-1]) # t_t = t_i + dt/dQ * Q_missing
                    self.chargePredictionLine.set_data([_time[-1],datetime.fromtimestamp(float(time_done))],[charge[-1],self.target])
                else:
                    self.chargePredictionLine.set_data([[_time[0]]],[0]) # hide at beginning and end of scan or if loaded from file
                _min = min(np.min(current),0)                   if np.sign(self.warnlevel) == 1 else max(np.max(current),0)
                _max = max(np.max(current),self.warnlevel) if np.sign(self.warnlevel) == 1 else min(np.min(current),self.warnlevel)
                _range = _max - _min
                self.axes[0].set_ylim(bottom=_min-_range*0.05,top=_max+_range*0.3) # add space on top for plotlabel
                if done:
                    self.removeAnnotations(self.axes[1])
                    self.axes[1].annotate(text=f"start: {self.roundDateTime(_time[0]).strftime('%H:%M')} end: {self.roundDateTime(_time[-1]).strftime('%H:%M')}\n"
                                            + f"{charge[-1]-charge[0]:2.1f} pAh deposited within {int(np.ceil((_timeInt[-1]-_timeInt[0])//60))} min",
                                            xy=(0.02,0.98), xycoords='axes fraction', fontsize=8, ha='left', va='top',bbox=dict(boxstyle='square,pad=.2',fc='w',ec='none'))
        else: # no data
            self.removeAnnotations(self.axes[1])
            self.currentLine.set_data([],[])
            self.chargeLine .set_data([],[])
        self.axes[0].autoscale(True,axis='x')
        self.axes[0].relim()
        self.axes[1].autoscale(True)
        self.axes[1].relim()
        super().scanPlot(update=update)

    def roundDateTime(self,tm):
        """Rounds to nearest minute."""
        discard = timedelta(minutes=tm.minute % 1,
                             seconds=tm.second,
                             microseconds=tm.microsecond)
        tm -= discard
        if discard >= timedelta(seconds=30):
            tm += timedelta(minutes=1)
        return tm

    def run(self,acquiring):
        """Monitor deposition and log data."""
        while acquiring():
            time.sleep(self.interval/1000)
            self.inputData[0].add(time.time())
            for i,o in enumerate(self.outputChannels):
                if i%2 == 0:
                    self.outputData[i].add(np.mean(o.getValues(subtractBackground = True)[-self.measurementsPerStep:]))
                else:
                    self.outputData[i].add(o.charge)
            if self.warn and (np.sign(self.warnlevel) == 1 and self.getData(self.getOutputIndex(),INOUT.OUT)[-1] < float(self.target) or
                              np.sign(self.warnlevel) == -1 and self.getData(self.getOutputIndex(),INOUT.OUT)[-1] > float(self.target)):
                winsound.PlaySound('media/alarm.wav', winsound.SND_ASYNC | winsound.SND_ALIAS)
            if acquiring(): # all but last step
                self.signalComm.scanUpdateSignal.emit(False) # update graph
        self.signalComm.scanUpdateSignal.emit(True) # update graph and save data # placed after while loop to ensure it will be executed
        self.signalComm.resetScanButtonSignal.emit()

class GAScan(ESIBD_Scan,GA):
    """Optimizes input values based on feedback from a single output channel.
    The output channel can be virtual and contain an equation that references many other channels."""
    def __init__(self,**kwargs):
        super().__init__(name = 'GA', **kwargs)

        self.scanPushButton.setText('Optimize')
        self.displayComboBox.setVisible(False) # GA only uses single channel and cannot switch during of after acquisition
        self.initialPushButton = self.addButton(0,0,'Initial',self.toogleInitial,'Toggles between optimized and initial settings.',checkable=True)
        self.axes.append(self.fig.add_subplot(111))
        self.bestLine = self.axes[0].plot([[datetime.now()]],[0],label = 'best fitness')[0] # need to be initialized with datetime on x axis
        self.avgLine  = self.axes[0].plot([[datetime.now()]],[0],label = 'avg fitness')[0]
        self.axes[0].legend(loc = 'lower right',prop={'size': 10},frameon=False)
        self.axes[0].set_xlabel('Time')
        self.axes[0].set_ylabel('Fitness Value')
        self.fig.autofmt_xdate()
        self.fig.tight_layout()
        self.maximize(True)
        # self.restore(True)

    def getDefaultSettings(self):
        ds = super().getDefaultSettings()
        ds.pop(self.WAITLONG)
        ds.pop(self.LARGESTEP)
        ds['GA Channel'] = ds.pop(self.DISPLAY) # keep display for using displaychannel functionality but modify properties as needed
        ds['GA Channel'][ESIBD_Parameter.TOOLTIP] = 'Genetic algorithm optimizes on this channel'
        ds['GA Channel'][ESIBD_Parameter.ITEMS] = 'C_Shuttle,RT_Detector,RT_Sample-Center,RT_Sample-End,LALB_Aperture'
        ds['Logging'] = parameterDict(value = True,toolTip = 'Shows detailed GA updates in console.',widgetType = ESIBD_Parameter.WIDGETBOOL,attr = 'log')
        return ds

    def toogleInitial(self):
        if len(self.outputChannels) > 0:
            self.applyGA(initial = self.initialPushButton.isChecked())
        else:
            self.print('GA not initialized.')

    def initScan(self):
        """ Start optimization."""
        # overwrite parent
        gaChannel = self.esibdWindow.outputWidget.getChannelbyName(self.displayDefault, inout=INOUT.OUT)
        if gaChannel is None:
            self.print(f'Warning: Channel {self.displayDefault} not found. Cannot start optimization')
            return False
        else:
            self.inputChannels.append(None)
            self.inputNames.append('Time')
            self.inputUnits.append('')
            self.inputData.append(dynamicNp())
            self.outputChannels.extend([gaChannel,gaChannel])
            self.outputNames.extend([f'{gaChannel.name}',f'{gaChannel.name}_Avg'])
            self.outputUnits.extend([gaChannel.parent.unit,gaChannel.parent.unit])
            self.outputData.extend([dynamicNp(),dynamicNp()])
            self.axes[0].set_ylabel(f'{gaChannel.name} Fitness')
        for c in self.esibdWindow.outputWidget.channels(inout = INOUT.IN):
            if c.optimize:
                self.optimize(c.value,c.min,c.max,.2,abs(c.max-c.min)/10,c.name)
            else:
                self.optimize(c.value,c.min,c.max,0,abs(c.max-c.min)/10,c.name) # add entry but set rate to 0 to prevent value change. Can be activated later.
        self.genesis()
        self.measurementsPerStep = int((self.average/self.outputChannels[0].parent.interval))-1
        self.updateFile()
        self.file_path(self.file.parent.as_posix())
        self.file_name(self.file.name)
        return True

    def scanPlot(self, update=False, **kwargs):
        """Plots fitness data"""
        # timing test with 160 generations: update True: 25 ms, update False: 37 ms
        if self.loading:
            return
        if len(self.outputData) > 0:
            _time = [datetime.fromtimestamp(float(t)) for t in self.getData(0,INOUT.IN)] # convert timestamp to datetime
            self.bestLine.set_data(_time,self.getData(0,INOUT.OUT))
            self.avgLine.set_data(_time,self.getData(1,INOUT.OUT))
            if len(self.getData(0,INOUT.OUT)) > 2:
                _min = np.min(self.getData(1,INOUT.OUT))
                _max = np.max(self.getData(0,INOUT.OUT))
                _range = np.abs(_max - _min)
                self.axes[0].set_ylim([_min-_range*0.05,_max+_range*0.1]) # add 10 % on top for plotlabel,assuming increasing fitness
        else: # no data
            self.bestLine.set_data([],[])
            self.avgLine.set_data([],[])
        self.axes[0].autoscale(True,axis='x')
        self.axes[0].relim()
        self.axes[0].autoscale_view(True,True,True)
        super().scanPlot(update=update)

    def run(self,acquiring):
        """Run GA optimization."""
        while acquiring():
            for c in [c for c in self.esibdWindow.outputWidget.channels(inout = INOUT.IN) if c.optimize]:
                c.signalComm.updateValueSignal.emit(self.GAget(c.name,c.value))
            time.sleep((self.wait+self.average)/1000)
            self.fitness(np.mean(self.outputChannels[0].getValues(subtractBackground = True)[-self.measurementsPerStep:]))
            if self.log:
                self.printFromThread(self.step_string())
            _,session_saved = self.check_restart()
            if session_saved:
                self.inputData[0].add(time.time())
                self.outputData[0].add(self.best_fitness())
                self.outputData[1].add(self.average_fitness())
                self.signalComm.scanUpdateSignal.emit(False)
        self.check_restart(True) # sort population
        self.applyGA()
        self.signalComm.scanUpdateSignal.emit(True)

    def applyGA(self,initial = False):
        for c in [c for c in self.esibdWindow.outputWidget.channels(inout = INOUT.IN) if c.optimize]:
            c.signalComm.updateValueSignal.emit(self.GAget(c.name,c.value,0,initial=initial))
