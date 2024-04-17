import logging

from bpy.types import Operator, Context
from bpy.props import FloatProperty

from ..model.utilities import update_pointers
from ..solver import solve_system
from ..declarations import Operators
from ..stateful_operator.utilities.register import register_stateops_factory
from .base_constraint import GenericConstraintOp
from ..utilities.select import deselect_all
from ..utilities.view import refresh
from ..solver import solve_system

from ..model.coincident import SlvsCoincident
from ..model.equal import SlvsEqual
from ..model.vertical import SlvsVertical
from ..model.horizontal import SlvsHorizontal
from ..model.parallel import SlvsParallel
from ..model.perpendicular import SlvsPerpendicular
from ..model.tangent import SlvsTangent
from ..model.midpoint import SlvsMidpoint
from ..model.ratio import SlvsRatio

logger = logging.getLogger(__name__)


def merge_points(context, duplicate, target):
    update_pointers(context.scene, duplicate.slvs_index, target.slvs_index)
    context.scene.sketcher.entities.remove(duplicate.slvs_index)


class VIEW3D_OT_slvs_add_coincident(Operator, GenericConstraintOp):
    """Add a coincident constraint"""

    bl_idname = Operators.AddCoincident
    bl_label = "Coincident"
    bl_options = {"UNDO", "REGISTER"}

    type = "COINCIDENT"

    def handle_merge(self, context):
        points = self.entity1, self.entity2

        if not all([e.is_point() for e in points]):
            return False

        for p1, p2 in (points, reversed(points)):
            if p1.origin:
                continue
            if p1.fixed:
                continue

            merge_points(context, p1, p2)
            solve_system(context, context.scene.sketcher.active_sketch)
            break
        return True

    def main(self, context: Context):
        # Implicitly merge points
        if self.handle_merge(context):
            return True

        if not self.exists(context, SlvsCoincident):
            self.target = context.scene.sketcher.constraints.add_coincident(
                self.entity1,
                self.entity2,
                sketch=self.sketch,
            )
        return super().main(context)


class VIEW3D_OT_slvs_add_equal(Operator, GenericConstraintOp):
    """Add an equal constraint"""

    bl_idname = Operators.AddEqual
    bl_label = "Equal"
    bl_options = {"UNDO", "REGISTER"}

    type = "EQUAL"

    def main(self, context):
        if not self.exists(context, SlvsEqual):
            self.target = context.scene.sketcher.constraints.add_equal(
                self.entity1,
                self.entity2,
                sketch=self.sketch,
            )

        return super().main(context)


class VIEW3D_OT_slvs_add_vertical(Operator, GenericConstraintOp):
    """Add a vertical constraint"""

    bl_idname = Operators.AddVertical
    bl_label = "Vertical"
    bl_options = {"UNDO", "REGISTER"}

    type = "VERTICAL"

    def main(self, context):
        if not self.exists(context, SlvsVertical):
            self.target = context.scene.sketcher.constraints.add_vertical(
                self.entity1,
                entity2=self.entity2,
                sketch=self.sketch,
            )

        return super().main(context)


class VIEW3D_OT_slvs_add_horizontal(Operator, GenericConstraintOp):
    """Add a horizontal constraint"""

    bl_idname = Operators.AddHorizontal
    bl_label = "Horizontal"
    bl_options = {"UNDO", "REGISTER"}

    type = "HORIZONTAL"

    def main(self, context):
        if not self.exists(context, SlvsHorizontal):
            self.target = context.scene.sketcher.constraints.add_horizontal(
                self.entity1,
                entity2=self.entity2,
                sketch=self.sketch,
            )

        return super().main(context)


class VIEW3D_OT_slvs_add_parallel(Operator, GenericConstraintOp):
    """Add a parallel constraint"""

    bl_idname = Operators.AddParallel
    bl_label = "Parallel"
    bl_options = {"UNDO", "REGISTER"}

    type = "PARALLEL"

    def main(self, context):
        if not self.exists(context, SlvsParallel):
            self.target = context.scene.sketcher.constraints.add_parallel(
                self.entity1,
                self.entity2,
                sketch=self.sketch,
            )

        return super().main(context)


class VIEW3D_OT_slvs_add_perpendicular(Operator, GenericConstraintOp):
    """Add a perpendicular constraint"""

    bl_idname = Operators.AddPerpendicular
    bl_label = "Perpendicular"
    bl_options = {"UNDO", "REGISTER"}

    type = "PERPENDICULAR"

    def main(self, context):
        if not self.exists(context, SlvsPerpendicular):
            self.target = context.scene.sketcher.constraints.add_perpendicular(
                self.entity1,
                self.entity2,
                sketch=self.sketch,
            )

        return super().main(context)


class VIEW3D_OT_slvs_add_tangent(Operator, GenericConstraintOp):
    """Add a tangent constraint"""

    bl_idname = Operators.AddTangent
    bl_label = "Tangent"
    bl_options = {"UNDO", "REGISTER"}

    type = "TANGENT"

    def main(self, context):
        if not self.exists(context, SlvsTangent):
            self.target = context.scene.sketcher.constraints.add_tangent(
                self.entity1,
                self.entity2,
                sketch=self.sketch,
            )

        return super().main(context)


class VIEW3D_OT_slvs_add_midpoint(Operator, GenericConstraintOp):
    """Add a midpoint constraint"""

    bl_idname = Operators.AddMidPoint
    bl_label = "Midpoint"
    bl_options = {"UNDO", "REGISTER"}

    type = "MIDPOINT"

    def main(self, context):
        if not self.exists(context, SlvsMidpoint):
            self.target = context.scene.sketcher.constraints.add_midpoint(
                self.entity1,
                self.entity2,
                sketch=self.sketch,
            )

        return super().main(context)


class VIEW3D_OT_slvs_add_ratio(Operator, GenericConstraintOp):
    """Add a ratio constraint"""

    bl_idname = Operators.AddRatio
    bl_label = "Ratio"
    bl_options = {"UNDO", "REGISTER"}

    value: FloatProperty(
        name="Ratio",
        subtype="UNSIGNED",
        options={"SKIP_SAVE"},
        min=0.0,
        precision=5,
    )
    type = "RATIO"
    property_keys = ("value",)

    def main(self, context):
        if not self.exists(context, SlvsRatio):
            self.target = context.scene.sketcher.constraints.add_ratio(
                self.entity1,
                self.entity2,
                sketch=self.sketch,
                init=not self.initialized,
                **self.get_settings(),
            )

        return super().main(context)


constraint_operators = (
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

register, unregister = register_stateops_factory(constraint_operators)
