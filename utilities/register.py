import importlib
import os
from traceback import print_exc
from typing import List


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
