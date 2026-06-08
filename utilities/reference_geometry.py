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

    # CAD Sketcher is authoritative for member placement mode.
    # IFC is only used to resolve physical depth when available.
    member_entry = tpg_entry_get(getattr(member, "guid", ""), _REF_TAG) or {
        "p": "",
        "g": "",
    }
    member_params = tpg_param_decode(member_entry.get("p", ""))
    member_guid = member_entry.get("g", "")
    offset = str(
        member_params.get("offset_type_vertical", "CENTER") or "CENTER"
    ).upper()
    if offset not in _VALID_OFFSETS:
        offset = "CENTER"

    # Prefer group type from CAD TAG parameters to resolve depth.
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

    # Depth fallback from current IFC instance when no type-based depth is available.
    if depth is None and ifc_file and ifc_element and member_guid:
        element = _resolve_ifc_entity_by_identifier(ifc_file, member_guid)
        if element is not None:
            try:
                material = ifc_element.get_material(element, should_skip_usage=False)
            except Exception:
                material = None
            thickness = _get_layer_set_thickness(_get_layer_set(material))
            if thickness is not None:
                depth = thickness * unit_scale

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


def _anchor_uid(sketch_index: int, group_uid: str, tag_uid: str, tag_member_uid: str) -> str:
    return f"{int(sketch_index)}:{group_uid}:{tag_uid}:{tag_member_uid}"


def _member_anchor_uids(sketch_index: int, group, member, tag_value: str = _REF_TAG) -> set[str]:
    if group is None or member is None:
        return set()

    group.ensure_internal_identity()
    group_uid = str(getattr(group, "internal_uid", "") or "").strip()
    if not group_uid:
        raise ValueError("Group is missing internal UID")

    member.ensure_internal_uid()

    anchors = set()
    for tag in getattr(group, "tags", ()):
        if not getattr(tag, "enabled", True):
            continue
        if tag_value and str(getattr(tag, "value", "") or "") != tag_value:
            continue
        tag_uid = str(getattr(tag, "internal_uid", "") or "").strip()
        if not tag_uid:
            raise ValueError("Group tag is missing internal UID")
        tag_member_uid = member.ensure_tag_member_uid(tag_uid)
        anchors.add(_anchor_uid(sketch_index, group_uid, tag_uid, tag_member_uid))

    return anchors


def _has_ref_entities(sse, sketch_index: int) -> bool:
    for collection_name in ("lines2D", "points2D"):
        for entity in getattr(sse, collection_name, ()):
            if _entity_is_ref(entity, sketch_index):
                return True
    return False


def should_refresh_reference_geometry(scene, sketch=None) -> bool:
    """Return True only when reference geometry could exist or be required."""
    if scene is None:
        return False

    if sketch is None:
        sketch = scene.sketcher.active_sketch
    if sketch is None:
        return False

    sketch_index = getattr(sketch, "slvs_index", -1)
    if sketch_index == -1:
        return False

    sse = scene.sketcher.entities

    # Existing reference entities always require upkeep.
    if _has_ref_entities(sse, sketch_index):
        return True

    # Only Plan sketches with enabled IfcWall group tags can generate references.
    if not _is_plan_sketch(sketch):
        return False

    for group in getattr(sketch, "groups", ()):
        if any(
            getattr(tag, "enabled", True) and getattr(tag, "value", "") == _REF_TAG
            for tag in getattr(group, "tags", ())
        ):
            return True

    return False


def _find_ref_point(
    sse,
    sketch_index: int,
    anchor_uid: str,
    role: str,
):
    target_anchor_uid = str(anchor_uid or "").strip()
    if not target_anchor_uid:
        return None

    # Anchor + role are the only valid identity for reference points.
    for point in sse.points2D:
        if not _entity_is_ref(point, sketch_index):
            continue
        if str(point.get("ref_anchor_uid", "")) != target_anchor_uid:
            continue
        if point.get("ref_role", "") == role:
            return point

    return None


def _find_ref_line(
    sse,
    sketch_index: int,
    anchor_uid: str,
    role: str,
):
    target_anchor_uid = str(anchor_uid or "").strip()
    if not target_anchor_uid:
        return None

    # Anchor + role are the only valid identity for reference lines.
    for line in sse.lines2D:
        if not _entity_is_ref(line, sketch_index):
            continue
        if str(line.get("ref_anchor_uid", "")) != target_anchor_uid:
            continue
        if line.get("ref_role", "") == role:
            return line

    return None


