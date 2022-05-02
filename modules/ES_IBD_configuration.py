"""This module contains internally used constants
Generally all internally used constants should be defined here and not be hard coded within other files.
This helps to keep things consistent and avoid errors to typos in strings etc.
In principle, different versions of this file could be used for localization
For now, English is the only supported language and use of hard coded error messages etc. in other files is tolerated if they are unique."""


from pathlib import Path

# system specific settings load and saved using QSettings -> use these to load all other settings from file
DATAPATH    = 'Data Path'
dataPathDefault=Path('').resolve()
CONFIGPATH  = 'Config Path'
configPathDefault=Path('../conf/').resolve()
SESSIONPATH  = 'Session Path'

# files
settingsFile        = lambda qSet : Path(qSet.value(CONFIGPATH,configPathDefault)) / 'settings.ini'
configFile          = lambda qSet : Path(qSet.value(CONFIGPATH,configPathDefault)) / 'config.h5'
currentConfigFile   = lambda qSet : Path(qSet.value(CONFIGPATH,configPathDefault)) / 'current.ini'
voltageConfigFile   = lambda qSet : Path(qSet.value(CONFIGPATH,configPathDefault)) / 'voltage.ini'

# General field
COMPANY_NAME = 'ES-IBD LAB'
PROGRAM_NAME = 'ES-IBD Explorer'
VERSION_MAYOR = 0
VERSION_MINOR = 2
VERSION = 'Version'

# general keys
NAME        = 'NAME'
VALUE       = 'VALUE'
ENABLED     = 'Enabled'
NOTESTXT    = 'notes.txt'
NOTES       = 'Notes'
HEADER      = 'notes.txt'
DEFAULT     = 'DEFAULT'
SELECTPATH  = 'Select Path'
SELECTFILE  = 'Select File'
TIME  = 'Time'

# UI keys
GEOMETRY            = 'GEOMETRY'
WINDOWSTATE         = 'WINDOWSTATE'
WINDOWSIZE          = 'WINDOWSIZE'
MAINSPLTTERSIZE     = 'MAINSPLTTERSIZE'
CONTENTSPLTTERSIZE  = 'CONTENTSPLTTERSIZE'

# settings keys
GENERALSETTINGS = 'GENERALSETTINGS'
CATEGORY    = 'CATEGORY'
HARDWARE    = 'Hardware'
GENERAL    = 'General'
CATGENERAL  = 'General'
CATEXPLORER = 'Explorer'
CATSETTINGS = 'Settings'
ITEMS       = 'ITEMS'
TOOLTIP     = 'TOOLTIP'
WIDGET      = 'WIDGET'
WIDGETLABEL = 'LABEL'
WIDGETCOMBO = 'COMBO'
WIDGETTEXT  = 'TEXT'
WIDGETCOLOR = 'COLOR'
WIDGETBOOL  = 'BOOL'
WIDGETINT   = 'INT'
WIDGETFLOAT = 'FLOAT'
DPI         = 'DPI'
ADDITEM     = 'Add Item'
EDITITEM     = 'Edit Item'
REMOVEITEM     = 'Remove Item'
DATAINTERVAL= 'Data Interval'
MONITORINTERVAL = 'Monitoring Interval'
DISPLAYTIME = 'Display Time'
GACHANNEL = 'GA Channel'
DEPOSITIONCHANNEL = 'Deposition Channel'

# session keys
SESSION     = 'Session'
AUTOSAVE    = 'Autosave Session'
MOLION      = 'Molecule/Ion'
SUBSTRATE   = 'Substrate'
SESSIONTYPE = 'Session Type'
MEASUREMENTNUMBER = 'Measurement Number'

# Current keys
COM         = 'COM'
LENS        = 'LENS'
RANGE       = 'RANGE'
AVERAGE     = 'AVERAGE'
BIAS        = 'BIAS'
DISPLAY     = 'DISPLAY'
SUM         = 'SUM'
COLOR       = 'COLOR'

# Voltage keys
VOLTAGE     = 'Voltage'
ACTIVE      = 'ACTIVE'
REAL        = 'REAL'
EQUATION    = 'EQUATION'
MIN         = 'MIN'
MAX         = 'MAX'
OPTIMIZE    = 'OPTIMIZE'
MODULE      = 'MODULE'
ID          = 'ID'
ISEGIP      = 'ISEG IP'
ISEGPORT    = 'ISEG Port'

