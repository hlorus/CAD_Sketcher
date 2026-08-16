"""Create and activate a native free-3D sketch."""

import bpy
from bpy.types import Context, Operator
from bpy.utils import register_classes_factory

from ..declarations import Operators
from ..model.native_3d import create_3d_sketch
from .utilities import activate_sketch


class View3D_OT_slvs_add_sketch3d(Operator):
    """Add a native sketch whose geometry is free in XYZ."""

    bl_idname = Operators.AddSketch3D
    bl_label = "Add 3D Sketch"
    bl_description = "Add a free-3D sketch anchored by an origin Empty"
    bl_options = {"UNDO"}

    @classmethod
    def poll(cls, context: Context):
        return context.scene.sketcher.active_sketch_object is None

    def execute(self, context: Context):
        sketch = create_3d_sketch(context)
        result = activate_sketch(context, sketch.target_object, self)
        if result == {"CANCELLED"}:
            sketch.remove_objects()
            return result
        return {"FINISHED"}


register, unregister = register_classes_factory((View3D_OT_slvs_add_sketch3d,))
