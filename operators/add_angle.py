import logging

from bpy.types import Operator, Context
from bpy.props import FloatProperty, BoolProperty

from ..utilities.constants import HALF_TURN

from ..declarations import Operators
from ..stateful_operator.utilities.register import register_stateops_factory
from .base_constraint import GenericConstraintOp

from ..model.angle import SlvsAngle

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
    property_keys = ("value", "setting")

    def main(self, context):
        if not self.exists(context, SlvsAngle):
            self.target = context.scene.sketcher.constraints.add_angle(
                self.entity1,
                self.entity2,
                sketch=self.sketch,
                init=not self.initialized,
                **self.get_settings()
            )

        return super().main(context)

    def fini(self, context: Context, succeede: bool):
        super().fini(context, succeede)
        if hasattr(self, "target"):
            self.target.draw_offset = 0.1 * context.region_data.view_distance


register, unregister = register_stateops_factory((VIEW3D_OT_slvs_add_angle,))
