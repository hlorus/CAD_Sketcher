"""Pick an element (edge or corner) of an object's generated geometry.

The geometry a node stack builds on a Curves object (a sketch's output) can't be
read with ``to_mesh``, but the depsgraph exposes it as an instance whose parent is
the object, and that instance's mesh *is* readable -- with the same element
indices the node tree sees. That makes "click the edge you want" possible on
procedural output, without inventing a rule to select it.
"""

from typing import Optional, Tuple

import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Matrix, Vector

from .view import get_picking_origin_dir


def generated_mesh(depsgraph, ob) -> Tuple[Optional[bpy.types.Mesh], Matrix]:
    """The mesh ``ob`` evaluates to, plus its world matrix.

    Returns ``(None, identity)`` when the object has no mesh output.
    """
    original = ob.original
    for inst in depsgraph.object_instances:
        if not inst.is_instance or inst.object.type != "MESH":
            continue
        parent = inst.parent
        if parent is not None and parent.original == original:
            return inst.object.data, inst.matrix_world.copy()

    evaluated = ob.evaluated_get(depsgraph)
    if evaluated.type == "MESH" and evaluated.data is not None:
        return evaluated.data, evaluated.matrix_world.copy()
    return None, Matrix.Identity(4)


def _face_elements(mesh, face_index: int, domain: str):
    """Element indices of one face, or of the whole mesh without a face hit."""
    if face_index is not None and 0 <= face_index < len(mesh.polygons):
        face = mesh.polygons[face_index]
        if domain != "EDGE":
            return list(face.vertices)
        return [mesh.loops[loop].edge_index for loop in face.loop_indices]
    count = len(mesh.edges) if domain == "EDGE" else len(mesh.vertices)
    return range(count)


def element_points(mesh, index: int, domain: str, matrix: Matrix) -> list:
    """World positions describing an element: an edge's ends, or one vertex."""
    if domain == "EDGE":
        if not 0 <= index < len(mesh.edges):
            return []
        return [matrix @ mesh.vertices[v].co for v in mesh.edges[index].vertices]
    if not 0 <= index < len(mesh.vertices):
        return []
    return [matrix @ mesh.vertices[index].co]


def _screen_distance(context, points, coords) -> Optional[float]:
    """Distance in pixels from ``coords`` to the element's screen projection."""
    region, rv3d = context.region, context.region_data
    projected = [location_3d_to_region_2d(region, rv3d, p) for p in points]
    if any(p is None for p in projected):
        return None
    if len(projected) == 1:
        return (projected[0] - coords).length
    a, b = projected
    edge = b - a
    length_sq = edge.length_squared
    if length_sq == 0.0:
        return (a - coords).length
    t = max(0.0, min(1.0, (coords - a).dot(edge) / length_sq))
    return (a + edge * t - coords).length


def element_under_cursor(
    context, coords: Vector, domain: str = "EDGE", ob=None, threshold: float = 40.0
):
    """Return ``(index, points)`` of the element nearest the cursor, or None.

    Only the face the view ray hits is searched, so this stays a local, cheap
    lookup rather than a scan of the whole mesh.
    """
    origin, direction = get_picking_origin_dir(context, coords)
    depsgraph = context.evaluated_depsgraph_get()
    hit, _location, _normal, face_index, hit_ob, _matrix = context.scene.ray_cast(
        depsgraph, origin, direction
    )
    if not hit or hit_ob is None:
        return None
    if ob is not None and hit_ob.original != ob.original:
        return None

    mesh, matrix = generated_mesh(depsgraph, hit_ob)
    if mesh is None:
        return None

    best = None
    for index in _face_elements(mesh, face_index, domain):
        points = element_points(mesh, index, domain, matrix)
        if not points:
            continue
        distance = _screen_distance(context, points, coords)
        if distance is None or distance > threshold:
            continue
        if best is None or distance < best[0]:
            best = (distance, index, points)
    if best is None:
        return None
    return best[1], best[2]
