"""Managed collections for CAD Sketcher.

Layout is *project-centric*, not addon-centric: one collection per **part** at the
scene level (where users expect their models), nested inside its assembly's
collection when it has one. The only genuinely shared thing, the three origin
planes, lives in a scene-level ``Origin`` collection. There is no addon wrapper
collection.

Collections are a **derived view**, never the authority: membership lives in the
object hierarchy (see ``utilities.part``), and ``sync_part_collections`` moves
objects to follow it. Names are set when a collection is created and then left
alone, so users can rename containers and a renamed root does not churn.

Critical invariant: nothing is **excluded** from the view layer. Excluding a
collection removes its objects from the depsgraph, which stops the convert
modifier and drops the fill (the curve object is both source and consumable).
Visibility is a display concern; evaluation must keep running.
"""

import bpy

ORIGIN_COLLECTION_NAME = "Origin"
_ORIGIN_MARKER = "cad_origin_collection"
_PART_MARKER = "cad_part_collection"
_ASSEMBLY_MARKER = "cad_assembly_collection"

# Per-sketch collections from before parts existed. Recognised only so old files
# can be dissolved into the part layout; nothing creates them any more.
_LEGACY_SKETCH_MARKER = "cad_sketch_collection"


# Signature of the hierarchy the layout is derived from, so the sync only runs
# when something it cares about moved. Rebuilding it is one cheap pass; the sync
# itself walks subtrees and rewrites collection links, which is not.
_last_signature = {}


def reset_cache():
    """Forget the hierarchy signature (e.g. on file load)."""
    _last_signature.clear()


def _hierarchy_signature(scene):
    """What the collection layout depends on: parenting, roles, and placement."""
    from .part import ASSEMBLY_ROOT_KEY, PART_ROOT_KEY

    return tuple(
        (
            obj.name,
            obj.parent.name if obj.parent else "",
            bool(obj.get(PART_ROOT_KEY, False)),
            bool(obj.get(ASSEMBLY_ROOT_KEY, False)),
            obj.users_collection[0].name if obj.users_collection else "",
        )
        for obj in scene.objects
    )


def _clear_object_collections(obj):
    for coll in list(obj.users_collection):
        coll.objects.unlink(obj)


def link_to_scene_root(obj, scene):
    """Link ``obj`` directly at the scene level.

    The home for anything that belongs to no part: a global sketch, a workplane
    nobody has claimed yet, a cutter that spans parts. Objects that *are* in a
    part are moved into its collection by ``sync_part_collections``.
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


# ---------------------------------------------------------------------------
# Part and assembly collections
# ---------------------------------------------------------------------------


def _marked_collections(root, marker):
    """Every collection under ``root`` carrying ``marker``."""
    found, stack = [], list(root.children)
    while stack:
        coll = stack.pop()
        if coll.get(marker):
            found.append(coll)
        stack.extend(coll.children)
    return found


def _link_into(obj, coll):
    """Put ``obj`` in ``coll`` and nowhere else. True if that changed anything."""
    if len(obj.users_collection) == 1 and obj.users_collection[0] == coll:
        return False
    _clear_object_collections(obj)
    coll.objects.link(obj)
    return True


def _collection_for(obj, scene, marker, created=None):
    """The collection standing for ``obj`` (a part or assembly root), created once.

    Found by containment: a root's collection is the marked one holding it. That
    needs no stored link back to the root, so renaming either, or the user moving
    a root somewhere of their own, cannot leave a dangling reference.
    """
    for coll in _marked_collections(scene.collection, marker):
        if obj.name in coll.objects:
            return coll
    coll = bpy.data.collections.new(obj.name)
    coll[marker] = True
    scene.collection.children.link(coll)
    # Link the root straight away, or the next pass would not recognise this
    # collection as its own and would make another.
    _link_into(obj, coll)
    if created is not None:
        created.append(coll)
    return coll


def is_part_collection(coll) -> bool:
    """Whether ``coll`` is the generated collection of a part."""
    return bool(coll is not None and coll.get(_PART_MARKER, False))


def part_collection(root, scene, created=None):
    """The collection holding the part rooted at ``root``."""
    return _collection_for(root, scene, _PART_MARKER, created)


def assembly_collection(root, scene, created=None):
    """The collection holding the assembly rooted at ``root``."""
    return _collection_for(root, scene, _ASSEMBLY_MARKER, created)


def _reparent_collection(coll, parent):
    """Move ``coll`` to be a direct child of ``parent``, unlinked from elsewhere."""
    if coll.name in parent.children:
        return False
    for scene in bpy.data.scenes:
        if coll.name in scene.collection.children:
            scene.collection.children.unlink(coll)
    for other in bpy.data.collections:
        if coll.name in other.children:
            other.children.unlink(coll)
    parent.children.link(coll)
    return True


def dissolve_legacy_sketch_collections(scene) -> bool:
    """Empty out the per-sketch collections older files were saved with.

    Their objects move to the scene level, from where the part sync claims the
    ones that belong to a part. Left in place they would strand old files in a
    layout nothing maintains any more.
    """
    changed = False
    for coll in _marked_collections(scene.collection, _LEGACY_SKETCH_MARKER):
        for obj in list(coll.objects):
            link_to_scene_root(obj, scene)
            changed = True
        for child in list(coll.children):
            _reparent_collection(child, scene.collection)
            changed = True
        bpy.data.collections.remove(coll)
        changed = True
    return changed


def sync_part_collections(scene) -> bool:
    """Move objects into the collection of the part (and assembly) they are in.

    Derived from the object hierarchy, so it converges regardless of how things
    got there: parenting a sketch into a part moves it here on the next pass, and
    taking it out returns it to the scene level. Collections that end up empty are
    removed. Returns True if anything changed.
    """
    from .part import assembly_root_of, is_assembly_root, is_part_root

    signature = _hierarchy_signature(scene)
    if _last_signature.get(scene.name) == signature:
        return False

    changed = dissolve_legacy_sketch_collections(scene)

    created = []
    owned = {}
    for obj in scene.objects:
        if is_assembly_root(obj):
            coll = assembly_collection(obj, scene, created)
            for member in (obj, *obj.children_recursive):
                # Parts inside keep their own collection; only loose members of
                # the assembly itself live directly in it.
                if not is_part_root(member) and assembly_root_of(member) is obj:
                    owned.setdefault(member.name, coll)

    for obj in scene.objects:
        if not is_part_root(obj):
            continue
        coll = part_collection(obj, scene, created)
        assembly = assembly_root_of(obj)
        if assembly is not None:
            if _reparent_collection(coll, assembly_collection(assembly, scene)):
                changed = True
        for member in (obj, *obj.children_recursive):
            owned[member.name] = coll

    for obj in scene.objects:
        target = owned.get(obj.name)
        if target is not None:
            if _link_into(obj, target):
                changed = True
            continue
        # Not in a part or assembly: belongs at the scene level, unless the user
        # (or the origin collection) put it somewhere deliberate.
        for coll in obj.users_collection:
            if coll.get(_PART_MARKER) or coll.get(_ASSEMBLY_MARKER):
                link_to_scene_root(obj, scene)
                changed = True
                break

    changed = changed or bool(created)

    for marker in (_PART_MARKER, _ASSEMBLY_MARKER):
        for coll in _marked_collections(scene.collection, marker):
            if not coll.objects and not coll.children:
                bpy.data.collections.remove(coll)
                changed = True

    # Record the settled state, not the one we were handed, so the next pass is
    # skipped rather than reacting to our own writes.
    _last_signature[scene.name] = _hierarchy_signature(scene)
    return changed
