"""User-defined attributes backed directly by native Curves data.

Attribute definitions (name/type/domain/default) live on the sketch Curves
datablock for UI/default metadata. Values themselves live only in native Blender
POINT/CURVE attributes, which are the single source of truth consumed by the
shared conversion path.

OBJECT-domain attributes are intentionally deferred: keeping a mirrored copy on
the Object plus a depsgraph synchronization handler made the implementation much
heavier than the conversion problem requires.
"""

import json

import bpy

from .curve_data import get_curve_index

DEFINITIONS_PROP = "cad_custom_attribute_definitions"

SUPPORTED_TYPES = {"BOOLEAN", "INT", "FLOAT"}
SUPPORTED_DOMAINS = {"POINT", "CURVE"}

_RESERVED_NAMES = {
    "position",
    "cyclic",
    "sketch_type",
    "curve_type",
    "nurbs_weight",
    "nurbs_order",
    "knots_mode",
    "resolution",
    "construction",
    "fixed",
    "visible",
    "merge_id",
    "id",
    "curve_id",
    "start_point_id",
    "end_point_id",
    "center_point_id",
    "name",
}


def _cast(data_type, value):
    if data_type == "BOOLEAN":
        return bool(value)
    if data_type == "INT":
        return int(value)
    if data_type == "FLOAT":
        return float(value)
    raise ValueError(f"Unsupported attribute type: {data_type}")


def _read_defs(curve_data):
    raw = curve_data.get(DEFINITIONS_PROP, "[]")
    if isinstance(raw, bytes):
        raw = raw.decode()
    try:
        defs = json.loads(raw)
    except (TypeError, ValueError):
        defs = []
    return [d for d in defs if isinstance(d, dict) and d.get("name")]


def _write_defs(curve_data, definitions):
    curve_data[DEFINITIONS_PROP] = json.dumps(definitions, separators=(",", ":"))


def _shared_conversion_definitions():
    """Return the union required by the one shared conversion node group.

    Definitions remain per-sketch; the converter only needs the minimal
    name/type/domain triples for attributes that cross lossy topology steps.
    Values are never copied or mirrored here. Orphan Curves datablocks are
    ignored so deleted sketches cannot keep stale schemas in the shared group.
    """
    definitions_by_key = {}
    for curve_data in bpy.data.hair_curves:
        if curve_data.users == 0:
            continue
        for entry in _read_defs(curve_data):
            domain = str(entry.get("domain", "")).upper()
            data_type = str(entry.get("type", "")).upper()
            name = str(entry.get("name", "")).strip()
            if domain not in SUPPORTED_DOMAINS or data_type not in SUPPORTED_TYPES:
                continue
            key = (name, data_type, domain)
            definitions_by_key[key] = {
                "name": name,
                "type": data_type,
                "domain": domain,
            }
    return [definitions_by_key[key] for key in sorted(definitions_by_key)]


def _convert_fill_socket(group):
    """The Fill input socket identifier of a convert group, or None."""
    for item in group.interface.items_tree:
        if (
            getattr(item, "item_type", "") == "SOCKET"
            and getattr(item, "in_out", "") == "INPUT"
            and item.name == "Fill"
        ):
            return item.identifier
    return None


def _sync_shared_conversion_group():
    """Refresh only the small attribute bridge in the shared 5.2+ converter.

    Rebuilding recreates the group's interface, which re-mints socket identifiers.
    Modifier inputs are keyed by identifier, so snapshot every bound convert
    modifier's Fill value first and re-apply it afterwards -- otherwise the
    orphaned value reads as False and defining an attribute silently flips fill
    off on existing sketches.
    """
    if bpy.app.version < (5, 2, 0):
        return
    from ..operators.modifiers import get_modifier_input, set_modifier_input
    from .convert_nodes import CONVERT_NODE_GROUP, build_convert_node_group

    group = bpy.data.node_groups.get(CONVERT_NODE_GROUP)
    saved = []
    if group is not None:
        fill_id = _convert_fill_socket(group)
        if fill_id is not None:
            for obj in bpy.data.objects:
                for mod in obj.modifiers:
                    if (
                        getattr(mod, "type", None) != "NODES"
                        or mod.node_group is not group
                    ):
                        continue
                    try:
                        saved.append((mod, bool(get_modifier_input(mod, fill_id))))
                    except Exception:
                        pass

    group = build_convert_node_group(
        attribute_definitions=_shared_conversion_definitions()
    )

    new_fill_id = _convert_fill_socket(group)
    if new_fill_id is not None:
        for mod, value in saved:
            try:
                set_modifier_input(mod, new_fill_id, value)
            except Exception:
                pass


def definitions(sketch):
    if not sketch or not sketch.data:
        return []
    return _read_defs(sketch.data)


def definition(sketch, name):
    return next((d for d in definitions(sketch) if d["name"] == name), None)


