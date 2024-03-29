REM Start script for windows
REM based on https://www.pythonguis.com/tutorials/packaging-pyqt5-pyside2-applications-windows-pyinstaller/

REM do not run this a script
REM run individual blocks manually and only proceed if successful
exit

:::::::::::::::::::::
REM Environment setup
:::::::::::::::::::::

REM If applicable perform clean install of virtual environment 
REM start from ESIBD_Explorer
cd setup
call create_env.bat
cd ..
call activate esibd

:::::::::::::::::::::::::::
REM Bump version
:::::::::::::::::::::::::::

REM update version in pyproject.toml
REM update PROGRAM_VERSION in config.py

REM Note that the program has to access the version during development and after deployment to test for plugin compatibility
REM Neither reading the version from pyproject.toml or from installed package using importlib.metadata.version covers both use cases, 
REM requiring to update the version in both files
REM bumpversion / bump-my-version seems overkill

:::::::::::::::::::::::::::
REM Sphinx -> read the docs
:::::::::::::::::::::::::::

REM use sphinx-quickstart to generate initial configuration
REM then edit docs/conf.py to customize
call rmdir /q /s docs\_build REM delete docs/_build to generate clean documentation
call rmdir /q /s esibd\docs REM delete docs/_build to generate clean documentation
REM call rm -r docs\_build REM delete docs/_build to generate clean documentation (works in powershell?)
REM -M coverage
call sphinx-build docs docs\_build
REM offline version for in app documentation (instrument computers often have no internet access)
call xcopy /i /y /e docs\_build esibd\docs
REM call docs\make.bat html


:::::::
REM git
:::::::
REM git config --global user.email "XXX@XXX.com" # setup email
REM git config --global user.name "ioneater" # setup user name

REM git remote add origin https://github.com/ioneater/ESIBD-Explorer

REM git add .
REM git status
REM git commit -a -m "message"
REM git push origin main

::::::::
REM PyPI
::::::::

call rmdir /q /s dist
call rmdir /q /s esibd_explorer.egg-info

python -m build

REM pip install . REM test installation locally
REM python -m esibd.explorer # start gui using module

twine check dist/*
twine upload -r testpypi dist/*

REM test on pypitest
conda create -y -n "estest" python=3.11
conda activate estest
pip install -i https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ esibd-explorer
REM ==0.6.15 NOTE latest will be used if no version specified  # extra-index-url specifies pypi dependencies that are not present on testpypi 
REM python -m esibd.reset # clear registry settings to emulate fresh install
REM test software
REM test software with hardware!
python -m esibd.explorer 

REM only upload on real pypi after testing!
REM twine upload dist/*

:::::::::::::::
REM pyinstaller
:::::::::::::::

call rmdir /q /s pyinstaller_build
call rmdir /q /s pyinstaller_dist
conda create -y -n "esibdtest" python=3.11
conda activate esibdtest
pip install esibd-explorer pyinstaller --upgrade
REM test software
python -m esibd.explorer 

REM Run the following line to create initial spec file
REM ATTENTION: Check absolute paths inf Files, Shortcuts, and Build! relative paths using <InstallPath> did not work
pyinstaller start.py -n "ESIBD Explorer" --noconsole --clean --icon=esibd/media/ESIBD_Explorer.ico --add-data="esibd;esibd" --noconfirm --additional-hooks-dir=./pyinstaller_hooks --distpath ./pyinstaller_dist --workpath ./pyinstaller_build
REM --noconsole # console can be useful for debugging. start .exe from command window to keep errors visible after crash
REM --additional-hooks-dir=./pyinstaller_hooks -> add any modules that plugins may require at run time
REM --onefile meant for release to make sure all dependencies are included in the exe but extracting everything from one exe on every start is unacceptably slow. For debugging use --onedir (default) Use this option only when you are sure that it does not limit performance or complicates debugging
REM do not modify spec file, will be overwritten


::::::::::::::::
REM InstallForge
::::::::::::::::

REM Next, create setup.exe using InstallForge
REM use EsibdExplorer.ifp and adjust absolute file paths for dependencies and setup file if applicable
REM NOTE without certificate users will see "publisher unknown" message during installation. $300 per year for certificate -> only if number of clients increases
REM NOTE https://installforge.net/support1/docs/setting-up-visual-update-express/ -> for small user groups installing from downloaded exe acceptable and less error prone (e.g. if online links should change). If applicable do manual uninstall before installing from exe to get clean installation.

::::::::::::::::
REM git release
::::::::::::::::

REM create tag used for releasing exe later
git tag -a 0.6.16 -m "message"
git push origin main --tags REM to include tags (otherwise tags are ignored)

REM create release with changelog based on commits and following sections

REM Added 		for new features.
REM Changed 	for changes in existing functionality.
REM Deprecated 	for soon-to-be removed features.
REM Removed 	for now removed features.
REM Fixed 		for any bug fixes.
REM Security 	in case of vulnerabilities.
REM Performance for speed improvements