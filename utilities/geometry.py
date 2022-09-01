from statistics import mean

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
