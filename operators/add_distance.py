from bpy.props import BoolProperty, EnumProperty, FloatProperty
from bpy.types import Operator
from bpy.utils import register_classes_factory

from ..declarations import Operators
from ..model.distance import align_items
from .add_dimension import DimensionAlias


class VIEW3D_OT_slvs_add_distance(DimensionAlias, Operator):
    """Add a distance constraint"""

    bl_idname = Operators.AddDistance
    bl_label = "Distance"

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

    def dimension_flags(self) -> dict:
        flags = {"kind": "DISTANCE", "align": self.align}
        if self.properties.is_property_set("value"):
            flags["length"] = self.value
        return flags


register, unregister = register_classes_factory((VIEW3D_OT_slvs_add_distance,))
