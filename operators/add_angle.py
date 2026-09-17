from bpy.props import BoolProperty, FloatProperty
from bpy.types import Operator
from bpy.utils import register_classes_factory

from ..declarations import Operators
from .add_dimension import DimensionAlias


class VIEW3D_OT_slvs_add_angle(DimensionAlias, Operator):
    """Add an angle constraint"""

    bl_idname = Operators.AddAngle
    bl_label = "Angle"

    value: FloatProperty(
        name="Angle",
        subtype="ANGLE",
        unit="ROTATION",
        precision=5,
        options={"SKIP_SAVE"},
    )
    setting: BoolProperty(name="Measure supplementary angle", default=False)

    def dimension_flags(self) -> dict:
        flags = {"kind": "ANGLE", "supplementary": self.setting}
        if self.properties.is_property_set("value"):
            flags["angle"] = self.value
        return flags


register, unregister = register_classes_factory((VIEW3D_OT_slvs_add_angle,))
