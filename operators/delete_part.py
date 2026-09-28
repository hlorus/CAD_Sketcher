"""Delete a whole part."""

from typing import List, Optional

import bpy
from bpy.props import StringProperty
from bpy.types import Collection, Context, Object, Operator
from bpy.utils import register_classes_factory

from ..declarations import Operators
from ..utilities.part import part_root_of


def part_members(root: Object) -> List[Object]:
    """Every object the part rooted at ``root`` is made of, the root included.

    The same set :func:`~..utilities.part.duplicate_part` copies: a part is its
    hierarchy, so the bodies, the workplane empties and the sketches on them all
    hang below its root.
    """
    from ..utilities.collections import is_editable

    return [obj for obj in (root, *root.children_recursive) if is_editable(obj)]


def part_placements(root: Object) -> List[Object]:
    """The Empties rendering a copy of ``root``'s part elsewhere in the scene.

    A placement draws a collection it does not own, so deleting the part behind
    it would leave an Empty rendering nothing.
    """
    from ..utilities.collections import is_editable

    coll = _own_collection(root)
    if coll is None:
        return []
    return [
        obj
        for obj in bpy.data.objects
        if obj.instance_collection == coll and is_editable(obj)
    ]


def _own_collection(root: Object) -> Optional[Collection]:
    """The generated collection holding this part, without creating one."""
    from ..utilities.collections import is_part_collection

    return next((c for c in root.users_collection if is_part_collection(c)), None)


class View3D_OT_slvs_delete_part(Operator):
    """Delete this part: its body, its sketches, and the cutters shaping it.

    A part is a unit, so removing one has to take the lot. Deleting only the body
    leaves the part standing, re-rooted in whatever is left of it, and deleting
    the objects by hand is awkward while the cutters are hidden."""

    bl_idname = Operators.DeletePart
    bl_label = "Delete Part"
    bl_options = {"REGISTER", "UNDO"}

    part_name: StringProperty(name="Part Name", default="", options={"SKIP_SAVE"})

    @classmethod
    def poll(cls, context: Context):
        return part_root_of(context.active_object) is not None

    def _root(self, context: Context) -> Optional[Object]:
        """The part to delete: the one named, else the one that was clicked."""
        if self.part_name:
            return part_root_of(bpy.data.objects.get(self.part_name))
        return part_root_of(context.active_object)

    def execute(self, context: Context):
        from ..model.sketch_ref import get_active_sketch
        from ..utilities.collections import sync_part_collections
        from .utilities import activate_sketch

        root = self._root(context)
        if root is None:
            self.report({"WARNING"}, "Select a part to delete")
            return {"CANCELLED"}

        name = root.name
        doomed = part_members(root)

        # Leaving the sketch first: editing one whose object is about to go would
        # leave the sketch mode pointing at nothing.
        active = get_active_sketch(context)
        if active and active.target_object in doomed:
            activate_sketch(context, None, self)

        for obj in (*part_placements(root), *doomed):
            bpy.data.objects.remove(obj)

        # Drops the collection the deletion emptied (orphan constraints go with
        # the depsgraph handler).
        sync_part_collections(context.scene)

        self.report({"INFO"}, f"Deleted part '{name}'")
        return {"FINISHED"}


register, unregister = register_classes_factory((View3D_OT_slvs_delete_part,))
