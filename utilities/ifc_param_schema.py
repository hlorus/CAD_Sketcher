from __future__ import annotations

PARAM_SCHEMA = {
    "IfcWall": [
        {"key": "IfcWallType", "type": "ifc_type_ref", "ifc_class": "IfcWallType"}
    ],
    "IfcWindow": [
        {
            "key": "IfcWindowType",
            "type": "ifc_type_ref",
            "ifc_class": "IfcWindowType",
        }
    ],
    "IfcDoor": [
        {"key": "IfcDoorType", "type": "ifc_type_ref", "ifc_class": "IfcDoorType"}
    ],
    "IfcColumn": [
        {
            "key": "IfcColumnType",
            "type": "ifc_type_ref",
            "ifc_class": "IfcColumnType",
        }
    ],
    "IfcSlab": [
        {"key": "IfcSlabType", "type": "ifc_type_ref", "ifc_class": "IfcSlabType"}
    ],
    "IfcCovering": [
        {
            "key": "IfcCoveringType",
            "type": "ifc_type_ref",
            "ifc_class": "IfcCoveringType",
        }
    ],
    "IfcPlate": [
        {"key": "IfcPlateType", "type": "ifc_type_ref", "ifc_class": "IfcPlateType"}
    ],
    "IfcBeam": [
        {"key": "IfcBeamType", "type": "ifc_type_ref", "ifc_class": "IfcBeamType"}
    ],
    "IfcMember": [
        {"key": "IfcMemberType", "type": "ifc_type_ref", "ifc_class": "IfcMemberType"}
    ],
    "IfcFooting": [
        {"key": "IfcFootingType", "type": "ifc_type_ref", "ifc_class": "IfcFootingType"}
    ],
    "IfcColumn": [
        {"key": "IfcColumnType", "type": "ifc_type_ref", "ifc_class": "IfcColumnType"}
    ],
    "IfcPile": [
        {"key": "IfcPileType", "type": "ifc_type_ref", "ifc_class": "IfcPileType"}
    ],
}

MEMBER_PARAM_SCHEMA = {
    "IfcWall": [
        {
            "key": "offset_type_vertical",
            "label": "Offset",
            "type": "scene_enum",
            "source": "offset_type_vertical",
        }
    ],
    "IfcSlab": [],
    "IfcCovering": [],
}

DISPLAY_SCHEMA = {
    "GROUP": {
        "IfcWall": [
            {"key": "type_name", "label": "Selected type", "source": "entity_name"},
            {"key": "depth", "label": "Depth", "source": "layer_set_thickness"},
            {"key": "layer_count", "label": "Layers", "source": "layer_count"},
        ],
        "IfcSlab": [
            {"key": "type_name", "label": "Selected type", "source": "entity_name"},
            {"key": "depth", "label": "Depth", "source": "layer_set_thickness"},
            {"key": "layer_count", "label": "Layers", "source": "layer_count"},
        ],
        "IfcCovering": [
            {"key": "type_name", "label": "Selected type", "source": "entity_name"},
            {"key": "depth", "label": "Depth", "source": "layer_set_thickness"},
            {"key": "layer_count", "label": "Layers", "source": "layer_count"},
        ],
    },
    "MEMBER": {
        "IfcWall": [
            {
                "key": "offset_type_vertical",
                "label": "Offset",
                "source": "scene_offset_type_vertical",
                "requires_resolved_entity": True,
            }
        ],
        "IfcSlab": [],
        "IfcCovering": [],
    },
}


def _format_ifc_measure(value: float) -> str:
    return f"{value:.4f}".rstrip("0").rstrip(".")


def get_display_schema(tag_value: str, owner_kind: str = "GROUP") -> list[dict]:
    owner_kind = (owner_kind or "GROUP").strip().upper()
    scope = DISPLAY_SCHEMA.get(owner_kind) or DISPLAY_SCHEMA.get("GROUP", {})
    return list(scope.get((tag_value or "").strip(), ()))


def _resolve_ifc_element(ifc_file, identifier: str):
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


def _get_layer_set(material):
    if material is None:
        return None
    if material.is_a("IfcMaterialLayerSet"):
        return material
    if material.is_a("IfcMaterialLayerSetUsage"):
        return getattr(material, "ForLayerSet", None)
    return None


def _get_material_layer_set(element_type):
    try:
        import ifcopenshell.util.element as ifc_element  # pyright: ignore[reportMissingImports]
    except ImportError:
        return None

    try:
        material = ifc_element.get_material(element_type, should_skip_usage=False)
    except Exception:
        return None

    return _get_layer_set(material)


