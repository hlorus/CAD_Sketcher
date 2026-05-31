import bpy
from bpy.utils import register_classes_factory
from bpy.props import StringProperty, BoolProperty, IntProperty
from bpy.types import Operator, Context, Event, PropertyGroup

from .. import global_data
from ..utilities.highlighting import HighlightElement
from ..utilities.reference_geometry import (
    reference_entities_for_source,
    reference_source_member_index,
)
from ..utilities.tpg import tpg_decode
from ..declarations import Operators
from ..model.types import SlvsLine2D
from ..solver import solve_system
from ..utilities.view import refresh
from .delete_entity import View3D_OT_slvs_delete_entity


def _rows_from_tpg(tags, raw_value):
    """Build (tag, param, guid) rows for display from structured TPG data."""
    entries, _unused = tpg_decode(raw_value)
    entry_by_tag = {entry["t"]: entry for entry in entries}

    rows = []
    for tag_value in tags:
        entry = entry_by_tag.get(tag_value)
        if entry:
            rows.append((tag_value, entry.get("p", ""), entry.get("g", "")))
        else:
            rows.append((tag_value, "", ""))
    for entry in entries:
        tag_value = entry.get("t", "")
        if tag_value and tag_value not in tags:
            rows.append((tag_value, entry.get("p", ""), entry.get("g", "")))

    return rows, bool(entries)


def _delete_reference_geometry_for_source(
    context: Context, sketch, source_member_i: int, log_prefix: str
):
    sse = context.scene.sketcher.entities
    sketch_index = getattr(sketch, "slvs_index", -1)
    deleted_count = 0

    for pass_i in range(1, 65):
        ref_lines, ref_points = reference_entities_for_source(
            sse,
            sketch_index,
            source_member_i,
        )

        if not ref_lines and not ref_points:
            break

        target_indices = {
            int(entity.slvs_index)
            for entity in (*ref_lines, *ref_points)
            if getattr(entity, "slvs_index", -1) != -1
        }
        if not target_indices:
            break

        progress = False
        for idx in sorted(target_indices, reverse=True):
            entity = sse.get(idx)
            if entity is None:
                continue

            if (
                getattr(entity, "geometry", "") != "REFERENCE"
                or reference_source_member_index(entity) != source_member_i
            ):
                continue

            View3D_OT_slvs_delete_entity.delete(entity, context)
            deleted_count += 1
            progress = True

        if not progress:
            break

    return deleted_count


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

        sketch = context.scene.sketcher.active_sketch
        has_reference_geometry = False
        if is_entity and element is not None and sketch is not None:
            ref_lines, ref_points = reference_entities_for_source(
                context.scene.sketcher.entities,
                getattr(sketch, "slvs_index", -1),
                element.slvs_index,
            )
            has_reference_geometry = bool(ref_lines or ref_points)

        def draw_context_menu(self, context: Context):
            col = self.layout.column()
            element.draw_props(col)
            if has_reference_geometry:
                col.separator()
                op = col.operator(
                    Operators.RemoveEntityReferenceGeometry,
                    text="Remove Reference Geometry",
                    icon="X",
                )
                op.entity_index = element.slvs_index
            if (
                isinstance(element, SlvsLine2D)
                and element.geometry_role(context) == "LINKING"
            ):
                col.separator()
                op = col.operator(
                    Operators.FlipLinkedSketchY,
                    text="Flip Linked Sketch Y",
                    icon="ARROW_LEFTRIGHT",
                )
                op.line_index = element.slvs_index

        if not element:
            bpy.ops.wm.call_menu(name="VIEW3D_MT_selected_menu")
            return {"FINISHED"}

        context.window_manager.popup_menu(draw_context_menu)
        return {"FINISHED"}


class View3D_OT_slvs_remove_group_coincident_constraints(Operator):
    """Remove all coincident constraints touching members of a sketch group"""

    bl_idname = Operators.RemoveGroupCoincidentConstraints
    bl_label = "Remove Coincident Constraints"
    bl_options = {"UNDO"}

    group_index: IntProperty(name="Group Index", default=-1, options={"SKIP_SAVE"})

    def execute(self, context: Context):
        sketch = context.scene.sketcher.active_sketch
        if sketch is None:
            return {"CANCELLED"}

        if not (0 <= self.group_index < len(sketch.groups)):
            return {"CANCELLED"}

        group = sketch.groups[self.group_index]
        member_indices = {
            int(member.entity_index)
            for member in getattr(group, "members", ())
            if getattr(member, "entity_index", -1) != -1
        }
        if not member_indices:
            self.report({"INFO"}, "Group has no members")
            return {"CANCELLED"}

        constraints = context.scene.sketcher.constraints
        coincident_to_remove = []
        for constraint in constraints.coincident:
            if any(
                reference_source_member_index(entity) in member_indices
                for entity in constraint.entities()
            ):
                coincident_to_remove.append(constraint)

        if not coincident_to_remove:
            self.report({"INFO"}, "No coincident constraints found for group members")
            return {"CANCELLED"}

        for constraint in coincident_to_remove:
            constraints.remove(constraint)

        solve_system(context, sketch=sketch)
        refresh(context)
        self.report(
            {"INFO"},
            f"Removed {len(coincident_to_remove)} coincident constraints",
        )
        return {"FINISHED"}


