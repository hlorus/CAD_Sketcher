"""Helpers for native free-3D sketches backed by Blender Curves."""

import bpy
from mathutils import Matrix, Vector

from .constants import BezierHandleType, SketchCurveType
from .curve_ref import (
    LineRef,
    PointRef,
    _allocate,
    _ensure_attrs,
    _ensure_curve_data,
    _invalidate,
)
from .sketch_ref import Sketch, stamp_sketch_props

SKETCH_3D_TAG = "is_3d_sketch"
SKETCH_3D_ORIGIN_TAG = "is_3d_sketch_origin"


def is_3d_sketch(sketch):
    """Return whether *sketch* is a native free-3D sketch."""
    return bool(sketch and getattr(sketch, "is_3d", False))


def create_3d_sketch(context, name="3D Sketch", matrix=None):
    """Create a Curves-backed 3D sketch parented to a stable origin Empty.

    The Curves object keeps the same structural shape as a 2D sketch, but its
    parent is an unconstrained origin Empty rather than a workplane. Geometry
    remains free in XYZ and the Empty provides the stable origin required by
    placement/editing helpers.
    """
    origin = bpy.data.objects.new(f"{name} Origin", None)
    origin.empty_display_type = "PLAIN_AXES"
    origin.empty_display_size = 0.5
    context.scene.collection.objects.link(origin)
    origin.matrix_world = matrix.copy() if matrix is not None else Matrix.Identity(4)
    origin[SKETCH_3D_ORIGIN_TAG] = True

    curve = bpy.data.hair_curves.new(name)
    obj = bpy.data.objects.new(name, curve)
    context.scene.collection.objects.link(obj)
    stamp_sketch_props(obj)
    obj[SKETCH_3D_TAG] = True

    from ..utilities.curve_data import _ensure_convert_modifier

    _ensure_convert_modifier(obj)

    obj.parent = origin
    obj.matrix_parent_inverse = Matrix.Identity(4)
    obj.matrix_basis = Matrix.Identity(4)
    obj.lock_location = (True, True, True)
    obj.lock_rotation = (True, True, True)
    obj.lock_scale = (True, True, True)
    return Sketch(obj)


def _local_point_position(ref):
    if not isinstance(ref, PointRef) or not ref._resolve():
        return Vector((0.0, 0.0, 0.0))
    point_index = ref._curve_slice.points[0].index
    return Vector(ref._curve_data.points[point_index].position)


def create_point_3d(sketch, co, construction=False, fixed=False, name=None):
    """Create a native point curve with an XYZ position in a 3D sketch."""
    if not is_3d_sketch(sketch):
        raise ValueError("create_point_3d requires a native 3D sketch")

    from ..utilities.curve_data import default_curve_name, set_attribute

    curve_data = _ensure_curve_data(sketch)
    if curve_data is None:
        return None

    position = Vector(co).to_3d()
    cid = _allocate(sketch)
    curve_data.add_curves([1])
    _ensure_attrs(curve_data, len(curve_data.curves) - 1)

    curve_idx = len(curve_data.curves) - 1
    curve_slice = curve_data.curves[curve_idx]
    curve_slice.points[0].position = tuple(position)

    attrs = curve_data.attributes
    set_attribute(attrs, "curve_id", cid, curve_idx)
    set_attribute(attrs, "sketch_type", SketchCurveType.POINT, curve_idx)
    set_attribute(attrs, "construction", construction, curve_idx)
    set_attribute(attrs, "fixed", fixed, curve_idx)
    set_attribute(attrs, "visible", True, curve_idx)
    set_attribute(
        attrs,
        "name",
        name or default_curve_name(curve_data, SketchCurveType.POINT),
        curve_idx,
    )

    _invalidate(sketch)
    curve_data.update_tag()
    return PointRef(sketch, cid)


def create_line_3d(sketch, p1, p2, construction=False, name=None):
    """Create a native line curve between two 3D point curves."""
    if not is_3d_sketch(sketch):
        raise ValueError("create_line_3d requires a native 3D sketch")
    if not isinstance(p1, PointRef) or not isinstance(p2, PointRef):
        raise TypeError("3D lines require PointRef endpoints")

    from ..utilities.curve_data import default_curve_name, set_attribute

    curve_data = _ensure_curve_data(sketch)
    if curve_data is None:
        return None

    cid = _allocate(sketch)
    curve_data.add_curves([2])
    curve_data.set_types(type="BEZIER")
    _ensure_attrs(curve_data, len(curve_data.curves) - 1)

    curve_idx = len(curve_data.curves) - 1
    curve_slice = curve_data.curves[curve_idx]
    positions = (_local_point_position(p1), _local_point_position(p2))

    attrs = curve_data.attributes
    for point, position in zip(curve_slice.points, positions):
        curve_data.points[point.index].position = tuple(position)
        attrs["handle_left"].data[point.index].vector = position
        attrs["handle_right"].data[point.index].vector = position
        attrs["handle_type_left"].data[point.index].value = BezierHandleType.FREE
        attrs["handle_type_right"].data[point.index].value = BezierHandleType.FREE

    set_attribute(attrs, "curve_id", cid, curve_idx)
    set_attribute(attrs, "sketch_type", SketchCurveType.LINE, curve_idx)
    set_attribute(attrs, "start_point_id", p1.curve_id, curve_idx)
    set_attribute(attrs, "end_point_id", p2.curve_id, curve_idx)
    set_attribute(attrs, "construction", construction, curve_idx)
    set_attribute(attrs, "fixed", False, curve_idx)
    set_attribute(attrs, "visible", True, curve_idx)
    set_attribute(
        attrs,
        "name",
        name or default_curve_name(curve_data, SketchCurveType.LINE),
        curve_idx,
    )

    _invalidate(sketch)
    curve_data.update_tag()
    return LineRef(sketch, cid)


def rebuild_3d_lines(sketch):
    """Sync native line geometry from its referenced 3D point curves."""
    from ..utilities.curve_data import compute_merge_ids, read_uuid_list

    curve_data = sketch.target_object.data
    type_attr = curve_data.attributes.get("sketch_type")
    if not type_attr:
        return

    cid_list = read_uuid_list(curve_data, "curve_id")
    sp_list = read_uuid_list(curve_data, "start_point_id")
    ep_list = read_uuid_list(curve_data, "end_point_id")

    point_positions = {}
    for curve_idx, cid in enumerate(cid_list):
        if type_attr.data[curve_idx].value != SketchCurveType.POINT:
            continue
        curve_slice = curve_data.curves[curve_idx]
        if not curve_slice.points_length:
            continue
        point_index = curve_slice.points[0].index
        point_positions[cid] = Vector(curve_data.points[point_index].position)

    handle_left = curve_data.attributes.get("handle_left")
    handle_right = curve_data.attributes.get("handle_right")

    for curve_idx in range(len(curve_data.curves)):
        if type_attr.data[curve_idx].value != SketchCurveType.LINE:
            continue
        curve_slice = curve_data.curves[curve_idx]
        if curve_slice.points_length < 2:
            continue

        for point_offset, cid in enumerate((sp_list[curve_idx], ep_list[curve_idx])):
            position = point_positions.get(cid)
            if position is None:
                continue
            point_index = curve_slice.points[point_offset].index
            curve_data.points[point_index].position = tuple(position)
            if handle_left:
                handle_left.data[point_index].vector = position
            if handle_right:
                handle_right.data[point_index].vector = position

    compute_merge_ids(sketch)
    curve_data.update_tag()
