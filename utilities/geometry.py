import math
from statistics import mean
from typing import Tuple

import mathutils
from mathutils import Matrix, Vector


def face_workplane_matrix(context, ob, face_index):
    """World matrix of the workplane a mesh face would produce.

    Shared by the Add Sketch operator (creating the empty) and the workplane
    gizmo (previewing it on hover) so both agree exactly.
    """
    from ..stateful_operator.utilities.geometry import get_evaluated_obj

    eval_ob = get_evaluated_obj(context, ob)
    mesh = eval_ob.data
    face = mesh.polygons[face_index]

    quat = get_face_orientation(mesh, face)
    quat.rotate(ob.matrix_world)
    pos = ob.matrix_world @ face.center
    return Matrix.LocRotScale(pos, quat, None)


def face_bounds_in_plane(context, ob, face_index, mat):
    """2D bounding box of a mesh face in a workplane's local frame.

    ``mat`` is the plane's world matrix (see :func:`face_workplane_matrix`).
    Returns (min_x, min_y, max_x, max_y).
    """
    from ..stateful_operator.utilities.geometry import get_evaluated_obj

    eval_ob = get_evaluated_obj(context, ob)
    mesh = eval_ob.data
    face = mesh.polygons[face_index]

    inv = mat.inverted()
    mw = ob.matrix_world
    xs, ys = [], []
    for vi in face.vertices:
        local = inv @ (mw @ mesh.vertices[vi].co)
        xs.append(local.x)
        ys.append(local.y)
    return min(xs), min(ys), max(xs), max(ys)


def orientation_from_normal(normal):
    """Quaternion with Z along ``normal`` and Y toward world Z when possible."""
    z = normal.normalized()
    up = Vector((0, 0, 1))
    if abs(z.dot(up)) > 0.999:
        up = Vector((0, 1, 0))
    x = up.cross(z).normalized()
    y = z.cross(x).normalized()
    mat = mathutils.Matrix((x, y, z)).transposed().to_3x3()
    return mat.to_quaternion()


def orientation_from_normal_ref(normal, ref):
    """Quaternion with Z along ``normal`` and X along ``ref`` (projected).

    Unlike :func:`orientation_from_normal`, the in-plane axes come from a
    caller-supplied reference direction instead of world-up, so the frame
    stays rigid with the geometry as it rotates. Falls back to the world-up
    heuristic if ``ref`` is parallel to the normal.
    """
    z = normal.normalized()
    x = ref - z * ref.dot(z)  # project ref into the plane
    if x.length < 1e-6:
        return orientation_from_normal(normal)
    x.normalize()
    y = z.cross(x).normalized()
    mat = mathutils.Matrix((x, y, z)).transposed().to_3x3()
    return mat.to_quaternion()


def get_face_orientation(mesh, face):
    """Quaternion with Z along face normal and Y toward world Z when possible."""
    normal = mathutils.geometry.normal([mesh.vertices[i].co for i in face.vertices])
    return orientation_from_normal(normal)


def get_face_midpoint(quat, ob, face):
    """Average distance from origin to face vertices."""
    mesh = ob.data
    coords = [mesh.vertices[i].co.copy() for i in face.vertices]
    quat_inv = quat.inverted()
    for v in coords:
        v.rotate(quat_inv)
    dist = mean([co[2] for co in coords])

    # offset origin along normal by average distance
    pos = Vector((0, 0, dist))
    pos.rotate(quat)
    return ob.matrix_world @ pos


def nearest_point_line_line(p1: Vector, d1: Vector, p2: Vector, d2: Vector) -> Vector:
    n = d1.cross(d2)
    n2 = d2.cross(n)
    return p1 + ((p2 - p1).dot(n2) / d1.dot(n2)) * d1


def line_abc_form(p1: Vector, p2: Vector) -> Tuple[float, float, float]:
    a = p2.y - p1.y
    b = p1.x - p2.x
    return a, b, a * p1.x + b * p1.y


def get_line_intersection(a1, b1, c1, a2, b2, c2) -> Vector:
    det = a1 * b2 - a2 * b1
    if det == 0:
        # Parallel lines
        return Vector((math.inf, math.inf))
    else:
        x = (b2 * c1 - b1 * c2) / det
        y = (a1 * c2 - a2 * c1) / det
        return Vector((x, y))


def intersect_line_line_2d(
    lineA_p1: Vector, lineA_p2: Vector, lineB_p1: Vector, lineB_p2: Vector
) -> Vector:
    """Replicates the fuction from the mathutils.geometry module but works on lines instead of segments"""
    return get_line_intersection(
        *line_abc_form(lineA_p1, lineA_p2),
        *line_abc_form(lineB_p1, lineB_p2),
    )


# https://stackoverflow.com/questions/30844482/what-is-most-efficient-way-to-find-the-intersection-of-a-line-and-a-circle-in-py
def intersect_line_sphere_2d(
    line_p1: Vector,
    line_p2: Vector,
    circle_p1: Vector,
    circle_radius: float,
    tangent_tol=1e-4,
):
    """Find the points at which a circle intersects a line-segment.  This can happen at 0, 1, or 2 points.

    :param line_p1: The (x, y) location of the first point of the segment
    :param line_p2: The (x, y) location of the second point of the segment
    :param circle_p1: The (x, y) location of the circle center
    :param circle_radius: The radius of the circle
    :param tangent_tol: Numerical tolerance at which we decide the intersections are close enough to consider it a tangent
    :return Sequence[Tuple[float, float]]: A list of length 0, 1, or 2, where each element is a point at which the circle intercepts a line segment.

    Note: We follow: http://mathworld.wolfram.com/Circle-LineIntersection.html
    """

    (p1x, p1y), (p2x, p2y), (cx, cy) = line_p1, line_p2, circle_p1
    (x1, y1), (x2, y2) = (p1x - cx, p1y - cy), (p2x - cx, p2y - cy)
    dx, dy = (x2 - x1), (y2 - y1)
    dr = (dx**2 + dy**2) ** 0.5
    big_d = x1 * y2 - x2 * y1
    discriminant = circle_radius**2 * dr**2 - big_d**2

    # No intersection between circle and line
    if discriminant < -tangent_tol:
        return []

    # There may be 0, 1, or 2 intersections with the segment
    discriminant = max(0, discriminant)
    intersections = [
        (
            cx
            + (big_d * dy + sign * (-1 if dy < 0 else 1) * dx * discriminant**0.5)
            / dr**2,
            cy + (-big_d * dx + sign * abs(dy) * discriminant**0.5) / dr**2,
        )
        for sign in ((1, -1) if dy < 0 else (-1, 1))
    ]  # This makes sure the order along the segment is correct
    intersections = [Vector(p) for p in intersections]

    # If line is tangent to circle, return just one point (as both intersections have same location)
    if len(intersections) == 2 and abs(discriminant) <= tangent_tol:
        return [intersections[0]]
    return intersections