class View3D_OT_slvs_remove_member_reference_geometry(Operator):
    """Remove generated reference geometry for one group member"""

    bl_idname = Operators.RemoveMemberReferenceGeometry
    bl_label = "Remove Reference Geometry"
    bl_options = {"UNDO"}

    group_index: IntProperty(name="Group Index", default=-1, options={"SKIP_SAVE"})
    member_index: IntProperty(name="Member Index", default=-1, options={"SKIP_SAVE"})

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
        source_member_i = int(getattr(member, "entity_index", -1))
        if source_member_i == -1:
            return {"CANCELLED"}

        ref_lines, ref_points = reference_entities_for_source(
            context.scene.sketcher.entities,
            getattr(sketch, "slvs_index", -1),
            source_member_i,
        )

        if not ref_lines and not ref_points:
            self.report({"INFO"}, "No reference geometry found for member")
            return {"CANCELLED"}

        deleted_count = _delete_reference_geometry_for_source(
            context,
            sketch,
            source_member_i,
            "remove_member_reference_geometry",
        )

        solve_system(context, sketch=sketch)
        refresh(context)
        self.report(
            {"INFO"},
            f"Removed {deleted_count} reference entities",
        )
        return {"FINISHED"}


class View3D_OT_slvs_remove_entity_reference_geometry(Operator):
    """Remove generated reference geometry for one source entity"""

    bl_idname = Operators.RemoveEntityReferenceGeometry
    bl_label = "Remove Reference Geometry"
    bl_options = {"UNDO"}

    entity_index: IntProperty(name="Entity Index", default=-1, options={"SKIP_SAVE"})

    def execute(self, context: Context):
        sketch = context.scene.sketcher.active_sketch
        if sketch is None or self.entity_index == -1:
            return {"CANCELLED"}

        ref_lines, ref_points = reference_entities_for_source(
            context.scene.sketcher.entities,
            getattr(sketch, "slvs_index", -1),
            int(self.entity_index),
        )
        if not ref_lines and not ref_points:
            self.report({"INFO"}, "No reference geometry found for entity")
            return {"CANCELLED"}

        deleted_count = _delete_reference_geometry_for_source(
            context,
            sketch,
            int(self.entity_index),
            "remove_entity_reference_geometry",
        )

        solve_system(context, sketch=sketch)
        refresh(context)
        self.report(
            {"INFO"},
            f"Removed {deleted_count} reference entities",
        )
        return {"FINISHED"}


class View3D_OT_slvs_group_context_menu(Operator, HighlightElement):
    """Show selected group tag GUID details"""

    bl_idname = "view3d.slvs_group_context_menu"
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
        group_index = self.group_index

        if not (0 <= self.tag_index < len(group.tags)):

            def draw_no_tags(self, context: Context):
                col = self.layout.column(align=True)
                col.prop(group, "name", text="")
                col.separator()
                col.label(text="No TAGs defined", icon="INFO")
                col.separator()
                op = col.operator(
                    "view3d.slvs_remove_sketch_group",
                    text="Delete Group",
                    icon="X",
                )
                op.group_index = group_index

            context.window_manager.popup_menu(draw_no_tags)
            return {"FINISHED"}

        raw_guid = (group.guid or "").strip()
        group_tags = [t.value for t in group.tags if (t.value or "").strip()]
        rows, _structured = _rows_from_tpg(group_tags, raw_guid)

        def draw_context_menu(self, context: Context):
            col = self.layout.column(align=True)
            col.prop(group, "name", text="")
            col.separator()
            col.label(text="TAG / Parameter / GUID")
            for tag_value, param_value, guid_value in rows:
                col.label(
                    text=f"{tag_value} | {param_value or '—'} | {guid_value or '—'}"
                )
            col.separator()
            op = col.operator(
                Operators.RemoveGroupCoincidentConstraints,
                text="Remove Coincident Constraints",
                icon="X",
            )
            op.group_index = group_index
            col.separator()
            op = col.operator(
                "view3d.slvs_remove_sketch_group",
                text="Delete Group",
                icon="X",
            )
            op.group_index = group_index

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
        rows, _structured = _rows_from_tpg(tags, raw_guid)
        group_index = self.group_index
        member_index = self.member_index

        def draw_context_menu(self, context: Context):
            col = self.layout.column(align=True)
            col.label(text="Group Member", icon="SNAP_VERTEX")
            col.separator()
            col.label(text=f"Group: {group.name}")
            col.label(text=f"Entity: {entity_name}")
            col.label(text=f"Index: {member.entity_index}")
            col.separator()
            op = col.operator(
                Operators.RemoveMemberReferenceGeometry,
                text="Remove Reference Geometry",
                icon="X",
            )
            op.group_index = group_index
            op.member_index = member_index
            col.separator()
            col.label(text="TAG / Parameter / GUID")
            for tag_value, param_value, guid_value in rows:
                row = col.row(align=True)
                row.label(
                    text=f"{tag_value} | {param_value or '—'} | {guid_value or '—'}"
                )
                op = row.operator(
                    Operators.EditTagParameters,
                    text="",
                    icon="PREFERENCES",
                )
                op.owner_kind = "MEMBER"
                op.group_index = group_index
                op.member_index = member_index
                op.tag_value = tag_value

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
        group_tags = group.tags

        if not (0 <= self.tag_index < len(group_tags)):
            return {"CANCELLED"}

        tag_obj = group_tags[self.tag_index]
        tag_value = (tag_obj.value or "").strip()
        all_tag_values = [t.value for t in group_tags if (t.value or "").strip()]
        raw_guid = (group.guid or "").strip()
        rows, _structured = _rows_from_tpg(all_tag_values, raw_guid)
        tag_row = next((r for r in rows if r[0] == tag_value), (tag_value, "", ""))
        tag_val, param_val, guid_val = tag_row
        group_index = self.group_index
        group_tag_index = self.tag_index

        def draw_context_menu(self, context: Context):
            col = self.layout.column(align=True)
            col.prop(tag_obj, "value", text="")
            col.separator()
            col.label(text="TAG / Parameter / GUID")
            col.label(text=f"{tag_val} | {param_val or '—'} | {guid_val or '—'}")
            col.separator()
            op = col.operator(
                Operators.EditTagParameters,
                text="Edit Parameters",
                icon="PREFERENCES",
            )
            op.owner_kind = "GROUP"
            op.group_index = group_index
            op.tag_index = group_tag_index
            col.separator()
            op = col.operator(
                "view3d.slvs_remove_group_tag",
                text="Delete Tag",
                icon="X",
            )
            op.group_index = group_index
            op.tag_index = group_tag_index

        context.window_manager.popup_menu(draw_context_menu)
        return {"FINISHED"}


