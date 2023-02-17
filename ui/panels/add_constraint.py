from bpy.types import Context

from .. import declarations
from .. import icon_manager
from . import VIEW3D_PT_sketcher_base


class VIEW3D_PT_sketcher_add_constraints(VIEW3D_PT_sketcher_base):
    """
    Add Constraint Menu: List of buttons with the constraint you want
    to create.
    """

    bl_label = "Add Constraints"
    bl_idname = declarations.Panels.SketcherAddContraint
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context: Context):
        layout = self.layout
        layout.label(text="Constraints:")
        col = layout.column(align=True)

        for op in declarations.ConstraintOperators:
            col.operator(op, icon_value=icon_manager.get_constraint_icon(op))
