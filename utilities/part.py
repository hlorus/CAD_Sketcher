"""Parts: the movable unit a sketch and its features belong to.

A part is rooted in an object, not in a holder empty: the first sketch of a part
*is* its root, and stays the root once extruded into a body, so the user grabs
the geometry they see instead of hunting for an empty. Everything else in the
part (workplane empties, the sketches on them) hangs under that root with a
fixed local transform, which is what "a feature is fixed within its part" means.

The root owns the part's transform; members do not. A root therefore has no
parent and its plane is its own frame (see ``Sketch.plane_matrix``), while a
member keeps its workplane empty as both parent and plane.
"""

import logging
import math
from typing import Optional

import bpy
from mathutils import Euler, Matrix

logger = logging.getLogger(__name__)

# Stamped on the object that roots a part.
PART_ROOT_KEY = "slvs:part_root"

# Stamped on the Empty that roots an assembly: a group of parts with a transform
# of its own. An assembly has no geometry, so an Empty is the right carrier, and
# joints will later act on exactly this transform.
ASSEMBLY_ROOT_KEY = "slvs:assembly_root"

# Stamped on a workplane empty that is one of a part's own base planes, with the
# axis pair it stands for, so a second sketch on the same part plane reuses it.
PART_PLANE_KEY = "slvs:part_plane"

# A part's base planes, in its root's frame. Same orientations as the scene's
# origin planes, so "the part's XY" means what the user expects.
PART_PLANE_AXES = (
    ("XY", (0.0, 0.0, 0.0)),
    ("XZ", (math.pi / 2, 0.0, 0.0)),
    ("YZ", (math.pi / 2, 0.0, math.pi / 2)),
)

# What each root held on the last pass: its world transform and the names of its
# members. Nothing of this is written to the file -- membership lives in the
# parent chain, and this is only what the chain looked like a moment ago, which is
# what a deleted root takes with it. Blender leaves its children holding only a
# local matrix, so without the remembered frame the part would collapse toward the
# origin, and without the remembered members there would be nothing to collect.
_last_root_matrices = {}
_last_members = {}

# Same, for assembly roots.
_last_assembly_matrices = {}
_last_assembly_members = {}


def reset_cache():
    """Drop what the last pass saw (e.g. on file load); it is rebuilt at once."""
    _last_root_matrices.clear()
    _last_members.clear()
    _last_assembly_matrices.clear()
    _last_assembly_members.clear()


def is_part_root(obj: Optional[bpy.types.Object]) -> bool:
    """Whether ``obj`` roots a part (owns a part's transform)."""
    return bool(obj is not None and obj.get(PART_ROOT_KEY, False))


def free_transform(obj: bpy.types.Object) -> None:
    """Let the user move and rotate ``obj``, but never scale it.

    Scale stays locked because the solver reads a sketch's plane as a rigid frame
    (origin plus quaternion) and silently drops any scale, so a scaled sketch
    would draw and solve at different sizes.
    """
    obj.lock_location = (False, False, False)
    obj.lock_rotation = (False, False, False)
    obj.lock_scale = (True, True, True)


def fix_transform(obj: bpy.types.Object) -> None:
    """Pin ``obj`` within its part: a feature does not move on its own."""
    obj.lock_location = (True, True, True)
    obj.lock_rotation = (True, True, True)
    obj.lock_scale = (True, True, True)


def mark_part_root(obj: bpy.types.Object) -> None:
    """Make ``obj`` the root of a part, owning the part's transform."""
    obj[PART_ROOT_KEY] = True
    free_transform(obj)


def clear_part_root(obj: bpy.types.Object) -> None:
    """Drop the part-root mark, e.g. when the object joins another part."""
    if PART_ROOT_KEY in obj:
        del obj[PART_ROOT_KEY]


def is_assembly_root(obj: Optional[bpy.types.Object]) -> bool:
    """Whether ``obj`` roots an assembly (owns a group of parts)."""
    return bool(obj is not None and obj.get(ASSEMBLY_ROOT_KEY, False))


def mark_assembly_root(obj: bpy.types.Object) -> None:
    """Make ``obj`` the root of an assembly: free to move, scale still locked."""
    obj[ASSEMBLY_ROOT_KEY] = True
    free_transform(obj)


