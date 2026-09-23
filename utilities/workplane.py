"""Workplane empty management."""

import logging
import math

import bpy
from mathutils import Vector

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Workplane empty IDs for picking
# ---------------------------------------------------------------------------

WP_ID_XY = 0xF00001
WP_ID_XZ = 0xF00002
WP_ID_YZ = 0xF00003

# Blender-style axis colors used to tint each origin plane by its normal
# (XY -> Z/blue, XZ -> Y/green, YZ -> X/red) and the short label drawn on it.
# A plane that stands for no axis: its label is tinted like the plane itself.
_PLAIN = (0.55, 0.55, 0.58)
_AXIS_X = (0.80, 0.24, 0.24)
_AXIS_Y = (0.34, 0.67, 0.20)
_AXIS_Z = (0.22, 0.40, 0.80)
# Pick ids for the base planes of the part in focus (see utilities.part).
WP_ID_PART_XY = 0xF00011
WP_ID_PART_XZ = 0xF00012
WP_ID_PART_YZ = 0xF00013

_PART_PLANE_IDS = (WP_ID_PART_XY, WP_ID_PART_XZ, WP_ID_PART_YZ)
_PART_PLANE_AXIS_ORDER = {"XY": 0, "XZ": 1, "YZ": 2}

# A part's planes stand in for the world's rather than being drawn beside them, so
# they can be close to full size; still smaller, so which set you are looking at
# is obvious at a glance.
PART_PLANE_SIZE_FACTOR = 0.8

# A part's base planes read as the same axes as the world's, so they are tinted
# the same way: the part's frame is what tells them apart, not the colour.
ORIGIN_AXIS_COLOR = {
    WP_ID_XY: _AXIS_Z,
    WP_ID_XZ: _AXIS_Y,
    WP_ID_YZ: _AXIS_X,
    WP_ID_PART_XY: _AXIS_Z,
    WP_ID_PART_XZ: _AXIS_Y,
    WP_ID_PART_YZ: _AXIS_X,
}

# The scene's datums say so, since a part's planes replace them on screen and the
# axis alone would not tell you which frame you are about to sketch in.
ORIGIN_LABEL = {
    WP_ID_XY: "Origin XY",
    WP_ID_XZ: "Origin XZ",
    WP_ID_YZ: "Origin YZ",
}


# A name is the object's, so it can be anything: cut it rather than let it
# shrink to a hairline trying to fit the plane.
_LABEL_MAX_CHARS = 22


def is_base_plane(pick_id) -> bool:
    """Whether ``pick_id`` is one of the six base planes (world or part)."""
    return pick_id in ORIGIN_LABEL or pick_id in _PART_PLANE_IDS


def label_lines(label: str, max_lines: int = 2) -> list:
    """Split a plane's label into at most ``max_lines`` lines to draw.

    A name has to fit a square, so it breaks at the space nearest the middle
    rather than running off the edge, and an over-long one is cut short: better
    an ellipsis than a line of unreadable glyphs.
    """
    label = label.strip()
    if len(label) > _LABEL_MAX_CHARS:
        label = label[: _LABEL_MAX_CHARS - 1].rstrip() + "\u2026"

    lines = [label]
    for _ in range(max_lines - 1):
        longest = max(lines, key=len)
        if " " not in longest.strip():
            break
        middle = len(longest) // 2
        spaces = [i for i, ch in enumerate(longest) if ch == " "]
        at = min(spaces, key=lambda i: abs(i - middle))
        lines[lines.index(longest) : lines.index(longest) + 1] = [
            longest[:at].strip(),
            longest[at + 1 :].strip(),
        ]
    return [line for line in lines if line]


def workplane_color(pick_id) -> tuple:
    """The axis colour a plane's label is tinted with, grey for a plain one."""
    return ORIGIN_AXIS_COLOR.get(pick_id, _PLAIN)


