import logging

from bpy.types import Operator, Context
from bpy.props import BoolProperty, FloatProperty, EnumProperty

from .base_constraint import GenericConstraintOp
from ..model.distance import align_items
from ..declarations import Operators
from ..stateful_operator.utilities.register import register_stateops_factory

from ..model.distance import SlvsDistance
from ..model.line_2d import SlvsLine2D
from ..model.point_2d import SlvsPoint2D
from ..model.types import SlvsPoint3D
from ..model.types import SlvsLine3D

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
        if isinstance(self.entity1, SlvsLine2D) and self.entity2 is None:
            dependencies = self.entity1.dependencies()
            if (isinstance(dependencies[0], SlvsPoint2D) and
                    isinstance(dependencies[1], SlvsPoint2D)):
                # for loop changes the values of self.entity1 and self.entity2
                # from a line entity to its endpoints
                for i in range(0, 2):
                    state_data = self.get_state_data(i)
                    state_data["hovered"] = -1
                    state_data["type"] = type(dependencies[i])
                    state_data["is_existing_entity"] = True
                    state_data["entity_index"] = dependencies[i].slvs_index
                self.next_state(context)  # end user selection, no need for second entity

        if (isinstance(self.entity1, (SlvsPoint3D, SlvsLine3D)) or
                isinstance(self.entity2, (SlvsPoint3D, SlvsLine3D))):
            max_constraints = 3
        elif ((isinstance(self.entity1, SlvsLine2D) and self.entity2 is None) or
                isinstance(self.entity1, SlvsPoint2D) and isinstance(self.entity2, SlvsPoint2D)):
            max_constraints = 2
        else:
            max_constraints = 1

        if not self.exists(context, SlvsDistance, max_constraints):
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
