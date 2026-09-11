"""Demote a linked-duplicated sketch (Alt+D) into a dumb linked consumable.

Blender's *linked* duplicate shares the sketch's Curves datablock between two
objects. Two objects driving one sketch is meaningless and makes the self-heal
churn (it can't separate the shared constraint uids, see utilities.validate), so
instead the copy is demoted: it gets its own empty data, loses its sketch role,
and shows the *source* sketch's evaluated result through an Object Info node. The
result is a live, linked consumable, no second sketch and no separate companion
object to keep in sync (the depsgraph tracks the dependency).

A *full* duplicate (Shift+D) copies the data, so each object owns its own sketch
and is left alone; only the ``_OWNER`` bookkeeping distinguishes the two (a copy
that shares the owner's datablock is a linked duplicate; a copy with its own
datablock just claims ownership).

The object transform must run outside the depsgraph handler (it swaps ``data``
and rebuilds the modifier stack), so the handler only *plans* the demotions and
a one-shot timer performs them.
"""

import logging

import bpy

from ..model.sketch_ref import _DOF, _OWNER, _SOLVER_STATE, _TAG, is_sketch_object

logger = logging.getLogger(__name__)

_CONSUME_GROUP = "CAD Sketcher Consumable"
_CONSUME_MODIFIER = "CAD Sketcher Consumable"

# Demotions queued by the depsgraph handler, performed by the timer below.
_pending: list[tuple[str, str]] = []


def _consume_node_group(source: bpy.types.Object) -> bpy.types.NodeTree:
    """Node group surfacing ``source``'s evaluated geometry, realized to real mesh.

    The source is baked into the Object Info node as an object pointer (stable
    across renames, and GN modifier object inputs can't be set by subscript in
    Blender 5.x). One group per source, reused across its consumables.
    """
    name = f"{_CONSUME_GROUP}: {source.name}"
    ng = bpy.data.node_groups.get(name)
    if ng is None:
        ng = bpy.data.node_groups.new(name, "GeometryNodeTree")
        ng.interface.new_socket(
            "Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry"
        )
        gout = ng.nodes.new("NodeGroupOutput")
        info = ng.nodes.new("GeometryNodeObjectInfo")
        info.name = "source_info"
        # ORIGINAL (not RELATIVE): emit the source's geometry in its local space
        # so the *consumable's own* object transform places it. The Alt+D copy
        # inherits the source's matrix, so it starts overlapping the source and
        # can then be grabbed and moved like any object. RELATIVE would glue it
        # to the source's world position, making it impossible to move.
        info.transform_space = "ORIGINAL"
        realize = ng.nodes.new("GeometryNodeRealizeInstances")
        ng.links.new(info.outputs["Geometry"], realize.inputs[0])
        ng.links.new(realize.outputs[0], gout.inputs[0])
    info = ng.nodes.get("source_info")
    if info is not None:
        info.inputs["Object"].default_value = source
    return ng


def demote_to_consumable(copy: bpy.types.Object, source: bpy.types.Object) -> None:
    """Turn a linked-dup sketch ``copy`` into a live consumable of ``source``.

    Gives ``copy`` its own empty data (so it stops sharing the source sketch),
    strips its sketch identity, and drives it from an Object Info node reading the
    source's evaluated result.
    """
    for key in (_TAG, _SOLVER_STATE, _DOF):
        if key in copy:
            del copy[key]

    # Sketches lock their transform (placement comes from the parent workplane),
    # and Alt+D copies that lock. A consumable is a free-standing object, so
    # unlock it, otherwise it can't be grabbed and moved after the duplicate.
    copy.lock_location = (False, False, False)
    copy.lock_rotation = (False, False, False)
    copy.lock_scale = (False, False, False)

    # Own, empty data: stops sharing the source's sketch datablock (which is what
    # made the self-heal churn) while keeping ``copy`` a Curves object.
    copy.data = bpy.data.hair_curves.new(copy.name)

    for modifier in list(copy.modifiers):
        copy.modifiers.remove(modifier)

    modifier = copy.modifiers.new(_CONSUME_MODIFIER, "NODES")
    modifier.node_group = _consume_node_group(source)


def plan_linked_duplicates(scene: bpy.types.Scene) -> list[tuple[str, str]]:
    """Claim datablock ownership and return ``(copy_name, source_name)`` to demote.

    Sketch objects are grouped by their Curves datablock. A datablock used by a
    single sketch object is that object's own (claim it). A datablock shared by
    several is a linked duplicate: keep the owner, list the rest for demotion.
    Only stamps ownership when it changes, so this is quiet on the common path.
    """
    by_data: dict[str, tuple[bpy.types.ID, list[bpy.types.Object]]] = {}
    for obj in scene.objects:
        if is_sketch_object(obj) and obj.data is not None:
            by_data.setdefault(obj.data.name, (obj.data, []))[1].append(obj)

    demote: list[tuple[str, str]] = []
    for data, objs in by_data.values():
        if len(objs) == 1:
            owner = objs[0]
            if data.get(_OWNER) != owner.name:
                data[_OWNER] = owner.name
            continue

        # Shared datablock -> linked duplicate. Keep the stamped owner if it's
        # among the users, else adopt the first deterministically.
        owner_name = data.get(_OWNER)
        keep = next((o for o in objs if o.name == owner_name), None) or objs[0]
        if data.get(_OWNER) != keep.name:
            data[_OWNER] = keep.name
        demote.extend((o.name, keep.name) for o in objs if o is not keep)

    return demote


def _run_demotions() -> None:
    """Timer: perform queued demotions (safe outside the depsgraph handler)."""
    pending, _pending[:] = list(_pending), []
    seen = set()
    for copy_name, source_name in pending:
        if (copy_name, source_name) in seen:
            continue
        seen.add((copy_name, source_name))
        copy = bpy.data.objects.get(copy_name)
        source = bpy.data.objects.get(source_name)
        # Only demote if still a linked duplicate (guards against undo/edits
        # between planning and this timer firing).
        if copy and source and copy is not source and copy.data is source.data:
            try:
                demote_to_consumable(copy, source)
            except Exception:
                logger.exception("Failed to demote linked sketch '%s'", copy_name)
    return None


def schedule_linked_duplicate_demotions(scene: bpy.types.Scene) -> None:
    """Plan linked-duplicate demotions and defer the object transforms to a timer.

    Called from the depsgraph handler. Planning only writes a data custom
    property; the heavier object mutation (data swap + modifier rebuild) can't run
    mid-evaluation, so it's deferred.
    """
    plan = plan_linked_duplicates(scene)
    if not plan:
        return
    _pending.extend(plan)
    if not bpy.app.timers.is_registered(_run_demotions):
        bpy.app.timers.register(_run_demotions)
