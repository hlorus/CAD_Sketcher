from bpy.types import Operator, Context
from bpy.utils import register_classes_factory

from ..declarations import Operators
from ..solver import Solver
from ..converters import update_convertor_geometry


class View3D_OT_update(Operator):
    """Solve all sketches and update converted geometry"""

    bl_idname = Operators.Update
    bl_label = "Force Update"

    def execute(self, context: Context):
        solver = Solver(context, None, all=True)
        solver.solve()

        update_convertor_geometry(context.scene)
        return {"FINISHED"}


register, unregister = register_classes_factory((View3D_OT_update,))
