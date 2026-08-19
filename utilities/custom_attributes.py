"""User-defined attributes backed by native Curves data.

Definitions live on the sketch Curves datablock and POINT/CURVE values live in
native Blender attributes. Blender carries those attributes through the normal
wire conversion path generically. The single shared conversion group only adds
small domain-aware bridges where topology changes would otherwise lose them;
attribute definitions never create per-schema node-group variants.
"""

import json

import bpy

from .curve_data import get_curve_index

DEFINITIONS_PROP = "cad_custom_attribute_definitions"
OBJECT_NAMES_PROP = "cad_custom_object_attribute_names"

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


def _shared_conversion_definitions():
    """Union of non-object definitions used by the one shared GN converter."""
    definitions_by_key = {}
    for curve_data in bpy.data.hair_curves:
        for entry in _read_defs(curve_data):
            domain = str(entry.get("domain", "")).upper()
            data_type = str(entry.get("type", "")).upper()
            name = str(entry.get("name", "")).strip()
            if domain not in {"POINT", "CURVE"} or data_type not in SUPPORTED_TYPES:
                continue
            key = (name, data_type, domain)
            definitions_by_key[key] = {
                "name": name,
                "type": data_type,
                "domain": domain,
            }
    return [definitions_by_key[key] for key in sorted(definitions_by_key)]


def _sync_shared_conversion_group():
    """Rebuild the existing shared converter in place when definitions change."""
    if bpy.app.version < (5, 2, 0):
        return
    from .convert_nodes import build_convert_node_group

    build_convert_node_group(
        attribute_definitions=_shared_conversion_definitions()
    )


def _read_object_names(obj):
    """Names of OBJECT-domain properties that must survive data replacement."""
    raw = obj.get(OBJECT_NAMES_PROP, "[]") if obj else "[]"
    if isinstance(raw, bytes):
        raw = raw.decode()
    try:
        names = json.loads(raw)
    except (TypeError, ValueError):
        names = []
    return [name for name in names if isinstance(name, str) and name]


def _write_object_names(obj, names):
    names = sorted(set(names))
    if names:
        obj[OBJECT_NAMES_PROP] = json.dumps(names, separators=(",", ":"))
    elif OBJECT_NAMES_PROP in obj:
        del obj[OBJECT_NAMES_PROP]


def sync_object_attribute_values(obj):
    """Mirror persistent OBJECT values onto the object's current data-block."""
    if obj is None or getattr(obj, "data", None) is None:
        return False

    changed = False
    for name in _read_object_names(obj):
        if name not in obj:
            continue
        value = obj[name]
        if obj.data.get(name) != value:
            obj.data[name] = value
            changed = True
    return changed


def _write_object_value(sketch, name, value):
    """Mirror an OBJECT-domain value to the sketch object and its data-block."""
    obj = sketch.target_object
    obj[name] = value
    sketch.data[name] = value
    names = _read_object_names(obj)
    if name not in names:
        names.append(name)
        _write_object_names(obj, names)


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

    attr = curve_data.attributes.new(name, type=data_type, domain=domain)
    for item in attr.data:
        item.value = value
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

    defs = [d for d in defs if d["name"] != name]
    _write_defs(curve_data, defs)
    if entry["domain"] == "OBJECT":
        obj = sketch.target_object
        if name in obj:
            del obj[name]
        if name in curve_data:
            del curve_data[name]
        names = _read_object_names(obj)
        if name in names:
            names.remove(name)
            _write_object_names(obj, names)
    else:
        attr = curve_data.attributes.get(name)
        if attr is not None:
            curve_data.attributes.remove(attr)
        curve_data.update_tag()
        _sync_shared_conversion_group()
    return True


def set_attribute_value(sketch, name, value, curve_id=None):
    """Set one native user attribute value."""
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
