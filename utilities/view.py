from typing import Optional, Tuple

from bpy.types import Context, RegionView3D
from bpy_extras.view3d_utils import (
    location_3d_to_region_2d,
    region_2d_to_location_3d,
    region_2d_to_origin_3d,
    region_2d_to_vector_3d,
)
from mathutils import Vector
from mathutils.geometry import intersect_line_line, intersect_line_plane


def get_picking_origin_dir(context: Context, coords: Vector) -> Tuple[Vector, Vector]:
    scene = context.scene
    region = context.region
    rv3d = context.region_data
    viewlayer = context.view_layer

    # get the ray from the viewport and mouse
    view_vector = region_2d_to_vector_3d(region, rv3d, coords)
    ray_origin = region_2d_to_origin_3d(region, rv3d, coords)
    return ray_origin, view_vector


def get_picking_origin_end(context: Context, coords: Vector) -> Tuple[Vector, Vector]:
    scene = context.scene
    region = context.region
    rv3d = context.region_data
    viewlayer = context.view_layer

    # get the ray from the viewport and mouse
    view_vector = region_2d_to_vector_3d(region, rv3d, coords)
    ray_origin = region_2d_to_origin_3d(region, rv3d, coords)

    # view vector needs to be scaled and translated
    end_point = view_vector * context.space_data.clip_end + ray_origin
    return ray_origin, end_point


def get_placement_pos(context: Context, coords: Vector) -> Vector:
    region = context.region
    rv3d = context.region_data
    view_vector = region_2d_to_vector_3d(region, rv3d, coords)
    return region_2d_to_location_3d(region, rv3d, coords, view_vector)


def get_wp_matrix(wp):
    """World matrix of a workplane, whether it's an entity or an empty object."""
    return wp.matrix_basis if hasattr(wp, "p1") else wp.matrix_world


def _snap_elements(tool_settings) -> set[str]:
    elements = set()
    for attr in ("snap_elements", "snap_elements_base"):
        value = getattr(tool_settings, attr, None)
        if not value:
            continue
        if isinstance(value, str):
            elements.add(value)
        else:
            elements.update(value)

    if "EDGE_PERPENDICULAR" in elements:
        elements.add("EDGE")

    return elements


def _closest_point_on_segment_to_ray(
    ray_origin: Vector, ray_dir: Vector, world_start: Vector, world_end: Vector
) -> Vector:
    """Closest point on the segment [world_start, world_end] to the given ray.

    Pure geometry (no viewport dependency), so it is unit-testable — including
    the parallel/degenerate case where ``intersect_line_line`` returns ``None``.
    """
    seg = world_end - world_start
    seg_len_sq = seg.length_squared
    if seg_len_sq < 1e-10:
        return world_start.copy()

    # intersect_line_line returns None for parallel/degenerate lines (not a
    # tuple), so guard the unpack before using the result.
    result = intersect_line_line(
        ray_origin, ray_origin + ray_dir, world_start, world_end
    )
    seg_point = result[1] if result is not None else None

    if seg_point is None:
        # Parallel/degenerate: project the ray origin onto the segment line.
        t_seg = (ray_origin - world_start).dot(seg.normalized()) / seg.length
    else:
        t_seg = (seg_point - world_start).dot(seg) / seg_len_sq

    t_seg = max(0.0, min(1.0, t_seg))
    return world_start.lerp(world_end, t_seg)


def _closest_segment_point_world(
    screen_point: Vector, world_start: Vector, world_end: Vector, region, rv3d
) -> Optional[Vector]:
    ray_origin = region_2d_to_origin_3d(region, rv3d, screen_point)
    ray_dir = region_2d_to_vector_3d(region, rv3d, screen_point)
    return _closest_point_on_segment_to_ray(ray_origin, ray_dir, world_start, world_end)


def _snap_screen_threshold(context: Context) -> float:
    inputs = context.preferences.inputs
    return max(inputs.drag_threshold, inputs.drag_threshold_mouse)


