"""Place a linked copy of a part."""

import bpy
from bpy.props import BoolProperty
from bpy.types import Context, Operator
from bpy.utils import register_classes_factory

from ..declarations import Operators
from ..utilities.part import instance_part, part_root_of, world_matrix_of


class View3D_OT_slvs_instance_part(Operator):
    """Place another copy of the selected part.

    The copy is linked: there is one part, placed in several spots, so editing it
    updates every copy. Edits happen on the part itself; a placement renders the
    part but holds no geometry of its own.

    From the panel it lands at the 3D cursor; on Alt+D it lands on the original
    and is handed to a move, which is what that key does everywhere else."""

    bl_idname = Operators.InstancePart
    bl_label = "Instance Part"
    bl_options = {"REGISTER", "UNDO"}

    at_cursor: BoolProperty(
        name="At Cursor",
        description="Place the copy at the 3D cursor instead of on the original",
        default=True,
        options={"SKIP_SAVE"},
    )

    @classmethod
    def poll(cls, context: Context):
        # See View3D_OT_slvs_duplicate_part.poll: the preference is checked in
        # invoke so that turning the shortcut off does not disable the button.
        return any(part_root_of(obj) is not None for obj in context.selected_objects)

    def execute(self, context: Context):
        roots = []
        for obj in context.selected_objects:
            root = part_root_of(obj)
            if root is not None and root not in roots:
                roots.append(root)

        placements = []
        for root in roots:
            location = None if self.at_cursor else world_matrix_of(root).translation
            placements.append(instance_part(context, root, location))

        # Leave the placements selected, as duplicating anything else would.
        bpy.ops.object.select_all(action="DESELECT")
        for placement in placements:
            placement.select_set(True)
        if placements:
            context.view_layer.objects.active = placements[0]

        self.report({"INFO"}, f"Placed {len(placements)} part copy(s)")
        return {"FINISHED"}

    def invoke(self, context: Context, event):
        from ..utilities.preferences import get_prefs

        if not self.at_cursor and not get_prefs().part_duplicate_shortcuts:
            # Hand the key back: Blender's own linked duplicate takes it.
            return {"PASS_THROUGH"}

        result = self.execute(context)
        if result != {"FINISHED"} or self.at_cursor:
            return result
        return bpy.ops.transform.translate("INVOKE_DEFAULT")


register, unregister = register_classes_factory((View3D_OT_slvs_instance_part,))
