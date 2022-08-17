import logging, math

from bpy.types import Operator, Context
from bpy.props import FloatProperty, BoolProperty

from ..utilities.constants import HALF_TURN

from ..declarations import Operators
from ..stateful_operator.utilities.register import register_stateops_factory
from .base_constraint import GenericConstraintOp

logger = logging.getLogger(__name__)


def invert_angle_getter(self):
    return self.get("setting", self.bl_rna.properties["setting"].default)


def invert_angle_setter(self, setting):
    self["value"] = HALF_TURN - self.value
    self["setting"] = setting


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
    setting: BoolProperty(
        name="Measure supplementary angle",
        default=False,
        get=invert_angle_getter,
        set=invert_angle_setter,
    )
    type = "ANGLE"

    def fini(self, context: Context, succeede: bool):
        super().fini(context, succeede)
        if hasattr(self, "target"):
            self.target.draw_offset = 0.1 * context.region_data.view_distance


register, unregister = register_stateops_factory((VIEW3D_OT_slvs_add_angle,))
