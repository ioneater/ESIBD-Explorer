REM Use this file to start ESIBD-Explorer from a local mirror of the github project using a local install of the esibd environment
REM This way of using the software is only necessary if the computer has no access to the internet and modifications of the source files is required for development.
REM Otherwise, please use the provided standalone excecutable.

REM Go to location of offline environment
REM Extract all file created using create_esibd_offline.bat here if not already done
call cd C:\Users\srgroup\AppData\Local\miniconda3\envs\esibd
REM Activate the esibd environment
call .\Scripts\activate.bat
REM Change to the location where the ESIBD-Explorer project is mirrored
call cd C:/Users/srgroup/Desktop/ESIBD_Explorer/ESIBD_Explorer
REM Start ESIBD-Explorer
call python start.py
REM exit
cmd /k REM keep batch open in case we need to restart