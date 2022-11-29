from bpy.types import Context, Object
from bpy_extras import view3d_utils
from mathutils import Vector
from bpy_extras.view3d_utils import region_2d_to_location_3d, region_2d_to_vector_3d

# TODO: Move into StateOps
from ..utilities.generic import bvhtree_from_object

from typing import Optional


def get_placement_pos(context: Context, coords: Vector) -> Vector:
    region = context.region
    rv3d = context.region_data
    view_vector = region_2d_to_vector_3d(region, rv3d, coords)
    return region_2d_to_location_3d(region, rv3d, coords, view_vector)


def get_evaluated_obj(context: Context, object: Object):
    return object.evaluated_get(context.evaluated_depsgraph_get())


def get_mesh_element(
    context: Context,
    coords,
    vertex=False,
    edge=False,
    face=False,
    threshold=0.5,
    object: Optional[Object] = None,
):

    # get the ray from the viewport and mouse
    region = context.region
    rv3d = context.region_data
    view_vector = view3d_utils.region_2d_to_vector_3d(region, rv3d, coords)
    ray_origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coords)
    depsgraph = context.view_layer.depsgraph
    scene = context.scene
    result, loc, _normal, face_index, ob, _matrix = scene.ray_cast(
        depsgraph, ray_origin, view_vector
    )

    if object:
        # Alternatively do a object raycast if we know the object already
        tree = bvhtree_from_object(ob)
        loc, _normal, face_index, _distance = tree.ray_cast(ray_origin, view_vector)
        result = loc is not None
        ob = object

    if not result:
        return None, None, None

    obj_eval = get_evaluated_obj(context, ob)

    closest_type = ""
    closest_dist = None

    loc = obj_eval.matrix_world.inverted() @ loc
    me = obj_eval.data
    polygon = me.polygons[face_index]

    def get_closest(deltas):
        index_min = min(range(len(deltas)), key=deltas.__getitem__)
        if deltas[index_min] > threshold:
            return None, None
        return index_min, deltas[index_min]

    def is_closer(distance, min_distance):
        if min_distance is None:
            return True
        if distance < min_distance:
            return True
        return False

    if vertex:
        i, dist = get_closest(
            [(me.vertices[i].co - loc).length for i in polygon.vertices]
        )
        if i is not None:
            closest_type = "VERTEX"
            closest_index = polygon.vertices[i]
            closest_dist = dist

    if edge:
        face_edge_map = {ek: me.edges[i] for i, ek in enumerate(me.edge_keys)}
        i, dist = get_closest(
            [
                (((me.vertices[start].co + me.vertices[end].co) / 2) - loc).length
                for start, end in polygon.edge_keys
            ]
        )
        if i is not None and is_closer(dist, closest_dist):
            closest_type = "EDGE"
            closest_index = face_edge_map[polygon.edge_keys[i]].index
            closest_dist = dist

    if face:
        # Check if face midpoint is closest
        if is_closer((polygon.center - loc).length, closest_dist):
            closest_type = "FACE"
            closest_index = face_index

    if closest_type:
        return ob, closest_type, closest_index
    return ob, Object, None
