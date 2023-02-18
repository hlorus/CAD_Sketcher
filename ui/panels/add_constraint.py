from bpy.types import Context

from ...declarations import Operators, Panels
from .. import icon_manager
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

        for op, icon in (
            (Operators.AddDistance, ""),
            (Operators.AddDiameter, ""),
            (Operators.AddAngle, ""),
            (Operators.AddCoincident, "COINCIDENT"),
            (Operators.AddEqual, "EQUAL"),
            (Operators.AddVertical, "VERTICAL"),
            (Operators.AddHorizontal, "HORIZONTAL"),
            (Operators.AddParallel, "PARALLEL"),
            (Operators.AddPerpendicular, "PERPENDICULAR"),
            (Operators.AddTangent, "TANGENT"),
            (Operators.AddMidPoint, "MIDPOINT"),
            (Operators.AddRatio, "RATIO"),
        ):
            col.operator(op, icon_value=icon_manager.get_icon_value(icon))
