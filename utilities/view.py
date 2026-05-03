from typing import Optional, Tuple

from bpy.types import Context, RegionView3D
from bpy_extras.view3d_utils import (
    location_3d_to_region_2d,
    region_2d_to_location_3d,
    region_2d_to_origin_3d,
    region_2d_to_vector_3d,
)
from mathutils import Vector
from mathutils.geometry import intersect_line_plane, intersect_point_line, intersect_line_line


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


def _closest_segment_point_world(
    screen_point: Vector, world_start: Vector, world_end: Vector, region, rv3d
) -> Optional[Vector]:
    ray_origin = region_2d_to_origin_3d(region, rv3d, screen_point)
    ray_dir = region_2d_to_vector_3d(region, rv3d, screen_point)

    seg = world_end - world_start
    seg_len_sq = seg.length_squared
    if seg_len_sq < 1e-10:
        return world_start.copy()

    ray_point, seg_point = intersect_line_line(
        ray_origin, ray_origin + ray_dir,
        world_start, world_end
    )

    if seg_point is None:
        seg_norm = seg.normalized()
        t_seg = (ray_origin - world_start).dot(seg_norm) / seg.length
        t_seg = max(0.0, min(1.0, t_seg))
        return world_start.lerp(world_end, t_seg)

    t_seg = (seg_point - world_start).dot(seg) / seg_len_sq
    t_seg = max(0.0, min(1.0, t_seg))
    return world_start.lerp(world_end, t_seg)


def _snap_screen_threshold(context: Context) -> float:
    inputs = context.preferences.inputs
    return max(inputs.drag_threshold, inputs.drag_threshold_mouse)


def _snap_show_xray(context: Context) -> bool:
    space_data = context.space_data
    if not space_data or space_data.type != "VIEW_3D":
        return False

    shading = getattr(space_data, "shading", None)
    if not shading:
        return False

    return getattr(shading, "show_xray", False)


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

    return candidates


def get_blender_snap_info(context: Context, coords: Vector) -> Optional[dict]:
    tool_settings = context.scene.tool_settings
    if not getattr(tool_settings, "use_snap", False):
        return None

    coords = Vector(coords)
    elements = _snap_elements(tool_settings)
    if not elements.intersection(
        {"VERTEX", "EDGE", "EDGE_MIDPOINT"}
    ):
        return None

    origin, view_vector = get_picking_origin_dir(context, coords)
    depsgraph = context.evaluated_depsgraph_get()

    result, location, _normal, face_index, ob, _matrix = context.scene.ray_cast(
        depsgraph, origin, view_vector
    )
    snap_target = getattr(tool_settings, "snap_target", "CLOSEST")
    candidates = []

    objects = []
    hit_object = ob.evaluated_get(depsgraph) if result and ob is not None and ob.type == "MESH" else None
    if hit_object is not None and not _snap_show_xray(context):
        objects.append(hit_object)
    else:
        for visible in context.visible_objects:
            if visible.type != "MESH":
                continue
            objects.append(visible.evaluated_get(depsgraph))

    for obj_eval in objects:
        candidate_face_index = None
        if (
            not _snap_show_xray(context)
            and hit_object is not None
            and obj_eval.original == hit_object.original
        ):
            candidate_face_index = face_index
        candidates.extend(
            _screen_snap_candidates(
                context,
                coords,
                obj_eval,
                elements,
                face_index=candidate_face_index,
            )
        )

    if not candidates:
        return None

    _priority, _distance, region_point, snap_data = min(
        candidates, key=lambda item: (item[0], item[1])
    )
    snap_data["region_point"] = region_point
    return snap_data


def get_pos_2d(
    context: Context,
    wp,
    coords: Vector,
    respect_snapping: bool = False,
) -> Vector:
    """Returns the coordinates on the workplane the mouse points at"""
    origin, end_point = get_picking_origin_end(context, coords)

    if respect_snapping:
        snap_info = get_blender_snap_info(context, coords)
        if snap_info and "world_point" in snap_info:
            snap_world_point = snap_info["world_point"]
            pos = intersect_line_plane(origin, end_point, wp.p1.location, wp.normal)
            if pos is None:
                return None
            closest_point = intersect_line_plane(snap_world_point, origin, wp.p1.location, wp.normal)
            if closest_point is None:
                return None
            pos = wp.matrix_basis.inverted() @ closest_point
            return Vector(pos[:-1])

    pos = intersect_line_plane(origin, end_point, wp.p1.location, wp.normal)
    if pos is None:
        return None
    pos = wp.matrix_basis.inverted() @ pos
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
