from bpy.types import MeshVertex
from mathutils import Quaternion, Vector


def project_vertex_to_workplane(
    vertex_world: MeshVertex, origin: Vector, wp_quat: Quaternion
):
    """
    Project a world-space vertex to a workplane defined by origin and quaternion.

    Returns the (x, y) coordinates in the workplane’s local space.
    """
    relative = vertex_world - origin
    # Rotate into workplane local space (inverse rotation)
    local = wp_quat.conjugated() @ relative
    return Vector((local.x, local.y))
