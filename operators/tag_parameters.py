# pyright: reportInvalidTypeForm=false
import json

import bpy
from bpy.props import EnumProperty, IntProperty, StringProperty
from bpy.types import Operator
from bpy.utils import register_classes_factory

from ..declarations import Operators
from ..utilities.ifc_param_schema import (
    get_ifc_display_rows,
    get_ifc_type_items,
    get_member_param_schema,
    get_primary_type_field,
)
from ..utilities.tpg import (
    tpg_entry_get,
    tpg_entry_upsert,
    tpg_param_decode,
    tpg_param_encode,
)
from ..utilities.reference_geometry import refresh_reference_geometry

_OWNER_ITEMS = (
    ("SKETCH", "Sketch", "Edit parameters stored on a sketch tag"),
    ("GROUP", "Group", "Edit parameters stored on a group tag"),
    ("MEMBER", "Member", "Edit parameters stored on a group member tag"),
)

_TYPE_NONE = "__NONE__"
_ENUM_NONE = "__NONE__"


def _resolve_ifc_entity_by_identifier(ifc_file, identifier: str):
    identifier = (identifier or "").strip()
    if not identifier or ifc_file is None:
        return None

    try:
        return ifc_file.by_guid(identifier)
    except Exception:
        pass

    if identifier.isdigit():
        try:
            return ifc_file.by_id(int(identifier))
        except Exception:
            return None

    return None


def _infer_member_offset_from_guid(guid: str) -> str:
    guid = (guid or "").strip()
    if not guid:
        return _ENUM_NONE

    try:
        import bonsai.tool as bonsai_tool  # pyright: ignore[reportMissingImports]
        import ifcopenshell.util.element as ifc_element  # pyright: ignore[reportMissingImports]
    except ImportError:
        return _ENUM_NONE

    ifc_file = bonsai_tool.Ifc.get()
    element = _resolve_ifc_entity_by_identifier(ifc_file, guid)
    if element is None:
        return _ENUM_NONE

    try:
        material = ifc_element.get_material(element, should_skip_usage=False)
    except Exception:
        return _ENUM_NONE

    if material is None or not material.is_a("IfcMaterialLayerSetUsage"):
        return _ENUM_NONE

    layer_set = getattr(material, "ForLayerSet", None)
    if layer_set is None:
        return _ENUM_NONE

    thickness = getattr(layer_set, "TotalThickness", None)
    if thickness is None:
        try:
            thickness = sum(
                (getattr(layer, "LayerThickness", 0.0) or 0.0)
                for layer in getattr(layer_set, "MaterialLayers", ())
            )
        except Exception:
            thickness = None
    if thickness is None:
        return _ENUM_NONE

    direction = str(getattr(material, "DirectionSense", "POSITIVE") or "POSITIVE")
    offset = float(getattr(material, "OffsetFromReferenceLine", 0.0) or 0.0)
    thickness = float(thickness)

    if direction == "POSITIVE":
        candidates = {
            "CENTER": -thickness / 2,
            "INTERIOR": -thickness,
            "EXTERIOR": 0.0,
        }
    else:
        candidates = {
            "CENTER": thickness / 2,
            "INTERIOR": 0.0,
            "EXTERIOR": thickness,
        }

    return min(candidates.items(), key=lambda item: abs(offset - item[1]))[0]


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


