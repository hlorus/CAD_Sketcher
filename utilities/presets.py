import shutil
import sys
import logging
from os import path

import bpy

from .register import get_path

logger = logging.getLogger(__name__)


def ensure_addon_presets(force_write=False):

    scripts_folder = bpy.utils.user_resource("SCRIPTS")
    presets_dir = path.join(scripts_folder, "presets", "bgs")

    is_existing = True
    if not path.isdir(presets_dir):
        is_existing = False

    if force_write or not is_existing:
        bundled_presets = path.join(get_path(), "resources", "presets")

        kwargs = {}
        if sys.version_info >= (3, 8):
            kwargs = {"dirs_exist_ok": True}

        shutil.copytree(bundled_presets, presets_dir, **kwargs)

        logger.info("Copy addon presets to: " + presets_dir)
