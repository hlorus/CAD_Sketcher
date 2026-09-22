"""Place a linked copy of a part."""

from bpy.types import Context, Operator
from bpy.utils import register_classes_factory

from ..declarations import Operators
from ..utilities.part import instance_part, part_root_of


class View3D_OT_slvs_instance_part(Operator):
    """Place another copy of the selected part at the 3D cursor.

    The copy is linked: there is one part, placed in several spots, so editing it
    updates every copy. Edits happen on the part itself; a placement renders the
    part but holds no geometry of its own."""

    bl_idname = Operators.InstancePart
    bl_label = "Instance Part"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: Context):
        return any(part_root_of(obj) is not None for obj in context.selected_objects)

    def execute(self, context: Context):
        roots = []
        for obj in context.selected_objects:
            root = part_root_of(obj)
            if root is not None and root not in roots:
                roots.append(root)

        for root in roots:
            instance_part(context, root)

        self.report({"INFO"}, f"Placed {len(roots)} part copy(s)")
        return {"FINISHED"}


register, unregister = register_classes_factory((View3D_OT_slvs_instance_part,))
