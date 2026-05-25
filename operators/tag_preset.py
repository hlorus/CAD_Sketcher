import bpy
from bpy.props import IntProperty, EnumProperty
from bpy.utils import register_classes_factory

from ..model.constants import TAG_ITEMS, SKETCH_ROLE_ITEMS


class SLVS_OT_TagGroupFromPreset(bpy.types.Operator):
    """Pick an IFC class tag for the active group from a searchable list"""

    bl_idname = "view3d.slvs_tag_group_from_preset"
    bl_label = "Pick Group Tag"
    bl_property = "tag"

    group_index: IntProperty(default=-1)
    tag: EnumProperty(name="Tag", items=TAG_ITEMS)

    @classmethod
    def poll(cls, context):
        return context.scene.sketcher.active_sketch is not None

    def execute(self, context):
        sketch = context.scene.sketcher.active_sketch
        if not (0 <= self.group_index < len(sketch.groups)):
            return {"CANCELLED"}
        sketch.groups[self.group_index].add_tag(self.tag)
        return {"FINISHED"}

    def invoke(self, context, event):
        context.window_manager.invoke_search_popup(self)
        return {"FINISHED"}


class SLVS_OT_SketchRoleFromPreset(bpy.types.Operator):
    """Pick a BIM role for the active sketch tag from a searchable list"""

    bl_idname = "view3d.slvs_sketch_role_from_preset"
    bl_label = "Pick Sketch Role"
    bl_property = "role"

    role: EnumProperty(name="Role", items=SKETCH_ROLE_ITEMS)

    @classmethod
    def poll(cls, context):
        sketch = context.scene.sketcher.active_sketch
        return sketch is not None and 0 <= sketch.active_tag_index < len(sketch.tags)

    def execute(self, context):
        sketch = context.scene.sketcher.active_sketch
        sketch.tags[sketch.active_tag_index].value = self.role
        return {"FINISHED"}

    def invoke(self, context, event):
        context.window_manager.invoke_search_popup(self)
        return {"FINISHED"}


register, unregister = register_classes_factory(
    (SLVS_OT_TagGroupFromPreset, SLVS_OT_SketchRoleFromPreset)
)
