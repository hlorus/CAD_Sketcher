"""Curve data access, curve_id system, and attribute helpers."""

import logging
import secrets

import bpy
import numpy as np
from mathutils import Vector

from ..model.constants import SketchCurveType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Attribute helpers
# ---------------------------------------------------------------------------

def ensure_attribute(attributes, name, type, domain):
    """Ensure an attribute exists or create it if missing."""
    attr = attributes.get(name)
    if not attr:
        attributes.new(name, type, domain)
        attr = attributes.get(name)
        if type == "STRING" and attr:
            for i in range(len(attr.data)):
                attr.data[i].value = b""
    return attr


# Only cosmetic text remains a STRING attribute. Blender drops CURVE-domain
# STRING attributes entirely on curve removal, so identity is stored as ints.
_STRING_ATTRS = frozenset(("name",))

# ---------------------------------------------------------------------------
# Curve identity: 128-bit UUIDs stored as 2x INT32_2D sub-attributes.
#
# Blender wipes STRING attributes on remove_curves(); integer attributes survive
# and re-index correctly. Each identity field is stored as two hidden ("."-
# prefixed) INT32_2D attributes — the low and high 64-bit halves, each a pair of
# int32 — and exposed as a 32-char lowercase hex string, so all higher-level code
# keeps using the same string ids it always has.
# ---------------------------------------------------------------------------

UUID_FIELDS = ("curve_id", "start_point_id", "end_point_id", "center_point_id")


def _uuid_subnames(field):
    # 128-bit id = low and high 64-bit halves, each an INT32_2D (2x int32).
    return (f".{field}_lo", f".{field}_hi")


def _i32(u):  # unsigned 32-bit -> signed (Blender int32 is signed)
    return u - 0x100000000 if u >= 0x80000000 else u


def _u32(v):  # signed int32 -> unsigned
    return v + 0x100000000 if v < 0 else v


def _hex_to_pairs(hexstr):
    """Hex id -> (lo_pair, hi_pair), each a signed-int32 2-tuple for INT32_2D."""
    u = int(hexstr, 16) if hexstr else 0
    w = [_i32((u >> (32 * k)) & 0xFFFFFFFF) for k in range(4)]
    return (w[0], w[1]), (w[2], w[3])


def _pairs_to_hex(lo, hi):
    """(lo_pair, hi_pair) -> 32-char hex id ('' when all-zero / unset)."""
    words = (lo[0], lo[1], hi[0], hi[1])
    if not any(words):
        return ""
    u = 0
    for k, v in enumerate(words):
        u |= _u32(v) << (32 * k)
    return f"{u:032x}"


def has_uuid_field(curve_data, field):
    """Presence proxy for an identity field (its low sub-attribute)."""
    return curve_data.attributes.get(f".{field}_lo")


def get_uuid(curve_data, field, index):
    """Read an identity field as a 32-char hex string ('' when unset)."""
    lo = curve_data.attributes.get(f".{field}_lo")
    hi = curve_data.attributes.get(f".{field}_hi")
    lo_v = tuple(lo.data[index].value) if lo else (0, 0)
    hi_v = tuple(hi.data[index].value) if hi else (0, 0)
    return _pairs_to_hex(lo_v, hi_v)


def set_uuid(curve_data, field, index, value):
    """Write a hex-string identity field into its 2 INT32_2D sub-attributes."""
    lo_pair, hi_pair = _hex_to_pairs(value)
    lo = curve_data.attributes.get(f".{field}_lo")
    hi = curve_data.attributes.get(f".{field}_hi")
    if lo:
        lo.data[index].value = lo_pair
    if hi:
        hi.data[index].value = hi_pair


def new_uuid():
    """Mint a fresh 128-bit identity as a 32-char hex string."""
    return secrets.token_hex(16)


def read_uuid_list(curve_data, field):
    """All curves' ids for a field as hex strings, read in bulk.

    Uses foreach_get on the 2 INT32_2D sub-attributes — far cheaper than calling
    get_uuid() per curve in hot loops (attribute lookup happens twice total
    instead of twice per curve).
    """
    n = len(curve_data.curves)
    lo = curve_data.attributes.get(f".{field}_lo")
    hi = curve_data.attributes.get(f".{field}_hi")
    if n == 0 or not lo or not hi:
        return [""] * n
    lob = np.zeros(n * 2, dtype=np.int32)
    hib = np.zeros(n * 2, dtype=np.int32)
    lo.data.foreach_get("value", lob)
    hi.data.foreach_get("value", hib)
    return [
        _pairs_to_hex((int(lob[2 * i]), int(lob[2 * i + 1])),
                      (int(hib[2 * i]), int(hib[2 * i + 1])))
        for i in range(n)
    ]


