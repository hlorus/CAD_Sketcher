from ..utilities.register import module_register_factory

modules = [
    "theme",
    "install_op",
    "preferences",
]

register, unregister = module_register_factory(__name__, modules)
