"""Managed collections for CAD Sketcher.

Layout is *project-centric*, not addon-centric: each part is its own collection
at the **scene level** (where users expect their models), with cutter sketches
nested under the body they feed and each sketch's own workplane grouped inside
it. The only genuinely shared thing -- the three origin planes -- lives in a
scene-level ``Origin`` collection. There is no addon wrapper collection.

Critical invariant: nothing is **excluded** from the view layer. Excluding a
collection removes its objects from the depsgraph, which stops the convert
modifier and drops the fill (the curve object is both source and consumable).
Visibility is a display concern; evaluation must keep running.
"""

import bpy

ORIGIN_COLLECTION_NAME = "Origin"
_SKETCH_MARKER = "cad_sketch_collection"
_ORIGIN_MARKER = "cad_origin_collection"
_SYNCED_NAME = "cad_synced_name"


def _clear_object_collections(obj):
    for coll in list(obj.users_collection):
        coll.objects.unlink(obj)


def link_loose_workplane(obj, scene):
    """Link a not-yet-claimed workplane empty at the scene level (transient home).

    Used for a workplane created before its sketch exists (e.g. a face pick);
    ``nest_workplane`` moves it into the sketch's collection once that's created.
    A workplane that never gets a sketch simply stays a scene-level object.
    """
    if obj.name not in scene.collection.objects:
        _clear_object_collections(obj)
        scene.collection.objects.link(obj)
    return scene.collection


def origin_collection(scene):
    """Scene-level ``Origin`` collection holding the three origin planes.

    The only shared internals; found by a marker among the scene's own children
    so each scene owns its own.
    """
    for child in scene.collection.children:
        if child.get(_ORIGIN_MARKER):
            return child
    coll = bpy.data.collections.new(ORIGIN_COLLECTION_NAME)
    coll[_ORIGIN_MARKER] = True
    scene.collection.children.link(coll)
    return coll


def link_origin_workplane(obj, scene):
    """Group the XY/XZ/YZ origin empties in the scene-level 'Origin' collection."""
    coll = origin_collection(scene)
    if obj.name in coll.objects:
        return coll
    _clear_object_collections(obj)
    coll.objects.link(obj)
    return coll


def nest_workplane(workplane, sketch_obj):
    """Move a dedicated workplane empty into its sketch's collection.

    A workplane made for one sketch (face, entity, or free-3D origin) otherwise
    clutters the scene root; grouping it with its sketch keeps the tree tidy.
    Skipped for origin planes (shared) and for a workplane already grouped with a
    sketch (don't steal a shared custom plane). Returns the collection, or None.
    """
    if workplane is None:
        return None
    for coll in workplane.users_collection:
        if coll.get(_ORIGIN_MARKER) or coll.get(_SKETCH_MARKER):
            return None
    sub = next((c for c in sketch_obj.users_collection if c.get(_SKETCH_MARKER)), None)
    if sub is None:
        return None
    if workplane.name not in sub.objects:
        _clear_object_collections(workplane)
        sub.objects.link(workplane)
    return sub


def link_sketch_object(obj, scene):
    """Put a sketch's curve object in its own scene-level collection.

    One collection per sketch keeps the outliner readable; the sketch's workplane
    nests in here too. Idempotent: an object already in a sketch collection is
    left where it is.
    """
    for coll in obj.users_collection:
        if coll.get(_SKETCH_MARKER):
            return coll
    sub = bpy.data.collections.new(obj.name)
    sub[_SKETCH_MARKER] = True
    sub[_SYNCED_NAME] = obj.name
    # Part collections live at the scene level, not inside the internals wrapper.
    scene.collection.children.link(sub)
    _clear_object_collections(obj)
    sub.objects.link(obj)
    return sub


def sync_sketch_collection_names(scene):
    """Reconcile each per-sketch sub-collection's name with its sketch object.

    Sketches rename through a plain name field (no callback), so drift is fixed
    here (from the depsgraph handler). The last intended name is tracked so a
    collision -- where Blender appends a numeric suffix -- can't spin a rename
    loop; only writes on an actual change, settling in one pass.
    """
    for sub in _walk_sketch_collections(scene.collection):
        obj = next((o for o in sub.objects if o.type == "CURVES"), None)
        if obj is None:
            continue
        if sub.get(_SYNCED_NAME) != obj.name:
            sub.name = obj.name
            sub[_SYNCED_NAME] = obj.name


def cleanup_sketch_collections(scene):
    """Remove empty per-sketch collections (e.g. after a sketch is deleted)."""
    for sub in _walk_sketch_collections(scene.collection):
        if not sub.objects and not sub.children:
            bpy.data.collections.remove(sub)


def _walk_sketch_collections(root):
    """All per-sketch sub-collections anywhere under ``root``."""
    found, stack = [], list(root.children)
    while stack:
        coll = stack.pop()
        if coll.get(_SKETCH_MARKER):
            found.append(coll)
        stack.extend(coll.children)
    return found


def _reparent_collection(coll, parent):
    """Move ``coll`` to be the single direct child of ``parent``."""
    if coll.name in parent.children:
        return
    for scene in bpy.data.scenes:
        if coll.name in scene.collection.children:
            scene.collection.children.unlink(coll)
    for other in bpy.data.collections:
        if coll.name in other.children:
            other.children.unlink(coll)
    parent.children.link(coll)


def organize_part_nesting(scene):
    """Nest each cutter sketch's collection under the body it feeds.

    Rebuilt from the boolean dependency graph, so it converges no matter the order
    booleans were added or removed. Parts live at the scene level; a cutter's
    collection moves under the body's. The graph is a DAG (the boolean tool
    refuses cycles), so the tree can't cycle. A cutter feeding several bodies
    nests under one -- Blender has no clean multi-parent tree; the others still
    reference it, which is harmless.
    """
    from ..operators.modifiers import boolean_cutters

    container = scene.collection
    by_obj = {}
    for coll in _walk_sketch_collections(container):
        for obj in coll.objects:
            by_obj[obj] = coll

    parent_of = {}
    for body, body_coll in by_obj.items():
        for cutter in boolean_cutters(body):
            cutter_coll = by_obj.get(cutter)
            if cutter_coll is not None and cutter_coll is not body_coll:
                parent_of[cutter_coll] = body_coll

    # Flatten to the scene root first so nesting can't transiently form a cycle.
    subs = set(by_obj.values())
    for coll in subs:
        _reparent_collection(coll, container)
    for coll in subs:
        target = parent_of.get(coll)
        if target is not None:
            _reparent_collection(coll, target)
