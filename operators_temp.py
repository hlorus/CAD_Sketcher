"""
Operators
"""
import logging
import math

import bpy
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
)
from bpy.types import Context, Operator


from . import class_defines, global_data

from .declarations import Operators
from .solver import solve_system
from .stateful_operator.integration import StatefulOperator
from .operators.base_stateful import GenericEntityOp

logger = logging.getLogger(__name__)


def add_point(context, pos, name=""):
    data = bpy.data
    ob = data.objects.new(name, None)
    ob.location = pos
    context.collection.objects.link(ob)
    return ob


from .operators.base_constraint import GenericConstraintOp

# Dimensional constraints
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
    align: EnumProperty(name="Alignment", items=class_defines.align_items)
    type = "DISTANCE"

    def fini(self, context, succeede):
        super().fini(context, succeede)
        if hasattr(self, "target"):
            self.target.align = self.align
            self.target.draw_offset = 0.05 * context.region_data.view_distance

    def draw_settings(self, context):
        if not hasattr(self, "target"):
            return

        layout = self.layout

        row = layout.row()
        row.active = self.target.use_align()
        row.prop(self, "align")


def invert_angle_getter(self):
    return self.get("setting", self.bl_rna.properties["setting"].default)


def invert_angle_setter(self, setting):
    self["value"] = math.pi - self.value
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
        options={"SKIP_SAVE"},
        precision=5,
    )
    setting: BoolProperty(name="Measure supplementary angle", default = False, get=invert_angle_getter, set=invert_angle_setter)
    type = "ANGLE"

    def fini(self, context, succeede):
        super().fini(context, succeede)
        if hasattr(self, "target"):
            self.target.draw_offset = 0.1 * context.region_data.view_distance


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


# Geomteric constraints
class VIEW3D_OT_slvs_add_coincident(Operator, GenericConstraintOp):
    """Add a coincident constraint"""

    bl_idname = Operators.AddCoincident
    bl_label = "Coincident"
    bl_options = {"UNDO", "REGISTER"}

    type = "COINCIDENT"

    def main(self, context: Context):
        p1, p2 = self.entity1, self.entity2
        if all([e.is_point() for e in (p1, p2)]):
            # Implicitly merge points
            class_defines.update_pointers(context.scene, p1.slvs_index, p2.slvs_index)
            context.scene.sketcher.entities.remove(p1.slvs_index)
            solve_system(context, context.scene.sketcher.active_sketch)
            return True
        return super().main(context)


class VIEW3D_OT_slvs_add_equal(Operator, GenericConstraintOp):
    """Add an equal constraint"""

    bl_idname = Operators.AddEqual
    bl_label = "Equal"
    bl_options = {"UNDO", "REGISTER"}

    type = "EQUAL"


class VIEW3D_OT_slvs_add_vertical(Operator, GenericConstraintOp):
    """Add a vertical constraint"""

    bl_idname = Operators.AddVertical
    bl_label = "Vertical"
    bl_options = {"UNDO", "REGISTER"}

    type = "VERTICAL"


class VIEW3D_OT_slvs_add_horizontal(Operator, GenericConstraintOp):
    """Add a horizontal constraint"""

    bl_idname = Operators.AddHorizontal
    bl_label = "Horizontal"
    bl_options = {"UNDO", "REGISTER"}

    type = "HORIZONTAL"


class VIEW3D_OT_slvs_add_parallel(Operator, GenericConstraintOp):
    """Add a parallel constraint"""

    bl_idname = Operators.AddParallel
    bl_label = "Parallel"
    bl_options = {"UNDO", "REGISTER"}

    type = "PARALLEL"


class VIEW3D_OT_slvs_add_perpendicular(Operator, GenericConstraintOp):
    """Add a perpendicular constraint"""

    bl_idname = Operators.AddPerpendicular
    bl_label = "Perpendicular"
    bl_options = {"UNDO", "REGISTER"}

    type = "PERPENDICULAR"


class VIEW3D_OT_slvs_add_tangent(Operator, GenericConstraintOp, GenericEntityOp):
    """Add a tagent constraint"""

    bl_idname = Operators.AddTangent
    bl_label = "Tangent"
    bl_options = {"UNDO", "REGISTER"}

    type = "TANGENT"


class VIEW3D_OT_slvs_add_midpoint(Operator, GenericConstraintOp, GenericEntityOp):
    """Add a midpoint constraint"""

    bl_idname = Operators.AddMidPoint
    bl_label = "Midpoint"
    bl_options = {"UNDO", "REGISTER"}

    type = "MIDPOINT"


class VIEW3D_OT_slvs_add_ratio(Operator, GenericConstraintOp, GenericEntityOp):
    """Add a ratio constraint"""

    value: FloatProperty(
        name="Ratio", subtype="UNSIGNED", options={"SKIP_SAVE"}, min=0.0, precision=5,
    )
    bl_idname = Operators.AddRatio
    bl_label = "Ratio"
    bl_options = {"UNDO", "REGISTER"}

    type = "RATIO"




constraint_operators = (
    VIEW3D_OT_slvs_add_distance,
    VIEW3D_OT_slvs_add_diameter,
    VIEW3D_OT_slvs_add_angle,
    VIEW3D_OT_slvs_add_coincident,
    VIEW3D_OT_slvs_add_equal,
    VIEW3D_OT_slvs_add_vertical,
    VIEW3D_OT_slvs_add_horizontal,
    VIEW3D_OT_slvs_add_parallel,
    VIEW3D_OT_slvs_add_perpendicular,
    VIEW3D_OT_slvs_add_tangent,
    VIEW3D_OT_slvs_add_midpoint,
    VIEW3D_OT_slvs_add_ratio,
)

from .stateful_operator.invoke_op import View3D_OT_invoke_tool

classes = (
    View3D_OT_invoke_tool,
    *constraint_operators,
)


def register():
    for cls in classes:
        if issubclass(cls, StatefulOperator):
            cls.register_properties()

        bpy.utils.register_class(cls)


def unregister():
    if global_data.offscreen:
        global_data.offscreen.free()
        global_data.offscreen = None

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
