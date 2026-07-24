"""Workplane empty management."""

import math

import bpy
from mathutils import Vector


# ---------------------------------------------------------------------------
# Workplane empty IDs for picking
# ---------------------------------------------------------------------------

WP_ID_XY = 0xF00001
WP_ID_XZ = 0xF00002
WP_ID_YZ = 0xF00003

# Sequential pick IDs for non-origin empties start here
_EMPTY_PICK_START = 0xE00001

# Fraction of the view distance used as the workplane's half-size when drawing
# and hit-testing its rectangle.
WP_SIZE_FACTOR = 0.1

# Grab band around the workplane outline, as a fraction of its half-size. A hit
# within this distance of the rectangle edge counts as a border hit.
WP_BORDER_FRACTION = 0.05

# Gap between an origin plane's inner corner and the world origin, as a fraction
# of its half-size, so the quadrants float clear of the axes.
WP_ORIGIN_GAP_FRACTION = 0.1

WP_ID_MAP = {}


def get_workplane_empty_by_id(wp_id):
    """Look up a workplane empty by its picking ID."""
    return WP_ID_MAP.get(wp_id)


# ---------------------------------------------------------------------------
# Drawable workplane enumeration, sizing and picking
# ---------------------------------------------------------------------------

def iter_wp_empties(context):
    """Yield (empty_obj, pick_id) for all drawable workplane empties.

    The three origin empties get their fixed WP_ID_* ids; every other visible
    empty gets a sequential id starting at ``_EMPTY_PICK_START``. Ordering is
    deterministic within a frame so draw and hit-test agree on ids.
    """
    sketcher = context.scene.sketcher
    origin_names = set()
    show_origin = sketcher.show_origin

    for wp_obj, wp_id in (
        (sketcher.wp_xy, WP_ID_XY),
        (sketcher.wp_xz, WP_ID_XZ),
        (sketcher.wp_yz, WP_ID_YZ),
    ):
        if wp_obj:
            # Track the name so the generic loop below never re-yields an origin,
            # but only expose it for drawing/picking when the toggle is on.
            origin_names.add(wp_obj.name)
            if show_origin:
                yield wp_obj, wp_id

    pick_id = _EMPTY_PICK_START
    for obj in context.scene.objects:
        if obj.type != 'EMPTY' or obj.name in origin_names or obj.hide_viewport:
            continue
        yield obj, pick_id
        pick_id += 1


def get_empty_by_pick_id(context, pick_id):
    """Resolve a drawable empty from its pick id (see :func:`iter_wp_empties`)."""
    for wp_obj, wp_pick_id in iter_wp_empties(context):
        if wp_pick_id == pick_id:
            return wp_obj
    return None


def wp_display_half_size(context):
    """Half-size of a workplane rectangle in world units for the current view."""
    view_distance = 1.0
    if context.region_data:
        view_distance = context.region_data.view_distance
    return view_distance * WP_SIZE_FACTOR


def wp_plane_bounds(context, pick_id):
    """Local-space rectangle (min_x, min_y, max_x, max_y) for a workplane.

    Origin planes are drawn in their positive quadrant (corner at the origin,
    extending toward +X/+Y) so the axis directions are obvious and the three
    planes only overlap along the positive axes rather than at the origin.
    Other planes stay centered on their object, where no quadrant is meaningful.

    Shared by drawing and hit-testing so the visible and pickable areas match.
    """
    h = wp_display_half_size(context)
    if pick_id in (WP_ID_XY, WP_ID_XZ, WP_ID_YZ):
        gap = h * WP_ORIGIN_GAP_FRACTION
        side = 2.0 * h
        return gap, gap, gap + side, gap + side
    return -h, -h, h, h


def hit_test_workplane(context, coords, border_only=False):
    """Analytic pick of the drawable workplane empty under the cursor.

    Casts a ray through ``coords`` against each workplane rectangle and returns
    the ``(pick_id, empty)`` of the nearest hit, or ``(None, None)``. Uses
    :func:`get_pos_2d` so no offscreen id-buffer is needed.

    When ``border_only`` is True, only hits within the grab band around the
    rectangle outline count (used to give the border pick priority over meshes);
    otherwise any hit inside the rectangle counts.
    """
    from .view import get_pos_2d, get_picking_origin_dir

    half = wp_display_half_size(context)
    border_width = half * WP_BORDER_FRACTION
    ray_origin, _ = get_picking_origin_dir(context, coords)

    best = None
    best_dist = None
    for wp_obj, pick_id in iter_wp_empties(context):
        local = get_pos_2d(context, wp_obj, coords)
        if local is None:
            continue

        # Signed distances past each edge (<= 0 means inside on that axis)
        min_x, min_y, max_x, max_y = wp_plane_bounds(context, pick_id)
        dx = max(min_x - local.x, local.x - max_x)
        dy = max(min_y - local.y, local.y - max_y)
        inside = dx <= 0.0 and dy <= 0.0

        if border_only:
            # Distance to the rectangle boundary (0 on the edge)
            if inside:
                border_dist = -max(dx, dy)
            else:
                border_dist = math.hypot(max(dx, 0.0), max(dy, 0.0))
            if border_dist > border_width:
                continue
        elif not inside:
            continue

        # Depth-order hits so the nearest workplane wins
        dist = (wp_obj.matrix_world.translation - ray_origin).length_squared
        if best_dist is None or dist < best_dist:
            best = (pick_id, wp_obj)
            best_dist = dist

    return best if best is not None else (None, None)


