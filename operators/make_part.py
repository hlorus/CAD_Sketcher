"""Make the selected objects a part by hand."""

from bpy.types import Context, Operator
from bpy.utils import register_classes_factory

from ..declarations import Operators
from ..utilities.part import (
    is_part_instance,
    is_part_root,
    join_part,
    promote_to_root,
)


def _can_become_part(obj) -> bool:
    """Whether ``obj`` is something a part can be rooted in.

    A placement renders a part rather than being geometry, and an Empty holding a
    group is what an assembly is, so neither can root a part.
    """
    return bool(
        obj is not None
        and not is_part_root(obj)
        and not is_part_instance(obj)
        and obj.type != "EMPTY"
    )


def _can_root_a_part(obj) -> bool:
    """Whether ``obj`` can be the part the selection ends up in.

    Either it becomes one, or it already is one and the rest join it, which is
    how this doubles as "add these to that part".
    """
    return bool(obj is not None and (is_part_root(obj) or _can_become_part(obj)))


class View3D_OT_slvs_make_part(Operator):
    """Make the selected objects a part, rooted in the active one.

    A part usually appears on its own, when a sketch is made solid or drawn on
    something. This is for the cases that never pass through those tools, such as
    imported geometry you want to sketch on, place in an assembly, or reuse. With
    a part already active, the rest of the selection joins it."""

    bl_idname = Operators.MakePart
    bl_label = "Make Part"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: Context):
        return _can_root_a_part(context.active_object)

    def execute(self, context: Context):
        from ..utilities.collections import sync_part_collections

        root = context.active_object
        if not _can_root_a_part(root):
            self.report({"WARNING"}, "Select what the part should be rooted in")
            return {"CANCELLED"}

        if not is_part_root(root):
            promote_to_root(root)

        members = [
            obj
            for obj in context.selected_objects
            if obj != root and _can_become_part(obj)
        ]
        for member in members:
            join_part(root, member)

        sync_part_collections(context.scene)
        self.report({"INFO"}, f"Part '{root.name}' with {len(members) + 1} object(s)")
        return {"FINISHED"}


register, unregister = register_classes_factory((View3D_OT_slvs_make_part,))