def workplane_label(wp_obj, pick_id) -> str:
    """The text drawn on a workplane: what the object is called.

    The scene's datums have no object name worth reading ("WP_XY"), so they say
    "Origin XY" instead. Everything else -- a part's base planes, a plane on a
    face, one the user placed -- says its own name, which for a part's plane is
    the part and the axis ("Bracket XY"). Drawn over two lines, so which part you
    are about to sketch in reads at a glance.
    """
    label = ORIGIN_LABEL.get(pick_id)
    if label is not None:
        return label
    return wp_obj.name if wp_obj is not None else ""


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


def _is_group_empty(obj) -> bool:
    """Whether ``obj`` is an Empty that stands for a group rather than a plane.

    An assembly root and a part placement are both Empties, so the picker would
    otherwise offer them as workplanes. Sketching on one promises more than it
    delivers: the sketch would sit at that frame but belong to nothing and would
    not follow it. Assembly-level sketches are worth having, but they need their
    own answer for what happens when one is made solid.
    """
    from .part import is_assembly_root, is_part_instance

    return is_assembly_root(obj) or is_part_instance(obj)


def iter_wp_empties(context):
    """Yield (empty_obj, pick_id) for all drawable workplane empties.

    The three origin empties get their fixed WP_ID_* ids; every other visible
    empty gets a sequential id starting at ``_EMPTY_PICK_START``. Ordering is
    deterministic within a frame so draw and hit-test agree on ids.
    """
    from .part import PART_PLANE_KEY, focused_part, part_plane_objects, part_root_of

    sketcher = context.scene.sketcher
    origin_names = set()
    show_origin = sketcher.show_origin

    focus = focused_part(context)
    # The base planes of the part in focus, in the part's own frame: sketching on
    # a moved or rotated part otherwise only offers world-aligned planes.
    part_planes = part_plane_objects(context) if show_origin else []

    for wp_obj, wp_id in (
        (sketcher.wp_xy, WP_ID_XY),
        (sketcher.wp_xz, WP_ID_XZ),
        (sketcher.wp_yz, WP_ID_YZ),
    ):
        if wp_obj:
            # Track the name so the generic loop below never re-yields an origin,
            # but only expose it for drawing/picking when the toggle is on. While
            # a part is in focus its own planes stand in for them: showing both
            # sets at once is six rectangles for three choices, and the part's
            # frame is the one being worked in. Deselect to sketch on the world.
            origin_names.add(wp_obj.name)
            if show_origin and not part_planes:
                yield wp_obj, wp_id

    for plane in part_planes:
        origin_names.add(plane.name)
        yield plane, _PART_PLANE_IDS[_PART_PLANE_AXIS_ORDER[plane[PART_PLANE_KEY]]]

    pick_id = _EMPTY_PICK_START
    for obj in context.scene.objects:
        # visible_get() covers the eye-icon hide and collection visibility too,
        # not just hide_viewport (the monitor icon) -- an empty hidden with the
        # eye was still getting its workplane overlay drawn.
        # Ours are hidden on purpose (see hide_managed_workplane) but must stay
        # pickable; an empty the user made is offered only while they can see it.
        if obj.type != "EMPTY" or obj.name in origin_names:
            continue
        if not is_managed_workplane(obj) and not obj.visible_get():
            continue
        if _is_group_empty(obj):
            continue
        if PART_PLANE_KEY in obj:
            # A part's base planes are offered only for the part in focus, by the
            # branch above. Reaching them here (they are managed, so being hidden
            # does not stop this loop) would draw every part's planes at once,
            # unlabelled and in the themed default colour.
            continue
        owner = part_root_of(obj)
        if owner is not None and owner != focus:
            # Every sketch has a plane, so a file full of parts would offer one
            # rectangle per sketch in it. A part's planes are its own business
            # until you are working on it; a plane belonging to no part (a global
            # sketch, or one the user made) is always on offer.
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
    if pick_id in _PART_PLANE_IDS:
        h *= PART_PLANE_SIZE_FACTOR
    if pick_id in (WP_ID_XY, WP_ID_XZ, WP_ID_YZ) + _PART_PLANE_IDS:
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
    from .view import get_picking_origin_dir, get_pos_2d

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


