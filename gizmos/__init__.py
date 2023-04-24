import bpy
from .angle import VIEW3D_GGT_slvs_angle, VIEW3D_GT_slvs_angle
from .constraint import (
    VIEW3D_GGT_slvs_constraint,
    VIEW3D_GT_slvs_constraint,
    VIEW3D_GT_slvs_constraint_value,
)
from .diameter import VIEW3D_GGT_slvs_diameter, VIEW3D_GT_slvs_diameter
from .distance import VIEW3D_GGT_slvs_distance, VIEW3D_GT_slvs_distance
from .preselection import (
    VIEW3D_GGT_slvs_preselection,
    VIEW3D_GT_slvs_preselection,
)


specific_constraint_types = ("angle", "diameter", "distance")


classes = (
    VIEW3D_GT_slvs_preselection,
    VIEW3D_GT_slvs_constraint,
    VIEW3D_GT_slvs_distance,
    VIEW3D_GT_slvs_angle,
    VIEW3D_GT_slvs_diameter,
    VIEW3D_GT_slvs_constraint_value,
    VIEW3D_GGT_slvs_preselection,
    VIEW3D_GGT_slvs_constraint,
    VIEW3D_GGT_slvs_distance,
    VIEW3D_GGT_slvs_angle,
    VIEW3D_GGT_slvs_diameter,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
