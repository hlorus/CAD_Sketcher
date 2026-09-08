"""Managed collection for CAD Sketcher's internal objects.

Groups the add-on's objects -- sketch curve objects and workplane empties --
under one collection per scene instead of scattering them through the scene's
master collection, so the outliner stays clean and the internals are easy to
find or hide as a group.

Critical invariant: the collection is **hidden, never excluded**. Excluding it
from the view layer removes its objects from the depsgraph, which stops the
convert modifier and drops the fill (the curve object is both source and
consumable). Visibility is a display concern; evaluation must keep running.
"""

import bpy

CAD_COLLECTION_NAME = "CAD Sketcher"
ORIGIN_COLLECTION_NAME = "Origin"
_MARKER = "is_cad_sketcher"
_SKETCH_MARKER = "cad_sketch_collection"
_ORIGIN_MARKER = "cad_origin_collection"


def _find_cad_collection(scene):
    for child in scene.collection.children:
        if child.get(_MARKER):
            return child
    return None


def ensure_cad_collection(scene):
    """Return this scene's CAD Sketcher collection, creating+linking it once.

    Found by a marker among the scene's own child collections (not by a global
    name) so each scene owns its own collection -- shared datablocks would leak
    one scene's sketches into another.
    """
    coll = _find_cad_collection(scene)
    if coll is not None:
        return coll
    coll = bpy.data.collections.new(CAD_COLLECTION_NAME)
    coll[_MARKER] = True
    scene.collection.children.link(coll)
    return coll


def _clear_object_collections(obj):
    for coll in list(obj.users_collection):
        coll.objects.unlink(obj)


def link_object(obj, scene):
    """Link ``obj`` into the scene's CAD Sketcher root collection, and nowhere else.

    Used for shared internals (workplane empties). Safe on a freshly created
    object; also relocates one linked into the scene master collection.
    """
    coll = ensure_cad_collection(scene)
    if obj.name not in coll.objects:
        coll.objects.link(obj)
    master = scene.collection
    if obj.name in master.objects:
        master.objects.unlink(obj)
    return coll


def origin_collection(scene):
    """Sub-collection under the CAD root that holds the three origin planes."""
    root = ensure_cad_collection(scene)
    for child in root.children:
        if child.get(_ORIGIN_MARKER):
            return child
    coll = bpy.data.collections.new(ORIGIN_COLLECTION_NAME)
    coll[_ORIGIN_MARKER] = True
    root.children.link(coll)
    return coll


def link_origin_workplane(obj, scene):
    """Group the XY/XZ/YZ origin empties in their own 'Origin' sub-collection."""
    coll = origin_collection(scene)
    if obj.name in coll.objects:
        return coll
    _clear_object_collections(obj)
    coll.objects.link(obj)
    return coll


def link_sketch_object(obj, scene):
    """Put a sketch's curve object in its own sub-collection under the CAD root.

    One collection per sketch keeps the outliner readable; workplanes stay in the
    root (they're shared and hidden). Idempotent: an object already in a sketch
    sub-collection is left where it is.
    """
    for coll in obj.users_collection:
        if coll.get(_SKETCH_MARKER):
            return coll
    root = ensure_cad_collection(scene)
    sub = bpy.data.collections.new(obj.name)
    sub[_SKETCH_MARKER] = True
    root.children.link(sub)
    _clear_object_collections(obj)
    sub.objects.link(obj)
    return sub


def cleanup_sketch_collections(scene):
    """Remove empty per-sketch sub-collections (e.g. after a sketch is deleted)."""
    root = _find_cad_collection(scene)
    if root is None:
        return
    for sub in _walk_sketch_collections(root):
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
    """Move ``coll`` to be a direct child of ``parent`` (single parent)."""
    if coll.name in parent.children:
        return
    for other in bpy.data.collections:
        if coll.name in other.children:
            other.children.unlink(coll)
    parent.children.link(coll)


def organize_part_nesting(scene):
    """Nest each cutter sketch's collection under the body it feeds.

    Rebuilt from the boolean dependency graph, so it converges no matter the order
    booleans were added or removed. The graph is a DAG (the boolean tool refuses
    cycles), so the collection tree can't cycle either. A cutter feeding several
    bodies nests under one of them -- Blender has no clean multi-parent tree; the
    other bodies still reference it, which is harmless.
    """
    root = _find_cad_collection(scene)
    if root is None:
        return
    from ..operators.modifiers import boolean_cutters

    by_obj = {}
    for coll in _walk_sketch_collections(root):
        for obj in coll.objects:
            by_obj[obj] = coll

    parent_of = {}
    for body, body_coll in by_obj.items():
        for cutter in boolean_cutters(body):
            cutter_coll = by_obj.get(cutter)
            if cutter_coll is not None and cutter_coll is not body_coll:
                parent_of[cutter_coll] = body_coll

    # Flatten to root first so nesting can't transiently form a descendant cycle.
    subs = set(by_obj.values())
    for coll in subs:
        _reparent_collection(coll, root)
    for coll in subs:
        target = parent_of.get(coll)
        if target is not None:
            _reparent_collection(coll, target)
