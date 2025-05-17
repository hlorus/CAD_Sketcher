import logging

import bpy
import addon_utils
from bpy.app import background
import bpy.app

# Define logger earlier for use in initial import attempts
logger = logging.getLogger(__name__)

bl_info = {
    "name": "CAD Sketcher",
    "author": "hlorus",
    "version": (0, 27, 6),
    "blender": (3, 3, 0),
    "location": "View3D > Toolbar",
    "description": "Parametric, constraint-based geometry sketcher",
    "warning": "Experimental",
    "category": "3D View",
    "doc_url": "https://hlorus.github.io/CAD_Sketcher",
    "tracker_url": "https://github.com/hlorus/CAD_Sketcher/discussions/categories/announcements",
}

# Import conditionally to avoid errors when in background mode
_icon_manager_module_for_init = None
if not background:
    try:
        # Print for immediate console feedback, as logger might not be fully configured.
        print("CAD Sketcher INIT: Attempting to import .icon_manager module.")
        from . import icon_manager as im_actual_module
        _icon_manager_module_for_init = im_actual_module
        # If import succeeds, this will be visible in console.
        print(f"CAD Sketcher INIT: Successfully imported .icon_manager: {_icon_manager_module_for_init}")
        # Use logger as well, it might catch it even if not fully configured.
        logger.info(f"Successfully imported .icon_manager: {_icon_manager_module_for_init}")
    except ImportError as e_imp:
        print(f"CAD Sketcher CRITICAL IMPORT_ERROR: Failed to import .icon_manager: {e_imp}. Icons will be unavailable.")
        logger.error(f"Failed to import .icon_manager due to ImportError: {e_imp}", exc_info=True)
    except Exception as e_gen: # Catch any other exception during the import process
        print(f"CAD Sketcher CRITICAL GENERAL_EXCEPTION: Failed during .icon_manager import: {e_gen}. Icons will be unavailable.")
        logger.error(f"Failed during .icon_manager import due to a general Exception: {e_gen}", exc_info=True)
        # _icon_manager_module_for_init remains None

icon_manager = _icon_manager_module_for_init  # This is what `from .. import icon_manager` will get.


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

# Keep module import for global_data since we modify module variables
from . import global_data
from .registration import register_base, unregister_base, register_full, unregister_full
from .utilities.install import check_module
from .utilities.register import cleanse_modules
from .utilities.presets import ensure_addon_presets
from .utilities.logging import setup_logger, update_logger


# Globals
_load_post_handler_added = False


def initialize_logger_level():
    global _load_post_handler_added
    # Ensure it runs only once and cleans up
    if initialize_logger_level in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(initialize_logger_level)
    _load_post_handler_added = False  # Reset flag after execution or removal
    try:
        update_logger(logger)
        logger.debug("Logger level updated from preferences.")
    except Exception as e:
        logger.error(f"Error updating logger level from preferences: {e}")


def register():
    global _load_post_handler_added
    # Setup root logger
    setup_logger(logger)  # Now logger is fully configured.

    # Register base
    ensure_addon_presets()
    register_base()

    # Load icons using the (hopefully) valid icon_manager module reference
    if not background:
        if icon_manager:  # Check if the module was successfully imported
            try:
                logger.info("Register: icon_manager module appears to be imported. Attempting icon_manager.load().")
                icon_manager.load()  # Call load() on the imported module
                logger.info("Register: icon_manager.load() called successfully.")
            except Exception as e:
                logger.error(f"Error calling icon_manager.load() during register: {e}", exc_info=True)
        else:
            # This log is crucial. If it appears, the import of icon_manager.py failed.
            logger.warning("Register: icon_manager module is None. Skipping icon_manager.load(). This usually means the import of .icon_manager failed earlier.")

    logger.info("Enabled CAD Sketcher base, version: {}".format(get_addon_version()))

    # Check Module and register all modules
    try:
        check_module("py_slvs", raise_exception=True)
        register_full()

        global_data.registered = True
        logger.info("Solvespace available, fully registered modules")
    except ModuleNotFoundError as e:
        global_data.registered = False
        logger.warning(
            "Solvespace module isn't available, only base modules registered\n" + str(e)
        )

    # Add handler to update logger level after Blender loads fully
    if not _load_post_handler_added and initialize_logger_level not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(initialize_logger_level)
        _load_post_handler_added = True


def unregister():
    global _load_post_handler_added
    # Remove the handler if it was added
    if _load_post_handler_added and initialize_logger_level in bpy.app.handlers.load_post:
        try:
            bpy.app.handlers.load_post.remove(initialize_logger_level)
            _load_post_handler_added = False
        except ValueError:
            _load_post_handler_added = False  # Ensure flag is reset
            pass  # Ignore error if handler not found

    if not background:
        if icon_manager:  # Check if the module exists
            try:
                icon_manager.unload()
                logger.info("icon_manager.unload() called successfully.")
            except Exception as e:
                logger.error(f"Error calling icon_manager.unload(): {e}", exc_info=True)

    if global_data.registered:
        unregister_full()

    unregister_base()

    cleanse_modules(__package__)