# Stamped on every workplane Empty this addon creates, so a workplane the user
# placed themselves is never silently deleted or re-anchored.
MANAGED_WP_KEY = "slvs:managed_wp"


def mark_managed_workplane(empty) -> None:
    """Record that this addon created ``empty`` as a workplane."""
    empty[MANAGED_WP_KEY] = True


def is_managed_workplane(empty) -> bool:
    """Whether this addon created ``empty`` (and so may retire it)."""
    return bool(empty is not None and empty.get(MANAGED_WP_KEY, False))


def hide_managed_workplane(empty, context) -> None:
    """Take a workplane we created out of the viewport, keeping it pickable.

    ``hide_set`` needs the object present in the view layer, and linking alone
    does not resync it, so the layer is updated first. A failure is not worth
    aborting a pick over: a visible workplane still works.

    """
    context.view_layer.update()
    try:
        _hide_managed_empty(empty, context.scene)
    except RuntimeError:
        logger.warning("Could not hide workplane '%s'", empty.name)


def _hide_managed_empty(empty, scene):
    """Hide an addon-managed workplane empty without dropping it from eval.

    ``hide_viewport`` (the monitor icon) excludes the object from depsgraph
    evaluation, so its ``matrix_world`` is never recomputed from its
    rotation/parent after a file load or when driven/animated. That left every
    orthogonal plane's ``matrix_world`` stale at identity, collapsing them onto
    XY (#670). The eye-icon hide keeps the object evaluated, so use that (in
    every view layer) plus ``hide_select`` so it can't be clicked, and clear any
    legacy ``hide_viewport`` so old files re-evaluate. The empty must already be
    linked to the view layer.
    """
    empty.hide_viewport = False
    empty.hide_select = True
    for view_layer in scene.view_layers:
        empty.hide_set(True, view_layer=view_layer)


def _managed_empty_needs_hide(empty, scene):
    """Whether ``empty`` has drifted from the hidden state ``_hide_managed_empty``
    enforces (undo/redo or a new view layer can unhide it)."""
    if empty.hide_viewport or not empty.hide_select:
        return True
    return any(not empty.hide_get(view_layer=vl) for vl in scene.view_layers)


def ensure_workplane_empty(sketch):
    """Ensure the sketch has a workplane empty object.

    Creates an empty from the sketch's entity workplane transform
    if it doesn't exist yet.

    Returns the empty Object, or None.
    """
    if sketch.workplane_object:
        return sketch.workplane_object

    if not hasattr(sketch, "wp") or not sketch.wp:
        return None

    name = f"WP_{sketch.name}"
    empty = bpy.data.objects.new(name, None)
    empty.empty_display_type = "SINGLE_ARROW"
    mark_managed_workplane(empty)
    empty.lock_location = (True, True, True)
    empty.lock_rotation = (True, True, True)
    empty.lock_scale = (True, True, True)
    empty.matrix_world = sketch.wp.matrix_basis

    scene = bpy.context.scene
    from .collections import link_to_scene_root

    # Scene level to start with; the part sync claims it once its sketch is in a
    # part.
    link_to_scene_root(empty, scene)

    # Hide only after linking: hide_set needs the object in the view layer.
    _hide_managed_empty(empty, scene)

    sketch.workplane_object = empty
    return empty


# (prop_name, object_name, local rotation, pick id) for the three origin planes.
_ORIGIN_WP_CONFIGS = (
    ("wp_xy", "WP_XY", (0.0, 0.0, 0.0), WP_ID_XY),
    ("wp_xz", "WP_XZ", (math.pi / 2, 0.0, 0.0), WP_ID_XZ),
    ("wp_yz", "WP_YZ", (math.pi / 2, 0.0, math.pi / 2), WP_ID_YZ),
)


