from bpy.types import Operator, Context
from bpy.props import BoolProperty
from bpy.utils import register_classes_factory

from ..declarations import Operators
from ..solver import Solver
from ..converters import update_geometry


class VIEW3D_OT_update(Operator):
    bl_idname = "view3d.slvs_update"
    bl_label = "Update"

    bl_idname = Operators.Update
    bl_label = "Force Update"

    solve: BoolProperty(name="Solve", default=True, description="Solve the sketches before converting the geometry")

    def execute(self, context: Context):
        if self.solve:
            solver = Solver(context, None, all=True)
            solver.solve()

        update_geometry(context.scene, self)
        return {"FINISHED"}


register, unregister = register_classes_factory((
    VIEW3D_OT_update,
))
