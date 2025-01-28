"""Extend internal plugins here before they are loaded. Make sure to exchange them in providePlugins.py."""

from pathlib import Path
from datetime import datetime
from esibd.plugins import Settings
from esibd.core import parameterDict, Parameter

class ESIBDSettings(Settings):
    """This version of the Settings plugin has a customized session path.
    If you need to customize Settings for another experiment you only need to replace this class."""
    documentation = Settings.__doc__ + __doc__

    SUBSTRATE           = 'Substrate'
    ION                 = 'Ion'
    SESSIONTYPE         = 'Session type'

    def getDefaultSettings(self):
        defaultSettings = super().getDefaultSettings()
        defaultSettings[f'{self.SESSION}/{self.SUBSTRATE}']      = parameterDict(value='None', toolTip='Choose substrate',
                                                                items='None, HOPG, aCarbon, Graphene, Silicon, Gold, Copper', widgetType=Parameter.TYPE.COMBO,
                                                                event=self.updateSessionPath, attr='substrate')
        defaultSettings[f'{self.SESSION}/{self.ION}']            = parameterDict(value='GroEL', toolTip='Choose ion',
                                                                items='Betagal, Ferritin, GroEL, ADH, GDH, BSA, DNA, BK', widgetType=Parameter.TYPE.COMBO,
                                                                event=self.updateSessionPath, attr='molion')
        defaultSettings[f'{self.SESSION}/{self.SESSIONTYPE}']   = parameterDict(value='MS', toolTip='Choose session type',
                                                                items='MS, depoHV, depoUHV, depoCryo, opt', widgetType=Parameter.TYPE.COMBO,
                                                                event=self.updateSessionPath, attr='sessionType')
        return defaultSettings

    def buildSessionPath(self):
        return Path(*[self.substrate, self.molion, datetime.now().strftime(f'%Y-%m-%d_%H-%M_{self.substrate}_{self.molion}_{self.sessionType}')])
