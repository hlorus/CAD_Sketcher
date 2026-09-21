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

from typing import Optional

import bpy
from mathutils import Matrix

# Stamped on the object that roots a part.
PART_ROOT_KEY = "slvs:part_root"

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


def mark_part_root(obj: bpy.types.Object) -> None:
    """Make ``obj`` the root of a part: free to move, scale still locked.

    Scale is kept locked because the solver reads the plane as a rigid frame
    (origin plus quaternion) and silently drops any scale, so a scaled part
    would draw and solve at different sizes.
    """
    obj[PART_ROOT_KEY] = True
    obj.lock_location = (False, False, False)
    obj.lock_rotation = (False, False, False)
    obj.lock_scale = (True, True, True)


def clear_part_root(obj: bpy.types.Object) -> None:
    """Drop the part-root mark, e.g. when the object joins another part."""
    if PART_ROOT_KEY in obj:
        del obj[PART_ROOT_KEY]


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


def reconcile_parts(scene: bpy.types.Scene) -> bool:
    """Repair parts whose root was deleted or unparented outside our operators.

    Deleting a root with Blender's own Delete never reaches the sketch delete
    operator, and Blender silently drops the parent while keeping each child's
    *local* transform, so the part's workplanes and sketches jump by the part's
    transform. Put them back using the root's remembered frame and hand the part
    to the next sketch in it, the same succession a deliberate delete follows.

    Returns True if anything changed.
    """
    from ..model.sketch_ref import is_sketch_object

    roots = {obj.name: obj for obj in scene.objects if is_part_root(obj)}
    for name, root in roots.items():
        _last_root_matrices[name] = world_matrix_of(root)

    orphans = {}
    for obj in scene.objects:
        root_name = obj.get(PART_MEMBER_KEY)
        if not root_name or root_name in roots:
            continue
        if obj.parent is not None and part_root_of(obj) is not None:
            # Still placed inside some part; its stamp is just stale.
            obj[PART_MEMBER_KEY] = part_root_of(obj).name
            continue
        orphans.setdefault(root_name, []).append(obj)

    # A member's own children (a sketch on an orphaned workplane) are part of the
    # same wreck, even though only the member itself carries the stamp.
    for members in orphans.values():
        for member in list(members):
            members.extend(c for c in member.children_recursive if c not in members)

    if not orphans:
        # Forget roots that are simply gone, with nothing left behind.
        for name in [n for n in _last_root_matrices if n not in roots]:
            del _last_root_matrices[name]
        return False

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
                join_part(successor, member)

    return True
