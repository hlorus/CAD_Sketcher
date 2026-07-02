from bpy.utils import register_classes_factory
from bpy.types import Operator, Context

from ..declarations import Operators
from ..model.sketch_ref import get_active_sketch


class View3D_OT_slvs_align_workplane_cursor(Operator):
    """Align workplane to the 3D Cursor"""

    bl_idname = Operators.AlignWorkplaneCursor
    bl_label = "Align Workplane to 3D Cursor"
    bl_options = {"UNDO"}

    def execute(self, context: Context):
        sketch = get_active_sketch(context)
        if not sketch:
            return {"CANCELLED"}

        wp_obj = sketch.workplane_object
        if not wp_obj:
            return {"CANCELLED"}

        cursor = context.scene.cursor
        wp_obj.matrix_world = cursor.matrix
        return {"FINISHED"}


register, unregister = register_classes_factory(
    (View3D_OT_slvs_align_workplane_cursor,)
)
