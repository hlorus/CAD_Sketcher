bl_info = {
    "name": "CAD Sketcher",
    "author": "hlorus",
    "version": (0, 25, 0),
    "blender": (2, 80, 0),
    "location": "View3D > Toolbar",
    "description": "Parametric, constraint-based geometry sketcher",
    "warning": "Experimental",
    "category": "3D View",
    "doc_url": "https://hlorus.github.io/CAD_Sketcher",
    "tracker_url": "https://github.com/hlorus/CAD_Sketcher/discussions/categories/announcements",
}

import logging

from . import icon_manager, global_data
from .registration import register_base, unregister_base, register_full, unregister_full
from .utilities.install import check_module
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
    register_base()

    update_logger(logger)
    icon_manager.load()

    logger.info("Enabled CAD Sketcher base, version: {}".format(bl_info["version"]))

    # Check Module and register all modules
    try:
        check_module("py_slvs")
        register_full()

        global_data.registered = True
        logger.info("Solvespace available, fully registered modules")
    except ModuleNotFoundError as e:
        global_data.registered = False
        logger.warning(
            "Solvespace module isn't available, only base modules registered\n" + str(e)
        )


def unregister():
    if global_data.registered:
        unregister_full()

    unregister_base()

    cleanse_modules(__package__)
