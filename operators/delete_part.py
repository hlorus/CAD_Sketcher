"""Delete what an object belongs to: its feature, its part, or its assembly.

Blender's own Delete takes the clicked object alone, which on anything built here
leaves the rest of it behind: a cutter's boolean without its cutter, a part
re-rooted in the features that shaped it, an assembly of nothing. Each operator
takes one whole unit, at the three granularities the model has.
"""

from typing import List, Optional

import bpy
from bpy.props import StringProperty
from bpy.types import Collection, Context, Object, Operator
from bpy.utils import register_classes_factory

from ..declarations import Operators
from ..utilities.part import (
    PART_PLANE_KEY,
    assembly_root_of,
    is_assembly_root,
    part_root_of,
    transform_owner,
)


def group_members(root: Object) -> List[Object]:
    """Every object the part or assembly rooted at ``root`` is made of.

    The same set :func:`~..utilities.part.duplicate_part` copies: a group is its
    hierarchy, so the bodies, the workplane empties and the sketches on them all
    hang below its root.
    """
    from ..utilities.collections import is_editable

    return [obj for obj in (root, *root.children_recursive) if is_editable(obj)]


def feature_root(obj: Optional[Object]) -> Optional[Object]:
    """The body of the feature ``obj`` belongs to, or None if it is not one.

    A feature is a member of a part that is not the part's root: the cut or the
    solid added on top of the base body. A sketch resolves to the body it is
    realised on, since that is what the feature *is*; a datum plane resolves to
    nothing, as it holds features rather than being one.
    """
    root = part_root_of(obj)
    if root is None:
        return None
    owner = transform_owner(obj)
    if owner is None or owner == root or owner.type == "EMPTY":
        return None
    return owner


def feature_members(body: Object) -> List[Object]:
    """The objects making up the feature realised on ``body``.

    The body, the sketch it is built from, and anything hanging below it. The
    workplane the sketch sits on is not included: it may be a part datum, or hold
    other sketches, so it is only removed when it is left holding nothing (see
    :func:`_spent_plane`).
    """
    from ..utilities.body import sketch_of
    from ..utilities.collections import is_editable

    members = [body, *body.children_recursive]
    sketch = sketch_of(body)
    if sketch is not None and sketch not in members:
        members.append(sketch)
    return [obj for obj in members if is_editable(obj)]


def _spent_plane(body: Object, doomed) -> Optional[Object]:
    """The workplane left holding nothing once ``doomed`` is gone.

    A feature's plane is usually made for it, so leaving it behind would litter
    the part with empties. One that still carries another sketch, or that is a
    part's base datum, stays.
    """
    from ..utilities.workplane import is_managed_workplane

    plane = body.parent
    if plane is None or not is_managed_workplane(plane) or PART_PLANE_KEY in plane:
        return None
    if any(child not in doomed for child in plane.children):
        return None
    return plane


