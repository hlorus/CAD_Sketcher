import bpy
from bpy.utils import register_classes_factory
from bpy.props import StringProperty, BoolProperty, IntProperty
from bpy.types import Operator, Context, Event, PropertyGroup

from .. import global_data
from ..utilities.highlighting import HighlightElement
from ..utilities.tpg import tpg_get_guid, tpg_to_map
from ..declarations import Operators


class View3D_OT_slvs_context_menu(Operator, HighlightElement):
    """Show element's settings"""

    bl_idname = Operators.ContextMenu
    bl_label = "Solvespace Context Menu"

    type: StringProperty(name="Type", options={"SKIP_SAVE"})
    index: IntProperty(name="Index", default=-1, options={"SKIP_SAVE"})
    delayed: BoolProperty(default=False)

    @classmethod
    def description(cls, context: Context, properties: PropertyGroup):
        cls.handle_highlight_hover(context, properties)
        if properties.type:
            return properties.type.capitalize()
        return cls.__doc__

    def invoke(self, context: Context, event: Event):
        if not self.delayed:
            return self.execute(context)

        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context: Context, event: Event):
        if event.value == "RELEASE":
            return self.execute(context)
        return {"RUNNING_MODAL"}

    def execute(self, context: Context):
        is_entity = True
        entity_index = None
        constraint_index = None
        element = None

        # Constraints
        if self.properties.is_property_set("type"):
            constraint_index = self.index
            constraints = context.scene.sketcher.constraints
            element = constraints.get_from_type_index(self.type, self.index)
            is_entity = False
        else:
            # Entities
            entity_index = (
                self.index
                if self.properties.is_property_set("index")
                else global_data.hover
            )

            if entity_index != -1:
                element = context.scene.sketcher.entities.get(entity_index)

        def draw_context_menu(self, context: Context):
            col = self.layout.column()
            element.draw_props(col)

        if not element:
            bpy.ops.wm.call_menu(name="VIEW3D_MT_selected_menu")
            return {"FINISHED"}

        context.window_manager.popup_menu(draw_context_menu)
        return {"FINISHED"}


class View3D_OT_slvs_group_tag_context_menu(Operator, HighlightElement):
    """Show selected group tag GUID details"""

    bl_idname = "view3d.slvs_group_tag_context_menu"
    bl_label = "Group Tag Details"

    group_index: IntProperty(name="Group Index", default=-1, options={"SKIP_SAVE"})
    tag_index: IntProperty(name="Tag Index", default=-1, options={"SKIP_SAVE"})
    index: IntProperty(name="Index", default=-1, options={"SKIP_SAVE"})

    @classmethod
    def description(cls, context: Context, properties: PropertyGroup):
        cls.handle_highlight_hover(context, properties)
        return cls.__doc__

    def execute(self, context: Context):
        sketch = context.scene.sketcher.active_sketch
        if sketch is None:
            return {"CANCELLED"}

        if not (0 <= self.group_index < len(sketch.groups)):
            return {"CANCELLED"}
        group = sketch.groups[self.group_index]

        if not (0 <= self.tag_index < len(group.tags)):
            return {"CANCELLED"}
        tag = group.tags[self.tag_index]

        tag_value = (tag.value or "").strip()
        raw_guid = (group.guid or "").strip()
        guid_map = tpg_to_map(raw_guid)
        guid_value = tpg_get_guid(raw_guid, tag_value)

        def draw_context_menu(self, context: Context):
            col = self.layout.column(align=True)
            col.label(text="Group Tag", icon="BOOKMARKS")
            col.separator()
            col.label(text=f"Group: {group.name}")
            col.label(text=f"Tag: {tag_value or '—'}")
            col.label(text=f"GUID: {guid_value or '—'}")

        context.window_manager.popup_menu(draw_context_menu)
        return {"FINISHED"}


