from bpy.utils import register_submodule_factory

packages = [
    "core",
    "handlers",
    "class_defines",
    "operators",
    "gizmos",
    "keymaps",
    "workspacetools",
    "ui",
    "draw_handler",
]

register, unregister = register_submodule_factory(__package__, packages)