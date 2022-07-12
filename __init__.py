bl_info = {
    "name": "CAD Sketcher",
    "author": "hlorus",
    "version": (0, 24, 0),
    "blender": (2, 80, 0),
    "location": "View3D > Toolbar",
    "description": "Parametric, constraint-based geometry sketcher",
    "warning": "Experimental",
    "category": "3D View",
    "doc_url": "https://hlorus.github.io/CAD_Sketcher",
    "tracker_url": "https://github.com/hlorus/CAD_Sketcher/discussions/categories/announcements",
}

import bpy

from . import theme, preferences, install, icon_manager, global_data, functions

from tempfile import gettempdir
from pathlib import Path

import logging

logger = logging.getLogger(__name__)

# Clear handlers
if logger.hasHandlers():
    logger.handlers.clear()

logger.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(name)s:{%(levelname)s}: %(message)s")

stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)

filepath = Path(gettempdir()) / (__name__ + ".log")

logger.info("Logging into: " + str(filepath))
file_handler = logging.FileHandler(filepath, mode="w")
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)



def update_logger():
    prefs = functions.get_prefs()
    logger.setLevel(prefs.logging_level)
from .utilities.register import cleanse_modules
from .utilities.presets import ensure_addon_presets




def register():
    # Register base
    ensure_addon_presets()
    theme.register()
    preferences.register()
    install.register()
    update_logger()
    icon_manager.load()

    logger.info(
        "Enabled CAD Sketcher base, version: {}".format(bl_info["version"])
    )

    # Check Module and register all modules
    try:
        install.check_module()
        logger.info("Solvespace available, fully registered modules")
    except ModuleNotFoundError:
        logger.warning(
            "Solvespace module isn't available, only base modules registered"
        )


def unregister():
    install.unregister()
    preferences.unregister()
    theme.unregister()

    if not global_data.registered:
        return

    install.unregister_full()

    cleanse_modules(__package__)
