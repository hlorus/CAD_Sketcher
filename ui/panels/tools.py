from bpy.types import Context

from ...model.sketch_ref import get_active_sketch
from .. import declarations, icon_manager
from . import VIEW3D_PT_sketcher_base


class VIEW3D_PT_sketcher_tools(VIEW3D_PT_sketcher_base):
    """
    Tools Menu: List of useful tools for sketching
    """

    bl_label = "Tools"
    bl_idname = declarations.Panels.SketcherTools
    bl_options = {"DEFAULT_CLOSED"}

    def _draw_sketch_tools(self, context: Context):
        """Tools that only make sense while editing a sketch."""
        layout = self.layout

        layout.operator(declarations.Operators.MergePoints)
        layout.operator(declarations.Operators.ProjectGeometry, icon="MOD_SHRINKWRAP")

        layout.label(text="Constraints:")
        col = layout.column(align=True)
        for op in declarations.ConstraintOperators:
            col.operator(op, icon_value=icon_manager.get_constraint_icon(op))

        layout.separator()

        layout.label(text="Drawing:")
        layout.prop(context.scene.sketcher, "use_construction")

    def _draw_node_tools(self, context: Context):
        """Node-modifier tools that act on objects outside of a sketch."""
        layout = self.layout

        layout.label(text="Node Tools:")
        col = layout.column(align=True)
        col.operator(declarations.Operators.NodeExtrude)
        col.operator(declarations.Operators.NodeRevolve)
        col.operator(declarations.Operators.NodeArrayLinear)
        col.operator(declarations.Operators.NodeBoolean)

    def draw(self, context: Context):
        # Mirror the workspace toolbar: sketch tools while a sketch is active,
        # node tools otherwise, instead of showing both at once.
        if get_active_sketch(context) is not None:
            self._draw_sketch_tools(context)
        else:
            self._draw_node_tools(context)
