from bpy.types import Context

from ...model.sketch_ref import get_active_sketch
from .. import declarations, icon_manager, preferences
from . import VIEW3D_PT_sketcher_base


class VIEW3D_PT_sketcher_tools(VIEW3D_PT_sketcher_base):
    """
    Tools Menu: List of useful tools for sketching
    """

    bl_label = "Tools"
    bl_idname = declarations.Panels.SketcherTools
    bl_options = set()  # expanded by default

    def _draw_sketch_tools(self, context: Context):
        """Tools that only make sense while editing a sketch."""
        layout = self.layout

        sketch = get_active_sketch(context)
        is_3d = sketch is not None and sketch.is_3d

        def _supported(operators):
            # A free-3D sketch only supports the constraints the solver dispatches;
            # hide the rest (see declarations). Hidden rather than disabled so the
            # icon grid keeps its seamless merged layout for the buttons shown.
            if not is_3d:
                return operators
            return tuple(
                op
                for op in operators
                if op in declarations.Supported3DConstraintOperators
            )

        dimensional = _supported(declarations.DimensionalConstraintOperators)
        geometric = _supported(declarations.GeometricConstraintOperators)

        layout.operator(declarations.Operators.MergePoints)
        layout.operator(declarations.Operators.ProjectGeometry, icon="MOD_SHRINKWRAP")

        layout.separator()
        prefs = preferences.get_prefs()
        header = layout.row(align=True)
        header.label(text="Constraints:")
        # Right-aligned, box-less icon that shows the view it switches *to* (list
        # icon while the grid is active). Use an operator rather than a prop toggle:
        # an emboss=False toggle would tint the icon by its on/off state (white vs
        # black), whereas an operator icon always follows the theme.
        toggle = header.row()
        toggle.alignment = "RIGHT"
        op = toggle.operator(
            "wm.context_toggle",
            text="",
            icon="LONGDISPLAY" if prefs.constraint_grid_view else "IMGDISPLAY",
            emboss=False,
        )
        op.data_path = (
            f'preferences.addons["{preferences.get_name()}"]'
            ".preferences.constraint_grid_view"
        )

        if prefs.constraint_grid_view:
            # Icon-only buttons; the constraint name still shows in the tooltip.
            # Dimensional constraints (value-based) go in their own grid, kept
            # separate from the geometric ones. Both use the same column count and
            # scale so the buttons are identically sized.
            def _icon_grid(operators):
                if not operators:
                    return
                grid = layout.grid_flow(
                    row_major=True,
                    columns=5,
                    even_columns=True,
                    even_rows=True,
                    align=True,
                )
                grid.scale_x = 1.2
                grid.scale_y = 1.2
                for op in operators:
                    grid.operator(
                        op, text="", icon_value=icon_manager.get_constraint_icon(op)
                    )

            _icon_grid(dimensional)
            _icon_grid(geometric)
        else:
            col = layout.column(align=True)
            for op in dimensional:
                col.operator(op, icon_value=icon_manager.get_constraint_icon(op))
            if dimensional and geometric:
                col.separator()
            for op in geometric:
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
