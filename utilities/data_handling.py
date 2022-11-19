from collections import deque
from typing import Generator, Deque, List, Sequence

from bpy.types import Scene, Context

from ..model.types import SlvsGenericEntity, SlvsSketch


def to_list(value):
    """Ensure value is of type list"""
    if value is None:
        return []
    if type(value) in (list, tuple):
        return list(value)
    return [
        value,
    ]


def get_flat_deps(entity: SlvsGenericEntity):
    """Return flattened list of entities given entity depends on"""
    list = []

    def walker(entity, is_root=False):
        if entity in list:
            return
        if not is_root:
            list.append(entity)
        if not hasattr(entity, "dependencies"):
            return
        for e in entity.dependencies():
            if e in list:
                continue
            walker(e)

    walker(entity, is_root=True)
    return list


def get_collective_dependencies(
    entities: Sequence[SlvsGenericEntity],
) -> List[SlvsGenericEntity]:
    """Returns a list of entities along with their dependencies"""
    deps = entities
    for entity in entities:
        for dep in get_flat_deps(entity):
            if dep in deps:
                continue
            deps.append(dep)
    return deps


def get_scene_constraints(scene: Scene):
    return scene.sketcher.constraints.all


def get_scene_entities(scene: Scene):
    return scene.sketcher.entities.all


def get_entity_deps(
    entity: SlvsGenericEntity, context: Context
) -> Generator[SlvsGenericEntity, None, None]:
    for scene_entity in get_scene_entities(context.scene):
        deps = set(get_flat_deps(scene_entity))
        if entity in deps:
            yield scene_entity


def _is_referenced_by_constraint(entity, context):
    for c in context.scene.sketcher.constraints.all:
        if entity in c.dependencies():
            return True
    return False


def is_entity_dependency(entity: SlvsGenericEntity, context: Context) -> bool:
    """Check if entity is a dependency of another entity"""
    deps = get_entity_deps(entity, context)
    try:
        next(deps)
    except StopIteration:
        return False
    return True


def is_entity_referenced(entity: SlvsGenericEntity, context: Context) -> bool:
    """Checks if the entity is referenced from anywhere"""
    if is_entity_dependency(entity, context):
        return True
    if _is_referenced_by_constraint(entity, context):
        return True
    return False


def get_sketch_deps_indicies(sketch: SlvsSketch, context: Context):
    deps = deque()
    for entity in get_scene_entities(context.scene):
        if not hasattr(entity, "sketch_i"):
            continue
        if sketch.slvs_index != entity.sketch.slvs_index:
            continue
        deps.append(entity.slvs_index)
    return deps


def get_constraint_local_indices(
    entity: SlvsGenericEntity, context: Context
) -> Deque[int]:
    constraints = context.scene.sketcher.constraints
    ret_list = deque()

    for data_coll in constraints.get_lists():
        indices = deque()
        for c in data_coll:
            if entity in c.dependencies():
                indices.append(constraints.get_index(c))
        ret_list.append((data_coll, indices))
    return ret_list


def entities_3d(context: Context) -> Generator[SlvsGenericEntity, None, None]:
    for entity in context.scene.sketcher.entities.all:
        if hasattr(entity, "sketch"):
            continue
        yield entity
