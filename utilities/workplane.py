"""Workplane empty management."""

import bpy
from mathutils import Vector


# ---------------------------------------------------------------------------
# Workplane empty IDs for picking
# ---------------------------------------------------------------------------

WP_ID_XY = 0xF00001
WP_ID_XZ = 0xF00002
WP_ID_YZ = 0xF00003

WP_ID_MAP = {}


def get_workplane_empty_by_id(wp_id):
    """Look up a workplane empty by its picking ID."""
    return WP_ID_MAP.get(wp_id)


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
