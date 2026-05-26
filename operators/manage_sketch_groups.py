import bpy
from bpy.props import IntProperty, StringProperty
from bpy.utils import register_classes_factory

from .. import global_data
from ..model.constants import TAG_ITEMS


def _next_group_name(sketch) -> str:
    prefix = "Group("
    used = set()
    for group in sketch.groups:
        name = group.name
        if not (name.startswith(prefix) and name.endswith(")")):
            continue
        number = name[len(prefix) : -1]
        if number.isdigit():
            used.add(int(number))

    i = 0
    while i in used:
        i += 1
    return f"Group({i})"


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
        g.name = _next_group_name(sketch)
        sketch.active_group_index = len(sketch.groups) - 1
        return {"FINISHED"}


class SLVS_OT_RemoveSketchGroup(bpy.types.Operator):
    """Remove a group from the active sketch"""

    bl_idname = "view3d.slvs_remove_sketch_group"
    bl_label = "Remove Group"
    bl_options = {"UNDO"}

    group_index: IntProperty(default=-1)

    @classmethod
    def poll(cls, context):
        sketch = context.scene.sketcher.active_sketch
        return sketch is not None and len(sketch.groups) > 0

    def execute(self, context):
        sketch = context.scene.sketcher.active_sketch
        idx = self.group_index if self.group_index >= 0 else sketch.active_group_index
        if not (0 <= idx < len(sketch.groups)):
            return {"CANCELLED"}
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


class SLVS_OT_SelectGroup(bpy.types.Operator):
    """Toggle selection of all entities in a group"""

    bl_idname = "view3d.slvs_select_group"
    bl_label = "Select Group"
    bl_options = {"UNDO"}

    group_index: IntProperty(default=-1)

    @classmethod
    def poll(cls, context):
        return context.scene.sketcher.active_sketch is not None

    def execute(self, context):
        sketch = context.scene.sketcher.active_sketch
        g_idx = self.group_index
        if not (0 <= g_idx < len(sketch.groups)):
            return {"CANCELLED"}
        group = sketch.groups[g_idx]
        indices = [m.entity_index for m in group.members if m.entity_index != -1]
        all_selected = all(i in global_data.selected for i in indices)
        if all_selected:
            for i in indices:
                if i in global_data.selected:
                    global_data.selected.remove(i)
        else:
            for i in indices:
                if i not in global_data.selected:
                    global_data.selected.append(i)
        global_data.needs_redraw = True
        context.area.tag_redraw()
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
    """Remove a tag from a group"""

    bl_idname = "view3d.slvs_remove_group_tag"
    bl_label = "Remove Tag"
    bl_options = {"UNDO"}

    group_index: IntProperty(default=-1)
    tag_index: IntProperty(default=-1)

    @classmethod
    def poll(cls, context):
        return context.scene.sketcher.active_sketch is not None

    def execute(self, context):
        sketch = context.scene.sketcher.active_sketch
        g_idx = self.group_index
        if not (0 <= g_idx < len(sketch.groups)):
            return {"CANCELLED"}
        group = sketch.groups[g_idx]
        t_idx = self.tag_index if self.tag_index >= 0 else group.active_tag_index
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
        SLVS_OT_SelectGroup,
    )
)
