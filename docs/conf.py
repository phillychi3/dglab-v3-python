import os
import sys

sys.path.insert(0, os.path.abspath(".."))

project = "dglabv3"
author = "phillychi3"
copyright = "2025, phillychi3"
language = "zh_TW"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "myst_parser",
]

source_suffix = {".rst": "restructuredtext", ".md": "markdown"}
exclude_patterns = ["_build"]

myst_enable_extensions = ["colon_fence"]
myst_heading_anchors = 3

autodoc_default_options = {
    "members": True,
    "show-inheritance": True,
    "member-order": "bysource",
}
autodoc_typehints = "description"
autodoc_class_signature = "separated"

html_theme = "furo"
html_title = "dglabv3"
