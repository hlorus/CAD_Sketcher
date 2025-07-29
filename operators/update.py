import bpy
from bpy.types import Operator
from bpy.utils import register_classes_factory

from ..solver import Solver
from ..converters import update_convertor_geometry


class VIEW3D_OT_update(Operator):
    bl_idname = "view3d.slvs_update"
    bl_label = "Update"

    def execute(self, context):
        update_convertor_geometry()
        solvesys = Solver()
        solvesys.solve()
        return {'FINISHED'}


register, unregister = register_classes_factory((
    VIEW3D_OT_update,
))
