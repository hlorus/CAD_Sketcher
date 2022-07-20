import logging

from bpy.types import Operator
from bpy.props import FloatProperty, BoolProperty

from ..declarations import Operators
from ..stateful_operator.utilities.register import register_stateops_factory
from .base_constraint import GenericConstraintOp

logger = logging.getLogger(__name__)


class VIEW3D_OT_slvs_add_diameter(Operator, GenericConstraintOp):
    """Add a diameter constraint"""

    bl_idname = Operators.AddDiameter
    bl_label = "Diameter"
    bl_options = {"UNDO", "REGISTER"}

    # Either Radius or Diameter
    value: FloatProperty(
        name="Size",
        subtype="DISTANCE",
        unit="LENGTH",
        options={"SKIP_SAVE"},
        precision=5,
    )

    setting: BoolProperty(name="Use Radius")
    type = "DIAMETER"

register, unregister = register_stateops_factory((VIEW3D_OT_slvs_add_diameter,))
