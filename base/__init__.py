from ..utilities.register import module_register_factory

modules = [
    "theme",
    "preferences",
    "whats_new",
]

register, unregister = module_register_factory(__name__, modules)
