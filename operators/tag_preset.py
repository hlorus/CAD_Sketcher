import bpy
from bpy.props import IntProperty, EnumProperty
from bpy.utils import register_classes_factory

from ..model.constants import TAG_ITEMS, SKETCH_ROLE_ITEMS


class SLVS_OT_TagFromPreset(bpy.types.Operator):
    """Pick a tag value from a searchable list of common IFC classes"""

    bl_idname = "view3d.slvs_tag_from_preset"
    bl_label = "Pick Tag"
    bl_property = "tag"

    index: IntProperty(default=-1)
    tag: EnumProperty(name="Tag", items=TAG_ITEMS)

    def execute(self, context):
        if self.index < 0:
            return {"CANCELLED"}
        entity = context.scene.sketcher.entities.get(self.index)
        if entity is None:
            return {"CANCELLED"}
        entity.tag = self.tag
        return {"FINISHED"}

    def invoke(self, context, event):
        context.window_manager.invoke_search_popup(self)
        return {"FINISHED"}


class SLVS_OT_SketchRoleFromPreset(bpy.types.Operator):
    """Pick a BIM role for the active sketch from a searchable list"""

    bl_idname = "view3d.slvs_sketch_role_from_preset"
    bl_label = "Pick Sketch Role"
    bl_property = "role"

    role: EnumProperty(name="Role", items=SKETCH_ROLE_ITEMS)

    @classmethod
    def poll(cls, context):
        return context.scene.sketcher.active_sketch is not None

    def execute(self, context):
        context.scene.sketcher.active_sketch.tag = self.role
        return {"FINISHED"}

    def invoke(self, context, event):
        context.window_manager.invoke_search_popup(self)
        return {"FINISHED"}


register, unregister = register_classes_factory(
    (SLVS_OT_TagFromPreset, SLVS_OT_SketchRoleFromPreset)
)
