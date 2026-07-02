import logging

from bpy.types import Operator, Context
from bpy.props import BoolProperty, FloatProperty, EnumProperty

from .base_constraint import GenericConstraintOp
from ..model.distance import align_items
from ..declarations import Operators
from ..stateful_operator.utilities.register import register_stateops_factory
from ..model.curve_ref import PointRef, LineRef

from ..model.distance import SlvsDistance

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
        e1, e2 = self.entity1, self.entity2

        # Line length: expand line to its endpoints
        if isinstance(e1, LineRef) and e2 is None:
            p1, p2 = e1.p1, e1.p2
            if p1 and p2:
                for i, pt in enumerate((p1, p2)):
                    state_data = self.get_state_data(i)
                    state_data["hovered"] = 0
                    state_data["type"] = PointRef
                    state_data["is_existing_entity"] = True
                    state_data["curve_id"] = pt.curve_id
                self.next_state(context)
                e1, e2 = self.entity1, self.entity2

        if isinstance(e1, LineRef) and e2 is None:
            max_constraints = 2
        elif isinstance(e1, PointRef) and isinstance(e2, PointRef):
            max_constraints = 2
        else:
            max_constraints = 1

        cid1 = e1.curve_id if e1 else 0
        cid2 = e2.curve_id if e2 else 0

        if not self.exists(context, SlvsDistance, max_constraints):
            self.target = self.sketch.constraints.add_distance(
                init=not self.initialized,
                curve_id_1=cid1,
                curve_id_2=cid2,
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