def assembly_root_of(obj: Optional[bpy.types.Object]) -> Optional[bpy.types.Object]:
    """The assembly ``obj`` sits in, or None.

    The same upward walk as :func:`part_root_of` with a different marker, so an
    assembly is simply the next level of the one hierarchy rather than a parallel
    concept: parts parent under it, sub-assemblies under those.
    """
    seen = set()
    current = obj
    while current is not None and current.name not in seen:
        if is_assembly_root(current):
            return current
        seen.add(current.name)
        current = current.parent
    return None


def create_assembly(context, name: str = "Assembly") -> bpy.types.Object:
    """Create an empty assembly root at the 3D cursor, linked at the scene level."""
    from .collections import assembly_collection, link_to_scene_root

    root = bpy.data.objects.new(name, None)
    root.empty_display_type = "ARROWS"
    root.empty_display_size = 0.5
    link_to_scene_root(root, context.scene)
    root.matrix_basis = Matrix.Translation(context.scene.cursor.location)
    mark_assembly_root(root)
    assembly_collection(root, context.scene)
    return root


def join_assembly(assembly: bpy.types.Object, obj: bpy.types.Object) -> None:
    """Put a part (or sub-assembly) in ``assembly``, keeping its world position.

    A part keeps its own transform inside an assembly: the assembly places the
    group, the part is still free to move within it.
    """
    if obj == assembly or assembly_root_of(assembly) == obj:
        return
    world = world_matrix_of(obj)
    obj.parent = assembly
    obj.matrix_parent_inverse = world_matrix_of(assembly).inverted_safe()
    obj.matrix_basis = world


def part_root_of(obj: Optional[bpy.types.Object]) -> Optional[bpy.types.Object]:
    """The root of the part ``obj`` belongs to, or None if it is in no part.

    Walks up the parent chain, ``obj`` itself included, so it answers for a
    body, a workplane empty, or a sketch on one of those workplanes alike.
    """
    seen = set()
    current = obj
    while current is not None and current.name not in seen:
        if is_part_root(current):
            return current
        seen.add(current.name)
        current = current.parent
    return None


def world_matrix_of(obj: bpy.types.Object) -> Matrix:
    """``obj``'s world transform, derived rather than read back.

    ``matrix_world`` is evaluated state: it only catches up on the next depsgraph
    update, so re-parenting several objects in one operator would read stale (or
    never-computed) matrices and bake the wrong transform. Compose it from the
    parent chain instead, which is exactly what Blender evaluates.
    """
    if obj.parent is None:
        return obj.matrix_basis.copy()
    return world_matrix_of(obj.parent) @ obj.matrix_parent_inverse @ obj.matrix_basis


def join_part(root: bpy.types.Object, obj: bpy.types.Object) -> None:
    """Put ``obj`` in ``root``'s part without moving it in world space.

    The member keeps the world transform it was placed at (a face-anchored
    workplane must stay on its face), so the part's transform is factored out
    into the parent inverse rather than re-derived.
    """
    if obj == root or part_root_of(root) == obj:
        return
    clear_part_root(obj)
    world = world_matrix_of(obj)
    obj.parent = root
    obj.matrix_parent_inverse = world_matrix_of(root).inverted_safe()
    obj.matrix_basis = world


def _bake_world_transform(obj: bpy.types.Object) -> None:
    """Unparent ``obj`` keeping its world transform (Blender's Keep Transform)."""
    world = world_matrix_of(obj)
    obj.parent = None
    obj.matrix_parent_inverse = Matrix.Identity(4)
    obj.matrix_basis = world


def rehome_children(root: bpy.types.Object) -> Optional[bpy.types.Object]:
    """Detach a part root's members before it is deleted, keeping them in place.

    Blender drops the parent silently and leaves the child's *local* transform,
    so members would jump by the part's transform when their root disappears.
    Bake it in instead, then hand the part to the next body in line: the first
    sketch left in the part becomes its root, and the rest re-join it.

    Returns the new root, or None when nothing is left to root the part.
    """

    members = list(root.children_recursive)
    # Freeze every member's world transform before any re-parenting, so each one
    # is placed from where it actually was rather than from a chain being edited.
    placements = {member.name: world_matrix_of(member) for member in members}

    for child in root.children:
        _bake_world_transform(child)

    successor = _successor(members)
    if successor is None:
        return None

    successor.parent = None
    successor.matrix_parent_inverse = Matrix.Identity(4)
    successor.matrix_basis = placements[successor.name]
    _promote(successor)
    for member in members:
        if member != successor and member.parent is None:
            join_part(successor, member)
    return successor


