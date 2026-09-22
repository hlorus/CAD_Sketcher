"""Copy a whole part."""

from bpy.types import Context, Operator
from bpy.utils import register_classes_factory

from ..declarations import Operators
from ..utilities.part import duplicate_part, part_root_of


class View3D_OT_slvs_duplicate_part(Operator):
    """Copy the selected part, with everything that shapes it.

    Blender's own duplicate copies just the objects you selected, so a body
    duplicated on its own arrives without its cutters: a part that looks finished
    and is not. This takes the whole part, as an independent copy. For another
    copy of the *same* part, use Instance Part instead."""

    bl_idname = Operators.DuplicatePart
    bl_label = "Duplicate Part"
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

        copies = [duplicate_part(context, root) for root in roots]
        self.report({"INFO"}, f"Copied {len(copies)} part(s)")
        return {"FINISHED"}


register, unregister = register_classes_factory((View3D_OT_slvs_duplicate_part,))
