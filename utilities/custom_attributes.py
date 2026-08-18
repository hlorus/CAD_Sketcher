"""User-defined attributes backed by native Curves data.

Definitions live on the sketch Curves datablock and values live in native Blender
attributes, so the sketch remains the source of truth. Geometry Nodes can carry
those named attributes into evaluated conversion geometry and rebuilding the
native curves does not discard them.
"""

import json

from .curve_data import get_curve_index

DEFINITIONS_PROP = "cad_custom_attribute_definitions"

SUPPORTED_TYPES = {"BOOLEAN", "INT", "FLOAT"}
SUPPORTED_DOMAINS = {"POINT", "CURVE", "OBJECT"}

# CAD Sketcher owns these names; user attributes must not shadow solver or
# conversion metadata.
_RESERVED_NAMES = {
    "position",
    "cyclic",
    "sketch_type",
    "handle_left",
    "handle_right",
    "handle_type_left",
    "handle_type_right",
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


def _write_object_value(sketch, name, value):
    """Mirror an OBJECT-domain value to the sketch object and its data-block.

    The conversion contract for #200 explicitly treats both ID-property targets
    as the object-level acceptance boundary. Keeping them synchronized also
    means either side can be copied/reused by a destructive conversion path.
    """
    sketch.target_object[name] = value
    sketch.data[name] = value


def _sync_conversion_group(sketch):
    """Keep the sketch bound to the shared converter on Blender 5.2+.

    Native named attributes propagate through Geometry Nodes generically, so
    custom attributes do not require a per-sketch node group or a rebuilt node
    tree for every definition change. This helper only ensures the standard
    shared converter is present and bound.
    """
    import bpy

    if bpy.app.version < (5, 2, 0) or not sketch or not sketch.target_object:
        return

    from .convert_nodes import CONVERT_NODE_GROUP, build_convert_node_group

    ob = sketch.target_object
    modifier = ob.modifiers.get(CONVERT_NODE_GROUP)
    if modifier is None:
        modifier = ob.modifiers.new(CONVERT_NODE_GROUP, "NODES")
    modifier.node_group = build_convert_node_group(CONVERT_NODE_GROUP)
    ob.update_tag()


def definitions(sketch):
    if not sketch or not sketch.data:
        return []
    return _read_defs(sketch.data)


def definition(sketch, name):
    return next((d for d in definitions(sketch) if d["name"] == name), None)


def define_attribute(sketch, name, data_type="FLOAT", domain="CURVE", default=0.0):
    """Define a persistent user attribute on a native sketch.

    ``CURVE`` maps naturally to a CAD Sketcher entity/segment, ``POINT`` to the
    native curve point domain, and ``OBJECT`` to mirrored properties on the
    sketch object and its Curves data-block.
    """
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
        raise ValueError(f"Unsupported attribute domain: {domain}")

    curve_data = sketch.data
    defs = _read_defs(curve_data)
    if any(d["name"] == name for d in defs):
        raise ValueError(f"Attribute '{name}' already exists")
    if curve_data.attributes.get(name) is not None:
        raise ValueError(f"Attribute '{name}' already exists on the Curves data")

    value = _cast(data_type, default)
    entry = {"name": name, "type": data_type, "domain": domain, "default": value}
    defs.append(entry)
    _write_defs(curve_data, defs)

    if domain == "OBJECT":
        _write_object_value(sketch, name, value)
        return entry

    attr = curve_data.attributes.new(name, type=data_type, domain=domain)
    for item in attr.data:
        item.value = value
    curve_data.update_tag()
    _sync_conversion_group(sketch)
    return entry


def remove_attribute(sketch, name):
    if not sketch or not sketch.data:
        return False
    curve_data = sketch.data
    defs = _read_defs(curve_data)
    entry = next((d for d in defs if d["name"] == name), None)
    if entry is None:
        return False

    defs = [d for d in defs if d["name"] != name]
    _write_defs(curve_data, defs)
    if entry["domain"] == "OBJECT":
        if name in sketch.target_object:
            del sketch.target_object[name]
        if name in curve_data:
            del curve_data[name]
    else:
        attr = curve_data.attributes.get(name)
        if attr is not None:
            curve_data.attributes.remove(attr)
        curve_data.update_tag()
        _sync_conversion_group(sketch)
    return True


def set_attribute_value(sketch, name, value, curve_id=None):
    """Set a user attribute value.

    For CURVE/POINT attributes ``curve_id`` selects one native sketch entity.
    POINT-domain values are applied to all native points belonging to that entity.
    OBJECT attributes ignore ``curve_id``.
    """
    entry = definition(sketch, name)
    if entry is None:
        raise KeyError(name)
    value = _cast(entry["type"], value)

    if entry["domain"] == "OBJECT":
        _write_object_value(sketch, name, value)
        return

    curve_data = sketch.data
    attr = curve_data.attributes.get(name)
    if attr is None:
        attr = curve_data.attributes.new(
            name, type=entry["type"], domain=entry["domain"]
        )
        for item in attr.data:
            item.value = _cast(entry["type"], entry["default"])

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
            for point in curve.points:
                attr.data[point.index].value = value
    curve_data.update_tag()


def get_attribute_value(sketch, name, curve_id=None):
    entry = definition(sketch, name)
    if entry is None:
        raise KeyError(name)
    if entry["domain"] == "OBJECT":
        if name in sketch.target_object:
            return sketch.target_object[name]
        return sketch.data.get(name, entry["default"])

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
        domain = entry["domain"]
        if domain == "OBJECT":
            continue
        attr = curve_data.attributes.get(entry["name"])
        if attr is None:
            attr = curve_data.attributes.new(
                entry["name"], type=entry["type"], domain=domain
            )
        value = _cast(entry["type"], entry["default"])
        if domain == "CURVE":
            attr.data[curve_index].value = value
        else:
            for point in curve_data.curves[curve_index].points:
                attr.data[point.index].value = value
