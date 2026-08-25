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
    region = context.region
    rv3d = context.region_data

    # get the ray from the viewport and mouse
    view_vector = region_2d_to_vector_3d(region, rv3d, coords)
    ray_origin = region_2d_to_origin_3d(region, rv3d, coords)
    return ray_origin, view_vector


def get_picking_origin_end(context: Context, coords: Vector) -> Tuple[Vector, Vector]:
    region = context.region
    rv3d = context.region_data

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
            face_vertex_indices
            if face_vertex_indices is not None
            else range(len(me.vertices))
        )
        for vertex_index in vertex_indices:
            vertex = me.vertices[vertex_index]
            add_candidate(
                0,
                get_vertex_screen(vertex.index),
                {
                    "type": "VERTEX",
                    "world_point": matrix @ vertex.co,
                    # Provenance so a placed point can be live-projected onto this
                    # source vertex (see projection_anchor.project_mesh_vertex).
                    "object": obj_eval.original.name,
                    "vertex_index": vertex.index,
                },
            )

    if "EDGE" in elements or "EDGE_MIDPOINT" in elements:
        if face_edge_keys is not None:
            face_edge_map = {
                edge_key: me.edges[i] for i, edge_key in enumerate(me.edge_keys)
            }
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
                        # Provenance so a placed point can be live-projected onto
                        # this edge's midpoint: the edge is projected as a line and a
                        # midpoint constraint pins the point (see
                        # projection_anchor.project_mesh_edge).
                        "object": obj_eval.original.name,
                        "edge_vertices": (int(v1), int(v2)),
                    },
                )

            if "EDGE" in elements:
                world_closest = _closest_segment_point_world(
                    coords, world_start, world_end, region, rv3d
                )
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
                        # Provenance so a point snapped along this edge can be
                        # live-projected onto it: the edge is projected and the
                        # point slides on it via a point-on-line coincidence (see
                        # projection_anchor.project_mesh_edge).
                        "object": obj_eval.original.name,
                        "edge_vertices": (int(v1), int(v2)),
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


def _project_points_to_region(world, region, rv3d):
    """Project an (N, 3) array of world points to region-space pixels in one
    numpy op (mirrors location_3d_to_region_2d, but batched). Returns an (N, 2)
    float array and a boolean (N,) validity mask (points in front of the view).
    """
    import numpy as np

    n = len(world)
    homog = np.empty((n, 4), dtype=np.float64)
    homog[:, :3] = world
    homog[:, 3] = 1.0
    clip = homog @ np.array(rv3d.perspective_matrix, dtype=np.float64).T
    w = clip[:, 3]
    valid = w > 1e-8
    w_safe = np.where(valid, w, 1.0)
    ndc = clip[:, :2] / w_safe[:, None]
    screen = np.empty((n, 2), dtype=np.float64)
    screen[:, 0] = (region.width * 0.5) * (1.0 + ndc[:, 0])
    screen[:, 1] = (region.height * 0.5) * (1.0 + ndc[:, 1])
    return screen, valid


