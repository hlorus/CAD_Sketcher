import os
import shutil
import sys
import logging

import bpy

logger = logging.getLogger(__name__)

def ensure_addon_presets(force_write=False):

    scripts_folder = bpy.utils.user_resource("SCRIPTS")
    presets_dir = os.path.join(scripts_folder, "presets", "bgs")

    is_existing = True
    if not os.path.isdir(presets_dir):
        is_existing = False

    if force_write or not is_existing:
        bundled_presets = os.path.join(os.path.dirname(__package__), "ressources", "presets")
        files = os.listdir(bundled_presets)

        kwargs = {}
        if sys.version_info >= (3, 8):
            kwargs = {"dirs_exist_ok": True}

        shutil.copytree(bundled_presets, presets_dir, **kwargs)

        logger.info("Copy addon presets to: " + presets_dir)
