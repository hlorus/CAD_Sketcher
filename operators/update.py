from bpy.types import Operator
from bpy.utils import register_classes_factory

from ..solver import solve_system
from ..converters import update_convertor_geometry


class VIEW3D_OT_update(Operator):
    bl_idname = "view3d.slvs_update"
    bl_label = "Update"

    def execute(self, context):
        update_convertor_geometry(context.scene)
        solve_system(context)
        return {'FINISHED'}


register, unregister = register_classes_factory((
    VIEW3D_OT_update,
))
