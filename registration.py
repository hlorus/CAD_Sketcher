from .utilities.register import module_register_factory

modules = [
    "base",
    "handlers",
    "model",
    "operators",
    "gizmos",
    "keymaps",
    "workspacetools",
    "ui",
    "ui.pie_menu",
    "draw_handler",
]

register_modules, unregister_modules = module_register_factory(__package__, modules)
