from ..utilities.register import module_register_factory

modules = [
    "point_3d",
    "line_3d",
    "normal_3d",
    "workplane",
    "sketch",
    "point_2d",
    "line_2d",
    "normal_2d",
    "arc",
    "circle",
    "group_entities",
    "distance",
    "angle",
    "diameter",
    "coincident",
    "equal",
    "parallel",
    "horizontal",
    "vertical",
    "tangent",
    "midpoint",
    "perpendicular",
    "ratio",
    # currently disabled because of a bug in the solver module
    # "symmetry",
    "group_constraints",
    "group_sketcher",
]


register, unregister = module_register_factory(__name__, modules)