def _screen_snap_candidates(
    context: Context,
    coords: Vector,
    obj_eval,
    elements,
    face_index: Optional[int] = None,
):
    me = getattr(obj_eval, "data", None)
    if me is None:
        return []

    threshold = _snap_screen_threshold(context)
    region = context.region
    rv3d = context.region_data
    matrix = obj_eval.matrix_world
    candidates = []
    vertex_screen = {}
    face_vertex_indices = None
    face_edge_keys = None

    if face_index is not None and 0 <= face_index < len(me.polygons):
        polygon = me.polygons[face_index]
        face_vertex_indices = tuple(polygon.vertices)
        face_edge_keys = tuple(polygon.edge_keys)

    def get_vertex_screen(index: int):
        if index not in vertex_screen:
            world = matrix @ me.vertices[index].co
            vertex_screen[index] = location_3d_to_region_2d(region, rv3d, world)
        return vertex_screen[index]

    def add_candidate(priority: int, region_point: Vector, snap_data: dict):
        if region_point is None:
            return

        distance = (coords - region_point).length
        if distance > threshold:
            return

        candidates.append((priority, distance, region_point, snap_data))

    if "VERTEX" in elements:
        vertex_indices = (
            face_vertex_indices if face_vertex_indices is not None else range(len(me.vertices))
        )
        for vertex_index in vertex_indices:
            vertex = me.vertices[vertex_index]
            add_candidate(
                0,
                get_vertex_screen(vertex.index),
                {
                    "type": "VERTEX",
                    "world_point": matrix @ vertex.co,
                },
            )

    if "EDGE" in elements or "EDGE_MIDPOINT" in elements:
        if face_edge_keys is not None:
            face_edge_map = {edge_key: me.edges[i] for i, edge_key in enumerate(me.edge_keys)}
            edges = [face_edge_map[edge_key] for edge_key in face_edge_keys]
        else:
            edges = me.edges

        for edge in edges:
            v1, v2 = edge.vertices
            start = get_vertex_screen(v1)
            end = get_vertex_screen(v2)
            if start is None or end is None:
                continue

            midpoint = (start + end) / 2
            world_start = matrix @ me.vertices[v1].co
            world_end = matrix @ me.vertices[v2].co

            if "EDGE_MIDPOINT" in elements:
                add_candidate(
                    1,
                    midpoint,
                    {
                        "type": "EDGE_MIDPOINT",
                        "world_point": (world_start + world_end) / 2,
                        "world_edge": (world_start, world_end),
                    },
                )

            if "EDGE" in elements:
                world_closest = _closest_segment_point_world(coords, world_start, world_end, region, rv3d)
                if world_closest is None:
                    continue
                region_point = location_3d_to_region_2d(region, rv3d, world_closest)
                if region_point is None:
                    continue

                add_candidate(
                    2,
                    region_point,
                    {
                        "type": "EDGE",
                        "world_point": world_closest,
                        "world_edge": (world_start, world_end),
                    },
                )

    if "FACE_MIDPOINT" in elements:
        face_indices = (
            (face_index,)
            if face_index is not None and 0 <= face_index < len(me.polygons)
            else range(len(me.polygons))
        )
        for fi in face_indices:
            world_center = matrix @ me.polygons[fi].center
            add_candidate(
                3,
                location_3d_to_region_2d(region, rv3d, world_center),
                {
                    "type": "FACE_MIDPOINT",
                    "world_point": world_center,
                },
            )

    return candidates


def _curve_snap_candidates(context: Context, obj, coords: Vector, elements):
    """Snap candidates from a curve object's control points and segments.

    Curve objects (CAD Sketcher sketches) don't expose a readable evaluated
    mesh, so snap to their points directly: each control point as a vertex, and
    consecutive points within a curve as edges.
    """
    cd = getattr(obj, "data", None)
    if cd is None or not hasattr(cd, "points") or len(cd.points) == 0:
        return []

    threshold = _snap_screen_threshold(context)
    region = context.region
    rv3d = context.region_data
    matrix = obj.matrix_world

    n = len(cd.points)
    world = [matrix @ Vector(cd.points[i].position) for i in range(n)]
    screen = [location_3d_to_region_2d(region, rv3d, w) for w in world]

    candidates = []

    def add_candidate(priority, region_point, snap_data):
        if region_point is None:
            return
        distance = (coords - region_point).length
        if distance > threshold:
            return
        candidates.append((priority, distance, region_point, snap_data))

    if "VERTEX" in elements:
        for i in range(n):
            add_candidate(0, screen[i], {"type": "VERTEX", "world_point": world[i]})

    if "EDGE" in elements or "EDGE_MIDPOINT" in elements:
        for curve in cd.curves:
            indices = [p.index for p in curve.points]
            for a, b in zip(indices, indices[1:]):
                world_start, world_end = world[a], world[b]
                start, end = screen[a], screen[b]

                if "EDGE_MIDPOINT" in elements and start is not None and end is not None:
                    add_candidate(
                        1,
                        (start + end) / 2,
                        {
                            "type": "EDGE_MIDPOINT",
                            "world_point": (world_start + world_end) / 2,
                            "world_edge": (world_start, world_end),
                        },
                    )

                if "EDGE" in elements:
                    world_closest = _closest_segment_point_world(
                        coords, world_start, world_end, region, rv3d
                    )
                    if world_closest is None:
                        continue
                    region_point = location_3d_to_region_2d(region, rv3d, world_closest)
                    add_candidate(
                        2,
                        region_point,
                        {
                            "type": "EDGE",
                            "world_point": world_closest,
                            "world_edge": (world_start, world_end),
                        },
                    )

    return candidates


