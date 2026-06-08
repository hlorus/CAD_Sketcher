from ..model.utilities import update_pointers


def collect_collapsed_line_indices(context, point_indices=None):
    entities = context.scene.sketcher.entities
    point_index_set = set(point_indices) if point_indices is not None else None
    return [
        entity.slvs_index
        for entity in entities.all
        if entity.is_line()
        and (p1 := getattr(entity, "p1_i", None)) is not None
        and p1 == getattr(entity, "p2_i", None)
        and (point_index_set is None or p1 in point_index_set)
    ]


def _delete_constraints_for_lines(context, collapsed_lines):
    if not collapsed_lines:
        return

    constraints = context.scene.sketcher.constraints
    collapsed_set = set(collapsed_lines)
    constraints_to_delete = []

    for constraint in constraints.all:
        try:
            deps = constraint.dependencies()
        except Exception:
            deps = []

        if any(getattr(dep, "slvs_index", None) in collapsed_set for dep in deps):
            constraints_to_delete.append(constraint)

    constraints_to_delete.sort(
        key=lambda constraint: (constraint.type, constraint.index()), reverse=True
    )
    for constraint in constraints_to_delete:
        constraints.remove(constraint)


def delete_collapsed_lines(context, point_indices=None):
    entities = context.scene.sketcher.entities
    collapsed = collect_collapsed_line_indices(context, point_indices=point_indices)
    if not collapsed:
        return 0

    _delete_constraints_for_lines(context, collapsed)

    deleted = 0
    for line_index in sorted(collapsed, reverse=True):
        line = entities.get(line_index)
        if line is None:
            continue
        entities.remove(line_index)
        deleted += 1

    return deleted


def merge_point_indices(context, target_index, duplicate_indices):
    entities = context.scene.sketcher.entities

    for duplicate_index in duplicate_indices:
        collection_name = entities.collection_name_from_index(duplicate_index)
        last_index_before_remove = (
            getattr(entities, collection_name)[-1].slvs_index if collection_name else None
        )

        update_pointers(context.scene, duplicate_index, target_index)
        entities.remove(duplicate_index)

        # SlvsEntities.remove swaps the last item into the removed slot.
        # If the merge target was that last item, its new index becomes duplicate_index.
        if (
            last_index_before_remove is not None
            and target_index == last_index_before_remove
            and duplicate_index != last_index_before_remove
        ):
            target_index = duplicate_index

    return target_index
