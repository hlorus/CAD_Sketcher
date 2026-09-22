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

# Stamped on every member with the name of the root it belongs to. Membership is
# the parent chain, but a name survives the root being deleted, which is exactly
# when a member has to be recognised and put back on its feet.
PART_MEMBER_KEY = "slvs:part"

# Last known world transform of each part root, by name. A deleted root takes its
# transform with it, and Blender leaves its children holding only a local matrix,
# so the part would collapse toward the origin. Remembering the frame lets the
# reconcile put the members back where they were.
_last_root_matrices = {}


def reset_cache():
    """Drop the remembered part-root transforms (e.g. on file load)."""
    _last_root_matrices.clear()


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
    obj[PART_MEMBER_KEY] = root.name


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
    from ..model.sketch_ref import is_sketch_object

    members = list(root.children_recursive)
    # Freeze every member's world transform before any re-parenting, so each one
    # is placed from where it actually was rather than from a chain being edited.
    placements = {member.name: world_matrix_of(member) for member in members}

    for child in root.children:
        _bake_world_transform(child)

    successor = next((m for m in members if is_sketch_object(m)), None)
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


def mark_part_member(obj: bpy.types.Object, root: bpy.types.Object) -> None:
    """Record which part ``obj`` belongs to, without re-parenting it.

    For things placed by something inside the part rather than by the root
    itself, such as a sketch sitting on one of the part's workplanes.
    """
    clear_part_root(obj)
    obj[PART_MEMBER_KEY] = root.name


def _promote(obj: bpy.types.Object) -> None:
    """Make ``obj`` root its part: it owns its transform, so it is its own plane."""
    if PART_MEMBER_KEY in obj:
        del obj[PART_MEMBER_KEY]
    mark_part_root(obj)
    obj.slvs_workplane = None


def _restore_world(obj: bpy.types.Object, root_matrix: Matrix) -> None:
    """Put an orphaned member back where its (now gone) root held it."""
    obj.matrix_basis = root_matrix @ obj.matrix_parent_inverse @ obj.matrix_basis
    obj.matrix_parent_inverse = Matrix.Identity(4)


def _is_managed_member(obj: bpy.types.Object) -> bool:
    """Whether this addon placed ``obj``, and so may pin or free its transform.

    A mesh the user parented into a part is theirs to move; a sketch or one of our
    workplane empties is a feature and stays put within its part.
    """
    from ..model.sketch_ref import is_sketch_object

    return bool(is_sketch_object(obj) or PART_PLANE_KEY in obj)


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
        mark_part_root(sketch_obj)
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
    join_part(root, sketch_obj)
    fix_transform(sketch_obj)
    return root


def reconcile_parts(scene: bpy.types.Scene) -> bool:
    """Follow what the user did to the hierarchy, and repair broken parts.

    Membership *is* the parent chain, so parenting a sketch into a part (Ctrl+P,
    or a drag in the outliner) is how it joins one, and unparenting it is how it
    leaves. This pass records that: adopted members get stamped and pinned, ones
    taken out are released, and their stamp is what lets a part be put back
    together later.

    The repair half handles a root deleted with Blender's own Delete, which never
    reaches the sketch delete operator: Blender drops the parent but keeps each
    child's *local* transform, so the part's workplanes and sketches would jump by
    the part's transform. They are put back using the root's remembered frame and
    the part is handed to the next sketch in it, the same succession a deliberate
    delete follows.

    Returns True if anything changed.
    """
    from ..model.sketch_ref import is_sketch_object

    roots = {obj.name: obj for obj in scene.objects if is_part_root(obj)}
    for name, root in roots.items():
        _last_root_matrices[name] = world_matrix_of(root)

    changed = False
    touched = []
    orphans = {}
    for obj in scene.objects:
        if is_part_root(obj):
            continue

        root = part_root_of(obj)
        stamp = obj.get(PART_MEMBER_KEY)

        if root is not None:
            # In a part: either adopted by the user parenting it there, or moved
            # between parts. Parenting *is* membership, so follow it.
            if stamp != root.name:
                obj[PART_MEMBER_KEY] = root.name
                touched.append(obj)
                changed = True
            if _is_managed_member(obj) and not all(obj.lock_location):
                fix_transform(obj)
                changed = True
            continue

        if stamp is None:
            continue

        if stamp in roots:
            # Taken out of a part whose root is still there: it is on its own now.
            del obj[PART_MEMBER_KEY]
            if PART_PLANE_KEY in obj:
                strip_part_plane(obj)
            if _is_managed_member(obj):
                free_transform(obj)
            touched.append(obj)
            changed = True
            continue

        orphans.setdefault(stamp, []).append(obj)

    # A member's own children (a sketch on an orphaned workplane) are part of the
    # same wreck, even though only the member itself carries the stamp.
    for members in orphans.values():
        for member in list(members):
            members.extend(c for c in member.children_recursive if c not in members)

    if not orphans:
        # Forget roots that are simply gone, with nothing left behind.
        for name in [n for n in _last_root_matrices if n not in roots]:
            del _last_root_matrices[name]
        _refresh_cutter_display(scene, touched)
        return changed

    for root_name, members in orphans.items():
        root_matrix = _last_root_matrices.pop(root_name, None)
        if root_matrix is not None:
            for member in members:
                if member.parent is None:
                    _restore_world(member, root_matrix)

        successor = next((m for m in members if is_sketch_object(m)), None)
        if successor is None:
            # No sketch left to root the part: the remains stand on their own.
            for member in members:
                if PART_MEMBER_KEY in member:
                    del member[PART_MEMBER_KEY]
            continue

        # Lift the successor clear of whatever placed it before it can take
        # members on: leaving it parented to one would close a parent cycle.
        _bake_world_transform(successor)
        _promote(successor)
        for member in members:
            if member != successor and member.parent is None:
                if PART_PLANE_KEY in member:
                    strip_part_plane(member)
                join_part(successor, member)
        touched.extend(members)

    _refresh_cutter_display(scene, touched)
    return True


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
    from .workplane import _hide_managed_empty, mark_managed_workplane

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
            mark_part_member(empty, root)
            fix_transform(empty)
            created.append(empty)
        planes.append(empty)

    if created:
        # hide_set() needs the object present in the view layer, and linking alone
        # does not resync it -- without this the first pick after creating a part
        # raises "cannot be hidden because it is not in View Layer".
        context.view_layer.update()
        for empty in created:
            try:
                _hide_managed_empty(empty, context.scene)
            except RuntimeError:
                # Not worth failing the pick over: an unhidden plane still works.
                logger.warning("Could not hide part plane '%s'", empty.name)
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
    """
    from ..model.sketch_ref import get_active_sketch

    sketch = get_active_sketch(context)
    if sketch is not None:
        root = part_root_of(sketch.target_object)
        if root is not None:
            return root

    for obj in (context.active_object, *context.selected_objects):
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
    hide it (with the eye, never ``hide_viewport``, which would drop it from
    evaluation and with it the boolean). Two cases stay visible as wireframe
    because the user needs to find them: one that cuts across several parts, which
    belongs to no part and is the only handle on that cut, and one that means to
    cut but currently reaches nothing, which would otherwise look like a finished
    body. A solid with no boolean at all is just a body, so it shows as one.
    """
    if cuts and bodies and part_root_of(cutter) is not None:
        cutter.display_type = "TEXTURED"
        cutter.hide_set(True)
        return

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
