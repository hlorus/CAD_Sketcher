"""User-defined attributes backed by native Curves data.

Definitions and public values live on the native Curves source of truth. For
POINT/CURVE values we also maintain a hidden native mirror used only by the
conversion graph. Blender already preserves CAD Sketcher's hidden source-id
attributes through the topology chain when they are consumed downstream; using
the same native-attribute mechanism avoids per-sketch value baking in Geometry
Nodes while keeping the public user attribute intact on the sketch itself.
"""

import hashlib
import json

from .curve_data import get_curve_index

DEFINITIONS_PROP = "cad_custom_attribute_definitions"

SUPPORTED_TYPES = {"BOOLEAN", "INT", "FLOAT"}
SUPPORTED_DOMAINS = {"POINT", "CURVE", "OBJECT"}

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


def transport_attribute_name(entry):
    """Deterministic hidden native mirror name for one public definition."""
    signature = f"{entry['name']}|{entry['type']}|{entry['domain']}"
    digest = hashlib.sha1(signature.encode("utf-8")).hexdigest()[:12]
    return f".cad_custom_transport_{digest}"


def _ensure_transport_mirror(curve_data, entry):
    """Create/synchronize a hidden native conversion mirror for one definition."""
    if entry["domain"] == "OBJECT":
        return None
    public = curve_data.attributes.get(entry["name"])
    if public is None:
        return None
    hidden_name = transport_attribute_name(entry)
    hidden = curve_data.attributes.get(hidden_name)
    if hidden is None:
        hidden = curve_data.attributes.new(
            hidden_name, type=entry["type"], domain=entry["domain"]
        )
    for index, item in enumerate(public.data):
        hidden.data[index].value = item.value
    return hidden


def _write_object_value(sketch, name, value):
    """Mirror an OBJECT-domain value to the sketch object and its data-block."""
    sketch.target_object[name] = value
    sketch.data[name] = value


def _attribute_group_name(specs):
    """Return a deterministic group name shared by equal attribute schemas."""
    from .convert_nodes import CONVERT_NODE_GROUP, attribute_signature

    signature = attribute_signature(specs)
    digest = hashlib.sha1(signature.encode("utf-8")).hexdigest()[:12]
    return f"{CONVERT_NODE_GROUP} [attrs {digest}]"


def _sync_conversion_group(sketch):
    """Bind the smallest converter needed by this sketch on Blender 5.2+.

    Attribute-bearing sketches share a converter by schema. Their hidden native
    mirrors carry live values, so value edits never rebuild or rebind the group.
    """
    import bpy

    if not sketch or not sketch.target_object:
        return

    entries = definitions(sketch)
    for entry in entries:
        _ensure_transport_mirror(sketch.data, entry)

    if bpy.app.version < (5, 2, 0):
        return

    from .convert_nodes import (
        CONVERT_NODE_GROUP,
        build_convert_node_group,
        normalize_attribute_definitions,
    )

    ob = sketch.target_object
    modifier = ob.modifiers.get(CONVERT_NODE_GROUP)
    if modifier is None:
        modifier = ob.modifiers.new(CONVERT_NODE_GROUP, "NODES")

    specs = normalize_attribute_definitions(entries)
    if specs:
        group = build_convert_node_group(
            _attribute_group_name(specs), attribute_definitions=specs
        )
    else:
        group = build_convert_node_group(CONVERT_NODE_GROUP)

    old_group = modifier.node_group
    modifier.node_group = group
    ob.update_tag()

    if (
        old_group is not None
        and old_group != group
        and old_group.users == 0
        and old_group.name.startswith(f"{CONVERT_NODE_GROUP} [attrs ")
    ):
        bpy.data.node_groups.remove(old_group)


def definitions(sketch):
    if not sketch or not sketch.data:
        return []
    return _read_defs(sketch.data)


def definition(sketch, name):
    return next((d for d in definitions(sketch) if d["name"] == name), None)


def define_attribute(sketch, name, data_type="FLOAT", domain="CURVE", default=0.0):
    """Define a persistent user attribute on a native sketch."""
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

    public = curve_data.attributes.new(name, type=data_type, domain=domain)
    hidden = curve_data.attributes.new(
        transport_attribute_name(entry), type=data_type, domain=domain
    )
    for public_item, hidden_item in zip(public.data, hidden.data):
        public_item.value = value
        hidden_item.value = value
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
        for attr_name in (name, transport_attribute_name(entry)):
            attr = curve_data.attributes.get(attr_name)
            if attr is not None:
                curve_data.attributes.remove(attr)
        curve_data.update_tag()
        _sync_conversion_group(sketch)
    return True


def set_attribute_value(sketch, name, value, curve_id=None):
    """Set public and hidden conversion values from one source operation."""
    entry = definition(sketch, name)
    if entry is None:
        raise KeyError(name)
    value = _cast(entry["type"], value)

    if entry["domain"] == "OBJECT":
        _write_object_value(sketch, name, value)
        return

    curve_data = sketch.data
    public = curve_data.attributes.get(name)
    if public is None:
        public = curve_data.attributes.new(
            name, type=entry["type"], domain=entry["domain"]
        )
        for item in public.data:
            item.value = _cast(entry["type"], entry["default"])
    hidden = _ensure_transport_mirror(curve_data, entry)
    attrs = (public, hidden)

    if curve_id is None:
        for attr in attrs:
            for item in attr.data:
                item.value = value
    else:
        curve_index = get_curve_index(sketch, curve_id)
        if curve_index is None:
            raise KeyError(curve_id)
        if entry["domain"] == "CURVE":
            for attr in attrs:
                attr.data[curve_index].value = value
        else:
            curve = curve_data.curves[curve_index]
            for point in curve.points:
                for attr in attrs:
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
    """Apply configured defaults to a newly-added native curve and mirror."""
    if curve_data is None or curve_index < 0 or curve_index >= len(curve_data.curves):
        return
    for entry in _read_defs(curve_data):
        domain = entry["domain"]
        if domain == "OBJECT":
            continue
        public = curve_data.attributes.get(entry["name"])
        if public is None:
            public = curve_data.attributes.new(
                entry["name"], type=entry["type"], domain=domain
            )
        hidden_name = transport_attribute_name(entry)
        hidden = curve_data.attributes.get(hidden_name)
        if hidden is None:
            hidden = curve_data.attributes.new(
                hidden_name, type=entry["type"], domain=domain
            )
        value = _cast(entry["type"], entry["default"])
        if domain == "CURVE":
            public.data[curve_index].value = value
            hidden.data[curve_index].value = value
        else:
            for point in curve_data.curves[curve_index].points:
                public.data[point.index].value = value
                hidden.data[point.index].value = value