def _successor(members) -> Optional[bpy.types.Object]:
    """Which of these should root the part now that its root has gone.

    A body first: a part is anchored in the mesh its sketches are realised on, so
    handing the part to a sketch would leave it rooted in something that carries
    no geometry. A sketch is the fallback, for files that predate bodies.
    """
    from ..model.sketch_ref import is_sketch_object
    from .body import is_body

    return next(
        (m for m in members if is_body(m)),
        next((m for m in members if is_sketch_object(m)), None),
    )


def _promote(obj: bpy.types.Object) -> None:
    """Make ``obj`` root its part: it owns its transform, so it is its own plane."""
    mark_part_root(obj)
    obj.slvs_workplane = None


def _restore_world(obj: bpy.types.Object, root_matrix: Matrix) -> None:
    """Put an orphaned member back where its (now gone) root held it."""
    obj.matrix_basis = root_matrix @ obj.matrix_parent_inverse @ obj.matrix_basis
    obj.matrix_parent_inverse = Matrix.Identity(4)


def _is_managed_member(obj: bpy.types.Object) -> bool:
    """Whether this addon placed ``obj``, and so may pin or free its transform.

    A mesh the user parented into a part is theirs to move; a sketch or one of our
    workplane empties is a feature and stays put within its part. Linked and
    overridden data belongs to the file it came from either way.
    """
    from ..model.sketch_ref import is_sketch_object
    from .collections import is_editable

    return bool(is_editable(obj) and (is_sketch_object(obj) or PART_PLANE_KEY in obj))


def transform_owner(obj: bpy.types.Object) -> bpy.types.Object:
    """The object that actually owns ``obj``'s transform.

    A sketch never owns its own: it sits on a workplane, and that workplane hangs
    under the body its geometry is realised on, so the body is what a part is
    rooted in and what an assembly carries. Rooting the sketch instead would
    leave two movable things disagreeing about where the part is.

    A free-3D sketch is placed by an origin Empty, which plays the same role.
    """
    from .body import body_of

    parent = obj.parent
    if (
        parent is not None
        and obj.get("is_3d_sketch")
        and parent.get("is_3d_sketch_origin", False)
    ):
        return parent

    body = body_of(obj)
    return body if body is not None else obj


def promote_to_root(obj: bpy.types.Object) -> None:
    """Make ``obj`` root a part, taking over the transform from whatever placed it.

    A root owns its transform and is its own plane. A sketch created before parts
    existed (or on a base datum) is placed by a workplane empty, so promoting it
    means keeping its world position while letting go of that plane: otherwise the
    part would appear unmovable, since the geometry would keep drawing on the plane
    the sketch no longer follows.
    """
    if obj.parent is not None:
        world = world_matrix_of(obj)
        obj.parent = None
        obj.matrix_parent_inverse = Matrix.Identity(4)
        obj.matrix_basis = world
    if getattr(obj, "slvs_workplane", None) is not None:
        obj.slvs_workplane = None
    mark_part_root(obj)


def _join_keeping_its_plane(root: bpy.types.Object, obj: bpy.types.Object) -> None:
    """Put ``obj`` in ``root``'s part without separating it from its plane.

    A sketch placed by a workplane must keep following that plane, so the *plane*
    is what joins the part and the sketch rides along; re-parenting the sketch
    itself would leave its geometry drawing on a plane that no longer moves with
    it. A sketch that owns its transform simply joins directly.
    """
    plane = obj.parent
    if plane is not None and getattr(obj, "slvs_workplane", None) == plane:
        if part_root_of(plane) is None:
            join_part(root, plane)
        clear_part_root(obj)
        return
    join_part(root, obj)
    fix_transform(obj)


