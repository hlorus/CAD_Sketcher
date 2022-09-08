from ..model.categories import POINT3D, POINT2D

types_point_3d = (
    *POINT3D,
    *((bpy.types.MeshVertex,) if False else ()),
)

types_point_2d = (
    *POINT2D,
    *((bpy.types.MeshVertex,) if False else ()),
)
