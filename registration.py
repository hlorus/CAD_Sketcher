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
    # Register this as last module
    "registration_delayed",
]

register_modules, unregister_modules = module_register_factory(__package__, modules)
