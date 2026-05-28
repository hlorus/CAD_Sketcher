# pyright: reportInvalidTypeForm=false
import json

import bpy
from bpy.props import EnumProperty, IntProperty, StringProperty
from bpy.types import Operator
from bpy.utils import register_classes_factory

from ..declarations import Operators
from ..utilities.ifc_param_schema import (
    get_ifc_type_display_rows,
    get_ifc_type_items,
    get_primary_type_field,
)
from ..utilities.tpg import (
    tpg_entry_get,
    tpg_entry_upsert,
    tpg_param_decode,
    tpg_param_encode,
)

_OWNER_ITEMS = (
    ("SKETCH", "Sketch", "Edit parameters stored on a sketch tag"),
    ("GROUP", "Group", "Edit parameters stored on a group tag"),
    ("MEMBER", "Member", "Edit parameters stored on a group member tag"),
)

_TYPE_NONE = "__NONE__"


def _type_items(self, _context):
    field = get_primary_type_field(self.tag_value)
    items = [(_TYPE_NONE, "None", "Clear the selected IFC type reference")]
    if field is None:
        return items

    ifc_class = field.get("ifc_class", "")
    try:
        new_items = get_ifc_type_items(ifc_class)
    except Exception as exc:
        print(f"[CAD_Sketcher] _type_items failed for {ifc_class!r}: {exc}")
        new_items = []
    items.extend(new_items)

    # Avoid recursively re-entering this callback by reading the raw RNA value.
    current_type_guid = self.get("type_guid", _TYPE_NONE)
    if not isinstance(current_type_guid, str):
        current_type_guid = _TYPE_NONE
    if current_type_guid != _TYPE_NONE and not any(
        item[0] == current_type_guid for item in items
    ):
        items.append(
            (
                current_type_guid,
                f"Missing: {current_type_guid}",
                "Value not found in current IFC file",
            )
        )
    return items


