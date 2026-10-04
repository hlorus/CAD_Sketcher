"""Take something out of a part, or take a part apart, without deleting it.

Make Part and Add Assembly had no inverse: the only way out of a group was to
delete it. Unparenting by hand does not do the job either, since a member is
pinned within its part and nothing frees a body again once it has left.
"""

from typing import List, Optional

import bpy
from bpy.props import StringProperty
from bpy.types import Context, Object, Operator
from bpy.utils import register_classes_factory

from ..declarations import Operators
from ..utilities.part import (
    PART,
    assembly_root_of,
    bake_world_transform,
    clear_part_root,
    free_transform,
    group_kind,
    group_root_of,
    is_assembly_root,
    strip_part_plane,
)


def detachable(obj: Optional[Object], root: Object) -> Optional[Object]:
    """What has to be unparented for ``obj`` to leave ``root``'s group.

    A feature does not hang off the root directly: its workplane does, and the
    body and sketch ride on that. So the member to detach is the one the parent
    chain reaches just below the root, which takes the whole feature with it.
    """
    node = obj
    seen = set()
    while node is not None and node.name not in seen:
        if node.parent == root:
            return node
        seen.add(node.name)
        node = node.parent
    return None


def _freed(member: Object) -> List[Object]:
    """``member`` and everything riding on it, which all leave together."""
    return [member, *member.children_recursive]


def _release_outside(obj: Object) -> None:
    """Let go of an object that no longer belongs to a group.

    ``_release`` in the reconcile pass only frees sketches and part planes, so a
    body keeps the lock :func:`fix_transform` put on it when it joined and cannot
    be moved again. Anything leaving on purpose is freed outright.
    """
    if obj.type == "EMPTY" and group_kind(obj) is not None:
        return  # a group of its own already owns its transform
    strip_part_plane(obj)
    free_transform(obj)


def _settle(context: Context, touched) -> None:
    """Put the scene back in order after a group has changed shape.

    The members have just been placed deliberately, so the new shape is accepted
    rather than reconciled: the repair pass would read a dissolved root as one
    deleted behind its back and apply its transform to them a second time.
    """
    from ..utilities.collections import sync_part_collections
    from ..utilities.part import accept_hierarchy

    # A cutter that belongs to no part shows as wireframe rather than hiding, so
    # one taken out of a part reappears instead of looking deleted.
    accept_hierarchy(context.scene, touched)
    sync_part_collections(context.scene)
    for obj in touched:
        obj.update_tag()


class View3D_OT_slvs_remove_from_part(Operator):
    """Take this out of its part, leaving it where it stands.

    The part keeps everything else. A cutter taken out still cuts what it cut,
    but it is no longer carried by the part and shows itself again."""

    bl_idname = Operators.RemoveFromPart
    bl_label = "Remove from Part"
    bl_options = {"REGISTER", "UNDO"}

    object_name: StringProperty(name="Object", default="", options={"SKIP_SAVE"})

    @classmethod
    def poll(cls, context: Context):
        return cls._member(context.active_object) is not None

    @staticmethod
    def _member(obj: Optional[Object]):
        """The (member, root) pair to split, or None if there is nothing to."""
        root = group_root_of(obj)
        if root is None or root == obj:
            # The root itself leaves only by leaving its assembly, if it is in one.
            root = assembly_root_of(obj.parent) if obj and obj.parent else None
            if root is None:
                return None
        member = detachable(obj, root)
        return (member, root) if member is not None else None

    def execute(self, context: Context):
        obj = bpy.data.objects.get(self.object_name) or context.active_object
        pair = self._member(obj)
        if pair is None:
            self.report({"WARNING"}, "Select something inside a part")
            return {"CANCELLED"}

        member, root = pair
        freed = _freed(member)
        bake_world_transform(member)
        for obj in freed:
            _release_outside(obj)

        _settle(context, freed)
        kind = "part" if group_kind(root) == PART else "assembly"
        self.report({"INFO"}, f"'{member.name}' left the {kind} '{root.name}'")
        return {"FINISHED"}


class View3D_OT_slvs_dissolve_part(Operator):
    """Take this part apart, keeping every object in it.

    The objects stay exactly where they are, free to move on their own again.
    The inverse of Make Part. An assembly dissolves the same way, and since its
    root is an Empty holding nothing of its own, that goes with it."""

    bl_idname = Operators.DissolvePart
    bl_label = "Dissolve Part"
    bl_options = {"REGISTER", "UNDO"}

    part_name: StringProperty(name="Part Name", default="", options={"SKIP_SAVE"})

    @classmethod
    def poll(cls, context: Context):
        return group_root_of(context.active_object) is not None

    def _root(self, context: Context) -> Optional[Object]:
        """The group to dissolve: the one named, else the one that was clicked."""
        if self.part_name:
            return group_root_of(bpy.data.objects.get(self.part_name))
        return group_root_of(context.active_object)

    def execute(self, context: Context):
        root = self._root(context)
        if root is None:
            self.report({"WARNING"}, "Select a part to dissolve")
            return {"CANCELLED"}

        name = root.name
        was_assembly = is_assembly_root(root)
        members = list(root.children)
        freed = [obj for member in members for obj in _freed(member)]

        for member in members:
            bake_world_transform(member)
        for obj in freed:
            _release_outside(obj)

        clear_part_root(root)
        if was_assembly:
            # Nothing of its own to keep: the Empty only stood for the group.
            bpy.data.objects.remove(root)
        else:
            free_transform(root)
            freed.append(root)

        _settle(context, freed)
        kind = "assembly" if was_assembly else "part"
        self.report({"INFO"}, f"Dissolved {kind} '{name}'")
        return {"FINISHED"}


register, unregister = register_classes_factory(
    (View3D_OT_slvs_remove_from_part, View3D_OT_slvs_dissolve_part)
)
