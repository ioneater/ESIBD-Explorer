REM Start script for windows
REM based on https://www.pythonguis.com/tutorials/packaging-pyqt5-pyside2-applications-windows-pyinstaller/

REM do not run this a script
REM run individual blocks manually and only proceed if successful
exit

::::::::::::::
REM Formatting
::::::::::::::

REM use the following regex to fix common formating errors
REM ,[a-zA-Z0-9_]| \n|\n\n\n|[^'],'| [b-hk-w] |as f:|lambda :
REM files to exclude: *.html,*.js,*.css,*.log,*.gitignore,*.bib,*.tex,*.rst,*.txt,*.svg,*.sh,*.toml,LICENSE,Makefile

::::::::::::::
REM Change Log
::::::::::::::
REM update changelog in changelog.rst (ideally update before each commit)
REM Often, writing the change log inspires some last minute changes!
REM Content: start bullet points with capitals and dot at the end
REM - will be replaced by bullet points on github

REM Added 		for new features.
REM Changed 	for changes in existing functionality.
REM Deprecated 	for soon-to-be removed features.
REM Removed 	for now removed features.
REM Fixed 		for any bug fixes.
REM Security 	in case of vulnerabilities.
REM Performance for speed improvements

:::::::::::
REM Testing
:::::::::::
REM make sure all test pass in development environment

:::::::::::::::::::::
REM Environment setup
:::::::::::::::::::::

REM If applicable perform clean install of virtual environment
REM start from ESIBD Explorer
cd setup
call create_env.bat REM make sure no other environments (including VSCode) are active during this step
cd ..
call activate esibd

REM If no change to the environment since last deployment following is sufficient.
call conda update -y -n base -c conda-forge conda

:::::::::::::::::::::::::::
REM Bump version
:::::::::::::::::::::::::::

REM update version in pyproject.toml
REM update Product Version in EsibdExplorer.ifp in the General tab
REM update PROGRAM_VERSION in config.py
REM if applicable update year in license file
REM update copyright year and release version also in docs/conf.py

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
call rm -r docs\_build REM works in powershell
call rm -r esibd\docs REM works in powershell
REM -M coverage
REM update autodoc_mock_imports and correspondingly pyinstaller_hooks
call sphinx-build docs docs\_build
REM NOTE disable script blocker to properly test documentation offline
REM offline version for in app documentation (instrument computers often have no internet access)
call xcopy /i /y /e docs\_build esibd\docs
REM call docs\make.bat html

:::::::
REM git
:::::::

REM git config --global user.email "XXX@XXX.com" # setup email
REM git config --global user.name "ioneater" # setup user name

REM git-init # (re)initialize current folder as git repository
REM git remote add origin https://github.com/ioneater/ESIBD-Explorer

REM git add .
REM git status
REM git commit -a -m "message"
REM git push origin main

::::::::
REM PyPI
::::::::

call rmdir /q /s dist
call rm -r dist REM works in powershell
call rmdir /q /s esibd_explorer.egg-info
call rm -r esibd_explorer.egg-info REM works in powershell

python -m build

REM pip install . REM test installation locally
REM python -m esibd.explorer # start gui using module

twine check dist/*
REM safer to use normal terminal instead of vscode to avoid issues when pasting token
twine upload -r testpypi dist/*

REM test on pypitest
conda create -y -n "estest" python=3.11 REM make sure no other environments (including VSCode) are active during this step
conda activate estest
pip install -i https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ esibd-explorer
REM ==0.6.15 NOTE latest will be used if no version specified  # extra-index-url specifies pypi dependencies that are not present on testpypi
REM python -m esibd.reset # clear registry settings to emulate fresh install
python -m esibd.explorer
REM activate all plugins for testing!
REM test software using PluginManager.test() in testmode
REM test software using PluginManager.test() with hardware!
REM Make sure VSCode or any other instance accessing the environment is not running at the same time while testing

REM only upload on real pypi after testing!
REM safer to use normal terminal instead of vscode to avoid issues when pasting token
twine upload dist/*

:::::::::::::::
REM pyinstaller
:::::::::::::::

call rmdir /q /s pyinstaller_build
call rm -r pyinstaller_build
call rmdir /q /s pyinstaller_dist
call rm -r pyinstaller_dist
conda create -y -n "esibdtest" python=3.11 REM make sure no other environments (including VSCode) are active during this step
conda activate esibdtest
REM pip install esibd-explorer pyinstaller --upgrade REM might install from local source
pip install esibd-explorer==0.7.2 pyinstaller
REM test software
python -m esibd.explorer

REM Run the following line to create initial spec file
REM ATTENTION: Check absolute paths in Files, Shortcuts, and Build! relative paths using <InstallPath> did not work
pyinstaller start.py -n "ESIBD Explorer" --noconsole --clean --icon=esibd/media/ESIBD_Explorer.ico --add-data="esibd;esibd" --copy-metadata nidaqmx --noconfirm --additional-hooks-dir=./pyinstaller_hooks --distpath ./pyinstaller_dist --workpath ./pyinstaller_build
REM --noconsole # console can be useful for debugging. start .exe from command window to keep errors visible after crash
REM --additional-hooks-dir=./pyinstaller_hooks -> add any modules that plugins may require at run time but are not imported at packaging time: e.g. modules only imported in plugins. modules added here should likely also be added to autodoc_mock_imports in docs/conf.py
REM --onefile meant for release to make sure all dependencies are included in the exe but extracting everything from one exe on every start is unacceptably slow. For debugging use --onedir (default) Use this option only when you are sure that it does not limit performance or complicates debugging
REM --copy-metadata nidaqmx is needed to avoid "No package metadata was found for nidaqmx"
REM do not modify spec file, will be overwritten

::::::::::::::::
REM InstallForge
::::::::::::::::

REM Next, create setup.exe using InstallForge
REM use EsibdExplorer.ifp and adjust absolute file paths for dependencies and setup file if applicable and update "Product Version" and update year in license section!
REM files:
REM pyinstaller_dist\ESIBD Explorer\_internal
REM pyinstaller_dist\ESIBD Explorer\ESIBD Explorer.exe

REM NOTE without certificate users will see "publisher unknown" message during installation. $300 per year for certificate -> only if number of clients increases
REM NOTE https://installforge.net/support1/docs/setting-up-visual-update-express/ -> for small user groups installing from downloaded exe acceptable and less error prone (e.g. if online links should change). If applicable do manual uninstall before installing from exe to get clean installation.

REM Test installation from exe before continuing

::::::::::::::::
REM git release
::::::::::::::::

REM create tag used for releasing exe later
git commit -a -m "Realeasing version v0.7.2"
git tag -a v0.7.1 -m "Realeasing version v0.7.2"
git push origin main --tags REM to include tags (otherwise tags are ignored)

REM create release on github with changelog based on commits and following sections (have to be signed in!)
REM select tag
REM Title: Version v0.7.1
REM Copy change log from changelog.rst
REM attach ESIBD_Explorer-setup.exe from pyinstaller_build to release
REM Source code (zip) and Source code (tar.gz) will be automatically attached, even though they are not visible before clicking on Publish release
