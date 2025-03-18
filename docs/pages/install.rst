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
It is highly recommended to use virtual environments, which isolate the installed packages from the system packages
(follow instructions for your respective python distribution).
Install using::

   pip install esibd-explorer

Run the program using::

   python -m esibd.explorer

From source (Miniconda)
-----------------------

| Install `Miniconda <https://docs.anaconda.com/miniconda/>`_
  or another conda distribution following the instructions on the
  website. You may need to manually add the following directories
  to the PATH environment variable.

.. code-block:: python3

   Miniconda3
   Miniconda3\Scripts
   Miniconda3\Library\bin

| The installation path may vary on your system. Also give the user
  account full write access in the Miniconda3 folder.

Download the source from github, go to the setup folder, and run create_env.bat
to install all dependencies. Later, update_env.bat can be used to update
dependencies. Start the program using *start.bat*. If desired, you can add
a shortcut to start.bat to the start menu.

From source (Miniconda offline)
-------------------------------

To install on a computer that is offline, create and export the esibd environment from another computer that is online.
All files you need to do this are in the `setup folder <https://github.com/ioneater/ESIBD-Explorer/tree/main/setup>`_.

1. Run :code:`create_env.bat` to create the esibd environment.
2. Run :code:`create_esibd_offline.bat` to export the esibd environment as :code:`esibd.tar.gz`.
3. Install Miniconda on the offline computer and extract the content of :code:`esibd.tar.gz` as a local environment.
4. Run :code:`start_esibd_offline.bat` to start *ESIBD Explorer* on the offline computer

You need to adjust the filepaths in these files depending on the location of the environment and software on your computer.
See comments within the files for more details.

From PyPi (Linux)
-----------------

While ESIBD Explorer is not developed for Linux, most features should work just as on Windows.
Installation on Ubuntu 24.04.1 was possible using the following commands.
Some additional dependencies and configurations may be necessary depending on your Linux distribution.

.. code-block:: python3

   sudo apt update
   sudo apt-get install python3.12-venv
   sudo apt install libxcb-cursor0
   python3.12 -m venv esibd

Set the include-system-site-packages to true in esibd/pyvenv.cfg

.. code-block:: python3

   source esibd/bin/activate
   pip install esibd-explorer --user
   python -m esibd.explorer --disable-gpu

From source (other)
-------------------

Instead of using Miniconda you can create an environment with any other
python package manager of your choice and install the packages defined in *esibd.yml*
independently. Refer to the installation instructions specific to your
package manager, then follow instructions above to run *ESIBD Explorer*.