def _infer_wall_offset_type_vertical(ifc_entity):
    if ifc_entity is None or not ifc_entity.is_a("IfcWall"):
        return None

    try:
        import ifcopenshell.util.element as ifc_element  # pyright: ignore[reportMissingImports]
    except ImportError:
        return None

    try:
        material = ifc_element.get_material(ifc_entity, should_skip_usage=False)
    except Exception:
        return None

    if material is None or not material.is_a("IfcMaterialLayerSetUsage"):
        return None

    layer_set = getattr(material, "ForLayerSet", None)
    if layer_set is None:
        return None

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
        return None

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


def _read_display_value(source: str, ifc_entity, context=None):
    if source == "entity_name":
        return getattr(ifc_entity, "Name", None) or ifc_entity.is_a()

    if source == "scene_offset_type_vertical":
        inferred = _infer_wall_offset_type_vertical(ifc_entity)
        if inferred:
            return inferred

        scene = getattr(context, "scene", None)
        model_props = getattr(scene, "BIMModelProperties", None)
        if model_props is None:
            return None
        value = getattr(model_props, "offset_type_vertical", None)
        if value is None:
            return None
        return str(value)

    layer_set = _get_material_layer_set(ifc_entity)
    if layer_set is None:
        return None

    if source == "layer_set_thickness":
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
            return None
        return _format_ifc_measure(float(thickness))

    if source == "layer_count":
        try:
            layers = getattr(layer_set, "MaterialLayers", ())
            return str(len(layers)) if layers else None
        except Exception:
            return None

    return None


def get_ifc_display_rows(
    tag_value: str,
    owner_kind: str,
    type_guid: str = "",
    instance_guid: str = "",
    context=None,
) -> list[tuple[str, str]]:
    schema = get_display_schema(tag_value, owner_kind)
    if not schema:
        return []

    try:
        import bonsai.tool as bonsai_tool  # pyright: ignore[reportMissingImports]
    except ImportError:
        return []

    ifc_file = bonsai_tool.Ifc.get()
    owner_kind = (owner_kind or "GROUP").strip().upper()
    identifier = instance_guid if owner_kind == "MEMBER" else type_guid
    ifc_entity = _resolve_ifc_element(ifc_file, identifier)
    if ifc_entity is None:
        return []

    rows = []
    for item in schema:
        if item.get("requires_resolved_entity") and not identifier:
            continue
        value = _read_display_value(item.get("source", ""), ifc_entity, context)
        if value is None or value == "":
            continue
        rows.append((item.get("label", item.get("key", "Value")), str(value)))
    return rows


def get_tag_schema(tag_value: str) -> list[dict]:
    return list(PARAM_SCHEMA.get((tag_value or "").strip(), ()))


def get_member_param_schema(tag_value: str) -> list[dict]:
    return list(MEMBER_PARAM_SCHEMA.get((tag_value or "").strip(), ()))


def get_primary_type_field(tag_value: str) -> dict | None:
    for field in get_tag_schema(tag_value):
        if field.get("type") == "ifc_type_ref":
            return field
    return None


def get_ifc_type_items(ifc_class: str) -> list[tuple[str, str, str]]:
    ifc_class = (ifc_class or "").strip()
    if not ifc_class:
        return []

    try:
        import bonsai.tool as bonsai_tool  # pyright: ignore[reportMissingImports]
    except ImportError:
        return []

    ifc_file = bonsai_tool.Ifc.get()
    if ifc_file is None:
        return []

    try:
        elements = ifc_file.by_type(ifc_class)
    except RecursionError as exc:
        print(
            f"[CAD_Sketcher] get_ifc_type_items({ifc_class!r}) recursion error in by_type: {exc}"
        )
        return []
    except Exception as exc:
        print(f"[CAD_Sketcher] get_ifc_type_items({ifc_class!r}) failed: {exc}")
        return []

    items = []
    for element in elements:
        try:
            step_id = element.id()
            try:
                guid = str(element.GlobalId or "").strip()
            except Exception:
                guid = ""
            try:
                label = str(element.Name or "").strip()
            except Exception:
                label = ""
            try:
                predefined = str(element.PredefinedType or "").strip()
            except Exception:
                predefined = ""

            if not label:
                label = guid or f"#{step_id}"
            if predefined and predefined not in {"NOTDEFINED", "USERDEFINED"}:
                label = f"{label} ({predefined})"

            value = guid or str(step_id)
            description = guid or f"STEP #{step_id}"
            items.append((value, label, description))
        except Exception as exc:
            print(
                f"[CAD_Sketcher] get_ifc_type_items: skipping element #{element.id()}: {exc}"
            )
            continue

    items.sort(key=lambda item: item[1].casefold())
    return items
