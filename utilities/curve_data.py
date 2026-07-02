"""Curve data access, curve_id system, and attribute helpers."""

import logging

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
    return attr


def set_attribute(attributes, name: str, value, index: int = None):
    """Set an attribute value either for given index or for all."""
    attribute = attributes.get(name)
    if index is None:
        attribute.data.foreach_set("value", (value,) * len(attribute.data))
    else:
        attribute.data[index].value = value


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
    ensure_attribute(attributes, "curve_id", "INT", "CURVE")
    ensure_attribute(attributes, "start_point_id", "INT", "CURVE")
    ensure_attribute(attributes, "end_point_id", "INT", "CURVE")
    ensure_attribute(attributes, "center_point_id", "INT", "CURVE")


# ---------------------------------------------------------------------------
# Curve ID system
# ---------------------------------------------------------------------------

_curve_id_cache = {}


def _allocate_curve_id(sketch):
    """Allocate a unique curve_id by scanning existing IDs."""
    cd = sketch.target_object.data if sketch.target_object else None
    if not cd or len(cd.curves) == 0:
        return 1
    cid_attr = cd.attributes.get("curve_id")
    if not cid_attr:
        return 1
    max_id = max(cid_attr.data[i].value for i in range(len(cd.curves)))
    return max_id + 1


def get_curve_index(sketch, curve_id):
    """Look up curve index by curve_id. Uses runtime cache, falls back to scan."""
    sk_key = id(sketch.target_object.data) if sketch.target_object else None
    if sk_key and sk_key in _curve_id_cache:
        cache = _curve_id_cache[sk_key]
        if curve_id in cache:
            return cache[curve_id]
    return _rebuild_curve_id_cache(sketch, curve_id)


def _rebuild_curve_id_cache(sketch, lookup_id=None):
    """Rebuild the curve_id -> curve_index cache for a sketch."""
    if not sketch.target_object or not sketch.target_object.data:
        return None
    curve_data = sketch.target_object.data
    sk_key = id(curve_data)
    cache = {}
    cid_attr = curve_data.attributes.get("curve_id")
    if cid_attr:
        for i in range(len(curve_data.curves)):
            cache[cid_attr.data[i].value] = i
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

def get_curve_data(sketch, curve_id):
    """Get curve slice and attributes for a curve_id.

    Returns:
        tuple: (curve_data, curve_index, curve_slice) or (None, None, None)
    """
    if not sketch or not sketch.target_object or not sketch.target_object.data:
        return None, None, None
    curve_data = sketch.target_object.data
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

    if ctype == SketchCurveType.POINT:
        pos = Vector(curve_data.points[curve_slice.points[0].index].position)
        return mat @ pos
    elif ctype == SketchCurveType.LINE:
        first = curve_slice.points[0].index
        p1 = Vector(curve_data.points[first].position)
        p2 = Vector(curve_data.points[first + 1].position)
        return mat @ ((p1 + p2) / 2)
    else:
        pos = Vector(curve_data.points[curve_slice.points[0].index].position)
        return mat @ pos


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
    for sketch in get_sketches(scene):
        if not sketch.target_object or not sketch.target_object.data:
            continue
        curve_data = sketch.target_object.data
        n_curves = len(curve_data.curves)
        if n_curves == 0:
            continue

        cid_attr = curve_data.attributes.get("curve_id")
        sel_attr = curve_data.attributes.get("selected")
        hov_attr = curve_data.attributes.get("hover")
        if not cid_attr:
            continue
        if not sel_attr:
            sel_attr = curve_data.attributes.new("selected", type="BOOLEAN", domain="CURVE")
        if not hov_attr:
            hov_attr = curve_data.attributes.new("hover", type="BOOLEAN", domain="CURVE")

        for curve_idx in range(n_curves):
            cid = cid_attr.data[curve_idx].value
            sel_attr.data[curve_idx].value = cid in global_data.selected
            hov_attr.data[curve_idx].value = cid == global_data.hover


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

    cid_attr = curve_data.attributes.get("curve_id")
    if not cid_attr:
        return

    to_remove = []
    for curve_idx in range(n_curves):
        if cid_attr.data[curve_idx].value == curve_id:
            to_remove.append(curve_idx)

    if to_remove:
        curve_data.remove_curves(indices=to_remove)
        invalidate_curve_id_cache(sketch)
        curve_data.update_tag()


_batch_sketches = set()


class batch_update:
    """Context manager that defers rebuild_segments until exit.

    Usage:
        with batch_update(sketch):
            for point in points:
                point.co = new_pos  # no rebuild per write
        # rebuild_segments called once here
    """
    def __init__(self, sketch):
        self.sketch = sketch

    def __enter__(self):
        _batch_sketches.add(id(self.sketch))
        return self

    def __exit__(self, *args):
        _batch_sketches.discard(id(self.sketch))
        rebuild_segments(self.sketch)


def is_batching(sketch):
    return id(sketch) in _batch_sketches


def is_fixed(sketch, curve_id):
    """Check if a curve is directly marked as fixed."""
    cd, idx, _ = get_curve_data(sketch, curve_id)
    if cd is None:
        return False
    fix_attr = cd.attributes.get("fixed")
    return bool(fix_attr and fix_attr.data[idx].value)


def rebuild_segments(sketch):
    """Rebuild all segment curve positions from their referenced point curves.

    Lines: copy endpoint positions from point curves.
    Arcs/circles: recompute bezier geometry from center/start/end point curves.

    Call after modifying point positions to keep segment data consistent.
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
    sp_attr = cd.attributes.get("start_point_id")
    ep_attr = cd.attributes.get("end_point_id")
    cp_attr = cd.attributes.get("center_point_id")
    if not type_attr:
        return

    for i in range(n):
        ctype = type_attr.data[i].value
        if ctype == SketchCurveType.POINT:
            continue

        curve_slice = cd.curves[i]

        if ctype == SketchCurveType.LINE:
            sp_cid = sp_attr.data[i].value if sp_attr else 0
            ep_cid = ep_attr.data[i].value if ep_attr else 0
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
            cp_cid = cp_attr.data[i].value if cp_attr else 0
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
                sp_cid = sp_attr.data[i].value if sp_attr else 0
                ep_cid = ep_attr.data[i].value if ep_attr else 0
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
        elif attr.data_type == 'FLOAT':
            data = np.zeros(domain_len, dtype=np.float32)
            attr.data.foreach_get("value", data)
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
        if info["type"] == 'FLOAT_VECTOR':
            attr.data.foreach_set("vector", info["data"])
        else:
            attr.data.foreach_set("value", info["data"])

    invalidate_curve_id_cache(sketch)
