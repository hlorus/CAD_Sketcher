import logging

import addon_utils
from bpy.app import background

# This add-on ships as a Blender extension; blender_manifest.toml is the source
# of truth for name/version/blender_version_min. Blender refuses to install the
# extension on unsupported versions, so no runtime version check is needed here.


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


from .registration import register_modules, unregister_modules
from .utilities.logging import setup_logger, update_logger
from .utilities.presets import register_addon_presets, unregister_addon_presets

# Globals
logger = logging.getLogger(__name__)


def register():
    setup_logger(logger)

    register_addon_presets()
    register_modules()

    update_logger(logger)

    if not background:
        from . import icon_manager

        icon_manager.load()

    logger.info("Enabled CAD Sketcher, version: {}".format(get_addon_version()))


def unregister():
    if not background:
        from . import icon_manager

        icon_manager.unload()

    unregister_modules()
    unregister_addon_presets()
