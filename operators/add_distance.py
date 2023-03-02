import logging

from bpy.types import Operator, Context
from bpy.props import FloatProperty, EnumProperty

from ..model.distance import align_items
from ..declarations import Operators
from ..stateful_operator.utilities.register import register_stateops_factory
from .base_constraint import GenericConstraintOp

logger = logging.getLogger(__name__)


class VIEW3D_OT_slvs_add_distance(Operator, GenericConstraintOp):
    """Add a distance constraint"""

    bl_idname = Operators.AddDistance
    bl_label = "Distance"
    bl_options = {"UNDO", "REGISTER"}

    value: FloatProperty(
        name="Distance",
        subtype="DISTANCE",
        unit="LENGTH",
        min=0.0,
        precision=5,
        options={"SKIP_SAVE"},
    )
    align: EnumProperty(name="Alignment", items=align_items)
    type = "DISTANCE"

    def initialize_constraint(self):
        if hasattr(self, "target"):
            self.target.align = self.align
        return super().initialize_constraint()

    def fini(self, context: Context, succeede: bool):
        super().fini(context, succeede)
        if hasattr(self, "target"):
            self.target.draw_offset = 0.05 * context.region_data.view_distance

    def draw_settings(self, context: Context):
        if not hasattr(self, "target"):
            return

        layout = self.layout

        row = layout.row()
        row.enabled = self.target.use_align()
        row.prop(self, "align")


register, unregister = register_stateops_factory((VIEW3D_OT_slvs_add_distance,))
