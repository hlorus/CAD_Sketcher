from bpy.types import Context

from CAD_Sketcher.declarations import Panels, ConstraintOperators
from . import VIEW3D_PT_sketcher_base


class VIEW3D_PT_sketcher_add_constraints(VIEW3D_PT_sketcher_base):
    """
    Add Constraint Menu: List of buttons with the constraint you want
    to create.
    """

    bl_label = "Add Constraints"
    bl_idname = Panels.SketcherAddContraint
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context: Context):
        layout = self.layout
        layout.label(text="Constraints:")
        col = layout.column(align=True)
        for op in ConstraintOperators:
            col.operator(op)
