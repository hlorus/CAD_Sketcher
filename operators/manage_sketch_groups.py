import bpy
from bpy.props import IntProperty, StringProperty
from bpy.utils import register_classes_factory

from .. import global_data
from ..model.constants import TAG_ITEMS


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


class SLVS_OT_AddGroupTag(bpy.types.Operator):
    """Add an IFC class tag to the active group"""

    bl_idname = "view3d.slvs_add_group_tag"
    bl_label = "Add Tag"
    bl_options = {"UNDO"}

    group_index: IntProperty(default=-1)

    @classmethod
    def poll(cls, context):
        sketch = context.scene.sketcher.active_sketch
        return sketch is not None

    def execute(self, context):
        sketch = context.scene.sketcher.active_sketch
        g_idx = self.group_index
        if not (0 <= g_idx < len(sketch.groups)):
            return {"CANCELLED"}
        group = sketch.groups[g_idx]
        t = group.tags.add()
        t.value = ""
        group.active_tag_index = len(group.tags) - 1
        return {"FINISHED"}


class SLVS_OT_RemoveGroupTag(bpy.types.Operator):
    """Remove the active tag from the active group"""

    bl_idname = "view3d.slvs_remove_group_tag"
    bl_label = "Remove Tag"
    bl_options = {"UNDO"}

    group_index: IntProperty(default=-1)

    @classmethod
    def poll(cls, context):
        sketch = context.scene.sketcher.active_sketch
        if sketch is None:
            return False
        return True

    def execute(self, context):
        sketch = context.scene.sketcher.active_sketch
        g_idx = self.group_index
        if not (0 <= g_idx < len(sketch.groups)):
            return {"CANCELLED"}
        group = sketch.groups[g_idx]
        t_idx = group.active_tag_index
        if not (0 <= t_idx < len(group.tags)):
            return {"CANCELLED"}
        group.remove_tag_by_index(t_idx)
        return {"FINISHED"}


class SLVS_OT_AddSketchTag(bpy.types.Operator):
    """Add a role tag to the active sketch"""

    bl_idname = "view3d.slvs_add_sketch_tag"
    bl_label = "Add Sketch Tag"
    bl_options = {"UNDO"}

    @classmethod
    def poll(cls, context):
        return context.scene.sketcher.active_sketch is not None

    def execute(self, context):
        sketch = context.scene.sketcher.active_sketch
        t = sketch.tags.add()
        t.value = ""
        sketch.active_tag_index = len(sketch.tags) - 1
        return {"FINISHED"}


class SLVS_OT_RemoveSketchTag(bpy.types.Operator):
    """Remove the active role tag from the active sketch"""

    bl_idname = "view3d.slvs_remove_sketch_tag"
    bl_label = "Remove Sketch Tag"
    bl_options = {"UNDO"}

    @classmethod
    def poll(cls, context):
        sketch = context.scene.sketcher.active_sketch
        return sketch is not None and 0 <= sketch.active_tag_index < len(sketch.tags)

    def execute(self, context):
        sketch = context.scene.sketcher.active_sketch
        idx = sketch.active_tag_index
        sketch.remove_tag_by_value(sketch.tags[idx].value)
        sketch.active_tag_index = max(0, idx - 1) if sketch.tags else -1
        return {"FINISHED"}


register, unregister = register_classes_factory(
    (
        SLVS_OT_AddSketchGroup,
        SLVS_OT_RemoveSketchGroup,
        SLVS_OT_AddGroupTag,
        SLVS_OT_RemoveGroupTag,
        SLVS_OT_AddSketchTag,
        SLVS_OT_RemoveSketchTag,
        SLVS_OT_AssignToGroup,
        SLVS_OT_UnassignFromGroup,
    )
)
