bl_info = {
    "name": "CAD Sketcher",
    "author": "hlorus",
    "version": (0, 20, 0),
    "blender": (2, 80, 0),
    "location": "View3D > Toolbar",
    "description": "Parametric, constraint-based geometry sketcher",
    "warning": "Experimental",
    "category": "3D View",
    "doc_url": "https://hlorus.github.io/CAD_Sketcher",
    "tracker_url": "https://github.com/hlorus/CAD_Sketcher/issues/new/choose",
}

if "bpy" in locals():
    import importlib

    my_modules = (
        theme,
        preferences,
        functions,
        global_data,
        gizmos,
        operators,
        workspacetools,
        class_defines,
        ui,
        install,
        icon_manager,
    )
    for m in my_modules:
        importlib.reload(m)
else:
    import bpy
    from . import (
        preferences,
        functions,
        global_data,
        gizmos,
        operators,
        workspacetools,
        class_defines,
        ui,
        install,
        theme,
        icon_manager,
    )

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


def ensure_addon_presets(force_write=False):
    import os
    import shutil

    scripts_folder = bpy.utils.user_resource("SCRIPTS")
    presets_dir = os.path.join(scripts_folder, "presets", "bgs")

    is_existing = True
    if not os.path.isdir(presets_dir):
        os.makedirs(presets_dir)
        is_existing = False

    if force_write or not is_existing:
        bundled_presets = os.path.join(os.path.dirname(__file__), "presets")
        files = os.listdir(bundled_presets)

        kwargs = {}
        if sys.version >= (3, 8):
            kwargs = {"dirs_exist_ok": True}

        shutil.copytree(bundled_presets, presets_dir, **kwargs)

        logger.info("Copy addon presets to: " + presets_dir)


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