def settle_membership(
    sketch_obj: bpy.types.Object, bodies
) -> Optional[bpy.types.Object]:
    """Decide which part a sketch belongs to, now that it has become solid.

    Membership is settled when material appears, not when a sketch is drawn: a
    sketch on a base datum plane is global until it is extruded or revolved.
    Then either it cuts or adds to an existing body, which makes it a feature of
    that body's part (a cut has to travel with what it cuts, or moving the target
    silently changes the result), or it stands alone and roots a part of its own.

    ``bodies`` are the bodies this solid booleans into, in the order the tool
    applied them (the body whose face was sketched on leads). A sketch that
    already belongs to a part keeps that part.

    A cut reaching bodies in *several* parts belongs to none of them: it is an
    assembly-level feature, and staying global says so instead of picking an
    owner arbitrarily. Returns the part root the sketch ended up in, or None when
    it stays global.
    """
    sketch_obj = transform_owner(sketch_obj)

    existing = part_root_of(sketch_obj)
    if existing is not None:
        return existing

    # Each target either already roots/belongs to a part, or would become one.
    owners = []
    for body in bodies:
        owner = part_root_of(body) or body
        if owner not in owners:
            owners.append(owner)

    if not owners:
        promote_to_root(sketch_obj)
        return sketch_obj

    if len(owners) > 1:
        # Belongs to no single part. If they all sit in one assembly it is an
        # assembly-level feature and lives there; otherwise it stays global.
        assemblies = {
            (assembly_root_of(owner).name if assembly_root_of(owner) else None)
            for owner in owners
        }
        if len(assemblies) == 1 and None not in assemblies:
            assembly = assembly_root_of(owners[0])
            join_assembly(assembly, sketch_obj)
            fix_transform(sketch_obj)
            return assembly
        return None

    root = owners[0]
    if not is_part_root(root):
        mark_part_root(root)
    _join_keeping_its_plane(root, sketch_obj)
    return root


def _members_of(root: bpy.types.Object) -> set:
    """Names of everything in ``root``'s group, at any depth.

    Linked and overridden children are left out: they belong to the file they
    came from, so nothing here may pin, move or re-home them.
    """
    from .collections import is_editable

    return {child.name for child in root.children_recursive if is_editable(child)}


def reconcile_parts(scene: bpy.types.Scene) -> bool:
    """Follow what the user did to the hierarchy, and repair broken parts.

    Membership *is* the parent chain, so parenting a sketch into a part (Ctrl+P,
    or a drag in the outliner) is how it joins one, and unparenting it is how it
    leaves. Nothing about that is written to the file; this pass compares the
    chain with what it saw last time, pins what joined, releases what left, and
    remembers the shape for next time.

    The repair half handles a root deleted with Blender's own Delete, which never
    reaches the sketch delete operator: Blender drops the parent but keeps each
    child's *local* transform, so the part's workplanes and sketches would jump by
    the part's transform. They are put back using the root's remembered frame and
    the part is handed to the next sketch in it, the same succession a deliberate
    delete follows.

    Returns True if anything changed.
    """
    from .collections import is_editable

    roots = {
        obj.name: obj for obj in scene.objects if is_part_root(obj) and is_editable(obj)
    }
    members = {name: _members_of(root) for name, root in roots.items()}

    changed = False
    touched = []
    orphans = {}

    # What each part holds now: pin what we manage (a feature does not move on
    # its own), and note what joined since the last pass -- a mesh joining writes
    # nothing at all, but its cutter display still has to follow.
    for root_name, names in members.items():
        joined = names - _last_members.get(root_name, set())
        for name in names:
            obj = scene.objects.get(name)
            if obj is None or is_part_root(obj):
                continue
            if name in joined:
                touched.append(obj)
                changed = True
            if _is_managed_member(obj) and not all(obj.lock_location):
                fix_transform(obj)
                if obj not in touched:
                    touched.append(obj)
                changed = True

    # What has left a part since the last pass, by whichever route.
    for root_name, previous in _last_members.items():
        for name in previous - members.get(root_name, set()):
            obj = scene.objects.get(name)
            if obj is None or part_root_of(obj) is not None:
                continue  # gone, or simply moved to another part

            if root_name in roots:
                # Taken out of a part whose root is still there: on its own now.
                if PART_PLANE_KEY in obj:
                    strip_part_plane(obj)
                if _is_managed_member(obj):
                    free_transform(obj)
                touched.append(obj)
                changed = True
                continue

            orphans.setdefault(root_name, []).append(obj)

    for root_name, stranded in orphans.items():
        root_matrix = _last_root_matrices.get(root_name)
        if root_matrix is not None:
            for member in stranded:
                if member.parent is None:
                    _restore_world(member, root_matrix)

        successor = _successor(stranded)
        if successor is not None:
            # Lift the successor clear of whatever placed it before it can take
            # members on: leaving it parented to one would close a parent cycle.
            _bake_world_transform(successor)
            _promote(successor)
            for member in stranded:
                if member != successor and member.parent is None:
                    if PART_PLANE_KEY in member:
                        strip_part_plane(member)
                    join_part(successor, member)
            touched.extend(stranded)
        changed = True

    _last_members.clear()
    for name, root in roots.items():
        _last_root_matrices[name] = world_matrix_of(root)
        _last_members[name] = _members_of(root)
    for name in [n for n in _last_root_matrices if n not in roots]:
        del _last_root_matrices[name]

    _refresh_cutter_display(scene, touched)
    return changed


