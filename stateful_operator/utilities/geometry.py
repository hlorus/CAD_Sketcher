from contextlib import contextmanager
from typing import Optional

from bpy.types import Context, Object, RegionView3D
from bpy_extras import view3d_utils
from bpy_extras.view3d_utils import region_2d_to_location_3d, region_2d_to_vector_3d
from mathutils import Vector

# TODO: Move into StateOps
from ..utilities.generic import bvhtree_from_object


def get_placement_pos(context: Context, coords: Vector) -> Vector:
    region = context.region
    rv3d = context.region_data
    view_vector = region_2d_to_vector_3d(region, rv3d, coords)
    return region_2d_to_location_3d(region, rv3d, coords, view_vector)


def get_scale_from_pos(co: Vector, rv3d: RegionView3D) -> Vector:
    if rv3d.view_perspective == "ORTHO":
        scale = rv3d.view_distance
    else:
        scale = (rv3d.perspective_matrix @ co.to_4d())[3]
    return scale


def get_evaluated_obj(context: Context, object: Object):
    return object.evaluated_get(context.evaluated_depsgraph_get())


def instance_origin(inst) -> Optional[Object]:
    """Original object a depsgraph instance belongs to (its emitter, if instanced)."""
    if inst.is_instance and inst.parent is not None:
        return inst.parent.original
    return inst.object.original


@contextmanager
def evaluated_surface_mesh(context: Context, ob: Object):
    """Yield ``(mesh, matrix_world)`` for ``ob``'s evaluated surface, else ``(None, None)``.

    A mesh object exposes its evaluated mesh directly on ``obj_eval.data``. A
    Curves object whose geometry-nodes modifier outputs a mesh (an extruded or
    filled CAD Sketcher sketch) exposes that mesh only as a depsgraph *instance*,
    not on the evaluated object, and ``to_mesh`` on the evaluated object raises
    "does not have geometry data". So fall back to scanning instances. Any
    temporary mesh created for the instance case is freed on exit, so callers
    must use the yielded mesh only inside the ``with`` block.
    """
    depsgraph = context.evaluated_depsgraph_get()
    obj_eval = ob.evaluated_get(depsgraph)
    data = obj_eval.data
    if hasattr(data, "polygons"):
        yield data, obj_eval.matrix_world
        return

    owner = None
    try:
        for inst in depsgraph.object_instances:
            if instance_origin(inst) != ob.original:
                continue
            try:
                mesh = inst.object.to_mesh()
            except RuntimeError:
                mesh = None
            if mesh is not None and len(mesh.polygons):
                owner = inst.object
                yield mesh, inst.matrix_world.copy()
                return
            if mesh is not None:
                inst.object.to_mesh_clear()
        yield None, None
    finally:
        if owner is not None:
            owner.to_mesh_clear()


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

    if not object:
        result, loc, _normal, face_index, ob, _matrix = scene.ray_cast(
            depsgraph, ray_origin, view_vector
        )
        # ray_cast hits geometry regardless of viewport visibility; don't pick a
        # face on an object hidden with the eye/monitor icon or via its collection.
        if result and ob is not None and not ob.visible_get():
            return None, None, None
    else:
        # Alternatively do a object raycast if we know the object already
        tree = bvhtree_from_object(object)
        if tree is None:
            return None, None, None
        loc, _normal, face_index, _distance = tree.ray_cast(ray_origin, view_vector)
        result = loc is not None
        ob = object

    if not result:
        return None, None, None

    # Object-only pick: the raycast hit is all we need — return it without
    # requiring mesh polygons, so non-mesh hits (e.g. a Curves sketch, whose
    # evaluated data has no polygons) can still be picked.
    if not (vertex or edge or face):
        return ob, Object, None

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

    # Read the evaluated surface mesh. For a Curves sketch (its extrude/fill
    # modifier outputs a mesh) that mesh lives on a depsgraph instance rather
    # than obj_eval.data, so go through the shared helper instead of reading
    # .data directly -- otherwise curve-object faces can't be picked.
    with evaluated_surface_mesh(context, ob) as (me, mw):
        if me is None or face_index >= len(me.polygons):
            return None, None, None

        closest_type = ""
        closest_dist = None

        loc_local = mw.inverted() @ loc
        polygon = me.polygons[face_index]

        if vertex:
            i, dist = get_closest(
                [(me.vertices[i].co - loc_local).length for i in polygon.vertices]
            )
            if i is not None:
                closest_type = "VERTEX"
                closest_index = polygon.vertices[i]
                closest_dist = dist

        if edge:
            face_edge_map = {ek: me.edges[i] for i, ek in enumerate(me.edge_keys)}
            i, dist = get_closest(
                [
                    (((me.vertices[s].co + me.vertices[e].co) / 2) - loc_local).length
                    for s, e in polygon.edge_keys
                ]
            )
            if i is not None and is_closer(dist, closest_dist):
                closest_type = "EDGE"
                closest_index = face_edge_map[polygon.edge_keys[i]].index
                closest_dist = dist

        if face:
            # Check if face midpoint is closest
            if is_closer((polygon.center - loc_local).length, closest_dist):
                closest_type = "FACE"
                closest_index = face_index

        if closest_type:
            return ob, closest_type, closest_index
        return ob, Object, None
