import math
from statistics import mean
from typing import Tuple

import mathutils
from mathutils import Vector


def get_face_orientation(mesh, face):
    # returns quaternion describing the face orientation in objectspace
    normal = mathutils.geometry.normal([mesh.vertices[i].co for i in face.vertices])
    return normal.to_track_quat("Z", "X")


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