def reconcile_assemblies(scene: bpy.types.Scene) -> bool:
    """Follow what the user did to assemblies, and take apart broken ones.

    The part-level pass one level up: parenting a part under an assembly root is
    how it joins, unparenting is how it leaves, and an assembly root deleted
    outside our operators would otherwise leave its parts holding only a local
    transform, so they jump by the assembly's transform. Unlike a part there is no
    successor to promote: an assembly is a container, so its parts simply stand on
    their own again.

    Returns True if anything changed.
    """
    changed = False
    from .collections import is_editable

    assemblies = {
        obj.name: obj
        for obj in scene.objects
        if is_assembly_root(obj) and is_editable(obj)
    }
    members = {name: _members_of(root) for name, root in assemblies.items()}

    for assembly_name, previous in _last_assembly_members.items():
        for name in previous - members.get(assembly_name, set()):
            obj = scene.objects.get(name)
            if obj is None or assembly_root_of(obj) is not None:
                continue

            if assembly_name not in assemblies and obj.parent is None:
                # The assembly is gone: put the part back where it was standing.
                matrix = _last_assembly_matrices.get(assembly_name)
                if matrix is not None:
                    _restore_world(obj, matrix)
            changed = True

    _last_assembly_members.clear()
    for name, root in assemblies.items():
        _last_assembly_matrices[name] = world_matrix_of(root)
        _last_assembly_members[name] = members[name]
    for name in [n for n in _last_assembly_matrices if n not in assemblies]:
        del _last_assembly_matrices[name]

    return changed


def _refresh_cutter_display(scene: bpy.types.Scene, touched) -> None:
    """Re-apply the cutter display rules after membership changed.

    Joining or leaving a part changes whether a cutter should be hidden, and that
    is decided by the extrude tool, which is not running here. Only cutters that
    actually feed a body are touched, so a plain sketch the user hid stays hidden.
    """
    if not touched:
        return

    fed = _bodies_by_cutter(scene)
    for obj in touched:
        bodies = fed.get(obj.name)
        if bodies:
            update_cutter_display(obj, bodies, True)


def ensure_part_planes(context, root: bpy.types.Object) -> list:
    """Create (once) and return ``root``'s own base plane empties, in axis order.

    A part that has been moved or rotated needs planes in *its* frame to sketch
    on, not the world's. They are ordinary workplane empties parented into the
    part, so they follow it, can carry sketches, and behave like any other
    workplane; they are hidden and unselectable like the origin planes so they
    stay out of the way.

    Created from operator context only (never a depsgraph handler, which must not
    add objects), which is why the Add Sketch tool asks for them as it starts.
    """
    from .collections import link_to_scene_root
    from .workplane import hide_managed_workplane, mark_managed_workplane

    planes = []
    created = []
    for axis, euler in PART_PLANE_AXES:
        empty = existing_part_plane(root, axis)
        if empty is None:
            empty = bpy.data.objects.new(f"{root.name} {axis}", None)
            empty.empty_display_type = "PLAIN_AXES"
            empty.empty_display_size = 0.25
            empty[PART_PLANE_KEY] = axis
            mark_managed_workplane(empty)
            link_to_scene_root(empty, context.scene)
            # Plain parenting, not join_part: these planes are *defined* by the
            # part's frame, so they must inherit it rather than keep a world
            # position of their own.
            empty.parent = root
            empty.matrix_parent_inverse = Matrix.Identity(4)
            empty.matrix_basis = Euler(euler).to_matrix().to_4x4()
            fix_transform(empty)
            created.append(empty)
        planes.append(empty)

    for empty in created:
        hide_managed_workplane(empty, context)
    return planes


