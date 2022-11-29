from typing import Tuple

from bpy.types import Context, RegionView3D
from mathutils import Vector
from mathutils.geometry import intersect_line_plane
from bpy_extras.view3d_utils import (
    location_3d_to_region_2d,
    region_2d_to_location_3d,
    region_2d_to_vector_3d,
    region_2d_to_origin_3d,
)


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


def get_pos_2d(context: Context, wp, coords: Vector) -> Vector:
    """Returns the coordinates on the workplane the mouse points at"""
    origin, end_point = get_picking_origin_end(context, coords)
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
    if not context.space_data:
        return
    # update gizmos!
    if context.space_data.type == "VIEW_3D":
        context.space_data.show_gizmo = True
