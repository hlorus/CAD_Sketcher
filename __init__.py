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


import logging

from .utilities.register import cleanse_modules
from .utilities.presets import ensure_addon_presets
from .utilities.logging import setup_logger, update_logger


# Globals
logger = logging.getLogger(__name__)

def register():

    # Setup root logger
    setup_logger(logger)


    # Register base
    ensure_addon_presets()
    theme.register()
    preferences.register()
    install.register()

    update_logger(logger)
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
