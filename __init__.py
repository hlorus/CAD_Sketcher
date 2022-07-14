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

import logging

from .utilities.install import check_module

from . import icon_manager, global_data, base
from . import register_full
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
    base.register()

    update_logger(logger)
    icon_manager.load()

    logger.info(
        "Enabled CAD Sketcher base, version: {}".format(bl_info["version"])
    )

    # Check Module and register all modules
    try:
        check_module("py_slvs")
        register_full.register()

        global_data.registered = True
        logger.info("Solvespace available, fully registered modules")
    except ModuleNotFoundError:
        global_data.registered = False
        logger.warning(
            "Solvespace module isn't available, only base modules registered"
        )


def unregister():
    if global_data.registered:
        register_full.unregister()

    base.unregister()

    cleanse_modules(__package__)
