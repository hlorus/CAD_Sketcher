import bpy
from bpy.types import Operator, Context
from bpy.props import StringProperty
from bpy.utils import register_classes_factory

from ..declarations import Operators
from ..model.sketch_ref import get_active_sketch, is_sketch_object
from .utilities import activate_sketch


class View3D_OT_slvs_delete_sketch(Operator):
    """Delete a sketch by removing its Curves object"""

    bl_idname = Operators.DeleteSketch
    bl_label = "Delete Sketch"
    bl_options = {"UNDO"}

    sketch_name: StringProperty(name="Sketch Name", default="")

    def execute(self, context: Context):
        ob = bpy.data.objects.get(self.sketch_name)
        if not ob or not is_sketch_object(ob):
            return {"CANCELLED"}

        # Leave sketch if active
        active = get_active_sketch(context)
        if active and active.target_object == ob:
            activate_sketch(context, None, self)

        # Remove the object (handler cleans up orphan constraints)
        bpy.data.objects.remove(ob)
        return {"FINISHED"}


register, unregister = register_classes_factory((View3D_OT_slvs_delete_sketch,))