def _matrix_differs(a, b, eps=1e-6):
    return any(abs(a[i][j] - b[i][j]) > eps for i in range(4) for j in range(4))


def _target_matrix(euler_tuple):
    from mathutils import Euler

    return Euler(euler_tuple).to_matrix().to_4x4()


def _enforce_origin_empty(empty, euler_tuple, scene):
    """Re-assert an origin empty's fixed transform and hidden state.

    Undo/redo can leave these at identity (all three then stack flat -> the
    mushy overlap of #571); they must never drift, so re-apply rather than
    trust the stored state. Only writes when it actually differs to avoid
    churning the depsgraph.
    """
    target = _target_matrix(euler_tuple)
    if _matrix_differs(empty.matrix_world, target):
        empty.matrix_world = target
    if _managed_empty_needs_hide(empty, scene):
        _hide_managed_empty(empty, scene)


def repair_origin_workplanes(context):
    """Fix the transform/visibility of existing origin empties (no creation)."""
    sketcher = context.scene.sketcher
    scene = context.scene
    for prop_name, _name, euler_tuple, wp_id in _ORIGIN_WP_CONFIGS:
        existing = getattr(sketcher, prop_name)
        if existing:
            WP_ID_MAP[wp_id] = existing
            _enforce_origin_empty(existing, euler_tuple, scene)


def ensure_origin_workplane_empties(context):
    """Create the three origin workplane empties (XY, XZ, YZ) if missing, and
    re-assert their fixed transform/hidden state if they already exist."""
    sketcher = context.scene.sketcher
    scene = context.scene

    for prop_name, name, euler_tuple, wp_id in _ORIGIN_WP_CONFIGS:
        existing = getattr(sketcher, prop_name)
        if existing:
            WP_ID_MAP[wp_id] = existing
            _enforce_origin_empty(existing, euler_tuple, scene)
            continue

        empty = bpy.data.objects.new(name, None)
        empty.empty_display_type = "SINGLE_ARROW"
        empty.matrix_world = _target_matrix(euler_tuple)
        empty.lock_location = (True, True, True)
        empty.lock_rotation = (True, True, True)
        empty.lock_scale = (True, True, True)

        from .collections import link_origin_workplane

        link_origin_workplane(empty, scene)

        # Hide only after linking: hide_set needs the object in the view layer.
        _hide_managed_empty(empty, scene)

        setattr(sketcher, prop_name, empty)
        WP_ID_MAP[wp_id] = empty


def get_workplane_origin_normal(sketch):
    """Get the workplane origin and normal from the workplane empty.

    Returns:
        tuple: (origin: Vector, normal: Vector) or (None, None)
    """
    if not sketch:
        return None, None

    mat = sketch.plane_matrix
    return mat.translation.copy(), Vector(mat.col[2][:3]).normalized()


# ---------------------------------------------------------------------------
# Base-plane axes
#
# An axis is not an object of its own: it is one of a base plane's own
# directions. The plane empties are parented into their part, so reading an
# axis off one keeps it bound to that part -- move the part and the axis moves
# with it -- and the world's datums give the world axes the same way.
# ---------------------------------------------------------------------------

AXIS_LETTERS = ("X", "Y", "Z")
# Pick ids for the three axes, in the same reserved block as the base planes.
AXIS_ID_X = 0xF00021
AXIS_ID_Y = 0xF00022
AXIS_ID_Z = 0xF00023
_AXIS_IDS = (AXIS_ID_X, AXIS_ID_Y, AXIS_ID_Z)
AXIS_COLOR = {AXIS_ID_X: _AXIS_X, AXIS_ID_Y: _AXIS_Y, AXIS_ID_Z: _AXIS_Z}

