from bpy.types import Context

from .. import constants
from .. import declarations
from .. import preferences
from . import VIEW3D_PT_sketcher_base


class VIEW3D_PT_sketcher_debug(VIEW3D_PT_sketcher_base):
    """Debug Menu"""

    bl_label = "Debug Settings"
    bl_idname = declarations.Panels.SketcherDebugPanel

    def draw(self, context: Context):
        layout = self.layout

        prefs = preferences.get_prefs()
        layout.operator(declarations.Operators.WriteSelectionTexture)
        layout.operator(declarations.Operators.Solve)
        layout.operator(
            declarations.Operators.Solve,
            text="Solve All",
        ).all = True

        layout.operator(constants.Operators.Test)
        layout.prop(context.scene.sketcher, "show_origin")
        layout.prop(prefs, "hide_inactive_constraints")
        layout.prop(prefs, "all_entities_selectable")
        layout.prop(prefs, "force_redraw")
        layout.prop(context.scene.sketcher, "selectable_constraints")
        layout.prop(prefs, "use_align_view")

    @classmethod
    def poll(cls, context: Context):
        prefs = preferences.get_prefs()
        return prefs.show_debug_settings
