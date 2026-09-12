"""Reconcile a linked-duplicated sketch (Alt+D) so it stops behaving as a sketch.

Blender's *linked* duplicate shares the sketch's Curves datablock between two
objects. Two objects driving one sketch is meaningless: it shows as a second
sketch entry and makes the self-heal churn (it re-mints a shared constraint uid
it can never separate, leaking a scene key per pass, see utilities.validate).

The minimal fix is to drop the copy's sketch role: remove its sketch tag (so it
leaves ``get_sketches`` and the self-heal) and unlock its transform (sketches
lock theirs, placed by their workplane). The copy keeps the shared data and its
copied modifiers, so it still displays the source's result and moves with its own
transform, exactly the native linked-duplicate behaviour, just no longer a
second sketch.

A *full* duplicate (Shift+D) copies the data, so each object owns its own sketch
and is left alone; the ``_OWNER`` stamp on the data distinguishes the two.
"""

import bpy

from ..model.sketch_ref import _DOF, _OWNER, _SOLVER_STATE, _TAG, is_sketch_object


def _demote(copy: bpy.types.Object) -> None:
    """Drop a linked-duplicate copy's sketch role: untag and unlock its transform."""
    for key in (_TAG, _SOLVER_STATE, _DOF):
        if key in copy:
            del copy[key]
    copy.lock_location = (False, False, False)
    copy.lock_rotation = (False, False, False)
    copy.lock_scale = (False, False, False)


def reconcile_linked_duplicates(scene: bpy.types.Scene) -> bool:
    """Demote the copy of any linked-duplicated sketch. Returns True if changed.

    Sketch objects are grouped by their Curves datablock. A datablock with one
    sketch object is that object's own (claim ownership). A datablock shared by
    several is a linked duplicate: keep the owner and demote the rest. Only
    stamps ownership when it changes, so this is quiet on the common path.
    """
    by_data: dict[str, tuple[bpy.types.ID, list[bpy.types.Object]]] = {}
    for obj in scene.objects:
        if is_sketch_object(obj) and obj.data is not None:
            by_data.setdefault(obj.data.name, (obj.data, []))[1].append(obj)

    changed = False
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
        for obj in objs:
            if obj is not keep:
                _demote(obj)
                changed = True

    return changed
