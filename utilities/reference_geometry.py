import math

from mathutils import Vector

from ..utilities.tpg import tpg_entry_get, tpg_param_decode

_REF_KIND = "IFCWALL_PLAN"
_REF_TAG = "IfcWall"
_REF_ROLE_PLAN = "Plan"
_POINT_ROLES = ("bl", "br", "tr", "tl")
_LINE_ROLES = {
    "bottom": ("bl", "br"),
    "right": ("br", "tr"),
    "top": ("tr", "tl"),
    "left": ("tl", "bl"),
}
_VALID_OFFSETS = {"EXTERIOR", "CENTER", "INTERIOR"}


def _is_plan_sketch(sketch) -> bool:
    if sketch is None:
        return False
    if hasattr(sketch, "tag_values"):
        return _REF_ROLE_PLAN in sketch.tag_values()
    return False


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


def _get_layer_set(material):
    if material is None:
        return None
    if material.is_a("IfcMaterialLayerSet"):
        return material
    if material.is_a("IfcMaterialLayerSetUsage"):
        return getattr(material, "ForLayerSet", None)
    return None


def _get_layer_set_thickness(layer_set):
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
            return None
    return float(thickness)


def _infer_offset_from_layer_usage(material) -> str:
    if material is None or not material.is_a("IfcMaterialLayerSetUsage"):
        return "CENTER"

    layer_set = getattr(material, "ForLayerSet", None)
    thickness = _get_layer_set_thickness(layer_set)
    if thickness is None:
        return "CENTER"

    direction = str(getattr(material, "DirectionSense", "POSITIVE") or "POSITIVE")
    offset = float(getattr(material, "OffsetFromReferenceLine", 0.0) or 0.0)

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


def _resolve_wall_depth_and_offset(context, group, member):
    try:
        import bonsai.tool as bonsai_tool  # pyright: ignore[reportMissingImports]
        import ifcopenshell.util.element as ifc_element  # pyright: ignore[reportMissingImports]
        import ifcopenshell.util.unit  # pyright: ignore[reportMissingImports]
    except ImportError:
        bonsai_tool = None
        ifc_element = None

    ifc_file = bonsai_tool.Ifc.get() if bonsai_tool else None
    unit_scale = (
        ifcopenshell.util.unit.calculate_unit_scale(ifc_file) if ifc_file else 1.0
    )

    # Primary source: resolved wall instance (GUID on member entry)
    member_entry = tpg_entry_get(getattr(member, "guid", ""), _REF_TAG) or {
        "p": "",
        "g": "",
    }
    member_params = tpg_param_decode(member_entry.get("p", ""))
    member_guid = member_entry.get("g", "")
    if ifc_file and ifc_element and member_guid:
        element = _resolve_ifc_entity_by_identifier(ifc_file, member_guid)
        if element is not None:
            try:
                material = ifc_element.get_material(element, should_skip_usage=False)
            except Exception:
                material = None

            layer_set = _get_layer_set(material)
            thickness = _get_layer_set_thickness(layer_set)
            if thickness is not None:
                depth = thickness * unit_scale
                return depth, _infer_offset_from_layer_usage(material)

    # Fallback source: group type depth + member param offset.
    group_entry = tpg_entry_get(getattr(group, "guid", ""), _REF_TAG) or {
        "p": "",
        "g": "",
    }
    group_params = tpg_param_decode(group_entry.get("p", ""))
    type_guid = str(group_params.get("IfcWallType", "") or "").strip()
    depth = None
    if ifc_file and ifc_element and type_guid:
        type_element = _resolve_ifc_entity_by_identifier(ifc_file, type_guid)
        if type_element is not None:
            try:
                type_material = ifc_element.get_material(
                    type_element, should_skip_usage=False
                )
            except Exception:
                type_material = None
            thickness = _get_layer_set_thickness(_get_layer_set(type_material))
            if thickness is not None:
                depth = thickness * unit_scale

    offset = str(
        member_params.get("offset_type_vertical", "CENTER") or "CENTER"
    ).upper()
    if offset not in _VALID_OFFSETS:
        offset = "CENTER"

    return depth, offset


def _member_rectangle_coords(line, depth: float, offset_mode: str):
    p1 = Vector(line.p1.co)
    p2 = Vector(line.p2.co)
    axis = p2 - p1
    if axis.length < 1e-9 or depth is None or depth <= 0:
        return None

    axis.normalize()
    normal = Vector((-axis.y, axis.x))

    if offset_mode == "EXTERIOR":
        n_min, n_max = 0.0, depth
    elif offset_mode == "INTERIOR":
        n_min, n_max = -depth, 0.0
    else:
        n_min, n_max = -depth / 2.0, depth / 2.0

    return {
        "bl": p1 + normal * n_min,
        "br": p2 + normal * n_min,
        "tr": p2 + normal * n_max,
        "tl": p1 + normal * n_max,
    }