def default_curve_name(curve_data, ctype):
    """A per-type default name like 'Line 3' based on current curve counts."""
    from ..model.constants import SketchCurveType

    labels = {
        SketchCurveType.POINT: "Point",
        SketchCurveType.LINE: "Line",
        SketchCurveType.ARC: "Arc",
        SketchCurveType.CIRCLE: "Circle",
    }
    label = labels.get(ctype, "Curve")
    type_attr = curve_data.attributes.get("sketch_type")
    n = 0
    if type_attr:
        for i in range(len(type_attr.data)):
            if type_attr.data[i].value == ctype:
                n += 1
    return f"{label} {n}"


def set_attribute(attributes, name: str, value, index: int = None):
    """Set an attribute value either for given index or for all."""
    if name in UUID_FIELDS:
        # Identity fields are hex ids stored as 2x INT32_2D (low/high halves).
        lo_pair, hi_pair = _hex_to_pairs(value)
        for sub, pair in ((f".{name}_lo", lo_pair), (f".{name}_hi", hi_pair)):
            a = attributes.get(sub)
            if not a:
                continue
            if index is None:
                for i in range(len(a.data)):
                    a.data[i].value = pair
            else:
                a.data[index].value = pair
        return
    attribute = attributes.get(name)
    if name in _STRING_ATTRS:
        val = value.encode() if isinstance(value, str) else value
        if index is None:
            for i in range(len(attribute.data)):
                attribute.data[i].value = val
        else:
            attribute.data[index].value = val
    elif index is None:
        attribute.data.foreach_set("value", (value,) * len(attribute.data))
    else:
        attribute.data[index].value = value


def get_str_attr(attr, index):
    """Read a STRING attribute value, decoding bytes to str."""
    try:
        v = attr.data[index].value
        if isinstance(v, bytes):
            try:
                s = v.decode("ascii")
            except (UnicodeDecodeError, ValueError):
                return ""
            return s.rstrip("\x00")
        return v
    except (ReferenceError, IndexError):
        return ""


def ensure_standard_attributes(curve_data):
    """Ensure all standard curve attributes are present."""
    attributes = curve_data.attributes
    ensure_attribute(attributes, "cyclic", "BOOLEAN", "CURVE")
    ensure_attribute(attributes, "sketch_type", "INT8", "CURVE")
    ensure_attribute(attributes, "handle_type_left", "INT8", "POINT")
    ensure_attribute(attributes, "handle_type_right", "INT8", "POINT")
    ensure_attribute(attributes, "handle_left", "FLOAT_VECTOR", "POINT")
    ensure_attribute(attributes, "handle_right", "FLOAT_VECTOR", "POINT")
    ensure_attribute(attributes, "resolution", "INT", "CURVE")
    ensure_attribute(attributes, "construction", "BOOLEAN", "CURVE")
    ensure_attribute(attributes, "selected", "BOOLEAN", "CURVE")
    ensure_attribute(attributes, "hover", "BOOLEAN", "CURVE")
    ensure_attribute(attributes, "fixed", "BOOLEAN", "CURVE")
    ensure_attribute(attributes, "visible", "BOOLEAN", "CURVE")
    # Identity fields: 2x INT32_2D each (128-bit), hidden. Integer attributes
    # survive remove_curves() (STRING attributes don't).
    for field in UUID_FIELDS:
        for sub in _uuid_subnames(field):
            ensure_attribute(attributes, sub, "INT32_2D", "CURVE")
    ensure_attribute(attributes, "name", "STRING", "CURVE")


def init_string_attrs(curve_data, curve_idx):
    """Initialize the STRING name attribute to empty for a curve index.

    Blender doesn't zero-init STRING attribute memory, so new curves may
    contain garbage bytes. (INT identity sub-attributes are zero-initialized.)
    """
    for name in _STRING_ATTRS:
        attr = curve_data.attributes.get(name)
        if attr:
            attr.data[curve_idx].value = b""


# ---------------------------------------------------------------------------
# Curve ID system
# ---------------------------------------------------------------------------

_curve_id_cache = {}


def _allocate_curve_id(sketch):
    """Allocate a unique curve_id using UUID generation."""
    return secrets.token_hex(16)


