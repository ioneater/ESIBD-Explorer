REM After installing ESIBD-Explorer using pip on a computer with internet, this file can be used to bundle all dependencies to create the esibd environment on a computer without internet connection
REM After running this, proceed by installing miniconda on the offline computer and extract the content of esibd.tar.gz as a local environment (e.g. to \AppData\Local\miniconda3\envs\esibd)
REM Then start the program using start_esibd_offline.bat

REM https://conda.github.io/conda-pack/
REM https://gist.github.com/pmbaumgartner/2626ce24adb7f4030c0075d2b35dda32
REM Make sure files are copied to local drive before unpacking (q drive insanely slow)
REM requires installation of conda-pack in base environment
REM conda install -c conda-forge conda-pack
call conda activate base
call conda pack -n esibd -o esibd.tar.gz
