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
_MARKER = "is_cad_sketcher"
_SKETCH_MARKER = "cad_sketch_collection"


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
    for sub in list(root.children):
        if sub.get(_SKETCH_MARKER) and not sub.objects:
            bpy.data.collections.remove(sub)