def _mark_ref_entity(entity, anchor: dict, role: str):
    anchor_uid = str(anchor["anchor_uid"])
    group_uid = str(anchor["group_uid"])
    tag_uid = str(anchor["tag_uid"])
    member_uid = str(anchor["member_uid"])
    tag_member_uid = str(anchor["tag_member_uid"])

    entity.geometry = "REFERENCE"
    entity["ref_anchor_uid"] = anchor_uid
    entity["ref_group_uid"] = group_uid
    entity["ref_tag_uid"] = tag_uid
    entity["ref_member_uid"] = member_uid
    entity["ref_tag_member_uid"] = tag_member_uid
    entity["ref_source_entity_index"] = int(anchor["source_entity_index"])
    entity["ref_role"] = role
    entity.fixed = True
    entity.construction = True
    entity.visible = True


def is_reference_geometry(entity) -> bool:
    """Return True when *entity* has the REFERENCE geometry role."""
    return entity.geometry == "REFERENCE"


def all_entities_are_reference(entities) -> bool:
    """Return True when every entity in *entities* is REFERENCE geometry."""
    if not entities:
        return False

    for entity in entities:
        if entity is None or not is_reference_geometry(entity):
            return False

    return True


def reference_source_member_index(entity) -> int:
    """Return the source member index represented by *entity*."""
    if entity is None:
        return -1

    if is_reference_geometry(entity):
        return int(entity.get("ref_source_entity_index", -1))

    return int(getattr(entity, "slvs_index", -1))


def reference_index_by_source(sse, sketch_index: int) -> dict[int, dict[str, list]]:
    """Return source->reference entities index for one sketch.

    Result shape:
        {
            source_index: {
                "lines": [line_entity, ...],
                "points": [point_entity, ...],
            },
            ...
        }
    """
    index: dict[int, dict[str, list]] = {}
    if sse is None or sketch_index == -1:
        return index

    for collection_name, key in (("lines2D", "lines"), ("points2D", "points")):
        for entity in getattr(sse, collection_name, ()):
            if not _entity_is_ref(entity, sketch_index):
                continue
            source_i = int(entity.get("ref_source_entity_index", -1))
            if source_i == -1:
                continue
            entry = index.setdefault(source_i, {"lines": [], "points": []})
            entry[key].append(entity)

    return index


def reference_entities_for_source(sse, sketch_index: int, source_member_i: int):
    """Return (lines, points) reference entities for one source index."""
    entry = reference_index_by_source(sse, sketch_index).get(source_member_i)
    if not entry:
        return [], []
    return entry["lines"], entry["points"]


def reference_entities_for_member(sse, sketch_index: int, group, member):
    anchors = _member_anchor_uids(sketch_index, group, member)
    if not anchors:
        return [], []

    lines = []
    points = []
    for line in getattr(sse, "lines2D", ()):
        if _entity_is_ref(line, sketch_index) and str(line.get("ref_anchor_uid", "")) in anchors:
            lines.append(line)
    for point in getattr(sse, "points2D", ()):
        if _entity_is_ref(point, sketch_index) and str(point.get("ref_anchor_uid", "")) in anchors:
            points.append(point)
    return lines, points


def member_representation_indices(
    sse,
    sketch_index: int,
    source_member_i: int,
    group=None,
    member=None,
) -> set[int]:
    """Return all selectable entity indices that represent one group member."""
    if source_member_i == -1:
        return set()

    indices = {int(source_member_i)}
    if sse is None or sketch_index == -1:
        return indices

    if group is not None and member is not None:
        ref_lines, ref_points = reference_entities_for_member(
            sse,
            sketch_index,
            group,
            member,
        )
        for line in ref_lines:
            indices.add(int(line.slvs_index))
        for point in ref_points:
            indices.add(int(point.slvs_index))
        return indices

    ref_index = reference_index_by_source(sse, sketch_index)
    for entity in ref_index.get(source_member_i, {}).get("lines", ()):
        indices.add(int(entity.slvs_index))
    for entity in ref_index.get(source_member_i, {}).get("points", ()):
        indices.add(int(entity.slvs_index))
    return indices


