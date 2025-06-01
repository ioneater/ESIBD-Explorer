"""Extend internal plugins here before they are loaded. Make sure to exchange them in provide_plugins.py."""

from datetime import datetime
from pathlib import Path

from esibd.core import PARAMETERTYPE, parameterDict
from esibd.plugins import Settings


class ESIBDSettings(Settings):
    """Settings plugin with customized session path.

    If you need to customize Settings for another experiment you only need to replace this class.
    """

    documentation = (Settings.__doc__ or '') + (__doc__ or '')

    SUBSTRATE = 'Substrate'
    ION = 'Ion'
    SESSIONTYPE = 'Session type'

    substrate: str
    molion: str
    sessionType: str

    def getDefaultSettings(self) -> dict[str, dict]:
        defaultSettings = super().getDefaultSettings()
        defaultSettings[f'{self.SESSION}/{self.SUBSTRATE}'] = parameterDict(value='None', toolTip='Choose substrate',
                                                                items='None, HOPG, aCarbon, Graphene, Silicon, Gold, Copper', parameterType=PARAMETERTYPE.COMBO,
                                                                event=self.updateSessionPath, attr='substrate')
        defaultSettings[f'{self.SESSION}/{self.ION}'] = parameterDict(value='GroEL', toolTip='Choose ion',
                                                                items='Betagal, Ferritin, GroEL, ADH, GDH, BSA, DNA, BK', parameterType=PARAMETERTYPE.COMBO,
                                                                event=self.updateSessionPath, attr='molion')
        defaultSettings[f'{self.SESSION}/{self.SESSIONTYPE}'] = parameterDict(value='MS', toolTip='Choose session type',
                                                                items='MS, depoHV, depoUHV, depoCryo, opt', parameterType=PARAMETERTYPE.COMBO,
                                                                event=self.updateSessionPath, attr='sessionType')
        return defaultSettings

    def buildSessionPath(self) -> Path:
        return Path(*[self.substrate, self.molion, datetime.now().strftime(f'%Y-%m-%d_%H-%M_{self.substrate}_{self.molion}_{self.sessionType}')])
