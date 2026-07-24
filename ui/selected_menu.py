import bpy
from bpy.types import Menu
from bpy.props import BoolProperty

from ..declarations import Operators, Menus
from .. import global_data


def _selected_refs(context):
    """Valid CurveRefs for the currently selected curve ids."""
    from ..model.sketch_ref import get_active_sketch
    from ..model.curve_ref import curve_ref

    sketch = get_active_sketch(context)
    if not sketch:
        return []
    refs = [curve_ref(sketch, cid) for cid in global_data.selected]
    return [r for r in refs if r.valid]


# Real checkbox for the selection's `fixed` flag, backed by get/set over the
# current selection (an operator button can only fake a checkbox with an icon).
def _get_selection_fixed(self):
    refs = _selected_refs(bpy.context)
    return bool(refs) and all(r.fixed for r in refs)


def _set_selection_fixed(self, value):
    context = bpy.context
    for r in _selected_refs(context):
        r.fixed = value
    from ..utilities.view import refresh
    refresh(context)


def register_props():
    bpy.types.WindowManager.slvs_selection_fixed = BoolProperty(
        name="Fixed",
        description="Fix the selected geometry in place",
        get=_get_selection_fixed,
        set=_set_selection_fixed,
    )


def unregister_props():
    del bpy.types.WindowManager.slvs_selection_fixed


def _toggle_state(refs, prop, default):
    """(value to set, icon) for a tri-state flag across the selection."""
    values = [getattr(r, prop) for r in refs]
    if values and all(values):
        return False, "CHECKBOX_HLT"
    if not any(values):
        return True, "CHECKBOX_DEHLT"
    return default, "SELECT_SUBTRACT"


class VIEW3D_MT_selected_menu(Menu):
    bl_label = "Selected Menu"
    bl_idname = Menus.SelectedMenu

    def draw(self, context):
        layout = self.layout
        refs = _selected_refs(context)

        if not refs:
            layout.label(text="Nothing selected")
            return

        # Same entry order as the single-entity context menu (curve_ref.draw_props):
        # construction, fixed, visible.
        def flag_toggle(prop, name, default):
            value, icon = _toggle_state(refs, prop, default)
            props = layout.operator(Operators.SetCurveFlag, text=name, icon=icon)
            props.curve_id = ""  # empty → apply to the whole selection
            props.flag = prop
            props.value = value

        flag_toggle("construction", "Construction", False)
        # Fixed as a real checkbox (backed by the WindowManager get/set prop).
        layout.prop(context.window_manager, "slvs_selection_fixed")
        flag_toggle("visible", "Visible", True)

        layout.separator()
        # No index → DeleteEntity deletes the current selection.
        layout.operator(Operators.DeleteEntity, text="Delete Entities", icon="X")