def _curve_snap_candidates(
    context: Context, obj, coords: Vector, elements, threshold=None
):
    """Snap candidates from a curve object's control points and segments.

    Curve objects (CAD Sketcher sketches) don't expose a readable evaluated
    mesh, so snap to their points directly: each control point as a vertex, and
    consecutive points within a curve as edges.

    All points are transformed and projected with numpy in bulk (not one
    Python call per point), and matched entirely in screen space, so hovering a
    dense sketch stays cheap on every mouse move. ``threshold`` overrides the
    default snap pixel radius (callers picking rather than snapping want a more
    forgiving radius).
    """
    import numpy as np

    cd = getattr(obj, "data", None)
    if cd is None or not hasattr(cd, "points") or len(cd.points) == 0:
        return []

    if threshold is None:
        threshold = _snap_screen_threshold(context)
    region = context.region
    rv3d = context.region_data

    n = len(cd.points)
    local = np.empty(n * 3, dtype=np.float64)
    cd.points.foreach_get("position", local)
    local = local.reshape(n, 3)

    # world = matrix @ local (batched)
    mat = np.array(obj.matrix_world, dtype=np.float64)
    world = local @ mat[:3, :3].T + mat[:3, 3]

    screen, valid = _project_points_to_region(world, region, rv3d)
    cur = np.array((coords[0], coords[1]), dtype=np.float64)

    candidates = []

    if "VERTEX" in elements:
        d = np.hypot(screen[:, 0] - cur[0], screen[:, 1] - cur[1])
        for i in np.nonzero(valid & (d <= threshold))[0]:
            candidates.append(
                (
                    0,
                    float(d[i]),
                    Vector((screen[i, 0], screen[i, 1])),
                    {"type": "VERTEX", "world_point": Vector(world[i])},
                )
            )

    if "FACE_MIDPOINT" in elements:
        # A face only exists for a closed region. Cheaply: the centroid of each
        # cyclic curve (a circle, or a shape drawn as one closed curve). Regions
        # formed by several separate coincident lines are the GN fill's loop
        # detection, which can't be replicated per frame, so they're skipped.
        cyc_attr = cd.attributes.get("cyclic")
        thr2 = threshold * threshold
        for ci, curve in enumerate(cd.curves):
            if not (cyc_attr.data[ci].value if cyc_attr else False):
                continue
            idx = [p.index for p in curve.points]
            if not idx:
                continue
            center_world = world[idx].mean(axis=0)
            cs, cv = _project_points_to_region(center_world[None, :], region, rv3d)
            if not cv[0]:
                continue
            dc = (cur[0] - cs[0, 0]) ** 2 + (cur[1] - cs[0, 1]) ** 2
            if dc <= thr2:
                candidates.append(
                    (
                        3,
                        float(dc**0.5),
                        Vector((cs[0, 0], cs[0, 1])),
                        {"type": "FACE_MIDPOINT", "world_point": Vector(center_world)},
                    )
                )

    if "EDGE" in elements or "EDGE_MIDPOINT" in elements:
        thr2 = threshold * threshold
        for curve in cd.curves:
            indices = [p.index for p in curve.points]
            for a, b in zip(indices, indices[1:]):
                if not (valid[a] and valid[b]):
                    continue
                sa = screen[a]
                sb = screen[b]

                if "EDGE_MIDPOINT" in elements:
                    mid = (sa + sb) * 0.5
                    dm = (cur[0] - mid[0]) ** 2 + (cur[1] - mid[1]) ** 2
                    if dm <= thr2:
                        candidates.append(
                            (
                                1,
                                float(dm**0.5),
                                Vector((mid[0], mid[1])),
                                {
                                    "type": "EDGE_MIDPOINT",
                                    "world_point": Vector((world[a] + world[b]) * 0.5),
                                    "world_edge": (Vector(world[a]), Vector(world[b])),
                                },
                            )
                        )

                if "EDGE" in elements:
                    # Closest point on the screen-space segment to the cursor.
                    seg = sb - sa
                    seg_len2 = seg[0] * seg[0] + seg[1] * seg[1]
                    if seg_len2 < 1e-9:
                        continue
                    t = (
                        (cur[0] - sa[0]) * seg[0] + (cur[1] - sa[1]) * seg[1]
                    ) / seg_len2
                    t = min(1.0, max(0.0, t))
                    cx = sa[0] + t * seg[0]
                    cy = sa[1] + t * seg[1]
                    de = (cur[0] - cx) ** 2 + (cur[1] - cy) ** 2
                    if de <= thr2:
                        world_closest = Vector(world[a]).lerp(Vector(world[b]), t)
                        candidates.append(
                            (
                                2,
                                float(de**0.5),
                                Vector((cx, cy)),
                                {
                                    "type": "EDGE",
                                    "world_point": world_closest,
                                    "world_edge": (Vector(world[a]), Vector(world[b])),
                                },
                            )
                        )

    return candidates


def _dist2_point_segment(px, py, a, b):
    abx, aby = b[0] - a[0], b[1] - a[1]
    seg2 = abx * abx + aby * aby
    if seg2 < 1e-9:
        return (px - a[0]) ** 2 + (py - a[1]) ** 2
    t = ((px - a[0]) * abx + (py - a[1]) * aby) / seg2
    t = min(1.0, max(0.0, t))
    cx, cy = a[0] + t * abx, a[1] + t * aby
    return (px - cx) ** 2 + (py - cy) ** 2


