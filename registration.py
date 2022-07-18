from .utilities.register import module_register_factory

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

register_base, unregister_base = module_register_factory(__package__, base_modules)
register_full, unregister_full = module_register_factory(__package__, core_modules)


# def register_base():
#     pass

# def unregister_base():
#     pass

# def register_full():
#     pass

# def unregister_full():
#     pass