def part_placements(root: Object) -> List[Object]:
    """The Empties rendering a copy of ``root``'s group elsewhere in the scene.

    A placement draws a collection it does not own, so deleting the group behind
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
    """The generated collection holding this group, without creating one."""
    from ..utilities.collections import is_group_collection

    return next((c for c in root.users_collection if is_group_collection(c)), None)


def _strip_booleans(doomed) -> None:
    """Remove the booleans the doomed cutters feed to bodies that survive.

    A boolean modifier outlives the object it reads, so a body cut by a deleted
    feature would keep an empty modifier that quietly does nothing.
    """
    from .modifiers import boolean_modifier_name

    names = {boolean_modifier_name(obj) for obj in doomed}
    for body in bpy.data.objects:
        if body in doomed:
            continue
        for name in names:
            mod = body.modifiers.get(name)
            if mod is not None:
                body.modifiers.remove(mod)


def _remove(context: Context, doomed, operator: Operator) -> None:
    """Delete these objects, leaving the file consistent behind them.

    Deduplicated first: a placement of a part inside an assembly is also a member
    of it, and removing the same object twice crashes Blender.
    """
    from ..model.sketch_ref import get_active_sketch
    from ..utilities.collections import sync_part_collections
    from .utilities import activate_sketch

    doomed = list(dict.fromkeys(doomed))

    # Leaving the sketch first: editing one whose object is about to go would
    # leave the sketch mode pointing at nothing.
    active = get_active_sketch(context)
    if active and active.target_object in doomed:
        activate_sketch(context, None, operator)

    _strip_booleans(doomed)
    for obj in doomed:
        bpy.data.objects.remove(obj)

    # Drops a collection the deletion emptied (orphan constraints go with the
    # depsgraph handler).
    sync_part_collections(context.scene)


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
        root = self._root(context)
        if root is None:
            self.report({"WARNING"}, "Select a part to delete")
            return {"CANCELLED"}

        name = root.name
        _remove(context, [*part_placements(root), *group_members(root)], self)
        self.report({"INFO"}, f"Deleted part '{name}'")
        return {"FINISHED"}


class View3D_OT_slvs_delete_feature(Operator):
    """Delete this feature: the solid, the sketch it is built from, its boolean.

    One step of the part, taken off it. The part itself stays, as do the datum
    planes and any other sketch sharing the feature's workplane."""

    bl_idname = Operators.DeleteFeature
    bl_label = "Delete Feature"
    bl_options = {"REGISTER", "UNDO"}

    feature_name: StringProperty(name="Feature Name", default="", options={"SKIP_SAVE"})

    @classmethod
    def poll(cls, context: Context):
        return feature_root(context.active_object) is not None

    def _body(self, context: Context) -> Optional[Object]:
        """The feature to delete: the one named, else the one that was clicked."""
        if self.feature_name:
            return feature_root(bpy.data.objects.get(self.feature_name))
        return feature_root(context.active_object)

    def execute(self, context: Context):
        body = self._body(context)
        if body is None:
            self.report({"WARNING"}, "Select a feature to delete")
            return {"CANCELLED"}

        name = body.name
        doomed = feature_members(body)
        plane = _spent_plane(body, doomed)
        if plane is not None:
            doomed.append(plane)

        _remove(context, doomed, self)
        self.report({"INFO"}, f"Deleted feature '{name}'")
        return {"FINISHED"}


class View3D_OT_slvs_delete_assembly(Operator):
    """Delete this assembly and every part in it.

    An assembly is a container, so removing one removes what it holds: the parts
    inside would otherwise be left scattered at the scene level, which is what
    Blender's own delete of the assembly Empty already does."""

    bl_idname = Operators.DeleteAssembly
    bl_label = "Delete Assembly"
    bl_options = {"REGISTER", "UNDO"}

    assembly_name: StringProperty(
        name="Assembly Name", default="", options={"SKIP_SAVE"}
    )

    @classmethod
    def poll(cls, context: Context):
        return assembly_root_of(context.active_object) is not None

    def _root(self, context: Context) -> Optional[Object]:
        """The assembly to delete: the one named, else the one that was clicked."""
        if self.assembly_name:
            return assembly_root_of(bpy.data.objects.get(self.assembly_name))
        return assembly_root_of(context.active_object)

    def execute(self, context: Context):
        root = self._root(context)
        if root is None or not is_assembly_root(root):
            self.report({"WARNING"}, "Select an assembly to delete")
            return {"CANCELLED"}

        name = root.name
        doomed = group_members(root)
        # Each part inside keeps its own collection, and so its own placements.
        placements = [
            obj
            for member in (root, *root.children_recursive)
            for obj in part_placements(member)
        ]
        _remove(context, [*placements, *doomed], self)
        self.report({"INFO"}, f"Deleted assembly '{name}'")
        return {"FINISHED"}


register, unregister = register_classes_factory(
    (
        View3D_OT_slvs_delete_part,
        View3D_OT_slvs_delete_feature,
        View3D_OT_slvs_delete_assembly,
    )
)
