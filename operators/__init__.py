from sys import modules
from ..utilities.register import module_register_factory

modules = [
    "select",
    "context_menu",
    "solver_state",
]

register, unregister = module_register_factory(__name__, modules)