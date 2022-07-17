import bpy

import os
import sys

# From: https://github.com/iyadahmed/bpy_helper/blob/main/bpy_helper/register.py
def cleanse_modules(parent_module_name):
    """search for your plugin modules in blender python sys.modules and remove them"""

    for module_name in list(sys.modules.keys()):
        if module_name.startswith(parent_module_name):
            del sys.modules[module_name]



def get_path():
    return os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


def get_name():
    return os.path.basename(get_path())


from typing import List
import importlib
from traceback import print_exc
# Similar to bpy.utils.register_submodule_factory
def module_register_factory(parent_module_name: str, module_names: List[str]):
    modules = [importlib.import_module(f"{parent_module_name}.{name}") for name in module_names]

    def register():
        for m in modules:
            try:
                m.register()
            except Exception:
                print_exc()

    def unregister():
        for m in reversed(modules):
            try:
                m.unregister()
            except Exception:
                print_exc()

    return register, unregister