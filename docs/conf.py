"""Configuration file for the Sphinx documentation builder."""
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

import sys
from pathlib import Path

print(f'Running using {sys.executable}') # validate that we are running in correct environment

docs_path = Path(__file__)
package_path = docs_path.parents[1].as_posix()
# print('package_path ', package_path)
sys.path.insert(0, package_path)
# print(sys.path)

sphinx = True # used for conditional doc strings (direct HTML vs. rst)

project = 'ESIBD Explorer'
project_copyright = '2025, Tim Esser'
author = 'Tim Esser'
release = '0.7'

# uncomment following to generate log while compiling
# import logging
# logging.basicConfig(level=logging.DEBUG, filename="sphinx_debug.log", filemode="w")
# logger = logging.getLogger()

# def on_import(app, what, name, obj, options, lines):
#     logger.debug(f"Processing: what={what}, name={name}")

# def setup(app):
#     app.connect("autodoc-process-docstring", on_import)

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = ['sphinx_rtd_theme', 'sphinx.ext.coverage', 'sphinxcontrib.bibtex', 'sphinx_search.extension',
# 'autoapi.extension',
# "sphinx_rtd_dark_mode", not supported for python 3.11
'sphinx_copybutton',
'sphinx.ext.autodoc',
'sphinxcontrib.video'
]

bibtex_reference_style = 'super'
bibtex_bibfiles = ['ESIBD.bib']
templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']
numfig = True

autodoc_mock_imports = ["PyQt6","pyqtgraph","PyQt5","PySide2","matplotlib","serial","mpl_toolkits","pywin32","picosdk",
                        "picosdk.usbPT104","picosdk.functions","pfeiffer_vacuum_protocol","nidaqmx","pyvisa","lakeshore"]

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'sphinx_rtd_theme'

# html_theme_options = {
#     # "collapse_navigation": False,  # Keep the sidebar expanded by default
#     "navigation_depth": 4,         # Allows up to 4 levels of TOC
#     # "titles_only": False           # Display section titles as links
# }

#html_static_path = ['_static']
html_logo = 'ESIBD_Explorer.png'
html_theme_options = {
    'prev_next_buttons_location': 'both',
    'collapse_navigation': False
    }

# def setup(app):
#     app.add_css_file("custom.css")

rst_prolog = """
.. raw:: html

   <style> .yellow {color:yellow} </style>
   <style> .red {color:#c00000} </style>
   <style> .green {color:#70ad47} </style>
   <style> .blue {color:#00b0f0} </style>
   <style> .darkblue {color:#0070c0} </style>
   <style> .orange {color:#ffc000} </style>
   <style> .darkorange {color:#ed7d31} </style>
   <style> .purple {color:#b381d9} </style>

.. role:: red
.. role:: green
.. role:: blue
.. role:: darkblue
.. role:: orange
.. role:: darkorange
.. role:: purple
"""
