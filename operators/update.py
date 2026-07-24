from bpy.types import Operator, Context
from bpy.props import BoolProperty
from bpy.utils import register_classes_factory

from ..declarations import Operators
from ..utilities.curve_data import refresh_curve_geometry


class VIEW3D_OT_update(Operator):
    bl_idname = Operators.Update
    bl_label = "Force Update"

    def execute(self, context: Context):
        from ..model.sketch_ref import get_sketches
        from ..curve_solver import solve_system
        for sketch in get_sketches(context):
            solve_system(context, sketch=sketch)
            refresh_curve_geometry(sketch)
        return {"FINISHED"}


register, unregister = register_classes_factory((
    VIEW3D_OT_update,
))
