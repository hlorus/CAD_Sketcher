from ..utilities.register import module_register_factory

modules = [
    "theme",
    "install_op",
    "preferences",
    "whats_new",
]

register, unregister = module_register_factory(__name__, modules)
