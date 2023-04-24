from .utilities.register import module_register_factory

base_modules = [
    "base",
]

core_modules = [
    "handlers",
    "model",
    "operators",
    "gizmos",
    "keymaps",
    "workspacetools",
    "ui",
    "draw_handler",
    # Register this as last module
    "registration_delayed",
]

register_base, unregister_base = module_register_factory(__package__, base_modules)
register_full, unregister_full = module_register_factory(__package__, core_modules)