class View3D_OT_slvs_sketch_tag_context_menu(Operator, HighlightElement):
    """Show selected sketch tag GUID details"""

    bl_idname = "view3d.slvs_sketch_tag_context_menu"
    bl_label = "Sketch Tag Details"

    sketch_index: IntProperty(name="Sketch Index", default=-1, options={"SKIP_SAVE"})
    tag_index: IntProperty(name="Tag Index", default=-1, options={"SKIP_SAVE"})
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

        sketch_index = self.sketch_index
        sketch_tags = getattr(sketch, "tags", [])

        if not (0 <= self.tag_index < len(sketch_tags)):

            def draw_no_tags(self, context: Context):
                col = self.layout.column(align=True)
                col.prop(sketch, "name", text="")
                col.separator()
                col.label(text="No TAGs defined", icon="INFO")

            context.window_manager.popup_menu(draw_no_tags)
            return {"FINISHED"}

        tag_obj = sketch_tags[self.tag_index]
        tag_value = (tag_obj.value or "").strip()
        all_tag_values = [t.value for t in sketch_tags if (t.value or "").strip()]
        raw_guid = (getattr(sketch, "guid", "") or "").strip()
        rows, _structured = _rows_from_tpg(all_tag_values, raw_guid)
        tag_row = next((r for r in rows if r[0] == tag_value), (tag_value, "", ""))
        tag_val, param_val, guid_val = tag_row
        sketch_tag_index = self.tag_index

        def draw_context_menu(self, context: Context):
            col = self.layout.column(align=True)
            col.prop(tag_obj, "value", text="")
            col.separator()
            col.label(text="TAG / Parameter / GUID")
            col.label(text=f"{tag_val} | {param_val or '—'} | {guid_val or '—'}")
            col.separator()
            op = col.operator(
                Operators.EditTagParameters,
                text="Edit Parameters",
                icon="PREFERENCES",
            )
            op.owner_kind = "SKETCH"
            op.sketch_index = sketch_index
            op.tag_index = sketch_tag_index
            col.separator()
            op = col.operator(
                "view3d.slvs_remove_sketch_tag",
                text="Delete Tag",
                icon="X",
            )
            op.tag_index = sketch_tag_index

        context.window_manager.popup_menu(draw_context_menu)
        return {"FINISHED"}


register, unregister = register_classes_factory(
    (
        View3D_OT_slvs_context_menu,
        View3D_OT_slvs_remove_group_coincident_constraints,
        View3D_OT_slvs_remove_entity_reference_geometry,
        View3D_OT_slvs_remove_member_reference_geometry,
        View3D_OT_slvs_group_context_menu,
        View3D_OT_slvs_group_tag_context_menu,
        View3D_OT_slvs_group_member_context_menu,
        View3D_OT_slvs_sketch_tag_context_menu,
    )
)
