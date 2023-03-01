from bpy.types import Menu

from ..declarations import Operators, Menus

from typing import Iterable


def _get_value_icon(collection: Iterable, property: str, default: bool) -> bool:
    values = [getattr(item, property) for item in collection]
    if all(values):
        return False, "CHECKBOX_HLT"
    if not any(values):
        return True, "CHECKBOX_DEHLT"
    return default, "SELECT_SUBTRACT"


class VIEW3D_MT_selected_menu(Menu):
    bl_label = "Selected Menu"
    bl_idname = Menus.SelectedMenu

    def draw(self, context):
        layout = self.layout

        path_sse = "scene.sketcher.entities"

        for data_path, sequence, prop, name, default in (
            (path_sse, "selected_all", "visible", "Visible", True),
            (path_sse, "selected", "construction", "Construction", False),
            (path_sse, "selected", "fixed", "Fixed", False),
        ):
            selected = getattr(context.path_resolve(data_path), sequence)
            active = bool(len(selected))
            row = layout.row()
            row.active = active

            value, icon = _get_value_icon(selected, prop, default)
            props = row.operator(Operators.BatchSet, text=name, icon=icon)
            props.data_path = data_path
            props.sequence = sequence
            props.property = prop
            props.value = value

        layout.separator()
        layout.operator(Operators.DeleteEntity, text="Delete Entities", icon="X")