def resolve_sketch_base(context, coords):
    """Resolve what the Add Sketch cursor is over, honoring pick priority.

    The order is: workplane outline > mesh face > workplane interior, so an
    outline is never obscured by a mesh. Shared by the operator's pick and the
    gizmo's hover so both always agree. Returns one of:

        ("border", pick_id, empty)
        ("mesh", mesh_object, face_index)
        ("interior", pick_id, empty)
        (None, None, None)
    """
    from ..stateful_operator.utilities.geometry import get_mesh_element

    pick_id, empty = hit_test_workplane(context, coords, border_only=True)
    if empty is not None:
        return "border", pick_id, empty

    ob, elem_type, index = get_mesh_element(context, coords, face=True)
    if ob and elem_type == "FACE":
        return "mesh", ob, index

    pick_id, empty = hit_test_workplane(context, coords)
    if empty is not None:
        return "interior", pick_id, empty

    return None, None, None


# ---------------------------------------------------------------------------
# Workplane empty creation
# ---------------------------------------------------------------------------

def ensure_workplane_empty(sketch):
    """Ensure the sketch has a workplane empty object.

    Creates an empty from the sketch's entity workplane transform
    if it doesn't exist yet.

    Returns the empty Object, or None.
    """
    if sketch.workplane_object:
        return sketch.workplane_object

    if not hasattr(sketch, 'wp') or not sketch.wp:
        return None

    name = f"WP_{sketch.name}"
    empty = bpy.data.objects.new(name, None)
    empty.empty_display_type = 'SINGLE_ARROW'
    empty.hide_viewport = True
    empty.lock_location = (True, True, True)
    empty.lock_rotation = (True, True, True)
    empty.lock_scale = (True, True, True)
    empty.matrix_world = sketch.wp.matrix_basis

    scene = bpy.context.scene
    if empty.name not in scene.collection.objects:
        scene.collection.objects.link(empty)

    sketch.workplane_object = empty
    return empty


def ensure_origin_workplane_empties(context):
    """Create the three origin workplane empties (XY, XZ, YZ) if they don't exist."""
    from mathutils import Euler

    sketcher = context.scene.sketcher
    scene = context.scene

    configs = [
        ("wp_xy", "WP_XY", Euler((0, 0, 0)), WP_ID_XY),
        ("wp_xz", "WP_XZ", Euler((1.5707963, 0, 0)), WP_ID_XZ),
        ("wp_yz", "WP_YZ", Euler((1.5707963, 0, 1.5707963)), WP_ID_YZ),
    ]

    for prop_name, name, euler, wp_id in configs:
        existing = getattr(sketcher, prop_name)
        if existing:
            WP_ID_MAP[wp_id] = existing
            continue

        empty = bpy.data.objects.new(name, None)
        empty.empty_display_type = 'SINGLE_ARROW'
        empty.matrix_world = euler.to_matrix().to_4x4()
        empty.hide_viewport = True
        empty.lock_location = (True, True, True)
        empty.lock_rotation = (True, True, True)
        empty.lock_scale = (True, True, True)

        if empty.name not in scene.collection.objects:
            scene.collection.objects.link(empty)

        setattr(sketcher, prop_name, empty)
        WP_ID_MAP[wp_id] = empty


def get_workplane_origin_normal(sketch):
    """Get the workplane origin and normal from the workplane empty.

    Returns:
        tuple: (origin: Vector, normal: Vector) or (None, None)
    """
    wp_obj = sketch.workplane_object if sketch else None

    if not wp_obj and sketch and sketch.target_object and sketch.target_object.parent:
        wp_obj = sketch.target_object.parent

    if wp_obj:
        mat = wp_obj.matrix_world
        return mat.translation.copy(), Vector(mat.col[2][:3]).normalized()

    return None, None