# How far an axis line reaches from its origin, as a fraction of the drawn
# workplane's half size: long enough to aim at, short enough not to fill the view.
AXIS_LENGTH_FACTOR = 2.0


def axis_plane(context):
    """The base plane whose frame the offered axes are read from, or None.

    The XY plane of the part in focus, and otherwise the scene's: the same
    "a part's frame stands in for the world's" rule the planes themselves follow.
    """
    from .part import PART_PLANE_KEY, part_plane_objects

    for plane in part_plane_objects(context):
        if plane.get(PART_PLANE_KEY) == "XY":
            return plane
    return context.scene.sketcher.wp_xy


def iter_axis_candidates(context):
    """Yield ``(plane, index, pick_id)`` for each axis on offer.

    ``index`` is which of the plane's own directions the axis is (0/1/2 for
    X/Y/Z), so the pair resolves live through the plane's matrix rather than
    freezing a direction at pick time.
    """
    plane = axis_plane(context)
    if plane is None:
        return
    for index, pick_id in enumerate(_AXIS_IDS):
        yield plane, index, pick_id


def axis_endpoints(plane, index, context=None):
    """World ends of one of ``plane``'s axes, reaching both ways from it.

    An axis is a line, not a ray: it is drawn to both sides of the frame and a
    revolve does not care which end was picked, so the same two ends serve the
    drawing and the hit test. Halves that disagree is how the negative side came
    to be drawn but not pickable.
    """
    matrix = plane.matrix_world
    origin = matrix.translation.copy()
    direction = matrix.to_3x3().col[index].normalized()
    reach = wp_display_half_size(context) if context else 1.0
    span = direction * reach * AXIS_LENGTH_FACTOR
    return origin - span, origin + span


def axis_label(plane, index) -> str:
    """The text drawn on an axis: whose frame it is, and which direction.

    Reads like the planes do ("Bracket X"), since a part's axes stand in for the
    world's exactly as its planes do and the letter alone would not say whose.
    """
    from .part import PART_PLANE_KEY

    letter = AXIS_LETTERS[index]
    if plane.get(PART_PLANE_KEY):
        owner = plane.name.rsplit(" ", 1)[0]
        return f"{owner} {letter}"
    return f"Origin {letter}"


def axis_by_pick_id(context, pick_id):
    """Resolve an axis pick id to ``(plane, index)``, or ``(None, None)``."""
    for plane, index, candidate in iter_axis_candidates(context):
        if candidate == pick_id:
            return plane, index
    return None, None


def hit_test_axis(context, coords, radius=12.0):
    """Nearest offered axis within ``radius`` pixels of ``coords``.

    Returns ``(pick_id, plane, index)`` or ``(None, None, None)``. Screen-space
    like the curve-segment pick, so what is highlighted and what is picked agree.
    """
    from bpy_extras.view3d_utils import location_3d_to_region_2d

    region = context.region
    rv3d = context.region_data
    if region is None or rv3d is None:
        return None, None, None

    cursor = Vector(coords)
    best = None
    best_dist = radius
    for plane, index, pick_id in iter_axis_candidates(context):
        start, end = axis_endpoints(plane, index, context)
        s0 = location_3d_to_region_2d(region, rv3d, start)
        s1 = location_3d_to_region_2d(region, rv3d, end)
        if s0 is None or s1 is None:  # behind the view plane
            continue
        distance = _distance_to_segment(cursor, s0, s1)
        if distance <= best_dist:
            best_dist = distance
            best = (pick_id, plane, index)
    return best if best is not None else (None, None, None)


def _distance_to_segment(point, start, end) -> float:
    """Shortest distance from ``point`` to the segment ``start``-``end``."""
    span = end - start
    length_squared = span.length_squared
    if length_squared == 0.0:
        return (point - start).length
    t = max(0.0, min(1.0, (point - start).dot(span) / length_squared))
    return (point - (start + span * t)).length