def get_curve_index(sketch, curve_id):
    """Look up curve index by curve_id. Uses runtime cache, falls back to scan."""
    cd = _get_original_data(sketch)
    if not cd:
        return None
    sk_key = id(cd)
    if sk_key in _curve_id_cache:
        cache = _curve_id_cache[sk_key]
        if curve_id in cache:
            return cache[curve_id]
    return _rebuild_curve_id_cache(sketch, curve_id)


def _rebuild_curve_id_cache(sketch, lookup_id=None):
    """Rebuild the curve_id -> curve_index cache for a sketch."""
    curve_data = _get_original_data(sketch)
    if not curve_data:
        return None
    sk_key = id(curve_data)
    cache = {cid: i for i, cid in enumerate(read_uuid_list(curve_data, "curve_id"))}
    _curve_id_cache[sk_key] = cache
    return cache.get(lookup_id) if lookup_id is not None else None


def invalidate_curve_id_cache(sketch=None):
    """Invalidate the curve_id cache. Call after add/remove curves."""
    if sketch and sketch.target_object:
        sk_key = id(sketch.target_object.data)
        _curve_id_cache.pop(sk_key, None)
    else:
        _curve_id_cache.clear()


# ---------------------------------------------------------------------------
# Curve data access
# ---------------------------------------------------------------------------

def _get_original_data(sketch):
    """Get the original (non-evaluated) Curves data for a sketch."""
    obj = sketch.target_object
    if not obj or not obj.data:
        return None
    if hasattr(obj, 'original') and obj.original and obj.original.data:
        return obj.original.data
    return obj.data


def get_curve_data(sketch, curve_id):
    """Get curve slice and attributes for a curve_id.

    Returns:
        tuple: (curve_data, curve_index, curve_slice) or (None, None, None)
    """
    curve_data = _get_original_data(sketch)
    if not curve_data:
        return None, None, None
    idx = get_curve_index(sketch, curve_id)
    if idx is None or idx >= len(curve_data.curves):
        return None, None, None
    return curve_data, idx, curve_data.curves[idx]


def get_curve_type(sketch, curve_id):
    """Get the SketchCurveType for a curve_id."""
    curve_data, idx, _ = get_curve_data(sketch, curve_id)
    if curve_data is None:
        return None
    type_attr = curve_data.attributes.get("sketch_type")
    if not type_attr:
        return None
    return type_attr.data[idx].value


def get_curve_position(sketch, curve_id):
    """Get the local-space position of a point curve."""
    curve_data, idx, curve_slice = get_curve_data(sketch, curve_id)
    if curve_data is None:
        return None
    pt_idx = curve_slice.points[0].index
    return Vector(curve_data.points[pt_idx].position)


def get_curve_world_position(sketch, curve_id):
    """Get the world-space position of a point curve."""
    pos = get_curve_position(sketch, curve_id)
    if pos is None:
        return None
    return sketch.target_object.matrix_world @ pos


def get_curve_placement(sketch, curve_id):
    """Get the world-space placement position for a curve (for gizmo positioning)."""
    curve_data, idx, curve_slice = get_curve_data(sketch, curve_id)
    if curve_data is None:
        return None

    type_attr = curve_data.attributes.get("sketch_type")
    ctype = type_attr.data[idx].value if type_attr else -1
    mat = sketch.target_object.matrix_world

    if ctype == SketchCurveType.LINE and curve_slice.points_length >= 2:
        first = curve_slice.points[0].index
        p1 = Vector(curve_data.points[first].position)
        p2 = Vector(curve_data.points[first + 1].position)
        return mat @ ((p1 + p2) / 2)
    elif curve_slice.points_length >= 1:
        pos = Vector(curve_data.points[curve_slice.points[0].index].position)
        return mat @ pos
    return None


def get_curve_midpoints(curve_slice, is_cyclic):
    """Get interior bezier points from a curve slice."""
    if len(curve_slice.points) <= 2:
        return []
    if is_cyclic:
        return [curve_slice.points[i] for i in range(1, len(curve_slice.points))]
    return [curve_slice.points[i] for i in range(1, len(curve_slice.points) - 1)]


# ---------------------------------------------------------------------------
# Selection sync
# ---------------------------------------------------------------------------

