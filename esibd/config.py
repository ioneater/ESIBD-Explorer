""" Defines program specific constants. Replace when using the tools provided by ESIBD Explorer to create a separate software."""

from pathlib import Path

COMPANY_NAME    = 'ESIBD LAB'
PROGRAM_NAME    = 'ESIBD Explorer'
ABOUTHTML       = f"""<p>{PROGRAM_NAME} controls all aspects of an ESIBD experiment, including ion beam guiding and steering, beam energy analysis, deposition monitoring, and data analysis.<br>
                    Using the build-in plugin system, it can be extended to support additional hardware as well as custom controls for data acquisition, analysis, and visualization.<br>
                    Read the docs: <a href='TODO read the docs'>here</a> for more details.<br><br>
                    Github: <a href='https://github.com/ioneater/ESIBD-Explorer'>https://github.com/ioneater/ESIBD-Explorer</a><br>
                    Rauschenbach Lab: <a href='https://rauschenbach.chem.ox.ac.uk/'>https://rauschenbach.chem.ox.ac.uk/</a><br>
                    Present implementation in Python/PyQt: ioneater <a href='mailto:tim.esser@gmx.de'>tim.esser@gmx.de</a><br>
                    Original implementation in LabView: rauschi2000 <a href='mailto:stephan.rauschenbach@chem.ox.ac.uk'>stephan.rauschenbach@chem.ox.ac.uk</a><br></p>"""
VERSION_MAYOR   = 0
VERSION_MINOR   = 6
internalPluginPath = Path(__file__).parent / 'plugins_internal'
internalMediaPath = Path(__file__).parent / 'media'
PROGRAM_ICON    = internalMediaPath / 'ESIBD_Explorer.png'
SPLASHIMAGE     = [internalMediaPath / f'ESIBD_Explorer_Splash{i+1}.png' for i in range(4)]
