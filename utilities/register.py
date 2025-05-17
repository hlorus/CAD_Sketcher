import os
import sys
import importlib
import logging
from typing import List
from traceback import print_exc
from bpy.utils import register_class, unregister_class

logger = logging.getLogger(__name__)


# From: https://github.com/iyadahmed/bpy_helper/blob/main/bpy_helper/register.py
def cleanse_modules(parent_module_name):
    """search for your plugin modules in blender python sys.modules and remove them"""

    for module_name in list(sys.modules.keys()):
        if module_name.startswith(parent_module_name):
            del sys.modules[module_name]


def get_path():
    return os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


def get_name():
    """Return the name of the addon package"""

    return __package__.rsplit(".", maxsplit=1)[0]


# Similar to bpy.utils.register_submodule_factory
def module_register_factory(parent_module_name: str, module_names: List[str]):
    modules = [
        importlib.import_module(f"{parent_module_name}.{name}") for name in module_names
    ]

    def register():
        logger.debug("Registering modules: {}".format(str(modules)))
        for m in modules:
            try:
                if not m:
                    logger.info("Empty module, skipping")
                    continue

                m.register()
            except Exception as e:
                logger.exception(f"Failed to register module: {m.__name__}")

    def unregister():
        logger.debug("Unregistering modules: {}".format(str(modules)))
        for m in reversed(list(modules)):
            if not m:
                logger.info("Empty module, skipping")
                continue

            try:
                m.unregister()
            except Exception as e:
                logger.exception(f"Error unregistering module {m.__name__}: {str(e)}")
                # Continue unregistering other modules even if one fails

    return register, unregister
