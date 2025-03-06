Welcome to ESIBD Explorer's documentation!
==========================================

The *ESIBD Explorer* controls all aspects of an :ref:`Electrospray Ion-Beam
Deposition<sec:ESIBD>` (ESIBD) experiment, including optimization and
characterization of the ion-beam energy, beam intensity, and beam size,
as well as monitoring of the deposition. At each step, results and
metadata are saved to document the experiment and allow for later
reproduction of all experimental conditions.

*ESIBD Explorer* was designed to
be used intuitively and without the need to memorize a lengthy manual.
The main functionality should be self-evident from the user interface
(see tooltips!). However, there are some aspects worth discussing below
in more detail to make sure you can make the most use of it. Please get
in touch if you have any feature requests or bug reports. The *ESIBD
Explorer* should allow researchers to focus on the science, instead of
performing repetitive tasks manually.

*ESIBD Explorer* provides a plugin system and plugin templates that
allow to add support for custom devices, scan modes, and more using only
a few lines of code. It can therefore be used for a broad range of
academic experiments beyond ESIBD. It **does** make it easy to generate
a consistent user interface for your custom hardware and data, and takes
care of saving and loading data and settings. It **does not** write
device specific code for you, and it is recommended to create a
standalone script for all required device communication before creating
your custom plugin. It **does not** eliminate the need to learn basic
Python and PyQt independently if you want to create more advanced plugins,
though the existing plugins can be a great resource to get started.

*ESIBD Explorer* is implemented based on Python and PyQt. It is
optimized for Microsoft Windows 10 or higher and distributed under the
GNU General Public License. There is no guarantee in case of any data
loss due to malfunction of *ESIBD Explorer*. Users are responsible for
backing up their own data and configuration files.

.. toctree::
   :numbered:
   :maxdepth: 2
   :caption: Contents:

   pages/install
   pages/esibd
   pages/users-guide
   pages/plugin-development
   library
   pages/changelog
   pages/acknowledgments
   pages/references

Links
=====

* :ref:`genindex`
* Online Documentation: https://esibd-explorer.readthedocs.io/en/stable/index.html
* Source code: https://github.com/ioneater/ESIBD-Explorer
* PyPI: https://pypi.org/project/esibd-explorer
* Contact: ioneater.dev@gmail.com