def get_blender_snap_info(context: Context, coords: Vector) -> Optional[dict]:
    from .. import global_data

    # Holding Shift during a draw bypasses snapping (also skips the ray_cast).
    if global_data.snap_bypass:
        return None

    tool_settings = context.scene.tool_settings
    if not getattr(tool_settings, "use_snap", False):
        return None

    coords = Vector(coords)
    elements = _snap_elements(tool_settings)
    if not elements.intersection({"VERTEX", "EDGE", "EDGE_MIDPOINT", "FACE_MIDPOINT"}):
        return None

    origin, view_vector = get_picking_origin_dir(context, coords)
    depsgraph = context.evaluated_depsgraph_get()

    result, location, _normal, face_index, ob, _matrix = context.scene.ray_cast(
        depsgraph, origin, view_vector
    )
    if not result or ob is None:
        # Nothing under the cursor -> nothing to snap to. Only the object
        # directly hit by the ray is considered, so a mouse-move over empty
        # space is free instead of scanning every visible object (the
        # drawing-lag path).
        #
        # NOTE: snapping deliberately does NOT use the viewport x-ray shading to
        # decide scope. The "Auto Fade Objects" feature turns x-ray on in sketch
        # mode, which would otherwise force the expensive all-geometry scan on
        # every frame.
        return None

    if ob.type == "MESH":
        # Restrict to the hit face's vertices/edges for a cheap, local search.
        candidates = _screen_snap_candidates(
            context, coords, ob.evaluated_get(depsgraph), elements, face_index=face_index
        )
    elif ob.type == "CURVES":
        # CAD Sketcher sketches (and other curve objects) are Curves objects; the
        # generated mesh can't be read back, but their control points can, so
        # snap to the curve's points and segments directly.
        candidates = _curve_snap_candidates(context, ob.original, coords, elements)
    else:
        return None

    if not candidates:
        return None

    _priority, _distance, region_point, snap_data = min(
        candidates, key=lambda item: (item[0], item[1])
    )
    snap_data["region_point"] = region_point
    return snap_data


def get_pos_2d(
    context: Context, wp, coords: Vector, respect_snapping: bool = False
) -> Vector:
    """Returns the coordinates on the workplane the mouse points at.

    wp can be a SlvsWorkplane entity or a Blender Object (empty). When
    ``respect_snapping`` is set and Blender's snapping is active, the position is
    snapped to the projection of nearby 3D geometry onto the workplane.
    """
    origin, end_point = get_picking_origin_end(context, coords)

    # Support both entity workplanes and empty objects
    if hasattr(wp, 'p1'):
        # Entity workplane
        wp_origin = wp.p1.location
        wp_normal = wp.normal
        mat = wp.matrix_basis
    else:
        # Empty object
        mat = wp.matrix_world
        wp_origin = mat.translation
        wp_normal = Vector(mat.col[2][:3]).normalized()

    if respect_snapping:
        snap_info = get_blender_snap_info(context, coords)
        if snap_info and "world_point" in snap_info:
            # Project the snapped 3D point onto the workplane along the view ray.
            closest_point = intersect_line_plane(
                snap_info["world_point"], origin, wp_origin, wp_normal
            )
            if closest_point is None:
                return None
            pos = mat.inverted() @ closest_point
            return Vector(pos[:-1])

    pos = intersect_line_plane(origin, end_point, wp_origin, wp_normal)
    if pos is None:
        return None
    pos = mat.inverted() @ pos
    return Vector(pos[:-1])


def get_2d_coords(context, pos: Vector) -> Vector:
    region = context.region
    rv3d = context.space_data.region_3d
    return location_3d_to_region_2d(region, rv3d, pos)


def get_scale_from_pos(co: Vector, rv3d: RegionView3D) -> Vector:
    if rv3d.view_perspective == "ORTHO":
        scale = rv3d.view_distance
    else:
        scale = (rv3d.perspective_matrix @ co.to_4d())[3]
    return scale


def refresh(context: Context):
    """Update gizmos"""
    if context.space_data and context.space_data.type == "VIEW_3D":
        context.space_data.show_gizmo = True

    if context.area and context.area.type == "VIEW_3D":
        context.area.tag_redraw()


def update_cb(self, context: Context):
    """Mark that the viewport needs a redraw, deferred to depsgraph_update_post."""
    from .. import global_data

    global_data.needs_redraw = True
