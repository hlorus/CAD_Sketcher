"""The Part menu: everything that manages a part, an assembly or a feature.

One menu class, drawn wherever parts are handled -- the viewport context menu,
the outliner's, and the Object menu -- so the entries cannot drift apart. The
outliner matters most: a cutter is hidden while it cuts, so the outliner is the
only place it can be reached at all.
"""

from typing import Optional

from bpy.types import Context, Menu, Object

from ..declarations import Menus, Operators


def part_context(context: Context):
    """(object, part root, assembly root) for what the menu is acting on."""
    from ..utilities.part import assembly_root_of, part_root_of

    obj = context.active_object
    if obj is None:
        return None, None, None
    return obj, part_root_of(obj), assembly_root_of(obj)


def has_part_entries(context: Context) -> bool:
    """Whether anything in this menu applies, so it is hidden for plain objects."""
    _obj, root, assembly = part_context(context)
    return root is not None or assembly is not None


def _leave_label(obj: Optional[Object], root, assembly) -> str:
    """A part member leaves its part; a part itself leaves its assembly."""
    if root is not None and root != obj:
        return "Remove from Part"
    return "Remove from Assembly"


class VIEW3D_MT_slvs_part(Menu):
    """Manage the part, feature or assembly the active object belongs to."""

    bl_label = "Part"
    bl_idname = Menus.Part

    @classmethod
    def poll(cls, context: Context):
        return has_part_entries(context)

    def draw(self, context: Context):
        from ..operators.delete_part import feature_root

        layout = self.layout
        obj, root, assembly = part_context(context)
        if obj is None:
            return

        layout.operator(
            Operators.RemoveFromPart, text=_leave_label(obj, root, assembly)
        ).object_name = obj.name

        target = root if root is not None else assembly
        if target is not None:
            text = "Dissolve Assembly" if target == assembly else "Dissolve Part"
            layout.operator(Operators.DissolvePart, text=text).part_name = target.name

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
