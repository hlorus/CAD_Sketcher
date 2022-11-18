from bpy.utils import register_classes_factory
from bpy.props import IntProperty
from bpy.types import Operator, Context

from ..model.types import SlvsWorkplane
from ..declarations import Operators


class View3D_OT_slvs_align_workplane_cursor(Operator):
    """Align workplane to the 3D Cursor"""

    bl_idname = Operators.AlignWorkplaneCursor
    bl_label = "Align Workplane to 3D Cursor"
    bl_options = {"UNDO"}

    index: IntProperty(default=-1)

    def execute(self, context: Context):
        wp = context.scene.sketcher.entities.get(self.index)
        if not wp or not isinstance(wp, SlvsWorkplane):
            return {"CANCELLED"}

        cursor = context.scene.cursor
        wp.nm.orientation = cursor.matrix.to_quaternion()
        wp.p1.location = cursor.location
        return {"FINISHED"}


register, unregister = register_classes_factory(
    (View3D_OT_slvs_align_workplane_cursor,)
)
