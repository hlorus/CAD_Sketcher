import logging

from bpy.types import Operator, Context
from bpy.props import FloatProperty

from ..solver import solve_system
from ..declarations import Operators
from ..stateful_operator.utilities.register import register_stateops_factory
from .base_constraint import GenericConstraintOp
from ..utilities.select import deselect_all
from ..utilities.view import refresh
from ..utilities.merge import delete_collapsed_lines, merge_point_indices

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


class VIEW3D_OT_slvs_add_coincident(Operator, GenericConstraintOp):
    """Add a coincident constraint"""

    bl_idname = Operators.AddCoincident
    bl_label = "Coincident"
    bl_options = {"UNDO", "REGISTER"}

    type = "COINCIDENT"

    def _is_restricted_point_pair(self):
        points = self.entity1, self.entity2

        if not all(point.is_point() for point in points):
            return False

        return all(point.fixed for point in points)

    def main(self, context: Context):
        if self._is_restricted_point_pair():
            self.report(
                {"WARNING"},
                "Cannot add coincident between two fixed points",
            )
            return False

        if not self.exists(context, SlvsCoincident):
            self.target = context.scene.sketcher.constraints.add_coincident(
                self.entity1,
                self.entity2,
                sketch=self.sketch,
            )
        return super().main(context)


class VIEW3D_OT_slvs_merge_points(Operator):
    """Merge selected points"""

    bl_idname = Operators.MergePoints
    bl_label = "Merge Points"
    bl_options = {"UNDO", "REGISTER"}

    @classmethod
    def poll(cls, context: Context):
        return context.scene.sketcher.active_sketch_i != -1

    def _selected_points(self, context: Context):
        entities = context.scene.sketcher.entities
        return [entity for entity in entities.selected if entity.is_point()]

    def _resolve_target(self, points):
        origin_points = [point for point in points if point.origin]
        fixed_points = [point for point in points if point.fixed and not point.origin]

        if len(origin_points) > 1:
            return None, "Multiple origin points selected"

        if origin_points:
            if fixed_points:
                return None, "Cannot merge with origin and fixed points selected"
            return origin_points[0], None

        if len(fixed_points) > 1:
            return None, "Cannot merge multiple fixed points"

        if fixed_points:
            return fixed_points[0], None

        return points[-1], None

    def execute(self, context: Context):
        points = self._selected_points(context)
        if len(points) < 2:
            self.report({"WARNING"}, "Select at least two points to merge")
            return {"CANCELLED"}

        target, error = self._resolve_target(points)
        if error:
            level = {"WARNING"} if error == "Cannot merge multiple fixed points" else {"ERROR"}
            self.report(level, error)
            return {"CANCELLED"}

        duplicates = list(points)
        duplicates.remove(target)
        duplicate_indices = sorted(
            (point.slvs_index for point in duplicates),
            reverse=True,
        )
        target_index = target.slvs_index
        target_index = merge_point_indices(context, target_index, duplicate_indices)

        target = context.scene.sketcher.entities.get(target_index)
        if target is None:
            self.report({"ERROR"}, "Merge target became invalid")
            return {"CANCELLED"}

        deselect_all(context)
        target.selected = True

        deleted_lines = delete_collapsed_lines(context, point_indices={target_index})

        solve_system(context, context.scene.sketcher.active_sketch)
        refresh(context)
        if deleted_lines:
            self.report(
                {"INFO"},
                f"Merged {len(duplicates)} point(s) and deleted {deleted_lines} collapsed line(s)",
            )
        else:
            self.report({"INFO"}, f"Merged {len(duplicates)} point(s)")
        return {"FINISHED"}


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


class VIEW3D_OT_slvs_add_symmetry(Operator, GenericConstraintOp):
    """Add a symmetry constraint"""

    bl_idname = Operators.AddSymmetry
    bl_label = "Symmetry"
    bl_options = {"UNDO", "REGISTER"}

    type = "SYMMETRY"

    def main(self, context):
        if not self.exists(context, SlvsRatio):
            self.target = context.scene.sketcher.constraints.add_symmetry(
                self.entity1,
                self.entity2,
                self.entity3,
                sketch=self.sketch,
            )

        return super().main(context)


constraint_operators = (
    VIEW3D_OT_slvs_add_coincident,
    VIEW3D_OT_slvs_merge_points,
    VIEW3D_OT_slvs_add_equal,
    VIEW3D_OT_slvs_add_vertical,
    VIEW3D_OT_slvs_add_horizontal,
    VIEW3D_OT_slvs_add_parallel,
    VIEW3D_OT_slvs_add_perpendicular,
    VIEW3D_OT_slvs_add_tangent,
    VIEW3D_OT_slvs_add_midpoint,
    VIEW3D_OT_slvs_add_ratio,
    VIEW3D_OT_slvs_add_symmetry,
)

register, unregister = register_stateops_factory(constraint_operators)
