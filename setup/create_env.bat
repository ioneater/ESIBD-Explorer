REM comment in line below for a clean installation of the virtual environment
REM call conda env remove --name esibd 
call conda update -y -n base conda
call conda env create -f esibd.yml --force
