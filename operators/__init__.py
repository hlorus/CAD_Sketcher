from sys import modules
from ..utilities.register import module_register_factory

modules = [
    "select",
    "context_menu",
    "solver_state",
    "solve",
    "update",
    "tweak",
    "save_offscreen",
    "add_point_3d",
    "add_line_3d",
    "add_workplane",
    "add_sketch",
    "add_point_2d",
    "add_line_2d",
    "add_circle",
    "add_arc",
    "add_rectangle",
]

register, unregister = module_register_factory(__name__, modules)