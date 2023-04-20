from pathlib import Path
import logging

import bpy
from .utilities.register import get_path

logger = logging.getLogger(__name__)


def load():
    asset_path = (Path(get_path()) / "resources").as_posix()

    if asset_path in [
        lib.path for lib in bpy.context.preferences.filepaths.asset_libraries
    ]:
        return

    bpy.ops.preferences.asset_library_add(directory=asset_path)
    logger.info("Add asset library: " + asset_path)
