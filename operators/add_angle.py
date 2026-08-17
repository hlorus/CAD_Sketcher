import logging

from bpy.props import BoolProperty, FloatProperty
from bpy.types import Context, Operator

from ..declarations import Operators
from ..model.angle import SlvsAngle
from ..stateful_operator.utilities.register import register_stateops_factory
from ..utilities.constants import HALF_TURN
from .base_constraint import GenericConstraintOp

logger = logging.getLogger(__name__)


def invert_angle_getter(self):
    return self.setting_store


def invert_angle_setter(self, setting):
    self.value = HALF_TURN - self.value
    self.setting_store = setting


class VIEW3D_OT_slvs_add_angle(Operator, GenericConstraintOp):
    """Add an angle constraint"""

    bl_idname = Operators.AddAngle
    bl_label = "Angle"
    bl_options = {"UNDO", "REGISTER"}

    value: FloatProperty(
        name="Angle",
        subtype="ANGLE",
        unit="ROTATION",
        precision=5,
        options={"SKIP_SAVE"},
    )
    setting_store: BoolProperty(
        name="Measure supplementary angle storage",
        default=False,
    )
    setting: BoolProperty(
        name="Measure supplementary angle",
        default=False,
        get=invert_angle_getter,
        set=invert_angle_setter,
    )
    type = "ANGLE"
    property_keys = ("value", "setting")
    has_value_state = False

    def main(self, context):
        if not self.exists(context, SlvsAngle):
            self.target = self.sketch.constraints.add_angle(
                init=not self.initialized,
                curve_id_1=self.entity1.curve_id,
                curve_id_2=self.entity2.curve_id,
                **self.get_settings(),
            )

        return super().main(context)

    def fini(self, context: Context, succeede: bool):
        # Set the default offset before super().fini() (which hands off to the
        # placement modal), so the interactive placement writes over the default
        # rather than the default clobbering the placement.
        if hasattr(self, "target"):
            self.target.draw_offset = 0.1 * context.region_data.view_distance
        super().fini(context, succeede)


register, unregister = register_stateops_factory((VIEW3D_OT_slvs_add_angle,))