def define_attribute(sketch, name, data_type="FLOAT", domain="CURVE", default=0.0):
    """Define a persistent POINT/CURVE attribute on native sketch geometry."""
    if not sketch or not sketch.data:
        raise ValueError("A native sketch is required")

    name = str(name).strip()
    if not name:
        raise ValueError("Attribute name cannot be empty")
    if name in _RESERVED_NAMES or name.startswith("."):
        raise ValueError(f"'{name}' is reserved by CAD Sketcher")

    data_type = str(data_type).upper()
    domain = str(domain).upper()
    if data_type not in SUPPORTED_TYPES:
        raise ValueError(f"Unsupported attribute type: {data_type}")
    if domain not in SUPPORTED_DOMAINS:
        raise ValueError(
            f"Unsupported attribute domain: {domain}. "
            "OBJECT-domain attributes are deferred."
        )

    curve_data = sketch.data
    defs = _read_defs(curve_data)
    if any(d["name"] == name for d in defs):
        raise ValueError(f"Attribute '{name}' already exists")
    if curve_data.attributes.get(name) is not None:
        raise ValueError(f"Attribute '{name}' already exists on the Curves data")

    value = _cast(data_type, default)
    attr = curve_data.attributes.new(name, type=data_type, domain=domain)
    for item in attr.data:
        item.value = value

    entry = {"name": name, "type": data_type, "domain": domain, "default": value}
    defs.append(entry)
    _write_defs(curve_data, defs)

    curve_data.update_tag()
    _sync_shared_conversion_group()
    return entry


def remove_attribute(sketch, name):
    if not sketch or not sketch.data:
        return False

    curve_data = sketch.data
    defs = _read_defs(curve_data)
    entry = next((d for d in defs if d["name"] == name), None)
    if entry is None:
        return False

    attr = curve_data.attributes.get(name)
    if attr is not None:
        curve_data.attributes.remove(attr)

    _write_defs(curve_data, [d for d in defs if d["name"] != name])
    curve_data.update_tag()
    _sync_shared_conversion_group()
    return True


def set_attribute_value(sketch, name, value, curve_id=None):
    """Set one native user attribute value."""
    entry = definition(sketch, name)
    if entry is None:
        raise KeyError(name)

    value = _cast(entry["type"], value)
    curve_data = sketch.data
    attr = curve_data.attributes.get(name)
    if attr is None:
        attr = curve_data.attributes.new(
            name, type=entry["type"], domain=entry["domain"]
        )
        default = _cast(entry["type"], entry["default"])
        for item in attr.data:
            item.value = default

    if curve_id is None:
        for item in attr.data:
            item.value = value
    else:
        curve_index = get_curve_index(sketch, curve_id)
        if curve_index is None:
            raise KeyError(curve_id)
        if entry["domain"] == "CURVE":
            attr.data[curve_index].value = value
        else:
            curve = curve_data.curves[curve_index]
            point_indices = [point.index for point in curve.points]
            for index in point_indices:
                attr.data[index].value = value
            _propagate_point_value(sketch, name, value, point_indices)

    curve_data.update_tag()


def _propagate_point_value(sketch, name, value, point_indices):
    """Write a POINT value onto every native point welded to the same vertex.

    A sketch vertex is stored as several coincident native points: a standalone
    point entity plus the endpoint of each segment meeting there. Conversion
    welds them by ``merge_id`` and, before meshing, deletes the point entity's
    degenerate one-point spline. A value written to only the authored point is
    therefore either dropped with that spline or diluted by the other points'
    defaults when Merge Points averages the welded corner. Broadcasting it to the
    whole weld group makes the surviving segment endpoints carry it too, so the
    welded vertex keeps the value exactly.
    """
    from .curve_data import compute_merge_ids

    compute_merge_ids(sketch)
    curve_data = sketch.data
    attr = curve_data.attributes.get(name)
    merge_id = curve_data.attributes.get("merge_id")
    if attr is None or merge_id is None:
        return

    # id 0 means "no weld" (interior/unreferenced points); never broadcast on it.
    groups = {merge_id.data[i].value for i in point_indices} - {0}
    if not groups:
        return
    for i in range(len(merge_id.data)):
        if merge_id.data[i].value in groups:
            attr.data[i].value = value


def get_attribute_value(sketch, name, curve_id=None):
    entry = definition(sketch, name)
    if entry is None:
        raise KeyError(name)

    attr = sketch.data.attributes.get(name)
    if attr is None:
        return entry["default"]
    if curve_id is None:
        return [item.value for item in attr.data]

    curve_index = get_curve_index(sketch, curve_id)
    if curve_index is None:
        raise KeyError(curve_id)
    if entry["domain"] == "CURVE":
        return attr.data[curve_index].value

    curve = sketch.data.curves[curve_index]
    return [attr.data[point.index].value for point in curve.points]


def initialize_curve_defaults(curve_data, curve_index):
    """Apply configured defaults to a newly-added native curve."""
    if curve_data is None or curve_index < 0 or curve_index >= len(curve_data.curves):
        return

    for entry in _read_defs(curve_data):
        attr = curve_data.attributes.get(entry["name"])
        if attr is None:
            attr = curve_data.attributes.new(
                entry["name"], type=entry["type"], domain=entry["domain"]
            )

        value = _cast(entry["type"], entry["default"])
        if entry["domain"] == "CURVE":
            attr.data[curve_index].value = value
        else:
            for point in curve_data.curves[curve_index].points:
                attr.data[point.index].value = value
