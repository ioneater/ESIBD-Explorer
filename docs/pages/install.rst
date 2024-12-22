Installation
============

Standalone Windows installer
----------------------------

A `standalone installer for windows <https://github.com/ioneater/ESIBD-Explorer/releases>`_ 
allows for a simple and fast installation, but may require more disk space, does
not allow to overwrite internal plugins, and does not allow to add additional python libraries.
You will still be able to include custom plugins and inherit from internal plugins.

From PyPi
-----------------------
Install directly from the `Python Package Index <https://pypi.org/project/esibd-explorer>`_ using pip.
It is highly recommended to use virtual environments, which isolate the installed packages from the system packages::

   pip install esibd-explorer

Run the program using::

   python -m esibd.explorer

From source (Miniconda)
-----------------------

| Install `Miniconda <https://docs.anaconda.com/miniconda/>`_
  or another conda distribution following the instructions on the
  website. You may need to manually add the paths to the following
  folders to the PATH environment variable.
| The installation path may vary on your system. Also give the user
  account full write access in the Miniconda3 folder.

Download the source from github, go to the setup folder, and run create_env.bat
to install all dependencies. Later, update_env.bat can be used to update
dependencies. Start the program using *start.bat*. If desired, you can add
a shortcut to start.bat to the start menu.

From source (other)
-------------------

Instead of using Miniconda you can create an environment with any other
python package manager of your choice and install the packages defined in *esibd.yml*
independently. Refer to the installation instructions specific to your
package manager, then follow instructions above to run *ESIBD Explorer*.

