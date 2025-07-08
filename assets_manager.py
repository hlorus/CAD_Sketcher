from pathlib import Path
import logging
import glob

import bpy
from .utilities.register import get_path
from .global_data import LIB_NAME

logger = logging.getLogger(__name__)


def _get_lib_by_path(path):
    libraries = bpy.context.preferences.filepaths.asset_libraries
    for lib in libraries:
        if path == lib.path:
            return lib
    return None


def _add_library(name, path):
    bpy.ops.preferences.asset_library_add(directory=path)
    logger.info("Add asset library: " + path)
    lib = _get_lib_by_path(path)
    if not lib:
        logger.error("Could not create asset library: " + path)
        return

    lib.name = name
    return lib


def load():
    asset_path = (Path(get_path()) / "resources").as_posix()
    libraries = bpy.context.preferences.filepaths.asset_libraries

    # Get library by name
    lib = libraries.get(LIB_NAME)

    # Add library
    if not lib:
        lib = _add_library(LIB_NAME, asset_path)

    # Ensure the path is correct
    if lib.path != asset_path:
        lib.path = asset_path


def load_asset(library, asset_type, asset):
    """Loads an asset of given type from a specified library
    Returns True if it is loaded or already present in file"""

    # Check if the asset is already present in file
    if asset in [a.name for a in getattr(bpy.data, asset_type)]:
        return True

    prefs = bpy.context.preferences
    fp = prefs.filepaths.asset_libraries[library].path

    for file in glob.glob(fp + "/*.blend"):
        with bpy.data.libraries.load(file, assets_only=True) as (data_from, data_to):
            coll = getattr(data_from, asset_type)
            if not asset in coll:
                continue
            getattr(data_to, asset_type).append(asset)

        group = getattr(bpy.data, "node_groups").get(asset)
        group.use_fake_user = True

        return True
    return False
