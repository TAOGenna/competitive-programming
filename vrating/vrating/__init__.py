"""vrating -- the rating you'd have if your virtual rounds had counted.

`.env` is read here, before any submodule, because settings like VRATING_DATA are read at
module import time and would otherwise be fixed before the file was ever looked at.
"""
from .config import load_env

load_env()
