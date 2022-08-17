from bpy.utils import register_classes_factory
from bpy.types import Operator
from bl_operators.presets import AddPresetBase

from ..declarations import Operators


class SKETCHER_OT_add_preset_theme(AddPresetBase, Operator):
    """Add an Theme Preset"""

    bl_idname = Operators.AddPresetTheme
    bl_label = "Add Theme Preset"
    preset_menu = "SKETCHER_MT_theme_presets"

    preset_defines = [
        'prefs = bpy.context.preferences.addons["CAD_Sketcher"].preferences',
        "theme = prefs.theme_settings",
        "entity = theme.entity",
        "constraint = theme.constraint",
    ]

    preset_values = [
        "entity.default",
        "entity.highlight",
        "entity.selected",
        "entity.selected_highlight",
        "entity.inactive",
        "entity.inactive_selected",
        "constraint.default",
        "constraint.highlight",
        "constraint.failed",
        "constraint.failed_highlight",
        "constraint.text",
    ]

    preset_subdir = "bgs/theme"


register, unregister = register_classes_factory((SKETCHER_OT_add_preset_theme,))
