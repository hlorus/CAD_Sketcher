import logging

from bpy.props import BoolProperty, EnumProperty, FloatProperty
from bpy.types import Context, Operator

from ..declarations import Operators
from ..model.curve_ref import LineRef, PointRef
from ..model.distance import SlvsDistance, align_items
from ..stateful_operator.utilities.register import register_stateops_factory
from .base_constraint import GenericConstraintOp

logger = logging.getLogger(__name__)


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
    align: EnumProperty(name="Alignment", items=align_items)
    flip: BoolProperty(name="Flip")
    type = "DISTANCE"
    property_keys = ("value", "align", "flip")
    has_value_state = True

    def _legacy_constraint_exists(self, constraints, e1, e2):
        indices = {
            entity.slvs_index
            for entity in (e1, e2)
            if entity is not None and hasattr(entity, "slvs_index")
        }
        for constraint in constraints.get_list(SlvsDistance.type):
            existing = {
                entity.slvs_index
                for entity in constraint.entities()
                if hasattr(entity, "slvs_index")
            }
            if existing == indices:
                return True
        return False

    def _add_legacy_3d_distance(self, context, e1, e2):
        constraints = context.scene.sketcher.constraints
        if self._legacy_constraint_exists(constraints, e1, e2):
            return None

        constraint = constraints.distance.add()
        constraint.entity1 = e1
        if e2 is not None:
            constraint.entity2 = e2
        constraints._init_constraint(constraint)

        settings = self.get_settings()
        if not self.initialized:
            constraint.assign_init_props(**settings)
        else:
            constraint.assign_settings(**settings)
        return constraint

    def main(self, context):
        e1, e2 = self.entity1, self.entity2

        # Line length: expand native-curve lines to their endpoints. Legacy 3D
        # lines are kept as a single entity and SlvsDistance expands them when
        # creating SolveSpace data.
        if isinstance(e1, LineRef) and e2 is None:
            p1, p2 = e1.p1, e1.p2
            if p1 and p2:
                for i, pt in enumerate((p1, p2)):
                    state_data = self.get_state_data(i)
                    state_data["hovered"] = 0
                    state_data["type"] = PointRef
                    state_data["is_existing_entity"] = True
                    state_data["curve_id"] = pt.curve_id
                self.next_state(context)
                e1, e2 = self.entity1, self.entity2

        # Native curves and scene-level 3D entities intentionally use different
        # storage. The native path stays unchanged; 3D constraints live on the
        # scene so they can exist outside a sketch.
        if e1 is not None and not hasattr(e1, "curve_id"):
            self.target = self._add_legacy_3d_distance(context, e1, e2)
            return super().main(context)

        if isinstance(e1, LineRef) and e2 is None:
            max_constraints = 2
        elif isinstance(e1, PointRef) and isinstance(e2, PointRef):
            max_constraints = 2
        else:
            max_constraints = 1

        cid1 = e1.curve_id if e1 else ""
        cid2 = e2.curve_id if e2 else ""

        if not self.exists(context, SlvsDistance, max_constraints):
            self.target = self.sketch.constraints.add_distance(
                init=not self.initialized,
                curve_id_1=cid1,
                curve_id_2=cid2,
                **self.get_settings(),
            )
        return super().main(context)

    def fini(self, context: Context, succeede: bool):
        super().fini(context, succeede)
        if hasattr(self, "target") and self.target:
            self.target.draw_offset = 0.05 * context.region_data.view_distance

    def draw(self, context: Context):
        if not hasattr(self, "target") or not self.target:
            return

        layout = self.layout
        c = self.target

        row = layout.row()
        row.prop(self, "value")

        row = layout.row()
        row.enabled = c.use_align()
        row.prop(self, "align")

        row = layout.row()
        row.enabled = c.use_flipping()
        row.prop(self, "flip")


register, unregister = register_stateops_factory((VIEW3D_OT_slvs_add_distance,))