class View3D_OT_slvs_group_member_context_menu(Operator, HighlightElement):
    """Show selected group member GUID details"""

    bl_idname = "view3d.slvs_group_member_context_menu"
    bl_label = "Group Member Details"

    group_index: IntProperty(name="Group Index", default=-1, options={"SKIP_SAVE"})
    member_index: IntProperty(name="Member Index", default=-1, options={"SKIP_SAVE"})
    index: IntProperty(name="Index", default=-1, options={"SKIP_SAVE"})

    @classmethod
    def description(cls, context: Context, properties: PropertyGroup):
        cls.handle_highlight_hover(context, properties)
        return cls.__doc__

    def execute(self, context: Context):
        sketch = context.scene.sketcher.active_sketch
        if sketch is None:
            return {"CANCELLED"}

        if not (0 <= self.group_index < len(sketch.groups)):
            return {"CANCELLED"}
        group = sketch.groups[self.group_index]

        if not (0 <= self.member_index < len(group.members)):
            return {"CANCELLED"}
        member = group.members[self.member_index]

        sse = context.scene.sketcher.entities
        entity = sse.get(member.entity_index)
        entity_name = entity.name if entity is not None else "(missing)"

        tags = [t.value for t in group.tags if (t.value or "").strip()]
        raw_guid = (member.guid or "").strip()
        guid_map = tpg_to_map(raw_guid)

        rows = []
        unmapped_guid = ""
        if guid_map:
            # Keep group tag order first, then append any extra map keys.
            for tag_value in tags:
                rows.append((tag_value, guid_map.get(tag_value, "")))
            for key, value in guid_map.items():
                if key not in tags:
                    rows.append((key, value))
        else:
            # Legacy/plain storage has only one string slot (member.guid).
            # For multi-tag groups we cannot safely infer which tag it belongs to.
            if len(tags) == 1:
                rows.append((tags[0], raw_guid))
            elif tags:
                for tag_value in tags:
                    rows.append((tag_value, ""))
                unmapped_guid = raw_guid
            else:
                rows.append(("—", raw_guid))

        def draw_context_menu(self, context: Context):
            col = self.layout.column(align=True)
            col.label(text="Group Member", icon="SNAP_VERTEX")
            col.separator()
            col.label(text=f"Group: {group.name}")
            col.label(text=f"Entity: {entity_name}")
            col.label(text=f"Index: {member.entity_index}")
            if not guid_map and len(tags) > 1:
                col.label(text="Single GUID storage detected", icon="INFO")
                if unmapped_guid:
                    col.label(text=f"Unmapped GUID: {unmapped_guid}")
            col.separator()
            col.label(text="Tag / GUID")
            for tag_value, guid_value in rows:
                col.label(text=f"{tag_value}: {guid_value or '—'}")

        context.window_manager.popup_menu(draw_context_menu)
        return {"FINISHED"}


class View3D_OT_slvs_sketch_context_menu(Operator, HighlightElement):
    """Show selected sketch metadata details"""

    bl_idname = "view3d.slvs_sketch_context_menu"
    bl_label = "Sketch Details"

    sketch_index: IntProperty(name="Sketch Index", default=-1, options={"SKIP_SAVE"})
    index: IntProperty(name="Index", default=-1, options={"SKIP_SAVE"})

    @classmethod
    def description(cls, context: Context, properties: PropertyGroup):
        cls.handle_highlight_hover(context, properties)
        return cls.__doc__

    def execute(self, context: Context):
        sse = context.scene.sketcher.entities
        sketch = sse.get(self.sketch_index)
        if sketch is None:
            return {"CANCELLED"}

        tags = [t.value for t in getattr(sketch, "tags", []) if (t.value or "").strip()]
        raw_guid = (getattr(sketch, "guid", "") or "").strip()
        guid_map = tpg_to_map(raw_guid)

        rows = []
        unmapped_guid = ""
        if guid_map:
            for tag_value in tags:
                rows.append((tag_value, guid_map.get(tag_value, "")))
            for key, value in guid_map.items():
                if key not in tags:
                    rows.append((key, value))
        else:
            if len(tags) == 1:
                rows.append((tags[0], raw_guid))
            elif tags:
                for tag_value in tags:
                    rows.append((tag_value, ""))
                unmapped_guid = raw_guid
            else:
                rows.append(("—", raw_guid))

        def draw_context_menu(self, context: Context):
            col = self.layout.column(align=True)
            col.label(text="Sketch", icon="GREASEPENCIL")
            col.separator()
            col.label(text=f"Name: {sketch.name}")
            col.label(text=f"Index: {sketch.slvs_index}")
            if not guid_map and len(tags) > 1:
                col.label(text="Single GUID storage detected", icon="INFO")
                if unmapped_guid:
                    col.label(text=f"Unmapped GUID: {unmapped_guid}")
            col.separator()
            col.label(text="Tag / GUID")
            for tag_value, guid_value in rows:
                col.label(text=f"{tag_value}: {guid_value or '—'}")

        context.window_manager.popup_menu(draw_context_menu)
        return {"FINISHED"}


register, unregister = register_classes_factory(
    (
        View3D_OT_slvs_context_menu,
        View3D_OT_slvs_group_tag_context_menu,
        View3D_OT_slvs_group_member_context_menu,
        View3D_OT_slvs_sketch_context_menu,
    )
)
