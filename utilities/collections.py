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


def ensure_cad_collection(scene):
    """Return this scene's CAD Sketcher collection, creating+linking it once.

    Found by a marker among the scene's own child collections (not by a global
    name) so each scene owns its own collection -- shared datablocks would leak
    one scene's sketches into another.
    """
    for child in scene.collection.children:
        if child.get(_MARKER):
            return child
    coll = bpy.data.collections.new(CAD_COLLECTION_NAME)
    coll[_MARKER] = True
    scene.collection.children.link(coll)
    return coll


def link_object(obj, scene):
    """Link ``obj`` into the scene's CAD Sketcher collection, and nowhere else.

    Safe to call on a freshly created (unlinked) object; also relocates one that
    was linked into the scene master collection.
    """
    coll = ensure_cad_collection(scene)
    if obj.name not in coll.objects:
        coll.objects.link(obj)
    master = scene.collection
    if obj.name in master.objects:
        master.objects.unlink(obj)
    return coll