def sync_curve_selection(scene):
    """Sync selection and hover state from global_data to curve attributes."""
    from .. import global_data

    from ..model.sketch_ref import get_sketches

    selected = set(global_data.selected)
    hover = global_data.hover
    for sketch in get_sketches(scene):
        if not sketch.target_object or not sketch.target_object.data:
            continue
        curve_data = sketch.target_object.data
        n_curves = len(curve_data.curves)
        if n_curves == 0 or not has_uuid_field(curve_data, "curve_id"):
            continue

        sel_attr = curve_data.attributes.get("selected")
        hov_attr = curve_data.attributes.get("hover")
        if not sel_attr:
            sel_attr = curve_data.attributes.new("selected", type="BOOLEAN", domain="CURVE")
        if not hov_attr:
            hov_attr = curve_data.attributes.new("hover", type="BOOLEAN", domain="CURVE")

        ids = read_uuid_list(curve_data, "curve_id")
        want_sel = np.fromiter((c in selected for c in ids), dtype=bool, count=n_curves)
        want_hov = np.fromiter((bool(c) and c == hover for c in ids), dtype=bool, count=n_curves)

        # Only write when something actually changed. Writing attribute data
        # every frame dirties the datablock and re-triggers the GN modifier +
        # redraw, which would spin the CPU on a static selection.
        cur_sel = np.empty(n_curves, dtype=bool)
        cur_hov = np.empty(n_curves, dtype=bool)
        sel_attr.data.foreach_get("value", cur_sel)
        hov_attr.data.foreach_get("value", cur_hov)
        if not np.array_equal(cur_sel, want_sel):
            sel_attr.data.foreach_set("value", want_sel)
        if not np.array_equal(cur_hov, want_hov):
            hov_attr.data.foreach_set("value", want_hov)


# ---------------------------------------------------------------------------
# Curve object management
# ---------------------------------------------------------------------------

CONVERT_MODIFIER_NAME = "CAD Sketcher Convert"


def _ensure_convert_modifier(ob):
    """Get or create the GN convert modifier on a curve object."""
    assert ob is not None, "_ensure_convert_modifier: object is None"

    modifier = ob.modifiers.get(CONVERT_MODIFIER_NAME)
    if not modifier:
        modifier = ob.modifiers.new(CONVERT_MODIFIER_NAME, "NODES")
        assert modifier is not None, "Failed to create GN modifier"

    if modifier and not modifier.node_group:
        from ..assets_manager import load_asset
        from .. import global_data
        loaded = load_asset(global_data.LIB_NAME, "node_groups", "CAD Sketcher Convert")
        ng = bpy.data.node_groups.get("CAD Sketcher Convert")
        if ng:
            modifier.node_group = ng
        else:
            logger.warning("Could not load 'CAD Sketcher Convert' node group")

    return modifier


def ensure_sketch_curve_object(sketch):
    """Ensure a sketch has a native curve object, creating one if needed."""
    assert sketch is not None, "ensure_sketch_curve_object: sketch is None"

    wp_obj = sketch.workplane_object
    if not wp_obj and hasattr(sketch, 'wp') and not sketch.wp:
        logger.warning("ensure_sketch_curve_object: no workplane empty or entity")
        return None

    if not sketch.target_object:
        curve = bpy.data.hair_curves.new(sketch.name)
        assert curve is not None, "Failed to create hair_curves data"

        ob = bpy.data.objects.new(sketch.name, curve)
        assert ob is not None, "Failed to create object for curve data"
        sketch.target_object = ob

        if wp_obj:
            ob.matrix_world = wp_obj.matrix_world
        elif hasattr(sketch, 'wp') and sketch.wp:
            ob.matrix_world = sketch.wp.matrix_basis

        scene = bpy.context.scene
        assert scene is not None, "No active scene"
        if ob.name not in scene.collection.objects:
            scene.collection.objects.link(ob)

        _ensure_convert_modifier(ob)

        # Stamp sketch custom properties
        from ..model.sketch_ref import stamp_sketch_props
        stamp_sketch_props(ob)

    assert sketch.target_object is not None, "target_object should exist after ensure"
    assert sketch.target_object.data is not None, "target_object.data should exist"
    return sketch.target_object.data


