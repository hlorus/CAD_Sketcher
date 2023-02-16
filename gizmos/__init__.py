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


def generic_constraints(context):
    """Iterate through constraints which don't have a specific gizmo"""
    constrs = context.scene.sketcher.constraints
    for prop_list in constrs.rna_type.properties:
        name = prop_list.identifier
        if name in ("name", "rna_type", *specific_constraint_types):
            continue
        list = getattr(constrs, name)

        for entity in list:
            yield entity


# TODO: This could already Skip entities and constraints that are not active
# TODO: only store indices instead of actual objects
def constraints_mapping(context):
    # Get a constraints per entity mapping
    entities = []
    constraints = []
    for c in generic_constraints(context):
        for e in c.entities():
            if e not in entities:
                entities.append(e)
                # i = len(entities)
            i = entities.index(e)
            if i >= len(constraints):
                constraints.append([])
            constrs = constraints[i]
            if c not in constrs:
                constrs.append(c)
    assert len(entities) == len(constraints)
    return entities, constraints


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