def _entity_is_ref(entity, sketch_index: int) -> bool:
    return (
        getattr(entity, "sketch_i", -1) == sketch_index
        and entity.geometry == "REFERENCE"
    )


def _find_ref_point(sse, sketch_index: int, source_member_i: int, role: str):
    for point in sse.points2D:
        if not _entity_is_ref(point, sketch_index):
            continue
        if point.get("ref_source_member_i", -1) != source_member_i:
            continue
        if point.get("ref_role", "") == role:
            return point
    return None


def _find_ref_line(sse, sketch_index: int, source_member_i: int, role: str):
    for line in sse.lines2D:
        if not _entity_is_ref(line, sketch_index):
            continue
        if line.get("ref_source_member_i", -1) != source_member_i:
            continue
        if line.get("ref_role", "") == role:
            return line
    return None


def _mark_ref_entity(entity, source_member_i: int, role: str):
    entity.geometry = "REFERENCE"
    entity["ref_source_member_i"] = int(source_member_i)
    entity["ref_role"] = role
    entity.fixed = True
    entity.construction = True
    entity.visible = True


def is_reference_geometry(entity) -> bool:
    """Return True when *entity* has the REFERENCE geometry role."""
    return entity.geometry == "REFERENCE"


def _delete_ref_entities(context, entities):
    if not entities:
        return

    from ..operators.delete_entity import View3D_OT_slvs_delete_entity

    for entity in entities:
        View3D_OT_slvs_delete_entity.delete(entity, context)


def regenerate_ifc_plan_references(context, sketch=None) -> None:
    scene = getattr(context, "scene", None)
    if scene is None:
        return

    if sketch is None:
        sketch = scene.sketcher.active_sketch
    if sketch is None:
        return

    sse = scene.sketcher.entities
    sketch_index = sketch.slvs_index

    desired = {}
    for group in getattr(sketch, "groups", ()):
        if not any(
            (getattr(t, "enabled", True) and getattr(t, "value", "") == _REF_TAG)
            for t in group.tags
        ):
            continue
        for member in group.members:
            source_i = member.entity_index
            line = sse.get(source_i)
            if line is None or not hasattr(line, "p1") or not hasattr(line, "p2"):
                continue
            if getattr(line, "sketch_i", -1) != sketch_index:
                continue

            if not _is_plan_sketch(sketch):
                continue

            depth, offset_mode = _resolve_wall_depth_and_offset(context, group, member)
            coords = _member_rectangle_coords(line, depth, offset_mode)
            if coords is None:
                continue
            desired[source_i] = coords

    # Clean references for members no longer producing references.
    stale_lines = []
    stale_points = []
    for line in list(sse.lines2D):
        if not _entity_is_ref(line, sketch_index):
            continue
        source_i = line.get("ref_source_member_i", -1)
        if source_i not in desired:
            stale_lines.append(line)
    for point in list(sse.points2D):
        if not _entity_is_ref(point, sketch_index):
            continue
        source_i = point.get("ref_source_member_i", -1)
        if source_i not in desired:
            stale_points.append(point)

    _delete_ref_entities(context, stale_lines)
    _delete_ref_entities(context, stale_points)

    # Upsert references for current members.
    for source_i, coords in desired.items():
        points = {}
        for role in _POINT_ROLES:
            point = _find_ref_point(sse, sketch_index, source_i, role)
            if point is None:
                point = sse.add_point_2d(tuple(coords[role]), sketch)
            else:
                point.co = tuple(coords[role])
            _mark_ref_entity(point, source_i, role)
            points[role] = point

        for line_role, (start_role, end_role) in _LINE_ROLES.items():
            line = _find_ref_line(sse, sketch_index, source_i, line_role)
            p1 = points[start_role]
            p2 = points[end_role]
            if line is None:
                line = sse.add_line_2d(p1, p2, sketch)
            else:
                line.p1 = p1
                line.p2 = p2
            _mark_ref_entity(line, source_i, line_role)


def refresh_reference_geometry(context, sketch=None) -> None:
    try:
        regenerate_ifc_plan_references(context, sketch=sketch)
    except Exception:
        # Never block interactive editing because of reference-preview errors.
        return
