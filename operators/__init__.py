from ..utilities.register import module_register_factory
from ..stateful_operator.utilities.register import register_stateops_factory

modules = [
    "select",
    "select_box",
    "context_menu",
    "solver_state",
    "solve",
    "update",
    "tweak",
    "save_offscreen",
    "copy_paste",
    "add_point_3d",
    "add_line_3d",
    "add_workplane",
    "add_sketch",
    "add_point_2d",
    "add_line_2d",
    "add_circle",
    "add_arc",
    "add_rectangle",
    "trim",
    "batch_set",
    "bevel",
    "offset",
    "set_sketch",
    "delete_entity",
    "delete_constraint",
    "constraint_visibility",
    "tweak_constraint",
    "presets",
    "add_distance",
    "add_diameter",
    "add_angle",
    "add_geometric_constraints",
    "align_workplane",
    "align_view",
    "modifiers",
    "move",
    "duplicate",
]


def _register_unregister_extern():
    """Imports and registers externally defined operators"""
    from ..stateful_operator.invoke_op import View3D_OT_invoke_tool
    from ..stateful_operator.test_op import View3D_OT_slvs_test

    classes = (View3D_OT_invoke_tool, View3D_OT_slvs_test)
    return register_stateops_factory(classes)


_register, _unregister = module_register_factory(__name__, modules)
_register_ext, _unregister_ext = _register_unregister_extern()


def register():
    _register()
    _register_ext()


def unregister():
    _unregister_ext()
    _unregister()
