REM Use this file to start ESIBD-Explorer using a local copy of the esibd environment
REM This way of using the software is only necessary if the computer has no access to the internet and modifications of the source files is required for development.
REM Otherwise, please use the provided standalone executable.

REM Go to location of offline environment
REM Extract all files from esibd.tar.gz created using create_esibd_offline.bat here
REM Extract esibd.tar.gz -> esibd.tar
REM Extract esibd.tar to esibd
REM Adjust following path as needed
call cd C:\Users\UserName\Desktop\esibd
REM Activate the esibd environment
call .\Scripts\activate.bat
REM Start ESIBD-Explorer
call python -m esibd.explorer
REM exit
call cmd /k REM keep batch open in case we need to restart