def curve_segment_under_cursor(context: Context, coords, threshold_px):
    """Nearest curve/sketch segment under the cursor -> (obj, point_index) or None.

    Curves have no raycastable geometry, so pick them in screen space (same bulk
    numpy projection the snapping uses). ``point_index`` is the segment's first
    control point; the segment is points [i, i+1] within one curve, so it
    resolves back to endpoints via ``cd.points[i]`` / ``cd.points[i + 1]``. Used
    by both the hover gizmo (highlight) and pointer picks so they agree.
    """
    import numpy as np

    region = context.region
    rv3d = context.region_data
    if region is None or rv3d is None:
        return None
    cx, cy = float(coords[0]), float(coords[1])
    thr2 = threshold_px * threshold_px
    best = None
    for ob in context.visible_objects:
        if ob.type not in {"CURVE", "CURVES"}:
            continue
        cd = getattr(ob.original, "data", None)
        if (
            cd is None
            or not hasattr(cd, "points")
            or len(cd.points) == 0
            or not hasattr(cd, "curves")
        ):
            continue
        n = len(cd.points)
        local = np.empty(n * 3, dtype=np.float64)
        cd.points.foreach_get("position", local)
        local = local.reshape(n, 3)
        mat = np.array(ob.matrix_world, dtype=np.float64)
        world = local @ mat[:3, :3].T + mat[:3, 3]
        screen, valid = _project_points_to_region(world, region, rv3d)
        for curve in cd.curves:
            indices = [p.index for p in curve.points]
            for a, b in zip(indices, indices[1:]):
                if not (valid[a] and valid[b]):
                    continue
                d2 = _dist2_point_segment(cx, cy, screen[a], screen[b])
                if d2 <= thr2 and (best is None or d2 < best[0]):
                    best = (d2, ob, a)
    if best is None:
        return None
    return best[1], best[2]


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

    # Don't snap to the sketch being drawn in: its own generated geometry would
    # otherwise capture the cursor (issue #591). Skip past it and keep looking for
    # real reference geometry behind it.
    from ..model.sketch_ref import get_active_sketch

    active = get_active_sketch(context)
    active_obj = active.target_object if active else None

    ray_origin = Vector(origin)
    ob = None
    face_index = -1
    for _ in range(16):
        hit, location, _normal, hit_face, hit_ob, _matrix = context.scene.ray_cast(
            depsgraph, ray_origin, view_vector
        )
        # Nothing (more) under the cursor -> nothing to snap to. Only the object
        # directly hit by the ray is considered, so a mouse-move over empty
        # space is free instead of scanning every visible object (the
        # drawing-lag path).
        #
        # NOTE: snapping deliberately does NOT use the viewport x-ray shading to
        # decide scope. The "Auto Fade Objects" feature turns x-ray on in sketch
        # mode, which would otherwise force the expensive all-geometry scan on
        # every frame.
        if not hit or hit_ob is None:
            return None
        # Skip the sketch being drawn in (#591) and any hidden object -- ray_cast
        # hits geometry regardless of viewport visibility, so without this you
        # could snap to an invisible mesh. Advance past and keep looking behind.
        is_active = active_obj is not None and hit_ob.original == active_obj
        if not is_active and hit_ob.visible_get():
            ob, face_index = hit_ob, hit_face
            break
        ray_origin = Vector(location) + view_vector * 1e-4
    else:
        return None

    if ob.type == "MESH":
        # Restrict to the hit face's vertices/edges for a cheap, local search.
        candidates = _screen_snap_candidates(
            context,
            coords,
            ob.evaluated_get(depsgraph),
            elements,
            face_index=face_index,
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
    if hasattr(wp, "p1"):
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
            # Drop the snapped 3D point straight onto the workplane -- its
            # orthogonal projection (foot of the perpendicular), not where the
            # view ray happens to cross the plane. So an edge floating above the
            # ground snaps to its footprint on the workplane, independent of the
            # viewing angle.
            wp_point = snap_info["world_point"]
            closest_point = intersect_line_plane(
                wp_point, wp_point + wp_normal, wp_origin, wp_normal
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