# General measurement keys
WAIT    = 'Wait'
WAITFIRST= 'Wait first'
AVERAGE = 'Average'
FROM    = 'From'
TO      = 'To'
STEP    = 'Step'
CHANNEL = 'Channel'
CURRENT = 'Current'
CURRENTDATA = 'Current Data'
# OFFSET  = 'Offset'
DISPLAY  = 'Display'
S2DDATA = 'S2DDATA'
SPECTRUM = 'SPECTRUM'
PROFILE = 'Profile'
S2DSETTINGS = 'S2DSETTINGS' # 2D scan
SESETTINGS = 'SESETTINGS' # energy scan

# S2D keys
LEFTRIGHT = 'Left-Right'
UPDOWN  = 'Up-Down'
S2D_DISPLAY     = f'/{S2DSETTINGS}/{DISPLAY}'
S2D_WAIT        = f'/{S2DSETTINGS}/{WAIT}'
S2D_WAITFIRST   = f'/{S2DSETTINGS}/{WAITFIRST}'
S2D_AVERAGE     = f'/{S2DSETTINGS}/{AVERAGE}'
S2D_LR_CHANNEL  = f'/{S2DSETTINGS}/{LEFTRIGHT}/{CHANNEL}'
S2D_LR_FROM     = f'/{S2DSETTINGS}/{LEFTRIGHT}/{FROM}'
# S2D_LR_OFFSET   = f'/{S2DSETTINGS}/{LEFTRIGHT}/{OFFSET}'
S2D_LR_STEP     = f'/{S2DSETTINGS}/{LEFTRIGHT}/{STEP}'
S2D_LR_TO       = f'/{S2DSETTINGS}/{LEFTRIGHT}/{TO}'
S2D_UD_CHANNEL  = f'/{S2DSETTINGS}/{UPDOWN}/{CHANNEL}'
S2D_UD_FROM     = f'/{S2DSETTINGS}/{UPDOWN}/{FROM}'
# S2D_UD_OFFSET   = f'/{S2DSETTINGS}/{UPDOWN}/{OFFSET}'
S2D_UD_STEP     = f'/{S2DSETTINGS}/{UPDOWN}/{STEP}'
S2D_UD_TO       = f'/{S2DSETTINGS}/{UPDOWN}/{TO}'

# energy scan keys
SE_DISPLAY  = f'/{SESETTINGS}/{DISPLAY}'
SE_CHANNEL    = f'/{SESETTINGS}/{CHANNEL}'
SE_FROM     = f'/{SESETTINGS}/{FROM}'
SE_TO       = f'/{SESETTINGS}/{TO}'
SE_STEP     = f'/{SESETTINGS}/{STEP}'
SE_WAIT     = f'/{SESETTINGS}/{WAIT}'
SE_WAITFIRST= f'/{SESETTINGS}/{WAITFIRST}'
SE_AVERAGE  = f'/{SESETTINGS}/{AVERAGE}'


# NOTIFICATIONS
NOTE_NOT_ACQUIRING = 'NOTE: Acquisition is not running.'

# WARNINGS


# ERRORS

# file types

FILE_CUR = '.cur.h5'
FILE_SE = '.swp.h5'
FILE_S2D = '.s2d.h5'
FILE_INI = '.ini'
FILE_PDF = '.pdf'

# file type filters
FILTER_H5 = 'HDF5 File (*.h5 *.hdf5)'
FILTER_INI = 'INI File (*.ini)'

# Load file dialog
LOAD_SE = 'Load Energy Scan Settings'
LOAD_S2D = 'Load 2D Scan Settings'
LOAD_GS = 'Load General Settings'
LOAD_CURRENT = 'Load Current Settings'
LOAD_VOLTAGE = 'Load Voltage Settings'

indexSettings, indexVoltage, indexCurrent, indexScan2D, indexScanEnergy, indexExplorer = range(6) # define indices
indexHtml, indexLine, indexLineQt, indexS2D, indexS2DQt, indexSE, indexImage, indexVector, indexPdb, indexText, indexNotes = range(11) # define indices for displayTabWidget

# assets
ICON_FOLDER = '../img/folder.png'
ICON_DOCUMENT = '../img/document.png'
ICON_REFRESH = '../img/arrow-circle-315.png'
ICON_DIRECTION = '../img/direction.png'

# other
UTF8 = 'utf-8'
MYBLUE='#1f77b4'
MYRED='#d62728'