def _member_offset_items(self, context):
    if self.owner_kind != "MEMBER" or self.tag_value != "IfcWall":
        return [(_ENUM_NONE, "None", "No offset override")]

    scene = getattr(context, "scene", None)
    model_props = getattr(scene, "BIMModelProperties", None)
    if model_props is None:
        return [(_ENUM_NONE, "None", "No offset override")]

    try:
        enum_items = model_props.bl_rna.properties["offset_type_vertical"].enum_items
    except Exception:
        return [(_ENUM_NONE, "None", "No offset override")]

    items = [(_ENUM_NONE, "None", "No offset override")]
    for item in enum_items:
        items.append((item.identifier, item.name, item.description))

    current_value = self.get("member_offset_type_vertical", _ENUM_NONE)
    if (
        isinstance(current_value, str)
        and current_value != _ENUM_NONE
        and not any(item[0] == current_value for item in items)
    ):
        items.append(
            (
                current_value,
                f"Missing: {current_value}",
                "Value not found in current scene enum",
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
    member_offset_type_vertical: EnumProperty(
        name="Offset",
        items=_member_offset_items,
        options={"SKIP_SAVE"},
    )
    params_json: StringProperty(name="Additional Parameters", default="")

    def _get_entry(self, context):
        tag_value = self._resolve_tag_value(context)
        _owner, raw_value, _attr = self._resolve_owner(context)
        if not tag_value:
            return None
        return tpg_entry_get(raw_value, tag_value) or {"p": "", "g": ""}

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
        if self.owner_kind == "MEMBER" and type_field is not None:
            params.pop(type_field["key"], None)
            self.type_guid = _TYPE_NONE
        elif type_field is not None:
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

        member_fields = (
            get_member_param_schema(tag_value) if self.owner_kind == "MEMBER" else []
        )
        member_offset = _ENUM_NONE
        for field in member_fields:
            if field.get("key") != "offset_type_vertical":
                continue
            requested = str(params.pop(field["key"], "") or _ENUM_NONE)
            if requested == _ENUM_NONE:
                requested = _infer_member_offset_from_guid(entry.get("g", ""))
            try:
                self.member_offset_type_vertical = requested
                member_offset = requested
            except Exception:
                self.member_offset_type_vertical = _ENUM_NONE
                member_offset = _ENUM_NONE
        if not member_fields:
            self.member_offset_type_vertical = _ENUM_NONE

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
        if self.owner_kind != "MEMBER" and field is not None:
            layout.prop(self, "type_guid", text=field["key"])
        else:
            if self.owner_kind != "MEMBER":
                print(f"[CAD_Sketcher] No schema fields for tag {self.tag_value!r}")

        for field in get_member_param_schema(self.tag_value):
            if self.owner_kind != "MEMBER":
                continue
            if field.get("key") == "offset_type_vertical":
                layout.prop(
                    self,
                    "member_offset_type_vertical",
                    text=field.get("label", "Offset"),
                )

        layout.prop(self, "params_json", text="Additional Parameters")

        entry = self._get_entry(context) or {"g": ""}
        summary = get_ifc_display_rows(
            self.tag_value,
            self.owner_kind,
            type_guid="" if self.type_guid == _TYPE_NONE else self.type_guid,
            instance_guid=entry.get("g", ""),
            context=context,
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
        if self.owner_kind == "MEMBER" and field is not None:
            params.pop(field["key"], None)
        elif field is not None:
            if current_type_guid != _TYPE_NONE:
                params[field["key"]] = current_type_guid
            else:
                params.pop(field["key"], None)

        if self.owner_kind == "MEMBER":
            for member_field in get_member_param_schema(tag_value):
                if member_field.get("key") != "offset_type_vertical":
                    continue
                current_value = getattr(self, "member_offset_type_vertical", _ENUM_NONE)
                if current_value and current_value != _ENUM_NONE:
                    params[member_field["key"]] = current_value
                else:
                    params.pop(member_field["key"], None)

        entry = tpg_entry_get(raw_value, tag_value) or {"g": ""}
        updated = tpg_entry_upsert(
            raw_value,
            tag_value,
            param=tpg_param_encode(params),
            guid=entry.get("g", ""),
        )
        setattr(owner, attr_name, updated)
        sketch = self._resolve_sketch(context)
        print(
            "[CAD_Sketcher] tag_parameters: refresh_reference_geometry "
            f"owner={self.owner_kind} tag={tag_value} "
            f"sketch_i={getattr(sketch, 'slvs_index', -1)}"
        )
        refs_changed = refresh_reference_geometry(context, sketch=sketch)
        print(
            "[CAD_Sketcher] tag_parameters: refresh_reference_geometry done "
            f"changed={refs_changed}"
        )
        return {"FINISHED"}


register, unregister = register_classes_factory((View3D_OT_slvs_edit_tag_parameters,))
