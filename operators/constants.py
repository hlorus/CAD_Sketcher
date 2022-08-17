from .. import class_defines

types_point_3d = (
    *class_defines.point_3d,
    *((bpy.types.MeshVertex,) if False else ()),
)

types_point_2d = (
    *class_defines.point_2d,
    *((bpy.types.MeshVertex,) if False else ()),
)