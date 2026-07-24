import logging

import bpy
import addon_utils
from bpy.app import background


# This add-on ships as a Blender extension (Blender 4.3+); blender_manifest.toml
# is the source of truth for name/version/etc. A literal bl_info is only needed
# for legacy (<4.2) add-on installs, which this build doesn't support — for an
# installed extension addon_utils.module_bl_info() is synthesized from the
# manifest, so the version helpers below still resolve correctly.


def get_addon_version_tuple() -> tuple:
    """Return addon version as a tuple e.g. (0, 27, 1)"""

    for mod in addon_utils.modules():
        if mod.__name__ == __package__:
            return addon_utils.module_bl_info(mod).get("version", (0, 0, 0))
    return (0, 0, 0)


def get_addon_version() -> str:
    """Return addon version as string"""

    version = get_addon_version_tuple()
    return ".".join(map(str, version))


def get_min_blender_version() -> tuple:
    """Returns the minimal required blender version from manifest file"""

    for mod in addon_utils.modules():
        if mod.__name__ == __package__:
            return addon_utils.module_bl_info(mod).get("blender", (0, 0, 0))
    return (0, 0, 0)


# Check user's Blender version against minimum required Blender version for add-on.
if bpy.app.version < get_min_blender_version():
    raise Exception(
        "This add-on is only compatible with Blender versions "
        f"{get_min_blender_version()} or greater.\n"
    )

from . import global_data
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
    ensure_addon_presets(force_write=True)
    register_base()

    update_logger(logger)

    if not background:
        from . import icon_manager
        icon_manager.load()

    logger.info("Enabled CAD Sketcher base, version: {}".format(get_addon_version()))

    # Check Module and register all modules
    try:
        check_module("slvs", raise_exception=True)
        register_full()

        global_data.registered = True
        logger.info("Solvespace available, fully registered modules")
    except ModuleNotFoundError as e:
        global_data.registered = False
        logger.warning(
            "Solvespace module isn't available, only base modules registered\n" + str(e)
        )


def unregister():
    if not background:
        from . import icon_manager
        icon_manager.unload()

    if global_data.registered:
        unregister_full()

    unregister_base()

    cleanse_modules(__package__)
