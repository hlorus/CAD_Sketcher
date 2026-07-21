import logging

from bpy.types import Operator, Context
from bpy.props import FloatProperty

from ..curve_solver import solve_system
from ..declarations import Operators
from ..stateful_operator.utilities.register import register_stateops_factory
from .base_constraint import GenericConstraintOp
from ..utilities.select import deselect_all
from ..utilities.view import refresh
from .. import global_data

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
    """Merge two point curves: remap all references from duplicate to target, then delete duplicate."""
    from ..model.sketch_ref import get_active_sketch
    sketch = get_active_sketch(context)
    if not sketch or not sketch.target_object or not sketch.target_object.data:
        return

    cd = sketch.target_object.data
    dup_cid = duplicate.curve_id
    tgt_cid = target.curve_id

    # Remap relationship attributes
    for attr_name in ("start_point_id", "end_point_id", "center_point_id"):
        attr = cd.attributes.get(attr_name)
        if not attr:
            continue
        for i in range(len(cd.curves)):
            if attr.data[i].value == dup_cid:
                attr.data[i].value = tgt_cid

    # Remap constraint curve_ids
    for c in sketch.constraints.all:
        if getattr(c, "curve_id_1", 0) == dup_cid:
            c.curve_id_1 = tgt_cid
        if getattr(c, "curve_id_2", 0) == dup_cid:
            c.curve_id_2 = tgt_cid
        if getattr(c, "curve_id_3", 0) == dup_cid:
            c.curve_id_3 = tgt_cid

    # Remove duplicate
    duplicate.remove()


class VIEW3D_OT_slvs_merge_points(Operator):
    """Merge selected points"""

    bl_idname = Operators.MergePoints
    bl_label = "Merge Points"
    bl_options = {"UNDO", "REGISTER"}

    @classmethod
    def poll(cls, context: Context):
        from ..model.sketch_ref import get_active_sketch
        return bool(get_active_sketch(context))

    def execute(self, context: Context):
        from ..model.sketch_ref import get_active_sketch
        from ..model.curve_ref import curve_ref

        sketch = get_active_sketch(context)
        if not sketch:
            return {"CANCELLED"}

        points = [
            curve_ref(sketch, cid)
            for cid in global_data.selected
            if curve_ref(sketch, cid).is_point()
        ]

        if len(points) < 2:
            self.report({"WARNING"}, "Select at least two points to merge")
            return {"CANCELLED"}

        fixed_points = [p for p in points if p.fixed]
        if len(fixed_points) > 1:
            self.report({"WARNING"}, "Cannot merge multiple fixed points")
            return {"CANCELLED"}

        target = fixed_points[0] if fixed_points else points[-1]
        duplicates = [p for p in points if p.curve_id != target.curve_id]

        for dup in duplicates:
            merge_points(context, dup, target)

        # Delete collapsed lines (start == end after merge)
        collapsed = []
        cd = sketch.target_object.data
        sp_attr = cd.attributes.get("start_point_id")
        ep_attr = cd.attributes.get("end_point_id")
        if sp_attr and ep_attr:
            cid_attr = cd.attributes.get("curve_id")
            for i in range(len(cd.curves)):
                sp = sp_attr.data[i].value
                ep = ep_attr.data[i].value
                if sp and ep and sp == ep:
                    collapsed.append(cid_attr.data[i].value)
            for cid in collapsed:
                curve_ref(sketch, cid).remove()

        deselect_all(context)
        global_data.selected.append(target.curve_id)

        solve_system(context, sketch)
        refresh(context)

        n = len(duplicates)
        if collapsed:
            self.report({"INFO"}, f"Merged {n} point(s) and deleted {len(collapsed)} collapsed line(s)")
        else:
            self.report({"INFO"}, f"Merged {n} point(s)")
        return {"FINISHED"}


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
            if p1.fixed:
                continue

            merge_points(context, p1, p2)
            from ..model.sketch_ref import get_active_sketch
            solve_system(context, get_active_sketch(context))
            break
        return True

    def main(self, context: Context):
        # Implicitly merge points
        if self.handle_merge(context):
            return True

        if not self.exists(context, SlvsCoincident):
            self.target = self.sketch.constraints.add_coincident(
                
                curve_id_1=self.entity1.curve_id,
                curve_id_2=self.entity2.curve_id,
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
            self.target = self.sketch.constraints.add_equal(
                
                curve_id_1=self.entity1.curve_id,
                curve_id_2=self.entity2.curve_id,
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
            self.target = self.sketch.constraints.add_vertical(
                
                curve_id_1=self.entity1.curve_id,
                curve_id_2=self.entity2.curve_id if self.entity2 else "",
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
            self.target = self.sketch.constraints.add_horizontal(
                
                curve_id_1=self.entity1.curve_id,
                curve_id_2=self.entity2.curve_id if self.entity2 else "",
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
            self.target = self.sketch.constraints.add_parallel(
                
                curve_id_1=self.entity1.curve_id,
                curve_id_2=self.entity2.curve_id,
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
            self.target = self.sketch.constraints.add_perpendicular(
                
                curve_id_1=self.entity1.curve_id,
                curve_id_2=self.entity2.curve_id,
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
            self.target = self.sketch.constraints.add_tangent(
                
                curve_id_1=self.entity1.curve_id,
                curve_id_2=self.entity2.curve_id,
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
            self.target = self.sketch.constraints.add_midpoint(
                
                curve_id_1=self.entity1.curve_id,
                curve_id_2=self.entity2.curve_id,
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
            self.target = self.sketch.constraints.add_ratio(
                
                init=not self.initialized,
                curve_id_1=self.entity1.curve_id,
                curve_id_2=self.entity2.curve_id,
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
            self.target = self.sketch.constraints.add_symmetry(
                
                curve_id_1=self.entity1.curve_id,
                curve_id_2=self.entity2.curve_id,
                curve_id_3=self.entity3.curve_id,
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
