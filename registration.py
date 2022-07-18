from bpy.utils import register_submodule_factory

base_modules = [
    "base",
]

core_modules = [
    "handlers",
    "class_defines",
    "operators",
    "gizmos",
    "keymaps",
    "workspacetools",
    "ui",
    "draw_handler",
]

register_base, unregister_base = register_submodule_factory(__package__, base_modules)
register_full, unregister_full = register_submodule_factory(__package__, core_modules)

