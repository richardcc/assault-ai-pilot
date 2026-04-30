# Configuration file for the Sphinx documentation builder.

import os
import sys
from datetime import datetime

# -- Path setup --------------------------------------------------------------

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(".."))

# -- Project information -----------------------------------------------------

project = "Assault-Env Documentation"
author = "Ricardo David Alba Atencia"
year = datetime.now().year
copyright = f"{year}, {author}"

# -- General configuration ---------------------------------------------------

extensions = [
    # Core Sphinx extensions
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",

    # Diagrams
    "sphinx.ext.graphviz",
]

templates_path = ["_templates"]

# Explicitly exclude non-public or internal documentation
exclude_patterns = [
    "_build",
    "Thumbs.db",
    ".DS_Store",

    # Private / non-public material
    "pdfs",
    "notes_privado",

    # Internal specs and tooling (not published)
    "contracts",
    "rendering",
    "curriculum/collect_rollouts.rst",
    "curriculum/generate_report.rst",
]

language = "en"

# -- Graphviz configuration --------------------------------------------------

# Use SVG for better scaling and clarity
graphviz_output_format = "svg"

# -- Options for HTML output -------------------------------------------------

html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]

# ---------------------------------------------------------------------------
# GitHub Pages configuration (CRITICAL)
# ---------------------------------------------------------------------------

# Base URL where the documentation is published
html_baseurl = "https://richardcc.github.io/assault-ai-pilot/"

# Use directory-style URLs (REQUIRED for GitHub Pages)
html_use_directory_urls = True

# Do NOT split the index; keep stable URLs
html_use_index = True
html_split_index = False