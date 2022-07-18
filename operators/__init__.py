from sys import modules
from ..utilities.register import module_register_factory

modules = [
    "select",
]

register, unregister = module_register_factory(__name__, modules)