def member_is_selected(
    sse,
    sketch_index: int,
    source_member_i: int,
    selected_indices,
    group=None,
    member=None,
) -> bool:
    """Return True when any representation of the member is selected."""
    selected = set(selected_indices)
    return any(
        index in selected
        for index in member_representation_indices(
            sse,
            sketch_index,
            source_member_i,
            group=group,
            member=member,
        )
    )


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
    has_enabled_ref_group = False
    for group in getattr(sketch, "groups", ()):
        group.ensure_internal_identity()
        ref_tags = [
            tag
            for tag in getattr(group, "tags", ())
            if getattr(tag, "enabled", True) and getattr(tag, "value", "") == _REF_TAG
        ]
        if not ref_tags:
            continue
        has_enabled_ref_group = True
        for tag in ref_tags:
            group.ensure_member_uids_for_tag(tag)
            tag_uid = str(getattr(tag, "internal_uid", "") or "").strip()
            if not tag_uid:
                raise ValueError("Missing group tag internal UID for reference generation")

            for member in group.members:
                source_i = member.entity_index
                line = sse.get(source_i)
                if line is None or not hasattr(line, "p1") or not hasattr(line, "p2"):
                    continue
                if getattr(line, "sketch_i", -1) != sketch_index:
                    continue

                if not _is_plan_sketch(sketch):
                    continue

                tag_member_uid = member.ensure_tag_member_uid(tag_uid)
                member_uid = member.ensure_internal_uid()
                group_uid = str(getattr(group, "internal_uid", "") or "").strip()
                if not group_uid:
                    raise ValueError("Missing group internal UID for reference generation")
                anchor_uid = (
                    f"{sketch_index}:{group_uid}:{tag_uid}:{tag_member_uid}"
                )

                depth, offset_mode = _resolve_wall_depth_and_offset(context, group, member)
                coords = _member_rectangle_coords(line, depth, offset_mode)
                if coords is None:
                    continue
                desired[anchor_uid] = {
                    "coords": coords,
                    "source_entity_index": int(source_i),
                    "group_uid": group_uid,
                    "tag_uid": tag_uid,
                    "member_uid": member_uid,
                    "tag_member_uid": str(tag_member_uid),
                    "anchor_uid": anchor_uid,
                }

    if not has_enabled_ref_group and not _has_ref_entities(sse, sketch_index):
        return False

    changed = False

    # Upsert references for current anchors and enforce uniqueness locally.
    stale_points = []
    stale_lines = []

    for anchor_uid, anchor in desired.items():
        coords = anchor["coords"]
        points = {}
        for role in _POINT_ROLES:
            point = _find_ref_point(
                sse,
                sketch_index,
                anchor_uid,
                role,
            )
            if point is None:
                point = sse.add_point_2d(tuple(coords[role]), sketch)
                changed = True
            else:
                new_co = tuple(coords[role])
                if tuple(point.co) != new_co:
                    point.co = new_co
                    changed = True
            _mark_ref_entity(point, anchor, role)
            points[role] = point

        for line_role, (start_role, end_role) in _LINE_ROLES.items():
            p1 = points[start_role]
            p2 = points[end_role]
            line = _find_ref_line(
                sse,
                sketch_index,
                anchor_uid,
                line_role,
            )
            if line is None:
                line = sse.add_line_2d(p1, p2, sketch)
                changed = True
            else:
                if line.p1 != p1:
                    line.p1 = p1
                    changed = True
                if line.p2 != p2:
                    line.p2 = p2
                    changed = True
            _mark_ref_entity(line, anchor, line_role)

        # Strict cardinality per anchor: keep exactly one entity per expected role.
        source_points = [
            p
            for p in sse.points2D
            if _entity_is_ref(p, sketch_index)
            and str(p.get("ref_anchor_uid", "")) == anchor_uid
        ]
        source_lines = [
            l
            for l in sse.lines2D
            if _entity_is_ref(l, sketch_index)
            and str(l.get("ref_anchor_uid", "")) == anchor_uid
        ]

        point_keep = {}
        for role in _POINT_ROLES:
            candidates = [p for p in source_points if str(p.get("ref_role", "")) == role]
            if not candidates:
                continue

            target = Vector(coords[role])
            keeper = min(candidates, key=lambda p: (Vector(p.co) - target).length)
            point_keep[role] = keeper

            for candidate in candidates:
                if candidate != keeper:
                    stale_points.append(candidate)

        # Remove points with invalid role labels for this source.
        for point in source_points:
            role = str(point.get("ref_role", ""))
            if role not in _POINT_ROLES:
                stale_points.append(point)

        line_keep = {}
        for role, (start_role, end_role) in _LINE_ROLES.items():
            candidates = [l for l in source_lines if str(l.get("ref_role", "")) == role]
            if not candidates:
                continue

            p1 = point_keep.get(start_role)
            p2 = point_keep.get(end_role)
            if p1 is None or p2 is None:
                keeper = candidates[0]
            else:
                wanted = {int(p1.slvs_index), int(p2.slvs_index)}
                exact = [
                    l
                    for l in candidates
                    if {int(l.p1.slvs_index), int(l.p2.slvs_index)} == wanted
                ]
                keeper = exact[0] if exact else candidates[0]

            line_keep[role] = keeper

            for candidate in candidates:
                if candidate != keeper:
                    stale_lines.append(candidate)

        # Remove lines with invalid role labels for this source.
        for line in source_lines:
            role = str(line.get("ref_role", ""))
            if role not in _LINE_ROLES:
                stale_lines.append(line)

    # Deduplicate stale lists and remove entities in descending index order.
    stale_points = {
        int(point.slvs_index): point
        for point in stale_points
        if point is not None and getattr(point, "slvs_index", -1) != -1
    }
    stale_lines = {
        int(line.slvs_index): line
        for line in stale_lines
        if line is not None and getattr(line, "slvs_index", -1) != -1
    }

    if stale_points or stale_lines:
        changed = True

    _delete_ref_entities(
        context,
        [stale_lines[i] for i in sorted(stale_lines.keys(), reverse=True)],
    )
    _delete_ref_entities(
        context,
        [stale_points[i] for i in sorted(stale_points.keys(), reverse=True)],
    )

    # Post-refresh integrity check: each desired anchor should resolve to one
    # entity per expected role (4 points + 4 lines).
    for anchor_uid in desired:
        source_points = [
            p
            for p in sse.points2D
            if _entity_is_ref(p, sketch_index)
            and str(p.get("ref_anchor_uid", "")) == anchor_uid
        ]
        source_lines = [
            l
            for l in sse.lines2D
            if _entity_is_ref(l, sketch_index)
            and str(l.get("ref_anchor_uid", "")) == anchor_uid
        ]

        point_roles = {
            str(p.get("ref_role", "")) for p in source_points if p.get("ref_role", "")
        }
        line_roles = {
            str(l.get("ref_role", "")) for l in source_lines if l.get("ref_role", "")
        }

        points_ok = point_roles == set(_POINT_ROLES)
        lines_ok = line_roles == set(_LINE_ROLES.keys())
        if not (points_ok and lines_ok):
            print(
                "[CAD_Sketcher] reference_geometry integrity warning: "
                f"anchor_uid={anchor_uid} "
                f"point_roles={sorted(point_roles)} expected={list(_POINT_ROLES)} "
                f"line_roles={sorted(line_roles)} expected={list(_LINE_ROLES.keys())}"
            )

    return changed


def refresh_reference_geometry(context, sketch=None) -> bool:
    try:
        scene = getattr(context, "scene", None) if context is not None else None
        sketcher = getattr(scene, "sketcher", None) if scene is not None else None
        if sketcher is not None and not getattr(sketcher, "geometry_solved", True):
            return False

        changed = bool(regenerate_ifc_plan_references(context, sketch=sketch))
        if changed:
            print(
                "[CAD_Sketcher] refresh_reference_geometry: "
                f"sketch_i={getattr(sketch, 'slvs_index', -1) if sketch else -1} "
                "changed=True"
            )
        return changed
    except Exception as exc:
        # Never block interactive editing because of reference-preview errors.
        print(f"[CAD_Sketcher] refresh_reference_geometry: error: {exc}")
        return False