def remove_native_curve_by_id(sketch, curve_id):
    """Remove a curve by its stable curve_id."""
    if not sketch or not sketch.target_object or not sketch.target_object.data:
        return
    curve_data = sketch.target_object.data
    n_curves = len(curve_data.curves)
    if n_curves == 0:
        return

    if not has_uuid_field(curve_data, "curve_id"):
        return

    to_remove = []
    for curve_idx in range(n_curves):
        if get_uuid(curve_data, "curve_id", curve_idx) == curve_id:
            to_remove.append(curve_idx)

    if to_remove:
        # INT identity attributes survive remove_curves() and re-index, but the
        # STRING `name` attribute is dropped entirely, so snapshot the survivors'
        # names (in order) and restore them afterwards.
        remove_set = set(to_remove)
        attrs = curve_data.attributes
        name_attr = attrs.get("name")
        survivor_names = [
            name_attr.data[i].value
            for i in range(n_curves)
            if i not in remove_set and name_attr
        ]

        curve_data.remove_curves(indices=to_remove)

        ensure_standard_attributes(curve_data)  # recreate the dropped `name`
        name_attr = curve_data.attributes.get("name")
        if name_attr:
            for new_idx, val in enumerate(survivor_names):
                name_attr.data[new_idx].value = val

        invalidate_curve_id_cache(sketch)
        curve_data.update_tag()


_batch_sketches = set()


def _batch_key(sketch):
    """Stable identity for batching, shared across Sketch wrapper instances.

    Different code paths wrap the same sketch object in distinct Sketch
    instances, so id(sketch) is NOT stable — keying on it makes is_batching()
    miss and rebuild every segment per point write. The object's C pointer is
    the same across all wrappers.
    """
    obj = sketch.target_object
    return obj.as_pointer() if obj else id(sketch)


class batch_update:
    """Context manager that defers rebuild_segments until exit.

    Usage:
        with batch_update(sketch):
            for point in points:
                point.co = new_pos  # no rebuild per write
        # rebuild_segments called once here

    Pass ``point_ids`` to rebuild only the segments referencing those points.
    """
    def __init__(self, sketch, point_ids=None):
        self.sketch = sketch
        self.point_ids = point_ids

    def __enter__(self):
        _batch_sketches.add(_batch_key(self.sketch))
        return self

    def __exit__(self, *args):
        _batch_sketches.discard(_batch_key(self.sketch))
        rebuild_segments(self.sketch, point_ids=self.point_ids)


def is_batching(sketch):
    return _batch_key(sketch) in _batch_sketches


def is_fixed(sketch, curve_id):
    """Check if a curve is directly marked as fixed."""
    cd, idx, _ = get_curve_data(sketch, curve_id)
    if cd is None:
        return False
    fix_attr = cd.attributes.get("fixed")
    return bool(fix_attr and fix_attr.data[idx].value)


def rebuild_segments(sketch, point_ids=None):
    """Rebuild segment curve positions from their referenced point curves.

    Lines: copy endpoint positions from point curves.
    Arcs/circles: recompute bezier geometry from center/start/end point curves.

    Call after modifying point positions to keep segment data consistent. When
    ``point_ids`` is given, only segments referencing one of those point ids are
    rebuilt (e.g. during a move, where only the dragged points changed) — this
    avoids re-resolving every segment in the sketch each frame.
    """
    from ..model.constants import SketchCurveType, BezierHandleType
    from ..model.curve_ref import _build_arc_bezier, PointRef
    from mathutils import Vector

    if not sketch or not sketch.target_object or not sketch.target_object.data:
        return

    cd = sketch.target_object.data
    n = len(cd.curves)
    if n == 0:
        return

    type_attr = cd.attributes.get("sketch_type")
    if not type_attr:
        return

    # Bulk-read the relationship ids once (get_uuid does 4 attribute lookups
    # per call, so per-segment reads add up in this per-frame hot path).
    sp_ids = read_uuid_list(cd, "start_point_id")
    ep_ids = read_uuid_list(cd, "end_point_id")
    cp_ids = read_uuid_list(cd, "center_point_id")

    for i in range(n):
        ctype = type_attr.data[i].value
        if ctype == SketchCurveType.POINT:
            continue

        # Scoped rebuild: skip segments that don't touch a changed point.
        if point_ids is not None and not (
            sp_ids[i] in point_ids
            or ep_ids[i] in point_ids
            or cp_ids[i] in point_ids
        ):
            continue

        curve_slice = cd.curves[i]

        # A native edit can leave a segment with too few points (e.g. an
        # endpoint deleted in Edit Mode). Skip such degenerate curves rather
        # than indexing past their point count.
        min_points = 2 if ctype == SketchCurveType.LINE else 1
        if curve_slice.points_length < min_points:
            continue

        if ctype == SketchCurveType.LINE:
            sp_cid = sp_ids[i]
            ep_cid = ep_ids[i]
            if sp_cid:
                p1 = PointRef(sketch, sp_cid)
                if p1.valid:
                    pos = (*p1.co, 0.0)
                    cd.points[curve_slice.points[0].index].position = pos
                    hl = cd.attributes.get("handle_left")
                    hr = cd.attributes.get("handle_right")
                    if hl: hl.data[curve_slice.points[0].index].vector = pos
                    if hr: hr.data[curve_slice.points[0].index].vector = pos
            if ep_cid:
                p2 = PointRef(sketch, ep_cid)
                if p2.valid:
                    pos = (*p2.co, 0.0)
                    cd.points[curve_slice.points[1].index].position = pos
                    hl = cd.attributes.get("handle_left")
                    hr = cd.attributes.get("handle_right")
                    if hl: hl.data[curve_slice.points[1].index].vector = pos
                    if hr: hr.data[curve_slice.points[1].index].vector = pos

        elif ctype in (SketchCurveType.ARC, SketchCurveType.CIRCLE):
            cp_cid = cp_ids[i]
            if not cp_cid:
                continue
            ct = PointRef(sketch, cp_cid)
            if not ct.valid:
                continue
            is_cyclic = ctype == SketchCurveType.CIRCLE
            if is_cyclic:
                edge = Vector(cd.points[curve_slice.points[0].index].position[:2])
                _build_arc_bezier(cd, i, ct.co, edge, edge, is_cyclic=True)
            else:
                sp_cid = sp_ids[i]
                ep_cid = ep_ids[i]
                if sp_cid and ep_cid:
                    s = PointRef(sketch, sp_cid)
                    e = PointRef(sketch, ep_cid)
                    if s.valid and e.valid:
                        _build_arc_bezier(cd, i, ct.co, s.co, e.co)