def part_plane_objects(context) -> list:
    """The base planes of the part in focus, or an empty list if there is none."""
    root = focused_part(context)
    if root is None:
        return []
    return [
        plane
        for plane in (existing_part_plane(root, axis) for axis, _e in PART_PLANE_AXES)
        if plane is not None
    ]


def strip_part_plane(obj: bpy.types.Object) -> None:
    """Stop treating ``obj`` as a part's base plane, keeping it as a workplane.

    Used when a plane leaves its part (its root was deleted): it no longer stands
    for the new owner's frame, so it becomes an ordinary workplane where it is.
    """
    if PART_PLANE_KEY in obj:
        del obj[PART_PLANE_KEY]
    obj.hide_select = False
    obj.hide_set(False)


def focused_part(context) -> Optional[bpy.types.Object]:
    """The part the user is working on, or None.

    Read from the active sketch first, then from the selection, so which part's
    planes are offered is always something visible on screen rather than a mode
    the user has to keep in mind.

    Only *selected* objects count. Blender leaves an object active after it is
    deselected, so consulting the active object alone would make focus stick:
    clicking empty space would never get you back to the world planes.
    """
    from ..model.sketch_ref import get_active_sketch

    sketch = get_active_sketch(context)
    if sketch is not None:
        root = part_root_of(sketch.target_object)
        if root is not None:
            return root

    selected = list(context.selected_objects)
    active = context.active_object
    if active is not None and active in selected:
        selected.insert(0, active)

    for obj in selected:
        root = part_root_of(obj)
        if root is not None:
            return root
    return None


def existing_part_plane(root: bpy.types.Object, axis: str):
    """The empty standing for ``root``'s ``axis`` base plane, if it has one."""
    for child in root.children_recursive:
        if child.get(PART_PLANE_KEY) == axis:
            return child
    return None


def update_cutter_display(cutter: bpy.types.Object, bodies, cuts: bool) -> None:
    """Show a cutter according to what it is actually doing.

    A cutter doing its job is in the way: its own solid sits over the result, so
    hide it with ``hide_viewport``. The eye (``hide_set``) is not enough: it is
    view-layer state, so an instanced copy of the part would still draw the
    cutter over its own result. ``hide_viewport`` keeps the cutter's modifiers
    evaluating and its transform live, so the boolean still reads it and still
    follows it (unlike a workplane empty, whose matrix we read ourselves and
    which must stay evaluated -- see ``_hide_managed_empty``).

    Two cases stay visible as wireframe because the user needs to find them: one
    that cuts across several parts, which belongs to no part and is the only
    handle on that cut, and one that means to cut but currently reaches nothing,
    which would otherwise look like a finished body. A solid with no boolean at
    all is just a body, so it shows as one.
    """
    from .collections import is_editable

    if not is_editable(cutter):
        return  # not ours to hide: it belongs to the file it came from

    if cuts and bodies and part_root_of(cutter) is not None:
        cutter.display_type = "TEXTURED"
        cutter.hide_viewport = True
        return

    cutter.hide_viewport = False
    cutter.hide_set(False)
    cutter.display_type = "WIRE" if cuts else "TEXTURED"


def _bodies_by_cutter(scene: bpy.types.Scene) -> dict:
    """Map each cutter to the bodies it feeds, read back out of the modifiers."""
    from ..operators.modifiers import boolean_cutters

    fed = {}
    for body in scene.objects:
        for cutter in boolean_cutters(body):
            fed.setdefault(cutter.name, []).append(body)
    return fed