class View3D_OT_slvs_edit_tag_parameters(Operator):
    """Edit the parameter payload for one TAG entry"""

    bl_idname = Operators.EditTagParameters
    bl_label = "Edit TAG Parameters"
    bl_options = {"UNDO"}

    owner_kind: EnumProperty(name="Owner", items=_OWNER_ITEMS, options={"SKIP_SAVE"})
    sketch_index: IntProperty(default=-1, options={"SKIP_SAVE"})
    group_index: IntProperty(default=-1, options={"SKIP_SAVE"})
    member_index: IntProperty(default=-1, options={"SKIP_SAVE"})
    tag_index: IntProperty(default=-1, options={"SKIP_SAVE"})
    tag_value: StringProperty(name="Tag", default="", options={"SKIP_SAVE"})

    type_guid: EnumProperty(name="Type", items=_type_items)
    params_json: StringProperty(name="Additional Parameters", default="")

    def _resolve_sketch(self, context):
        scene = context.scene
        sse = scene.sketcher.entities

        if self.sketch_index >= 0:
            sketch = sse.get(self.sketch_index)
            if sketch is not None and hasattr(sketch, "groups"):
                return sketch

        return scene.sketcher.active_sketch

    def _resolve_group(self, context):
        sketch = self._resolve_sketch(context)
        if sketch is None:
            return None

        groups = getattr(sketch, "groups", ())
        if not groups:
            return None

        if 0 <= self.group_index < len(groups):
            return groups[self.group_index]

        active_index = getattr(sketch, "active_group_index", -1)
        if 0 <= active_index < len(groups):
            return groups[active_index]

        return groups[0]

    def _resolve_owner(self, context):
        if self.owner_kind == "SKETCH":
            sketch = self._resolve_sketch(context)
            if sketch is None:
                return None, None, None
            return sketch, getattr(sketch, "guid", ""), "guid"

        group = self._resolve_group(context)
        if group is None:
            return None, None, None

        if self.owner_kind == "GROUP":
            return group, group.guid, "guid"

        if self.owner_kind == "MEMBER":
            members = group.members
            if not members:
                return None, None, None

            if 0 <= self.member_index < len(members):
                member = members[self.member_index]
                return member, member.guid, "guid"

            active_member_index = getattr(group, "active_member_index", -1)
            if 0 <= active_member_index < len(members):
                member = members[active_member_index]
                return member, member.guid, "guid"

            member = members[0]
            return member, member.guid, "guid"

        return None, None, None

    def _resolve_tag_value(self, context):
        if self.tag_value:
            return self.tag_value.strip()

        if self.owner_kind == "SKETCH":
            sketch = self._resolve_sketch(context)
            tags = getattr(sketch, "tags", []) if sketch is not None else []
        else:
            group = self._resolve_group(context)
            tags = getattr(group, "tags", []) if group is not None else []

        if not tags:
            return ""

        tag_index = self.tag_index
        if not (0 <= tag_index < len(tags)):
            active_tag_index = getattr(
                (
                    self._resolve_group(context)
                    if self.owner_kind != "SKETCH"
                    else self._resolve_sketch(context)
                ),
                "active_tag_index",
                -1,
            )
            if 0 <= active_tag_index < len(tags):
                tag_index = active_tag_index
            else:
                enabled_index = next(
                    (i for i, tag in enumerate(tags) if getattr(tag, "enabled", True)),
                    0,
                )
                tag_index = enabled_index

        if 0 <= tag_index < len(tags):
            return (tags[tag_index].value or "").strip()
        return ""

    def _load_state_from_owner(self, context):
        tag_value = self._resolve_tag_value(context)
        owner, raw_value, _attr = self._resolve_owner(context)
        if owner is None or not tag_value:
            return False

        self.tag_value = tag_value
        entry = tpg_entry_get(raw_value, tag_value) or {"p": "", "g": ""}
        params = tpg_param_decode(entry.get("p", ""))

        type_field = get_primary_type_field(tag_value)
        if type_field is not None:
            requested = str(params.pop(type_field["key"], "") or _TYPE_NONE)
            try:
                self.type_guid = requested
            except Exception:
                self.type_guid = _TYPE_NONE
                print(
                    f"[CAD_Sketcher] Invalid type enum value {requested!r} for tag {tag_value!r}, reset to None"
                )
        else:
            self.type_guid = _TYPE_NONE

        raw_params = entry.get("p", "") or ""
        self.params_json = (
            tpg_param_encode(params) if params else (raw_params if not params else "")
        )
        if self.params_json == "{}":
            self.params_json = ""
        return True

    def invoke(self, context, _event):
        if not self._load_state_from_owner(context):
            self.report({"ERROR"}, "Unable to resolve TAG parameter owner or tag")
            return {"CANCELLED"}
        return context.window_manager.invoke_props_dialog(self, width=460)

    def draw(self, context):
        layout = self.layout
        layout.label(text=f"TAG: {self.tag_value or '—'}")

        field = get_primary_type_field(self.tag_value)
        if field is not None:
            layout.prop(self, "type_guid", text=field["key"])
        else:
            print(f"[CAD_Sketcher] No schema fields for tag {self.tag_value!r}")

        layout.prop(self, "params_json", text="Additional Parameters")

        summary = get_ifc_type_display_rows(
            self.tag_value,
            "" if self.type_guid == _TYPE_NONE else self.type_guid,
        )
        if summary:
            box = layout.box()
            box.label(text="Selected IFC Data")
            for label, value in summary:
                row = box.row()
                row.label(text=label)
                row.label(text=value)

    def execute(self, context):
        owner, raw_value, attr_name = self._resolve_owner(context)
        tag_value = self._resolve_tag_value(context)
        if owner is None or attr_name is None or not tag_value:
            return {"CANCELLED"}

        params_text = (getattr(self, "params_json", "") or "").strip()
        params = {}
        if params_text:
            try:
                decoded = json.loads(params_text)
            except Exception as exc:
                self.report({"ERROR"}, f"Parameters must be valid JSON object: {exc}")
                return {"CANCELLED"}
            if not isinstance(decoded, dict):
                self.report({"ERROR"}, "Parameters must be a JSON object")
                return {"CANCELLED"}
            params = decoded

        field = get_primary_type_field(tag_value)
        current_type_guid = getattr(self, "type_guid", _TYPE_NONE)
        if field is not None:
            if current_type_guid != _TYPE_NONE:
                params[field["key"]] = current_type_guid
            else:
                params.pop(field["key"], None)

        entry = tpg_entry_get(raw_value, tag_value) or {"g": ""}
        updated = tpg_entry_upsert(
            raw_value,
            tag_value,
            param=tpg_param_encode(params),
            guid=entry.get("g", ""),
        )
        setattr(owner, attr_name, updated)
        return {"FINISHED"}


register, unregister = register_classes_factory((View3D_OT_slvs_edit_tag_parameters,))
