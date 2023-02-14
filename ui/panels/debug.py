from bpy.types import Context

from CAD_Sketcher.utilities.preferences import get_prefs
from CAD_Sketcher.declarations import Operators, Panels
from CAD_Sketcher.stateful_operator.constants import (
    Operators as StatefulOperators,
)
from . import VIEW3D_PT_sketcher_base


class VIEW3D_PT_sketcher_debug(VIEW3D_PT_sketcher_base):
    """Debug Menu"""

    bl_label = "Debug Settings"
    bl_idname = Panels.SketcherDebugPanel

    def draw(self, context: Context):
        layout = self.layout

        prefs = get_prefs()
        layout.operator(Operators.WriteSelectionTexture)
        layout.operator(Operators.Solve)
        layout.operator(Operators.Solve, text="Solve All").all = True

        layout.operator(StatefulOperators.Test)
        layout.prop(context.scene.sketcher, "show_origin")
        layout.prop(prefs, "hide_inactive_constraints")
        layout.prop(prefs, "all_entities_selectable")
        layout.prop(prefs, "force_redraw")
        layout.prop(context.scene.sketcher, "selectable_constraints")
        layout.prop(prefs, "use_align_view")

    @classmethod
    def poll(cls, context: Context):
        prefs = get_prefs()
        return prefs.show_debug_settings
