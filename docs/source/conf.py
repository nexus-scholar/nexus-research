import os
import sys
sys.path.insert(0, os.path.abspath('../../src'))

project = 'Nexus Research'
copyright = '2026, Nexus Team'
author = 'Nexus Team'
release = '0.1.0'

extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.napoleon',
    'sphinx.ext.viewcode',
    'sphinx.ext.todo',
    'sphinx_rtd_theme',
]

templates_path = ['_templates']
exclude_patterns = []

html_theme = 'sphinx_rtd_theme'
html_static_path = ['_static']

todo_include_todos = True
