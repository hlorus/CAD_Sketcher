"""Helpers for native free-3D sketches backed by Blender Curves."""

import bpy
from mathutils import Matrix, Vector

from .constants import SketchCurveType
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


def _set_convert_fill(modifier, value):
    """Set the shared converter's Fill input across Blender versions."""
    if modifier is None or modifier.node_group is None:
        return False

    fill_socket = next(
        (
            item
            for item in modifier.node_group.interface.items_tree
            if getattr(item, "item_type", "") == "SOCKET"
            and getattr(item, "in_out", "") == "INPUT"
            and item.name == "Fill"
        ),
        None,
    )
    if fill_socket is None:
        return False

    props = getattr(modifier, "properties", None)
    if props is not None and hasattr(props, "inputs"):
        getattr(props.inputs, fill_socket.identifier).value = bool(value)
    else:
        modifier[fill_socket.identifier] = bool(value)

    # When the guard resets Fill from inside depsgraph_update_post, changing the
    # modifier input alone can leave the already-evaluated Fill Curve result in
    # the viewport until some unrelated edit dirties the object. Explicitly tag
    # the modifier owner so Blender schedules a fresh Geometry Nodes evaluation
    # with Fill=False on the next depsgraph pass.
    owner = getattr(modifier, "id_data", None)
    if owner is not None:
        owner.update_tag()
    return True


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

    modifier = _ensure_convert_modifier(obj)
    # A free-3D sketch is not a planar profile. The shared converter defaults
    # Fill on for normal 2D sketches, but Fill Curve necessarily planarizes a
    # non-coplanar loop and makes Blender's evaluated geometry diverge from the
    # native XYZ overlay. Keep 3D sketches wire/free-space by default; users can
    # constrain geometry to a plane before opting into profile-style operations.
    _set_convert_fill(modifier, False)

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
    return Vector(ref._curve_data.points[point_index].position).to_3d()


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
    curve_idx = len(curve_data.curves) - 1
    # add_curves() does not promise a linear curve type. Blender's set_types()
    # default is CATMULL_ROM, and Blender 5.0's rewritten viewport curve drawing
    # can hit invalid evaluation paths on degenerate 1/2-point spline types.
    # Native 3D points/lines are intentionally linear, so make that explicit.
    curve_data.set_types(type="POLY", indices=[curve_idx])
    _ensure_attrs(curve_data, curve_idx)

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
    """Create a native straight line curve between two 3D point curves.

    The segment is stored as POLY geometry. 2D lines use Bezier curves because
    the shared 2D curve machinery also services arcs/handles, but a native 3D
    line has no handles and must preserve the endpoint XYZ values verbatim.
    Keeping this path handle-free also prevents any 2D handle/default state from
    re-projecting the generated segment onto XY during interactive creation.
    """
    if not is_3d_sketch(sketch):
        raise ValueError("create_line_3d requires a native 3D sketch")
    if not isinstance(p1, PointRef) or not isinstance(p2, PointRef):
        raise TypeError("3D lines require PointRef endpoints")

    from ..utilities.curve_data import default_curve_name, set_attribute

    curve_data = _ensure_curve_data(sketch)
    if curve_data is None:
        return None

    positions = (_local_point_position(p1), _local_point_position(p2))
    cid = _allocate(sketch)
    curve_data.add_curves([2])
    curve_idx = len(curve_data.curves) - 1
    # Keep the new line explicitly POLY instead of relying on the Curves data
    # block's implicit/default type. This matters on Blender 5.0 where the
    # viewport drawing path changed substantially and a two-point non-linear
    # spline can reach unsafe GPU curve evaluation code.
    curve_data.set_types(type="POLY", indices=[curve_idx])
    _ensure_attrs(curve_data, curve_idx)

    curve_slice = curve_data.curves[curve_idx]
    # Set the raw curve points directly from referenced native 3D points so Z
    # can never be reconstructed via a 2D API.
    for point, position in zip(curve_slice.points, positions):
        curve_data.points[point.index].position = tuple(position)

    attrs = curve_data.attributes
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
    rebuild_3d_lines(sketch)
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
        point_positions[cid] = Vector(curve_data.points[point_index].position).to_3d()

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
            # Older files may contain Bezier-backed 3D lines from the first
            # implementation. Keep their handles coincident with the 3D point
            # rather than allowing stale XY handle data to distort the segment.
            if handle_left:
                handle_left.data[point_index].vector = position
            if handle_right:
                handle_right.data[point_index].vector = position

    compute_merge_ids(sketch)
    curve_data.update_tag()
