import bpy
from bpy.props import StringProperty
from bpy.types import Context, Operator
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

        # Hand the part on before the root disappears, so its workplanes and
        # their sketches keep their place instead of jumping by the part's
        # transform (Blender drops the parent but keeps the local matrix).
        from ..utilities.part import is_part_root, rehome_children

        if is_part_root(ob):
            rehome_children(ob)

        # The body only exists to realise this sketch.
        from ..utilities.body import remove_body

        remove_body(ob)

        # Remove the object (handler cleans up orphan constraints)
        bpy.data.objects.remove(ob)

        # Drop a part collection the deletion emptied.
        from ..utilities.collections import sync_part_collections

        sync_part_collections(context.scene)
        return {"FINISHED"}


register, unregister = register_classes_factory((View3D_OT_slvs_delete_sketch,))
