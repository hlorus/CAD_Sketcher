import logging

from bpy.types import Operator, Context
from bpy.props import BoolProperty, FloatProperty, EnumProperty

from .base_constraint import GenericConstraintOp
from ..model.distance import align_items
from ..declarations import Operators
from ..stateful_operator.utilities.register import register_stateops_factory


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
    flip: BoolProperty(name="Flip")
    type = "DISTANCE"
    property_keys = ("value", "align", "flip")

    def main(self, context):
        self.target = context.scene.sketcher.constraints.add_distance(
            self.entity1,
            self.entity2,
            sketch=self.sketch,
            init=not self.initialized,
            **self.get_settings(),
        )
        return super().main(context)

    def fini(self, context: Context, succeede: bool):
        super().fini(context, succeede)
        if hasattr(self, "target"):
            self.target.draw_offset = 0.05 * context.region_data.view_distance

    def draw(self, context: Context):
        if not hasattr(self, "target"):
            return

        layout = self.layout
        c = self.target

        row = layout.row()
        row.prop(self, "value")

        row = layout.row()
        row.enabled = c.use_align()
        row.prop(self, "align")

        row = layout.row()
        row.enabled = c.use_flipping()
        row.prop(self, "flip")


register, unregister = register_stateops_factory((VIEW3D_OT_slvs_add_distance,))