def refresh_curve_geometry(sketch):
    """Force GN modifier re-evaluation by doing a topology rebuild."""
    if not sketch or not sketch.target_object or not sketch.target_object.data:
        return

    curve_data = sketch.target_object.data
    n_curves = len(curve_data.curves)
    if n_curves == 0:
        return

    n_points = len(curve_data.points)
    point_counts = np.zeros(n_curves, dtype=np.int32)
    curve_data.curves.foreach_get("points_length", point_counts)

    positions = np.zeros(n_points * 3, dtype=np.float32)
    curve_data.points.foreach_get("position", positions)

    saved_attrs = {}
    for attr in curve_data.attributes:
        if attr.name == "position":
            continue
        domain_len = n_points if attr.domain == 'POINT' else n_curves
        if attr.data_type == 'FLOAT_VECTOR':
            data = np.zeros(domain_len * 3, dtype=np.float32)
            attr.data.foreach_get("vector", data)
        elif attr.data_type == 'BOOLEAN':
            data = np.zeros(domain_len, dtype=np.bool_)
            attr.data.foreach_get("value", data)
        elif attr.data_type in ('INT', 'INT8'):
            data = np.zeros(domain_len, dtype=np.int32)
            attr.data.foreach_get("value", data)
        elif attr.data_type in ('INT32_2D', 'INT16_2D'):
            data = np.zeros(domain_len * 2, dtype=np.int32)
            attr.data.foreach_get("value", data)
        elif attr.data_type == 'FLOAT':
            data = np.zeros(domain_len, dtype=np.float32)
            attr.data.foreach_get("value", data)
        elif attr.data_type == 'STRING':
            data = [attr.data[i].value for i in range(domain_len)]
        else:
            continue
        saved_attrs[attr.name] = {
            "data": data, "type": attr.data_type, "domain": attr.domain,
        }

    curve_data.remove_curves()
    curve_data.add_curves(point_counts.tolist())
    curve_data.set_types(type="BEZIER")
    ensure_standard_attributes(curve_data)

    curve_data.points.foreach_set("position", positions)
    for name, info in saved_attrs.items():
        attr = curve_data.attributes.get(name)
        if not attr:
            attr = curve_data.attributes.new(name, type=info["type"], domain=info["domain"])
        if info["type"] == 'STRING':
            for i, v in enumerate(info["data"]):
                attr.data[i].value = v
        elif info["type"] == 'FLOAT_VECTOR':
            attr.data.foreach_set("vector", info["data"])
        else:
            attr.data.foreach_set("value", info["data"])

    invalidate_curve_id_cache(sketch)
