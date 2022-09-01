from ..model.categories import point_3d, point_2d

types_point_3d = (
    *point_3d,
    *((bpy.types.MeshVertex,) if False else ()),
)

types_point_2d = (
    *point_2d,
    *((bpy.types.MeshVertex,) if False else ()),
)
