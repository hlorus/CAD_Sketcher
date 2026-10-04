"""The Part menu: every verb that acts on a part, an assembly or a feature.

One menu class, drawn wherever parts are handled -- the viewport context menu,
the outliner's, the Object menu, and the sidebar -- so there is one definition
and the entries cannot drift apart. The outliner matters most: a cutter is
hidden while it cuts, so the outliner is the only place it can be reached.

Rows stay put and grey out rather than disappearing, so the menu does not
reshuffle between clicks. The deletes are the exception: they name what they
take, and a part with no assembly has no assembly to delete.
"""

from typing import Optional

from bpy.types import Context, Menu, Object

from ..declarations import Menus, Operators

# What a part can be built out of: a mesh body, or a sketch's curves.
_PART_MATERIAL = {"MESH", "CURVES", "CURVE", "SURFACE", "FONT"}


def part_context(context: Context):
    """(object, part root, assembly root) for what the menu is acting on."""
    from ..utilities.part import assembly_root_of, part_root_of

    obj = context.active_object
    if obj is None:
        return None, None, None
    return obj, part_root_of(obj), assembly_root_of(obj)


def has_part_entries(context: Context) -> bool:
    """Whether the menu has anything to say about the active object.

    Gates the menus this addon appends itself to, so nothing is added to the
    context menu of an object that has nothing to do with parts. The sidebar
    draws the menu unconditionally: that is where an assembly is started, and
    one can be started with nothing selected at all.
    """
    from ..operators.make_part import can_root_a_part

    obj, root, assembly = part_context(context)
    if obj is None:
        return False
    if root is not None or assembly is not None:
        return True
    # Make Part takes anything that is not an Empty, but offering it on a camera
    # or a light is just noise in their context menu: only the kinds a part is
    # ever built from earn the entry.
    return obj.type in _PART_MATERIAL and can_root_a_part(obj)


def _leave_label(obj: Optional[Object], root) -> str:
    """A part member leaves its part; a part itself leaves its assembly."""
    if root is not None and root != obj:
        return "Remove from Part"
    return "Remove from Assembly"


class VIEW3D_MT_slvs_part(Menu):
    """Make, copy, take apart or delete a part, an assembly or a feature."""

    bl_label = "Part"
    bl_idname = Menus.Part

    @classmethod
    def poll(cls, context: Context):
        # Always available: Add Assembly works with nothing selected, which is
        # how an empty assembly is started. What is *gated* is each row.
        return True

    def draw(self, context: Context):
        from ..operators.delete_part import feature_root
        from ..operators.make_part import can_root_a_part
        from ..utilities.part import instanceable_root, part_root_of

        layout = self.layout
        obj, root, assembly = part_context(context)

        row = layout.row()
        row.enabled = can_root_a_part(obj)
        row.operator(Operators.MakePart, icon="OUTLINER_OB_MESH")
        layout.operator(Operators.AddAssembly, icon="OUTLINER_OB_GROUP_INSTANCE")

        layout.separator()

        selected = context.selected_objects
        row = layout.row()
        row.enabled = any(part_root_of(o) is not None for o in selected)
        row.operator(Operators.DuplicatePart, icon="DUPLICATE")
        row = layout.row()
        row.enabled = any(instanceable_root(o) is not None for o in selected)
        row.operator(Operators.InstancePart, icon="LINKED")

        layout.separator()

        in_group = root is not None or assembly is not None
        row = layout.row()
        row.enabled = in_group
        row.operator(
            Operators.RemoveFromPart, text=_leave_label(obj, root)
        ).object_name = obj.name if obj else ""

        target = root if root is not None else assembly
        row = layout.row()
        row.enabled = target is not None
        text = (
            "Dissolve Assembly"
            if target is not None and target == assembly
            else ("Dissolve Part")
        )
        row.operator(Operators.DissolvePart, text=text).part_name = (
            target.name if target is not None else ""
        )

        if not in_group:
            return

        layout.separator()

        feature = feature_root(obj)
        if feature is not None:
            row = layout.row()
            row.alert = True
            row.operator(
                Operators.DeleteFeature, text="Delete Feature", icon="X"
            ).feature_name = feature.name

        if root is not None:
            row = layout.row()
            row.alert = True
            row.operator(
                Operators.DeletePart, text="Delete Part", icon="X"
            ).part_name = root.name

        if assembly is not None:
            row = layout.row()
            row.alert = True
            row.operator(
                Operators.DeleteAssembly, text="Delete Assembly", icon="X"
            ).assembly_name = assembly.name


def draw_part_menu(self, context: Context) -> None:
    """Draw the Part submenu, for menus this addon appends itself to."""
    if not has_part_entries(context):
        return
    self.layout.menu(Menus.Part.value, icon="OUTLINER_OB_MESH")


def draw_part_menu_in_object_menu(self, context: Context) -> None:
    """Same, with the separator the header's Object menu wants around it."""
    if not has_part_entries(context):
        return
    self.layout.separator()
    self.layout.menu(Menus.Part.value, icon="OUTLINER_OB_MESH")


classes = (VIEW3D_MT_slvs_part,)