def _has_solid_feature(obj: bpy.types.Object) -> bool:
    """Whether this has been made solid (an extrude or revolve modifier).

    Asked of the transform owner, not the sketch: the stack lives on the body a
    sketch is realised on.
    """
    from .extrude_nodes import EXTRUDE_NODE_GROUP
    from .revolve_nodes import REVOLVE_NODE_GROUP

    solids = {EXTRUDE_NODE_GROUP, REVOLVE_NODE_GROUP}
    return any(
        getattr(mod, "node_group", None) is not None and mod.node_group.name in solids
        for mod in obj.modifiers
    )


# The version parts ship in. A file saved by an older build may hold sketches
# that predate them, so it is offered the update; one saved by 0.32 is not, since
# that covers both this build and the pre-parts builds on the "latest" channel.
# Those files can still be updated by running the operator by hand.
PARTS_VERSION = (0, 32, 0)


def needs_part_migration(scene: bpy.types.Scene) -> bool:
    """Whether ``scene`` holds sketches from before parts existed.

    Gated on the version the file was saved with, because "a sketch in no part"
    is not by itself a sign of age: a sketch is global until it is made solid,
    and a cut spanning several parts stays global for good. Without the gate a
    brand-new file would offer to migrate itself as soon as it held a sketch.

    A scene with no recorded version was never saved, so it belongs to this
    session and is current by definition.

    Cheap enough to call while a panel is drawn (a pass over the sketches), which
    is how it is offered: never as a file-load handler, matching how legacy
    sketch migration is surfaced. Migrating restructures the hierarchy, so it is
    the user's call, not something a file open does behind their back.
    """
    from ..model.sketch_ref import get_sketches
    from .boolean_targets import sketch_source_body

    saved_with = tuple(scene.sketcher.version)
    if not any(saved_with) or saved_with >= PARTS_VERSION:
        return False

    for sketch in get_sketches(scene):
        obj = sketch.target_object
        if part_root_of(transform_owner(obj)) is not None:
            continue
        source = sketch_source_body(sketch)
        if (source is not None and source != obj) or _has_solid_feature(
            transform_owner(obj)
        ):
            return True
    return False


def migrate_parts(scene: bpy.types.Scene) -> bool:
    """Bring sketches from files written before parts existed into the model.

    Applies the same rules new sketches follow, from what the file already
    records: a sketch drawn on a body joins that body's part, and one that has
    been made solid roots a part of its own. A plain sketch that is neither is
    left exactly as it was, still placed by its workplane, and settles the first
    time it becomes solid.

    Idempotent: anything already in a part is skipped, so running it twice is
    harmless. Offered through an operator (see ``needs_part_migration``).
    """
    from ..model.sketch_ref import get_sketches
    from .boolean_targets import sketch_source_body
    from .collections import is_editable

    changed = False
    for sketch in get_sketches(scene):
        obj = sketch.target_object
        if not is_editable(obj):
            continue  # a linked sketch is the owning file's to update
        owner = transform_owner(obj)
        if part_root_of(owner) is not None:
            continue

        source = sketch_source_body(sketch)
        if source is not None and source != obj:
            root = part_root_of(source)
            if root is None:
                root = source
                mark_part_root(root)
            _join_keeping_its_plane(root, obj)
            changed = True
            continue

        if _has_solid_feature(owner):
            promote_to_root(owner)
            changed = True

    return changed


def is_part_instance(obj: Optional[bpy.types.Object]) -> bool:
    """Whether ``obj`` places a copy of a part or an assembly.

    Derived, not stamped: an Empty whose instance collection is one of the
    collections we generate *is* a placement of what that collection holds.
    """
    from .collections import is_group_collection

    return bool(
        obj is not None
        and obj.type == "EMPTY"
        and obj.instance_type == "COLLECTION"
        and is_group_collection(obj.instance_collection)
    )


def instanceable_root(obj: Optional[bpy.types.Object]) -> Optional[bpy.types.Object]:
    """What ``obj`` would place a copy of: its assembly, else its part.

    An assembly is picked over the part inside it only when the assembly itself
    is what is selected; selecting a part inside one still places that part.
    """
    if is_assembly_root(obj):
        return obj
    return part_root_of(obj)


