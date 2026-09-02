import logging

from bpy.types import Context, Operator

from ..declarations import Operators
from ..model.angle import SlvsAngle
from ..model.arc import SlvsArc
from ..model.circle import SlvsCircle
from ..model.curve_ref import ArcRef, CircleRef, LineRef, PointRef
from ..model.diameter import SlvsDiameter
from ..model.distance import SlvsDistance
from ..model.line_2d import SlvsLine2D
from ..model.point_2d import SlvsPoint2D
from ..stateful_operator.state import state_from_args
from ..stateful_operator.utilities.register import register_stateops_factory
from .base_constraint import GenericConstraintOp

logger = logging.getLogger(__name__)


class VIEW3D_OT_slvs_add_dimension(Operator, GenericConstraintOp):
    """Add a dimension. The constraint type (distance, diameter or angle) is
    inferred from the selected geometry, so the user doesn't pick it up front."""

    bl_idname = Operators.AddDimension
    bl_label = "Dimension"
    bl_options = {"UNDO", "REGISTER"}

    # No single constraint type -- dispatched at runtime in main(). Both
    # states()/_available_entities() are overridden so cls.type is never used.
    type = None
    property_keys = ()
    has_value_state = False

    @staticmethod
    def _second_slot(operator):
        """(types, optional) for the second pick, narrowed by the first entity.

        A lone point can't be dimensioned so its second pick is required; a line
        or curve can (length / diameter), so theirs is optional -- picking a
        second entity then switches the inferred type (e.g. line -> angle).
        """
        e1 = getattr(operator, "entity1", None) if operator else None
        if isinstance(e1, PointRef):
            return (SlvsPoint2D, SlvsLine2D), False
        if isinstance(e1, LineRef):
            # + line -> angle, + point -> point/line distance, none -> length.
            return (SlvsLine2D, SlvsPoint2D), True
        if isinstance(e1, (CircleRef, ArcRef)):
            # + line/point -> distance, none -> diameter/radius.
            return (SlvsLine2D, SlvsPoint2D), True
        # Before the first pick: offer a generic optional second entity.
        return (SlvsPoint2D, SlvsLine2D), True

    @classmethod
    def states(cls, operator=None):
        first_types = (SlvsPoint2D, SlvsLine2D, SlvsCircle, SlvsArc)
        states = [
            state_from_args(
                "Entity 1",
                description="Pick geometry to dimension.",
                pointer="entity1",
                types=first_types,
                use_create=False,
            )
        ]
        second_types, optional = cls._second_slot(operator)
        if second_types:
            states.append(
                state_from_args(
                    "Entity 2",
                    description="Optionally pick a second entity to dimension against.",
                    pointer="entity2",
                    types=second_types,
                    use_create=False,
                    optional=optional,
                )
            )
        return states

    def _available_entities(self):
        return [getattr(self, "entity1", None), getattr(self, "entity2", None)]

    def _add_line_length(self, context):
        """Distance = a line's length: expand the line to its two endpoints and
        constrain their distance (mirrors VIEW3D_OT_slvs_add_distance)."""
        e1 = self.entity1
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
        if not self.exists(context, SlvsDistance, max_constraints=2):
            self.target = self.sketch.constraints.add_distance(
                init=not self.initialized,
                curve_id_1=e1.curve_id if e1 else "",
                curve_id_2=e2.curve_id if e2 else "",
            )

    def main(self, context):
        e1, e2 = self.entity1, self.entity2
        if e1 is None:
            return False

        constraints = self.sketch.constraints

        if e2 is None:
            if isinstance(e1, (CircleRef, ArcRef)):
                if not self.exists(context, SlvsDiameter):
                    self.target = constraints.add_diameter(
                        init=not self.initialized, curve_id_1=e1.curve_id
                    )
            elif isinstance(e1, LineRef):
                self._add_line_length(context)
            else:
                self.report({"WARNING"}, "Select a second entity to add a dimension")
                return False
        elif isinstance(e1, LineRef) and isinstance(e2, LineRef):
            if not self.exists(context, SlvsAngle):
                self.target = constraints.add_angle(
                    init=not self.initialized,
                    curve_id_1=e1.curve_id,
                    curve_id_2=e2.curve_id,
                )
        else:
            max_constraints = (
                2 if isinstance(e1, PointRef) and isinstance(e2, PointRef) else 1
            )
            if not self.exists(context, SlvsDistance, max_constraints):
                self.target = constraints.add_distance(
                    init=not self.initialized,
                    curve_id_1=e1.curve_id,
                    curve_id_2=e2.curve_id,
                )

        return super().main(context)

    def fini(self, context: Context, succeede: bool):
        # Default label offset before the placement handoff (see add_distance).
        if getattr(self, "target", None):
            self.target.draw_offset = 0.1 * context.region_data.view_distance
        super().fini(context, succeede)


register, unregister = register_stateops_factory((VIEW3D_OT_slvs_add_dimension,))
