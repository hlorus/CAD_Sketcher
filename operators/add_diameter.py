from bpy.props import BoolProperty, FloatProperty
from bpy.types import Operator
from bpy.utils import register_classes_factory

from ..declarations import Operators
from .add_dimension import DimensionAlias


class VIEW3D_OT_slvs_add_diameter(DimensionAlias, Operator):
    """Add a diameter constraint"""

    bl_idname = Operators.AddDiameter
    bl_label = "Diameter"

    # Either Radius or Diameter
    value: FloatProperty(
        name="Size",
        subtype="DISTANCE",
        unit="LENGTH",
        precision=5,
        options={"SKIP_SAVE"},
    )
    setting: BoolProperty(name="Use Radius")

    def dimension_flags(self) -> dict:
        flags = {"kind": "DIAMETER", "radius": self.setting}
        if self.properties.is_property_set("value"):
            flags["length"] = self.value
        return flags


register, unregister = register_classes_factory((VIEW3D_OT_slvs_add_diameter,))
