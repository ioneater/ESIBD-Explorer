# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information


import os
import sys
print(f'Running using {sys.executable}') # validate that we are running in correct environment
# sys.path.insert(0, os.path.abspath('..')) # add path to package
# sys.path.insert(0, os.path.abspath('../..')) # add path to package

docs_path = os.path.dirname(os.path.abspath(__file__))
# print('docs_path: ', docs_path)
package_path = os.path.join(docs_path, '..')
# print('package_path: ', package_path)
# print('walk package_path: ', [x for x in os.walk(package_path)])
sys.path.insert(0, package_path)
# print('sys.path: ',sys.path)
import esibd

project = 'ESIBD Explorer'
copyright = '2023, Tim Esser'
author = 'Tim Esser'
release = '0.6'

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = ['sphinx_rtd_theme', 'sphinx.ext.coverage','sphinxcontrib.bibtex','sphinx_search.extension',
# 'autoapi.extension',
'sphinx.ext.autodoc'
]

bibtex_reference_style = 'super'
bibtex_bibfiles = ['ESIBD.bib']
templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']
numfig = True

autodoc_mock_imports = ["PyQt6","pyqtgraph","PyQt5","PySide2","matplotlib"]
# autoapi_dirs = ['../Esibd','../plugins']
# autoapi_add_toctree_entry = False
# autoapi_generate_api_docs = False

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'sphinx_rtd_theme'
#html_static_path = ['_static']
html_logo = 'ESIBD_Explorer.png'
html_theme_options = {
    'prev_next_buttons_location': 'both',
    'collapse_navigation': False
    }


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
