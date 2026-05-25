import bpy
from bpy.props import IntProperty
from bpy.utils import register_classes_factory

from .. import global_data


class SLVS_OT_AddSketchGroup(bpy.types.Operator):
    """Add a new semantic group to the active sketch"""

    bl_idname = "view3d.slvs_add_sketch_group"
    bl_label = "Add Group"
    bl_options = {"UNDO"}

    @classmethod
    def poll(cls, context):
        return context.scene.sketcher.active_sketch is not None

    def execute(self, context):
        sketch = context.scene.sketcher.active_sketch
        g = sketch.groups.add()
        g.name = "Group"
        sketch.active_group_index = len(sketch.groups) - 1
        return {"FINISHED"}


class SLVS_OT_RemoveSketchGroup(bpy.types.Operator):
    """Remove the active group from the active sketch"""

    bl_idname = "view3d.slvs_remove_sketch_group"
    bl_label = "Remove Group"
    bl_options = {"UNDO"}

    @classmethod
    def poll(cls, context):
        sketch = context.scene.sketcher.active_sketch
        return sketch is not None and 0 <= sketch.active_group_index < len(
            sketch.groups
        )

    def execute(self, context):
        sketch = context.scene.sketcher.active_sketch
        idx = sketch.active_group_index
        sketch.groups.remove(idx)
        sketch.active_group_index = max(0, idx - 1) if sketch.groups else -1
        return {"FINISHED"}


class SLVS_OT_AssignToGroup(bpy.types.Operator):
    """Assign currently selected entities to the group"""

    bl_idname = "view3d.slvs_assign_to_group"
    bl_label = "Assign Selected"
    bl_options = {"UNDO"}

    group_index: IntProperty(default=-1)

    @classmethod
    def poll(cls, context):
        sketch = context.scene.sketcher.active_sketch
        return sketch is not None and bool(global_data.selected)

    def execute(self, context):
        sketch = context.scene.sketcher.active_sketch
        idx = self.group_index
        if not (0 <= idx < len(sketch.groups)):
            return {"CANCELLED"}
        group = sketch.groups[idx]
        added = 0
        for slvs_index in global_data.selected:
            if not group.contains(slvs_index):
                group.add_member(slvs_index)
                added += 1
        return {"FINISHED"} if added else {"CANCELLED"}


class SLVS_OT_UnassignFromGroup(bpy.types.Operator):
    """Remove entity from the group"""

    bl_idname = "view3d.slvs_unassign_from_group"
    bl_label = "Remove Member"
    bl_options = {"UNDO"}

    group_index: IntProperty(default=-1)
    member_index: IntProperty(default=-1)

    def execute(self, context):
        sketch = context.scene.sketcher.active_sketch
        if sketch is None:
            return {"CANCELLED"}
        g_idx, m_idx = self.group_index, self.member_index
        if not (0 <= g_idx < len(sketch.groups)):
            return {"CANCELLED"}
        group = sketch.groups[g_idx]
        if not (0 <= m_idx < len(group.members)):
            return {"CANCELLED"}
        group.remove_member(m_idx)
        if group.active_member_index >= len(group.members):
            group.active_member_index = len(group.members) - 1
        return {"FINISHED"}


register, unregister = register_classes_factory(
    (
        SLVS_OT_AddSketchGroup,
        SLVS_OT_RemoveSketchGroup,
        SLVS_OT_AssignToGroup,
        SLVS_OT_UnassignFromGroup,
    )
)
