"""Copy a whole part."""

import bpy
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
        # Bound to Shift+D as well as the panel button. A failing poll does not
        # consume the key, so anything that is not a part still gets Blender's
        # own duplicate. The preference is checked in invoke instead: gating the
        # poll on it would grey the button out too.
        return any(part_root_of(obj) is not None for obj in context.selected_objects)

    def execute(self, context: Context):
        roots = []
        for obj in context.selected_objects:
            root = part_root_of(obj)
            if root is not None and root not in roots:
                roots.append(root)

        copies = [duplicate_part(context, root) for root in roots]

        # Leave the copies selected, as duplicating anything else would.
        bpy.ops.object.select_all(action="DESELECT")
        for copy in copies:
            copy.select_set(True)
        if copies:
            context.view_layer.objects.active = copies[0]

        self.report({"INFO"}, f"Copied {len(copies)} part(s)")
        return {"FINISHED"}

    def invoke(self, context: Context, event):
        from ..utilities.preferences import get_prefs

        if not get_prefs().part_duplicate_shortcuts:
            # Hand the key back: Blender's own duplicate takes it from here.
            return {"PASS_THROUGH"}

        # Shift+D hands the copy straight to a move, and a part copy landing
        # exactly on its original would otherwise look like nothing happened.
        result = self.execute(context)
        if result != {"FINISHED"}:
            return result
        return bpy.ops.transform.translate("INVOKE_DEFAULT")


register, unregister = register_classes_factory((View3D_OT_slvs_duplicate_part,))
