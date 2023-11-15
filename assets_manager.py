from pathlib import Path
import logging

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