def instance_part(context, root: bpy.types.Object, location=None) -> bpy.types.Object:
    """Place a linked copy of ``root``'s part or assembly, at the cursor by default.

    The copy is a collection instance: one source, any number of placements, so
    editing the source updates every one of them. A part's copy joins the
    source's assembly if it has one, since a second copy belongs wherever the
    first does.

    The placements are not editable where they stand (Blender renders instanced
    geometry, it does not duplicate the objects), so edits go to the source.
    """
    from .collections import assembly_collection, link_to_scene_root, part_collection

    is_assembly = is_assembly_root(root)
    coll = (
        assembly_collection(root, context.scene)
        if is_assembly
        else part_collection(root, context.scene)
    )
    # Without this the contents would be drawn at their own world position *plus*
    # the placement, putting the copy at twice the offset.
    coll.instance_offset = world_matrix_of(root).translation

    instance = bpy.data.objects.new(f"{root.name} instance", None)
    instance.instance_type = "COLLECTION"
    instance.instance_collection = coll
    instance.empty_display_size = 0.25
    link_to_scene_root(instance, context.scene)
    if location is None:
        location = context.scene.cursor.location
    instance.matrix_basis = Matrix.Translation(location)

    if not is_assembly:
        assembly = assembly_root_of(root)
        if assembly is not None:
            join_assembly(assembly, instance)
    return instance


def duplicate_part(context, root: bpy.types.Object) -> bpy.types.Object:
    """Copy a whole part: its body, its workplanes, the sketches on them.

    A part is a unit, so duplicating one has to take the lot. Blender's own
    duplicate copies just what is selected, which on a body leaves the copy
    without the cutters that shape it: a part that looks finished and is not.

    Every object gets its own data, so the copy is independent of the original;
    use :func:`instance_part` for another copy of the *same* part. References
    between the copied objects (a boolean's cutter, a sketch's workplane) are
    rewritten to point inside the copy.
    """
    from .collections import link_to_scene_root, sync_part_collections

    originals = [root, *root.children_recursive]
    copies = {}
    for obj in originals:
        copy = obj.copy()
        if obj.data is not None:
            copy.data = obj.data.copy()
        link_to_scene_root(copy, context.scene)
        copies[obj.name] = copy

    for obj in originals:
        copy = copies[obj.name]
        if obj.parent is not None and obj.parent.name in copies:
            copy.parent = copies[obj.parent.name]
            copy.matrix_parent_inverse = obj.matrix_parent_inverse.copy()
        _redirect_references(copy, copies)

    new_root = copies[root.name]
    new_root.parent = None
    mark_part_root(new_root)
    sync_part_collections(context.scene)
    return new_root


def _redirect_references(copy: bpy.types.Object, copies: dict) -> None:
    """Point a copied object's references at the copies, not the originals.

    Otherwise the new part's body would still be cut by the *old* part's cutter,
    and its sketches would still sit on the old workplanes.
    """
    from ..operators.modifiers import (
        boolean_input_ids,
        get_modifier_input,
        set_modifier_input,
    )
    from .boolean_nodes import BOOLEAN_NODE_GROUP
    from .face_anchor import KEY_SOURCE

    plane = copy.slvs_workplane
    if plane is not None and plane.name in copies:
        copy.slvs_workplane = copies[plane.name]

    # A copied body must read the copied sketch, not the original's.
    from .body import BODY_SKETCH_KEY, bind_body_to_sketch, is_body

    source_sketch = copy.get(BODY_SKETCH_KEY)
    if is_body(copy) and isinstance(source_sketch, bpy.types.Object):
        if source_sketch.name in copies:
            copied_sketch = copies[source_sketch.name]
            copy[BODY_SKETCH_KEY] = copied_sketch
            copied_sketch.slvs_body = copy
            bind_body_to_sketch(copy, copied_sketch)

    source = copy.get(KEY_SOURCE)
    if isinstance(source, bpy.types.Object) and source.name in copies:
        copy[KEY_SOURCE] = copies[source.name]

    for modifier in copy.modifiers:
        group = getattr(modifier, "node_group", None)
        if modifier.type != "NODES" or group is None:
            continue
        if group.name != BOOLEAN_NODE_GROUP:
            continue
        cutter_id = boolean_input_ids(group)["Cutter"]
        cutter = get_modifier_input(modifier, cutter_id)
        if cutter is not None and cutter.name in copies:
            set_modifier_input(modifier, cutter_id, copies[cutter.name])
