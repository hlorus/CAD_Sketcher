import logging

from bpy.props import FloatProperty
from bpy.types import Context, Operator
from mathutils.geometry import intersect_line_plane

from ..declarations import Operators
from ..model.angle import SlvsAngle
from ..model.arc import SlvsArc
from ..model.circle import SlvsCircle
from ..model.curve_ref import ArcRef, CircleRef, LineRef, PointRef
from ..model.diameter import SlvsDiameter
from ..model.distance import SlvsDistance
from ..model.line_2d import SlvsLine2D
from ..model.point_2d import SlvsPoint2D
from ..model.sketch_ref import get_active_constraints
from ..stateful_operator.state import state_from_args
from ..stateful_operator.utilities.register import register_stateops_factory
from ..utilities.view import get_picking_origin_end, refresh
from .base_constraint import GenericConstraintOp

logger = logging.getLogger(__name__)

_PLACEMENT_STATE = "Placement"


class VIEW3D_OT_slvs_add_dimension(Operator, GenericConstraintOp):
    """Add a dimension.

    The concrete constraint type is inferred from the selected geometry, so the
    user does not have to choose between distance, angle and diameter up front:

    - a single line              -> distance (its length)
    - two lines                  -> angle
    - a circle or arc            -> diameter
    - two points / point + line  -> distance

    After the geometry is picked the same operator stays live in a final
    placement state where the dimension label is dragged into place (display
    only, no re-solve) and confirmed with a click.
    """

    bl_idname = Operators.AddDimension
    bl_label = "Dimension"
    bl_options = {"UNDO", "REGISTER"}

    # GenericConstraintOp keys off a single constraint ``type``; this operator
    # spans several, so it drives ``states``/creation itself and never resolves a
    # type from the base machinery.
    type = None
    property_keys = ()
    has_value_state = False

    # Live label offset. Filled by the placement state's ``state_func`` as a
    # display-only side effect; the property itself is only a confirm carrier.
    placement: FloatProperty(options={"SKIP_SAVE", "HIDDEN"})

    @staticmethod
    def _second_slot(operator):
        """Return ``(types, optional)`` for the second pick, given the first.

        The second slot is narrowed by what the first entity was: a line pairs
        with another line (angle) or a point/line (distance); a point needs a
        partner to be dimensionable at all; a circle/arc needs nothing more.
        ``optional`` marks whether the operator can finish on the first pick.
        """
        e1 = getattr(operator, "entity1", None) if operator else None
        if isinstance(e1, (CircleRef, ArcRef)):
            # Diameter needs no second entity.
            return (), False
        if isinstance(e1, PointRef):
            # A lone point cannot be dimensioned -- require a partner.
            return (SlvsPoint2D, SlvsLine2D), False
        if isinstance(e1, LineRef):
            # A single line already has a length; a second line switches to angle.
            return (SlvsLine2D, SlvsPoint2D), True
        return (SlvsPoint2D, SlvsLine2D), True

    @classmethod
    def states(cls, operator=None):
        """Build the pick states, then a terminal interactive placement state."""
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

        # Placement: no property/pointer, so it neither re-solves nor snapshots
        # per move -- its ``state_func`` just drags the label offset, and a click
        # confirms via the optional-state skip in the state machine.
        states.append(
            state_from_args(
                _PLACEMENT_STATE,
                description="Move to place the dimension label, click to confirm.",
                property=None,
                state_func="_place_dimension",
                interactive=True,
                optional=True,
                allow_prefill=False,
            )
        )
        return states

    def _available_entities(self):
        return [getattr(self, "entity1", None), getattr(self, "entity2", None)]

    def _is_placement_state(self) -> bool:
        return self.state.name == _PLACEMENT_STATE

    def _apply_undo(self, context: Context):
        """Keep label placement out of the state machine's per-move undo cycle.

        Once the geometry is picked the constraint is stable and only its display
        offset changes. The framework otherwise restores its snapshot on every
        move here -- which deletes the constraint (main() is guarded, so nothing
        recreates it) and resets the offset, leaving the gizmo nothing to track.
        Suppressing it makes placement behave like the standalone tweak modal: a
        single live constraint whose gizmo follows the cursor. Outside placement
        the normal undo/redo still runs so each pick can re-infer the type.
        """
        if self._is_placement_state():
            self._undo = False
            return
        super()._apply_undo(context)

    def _distance_exists(self, context: Context, cids) -> bool:
        """True if a distance constraint already spans exactly ``cids``."""
        want = set(cids)
        for c in get_active_constraints(context).all:
            if isinstance(c, SlvsDistance) and set(c.curve_id_placements()) == want:
                return True
        return False

    def _clear_target(self, context: Context):
        """Drop a previously created constraint before re-inferring the type.

        Picking a second line after a first turns a tentative length into an
        angle; without a snapshot in the placement path we remove the stale one
        explicitly so the two never coexist.
        """
        target = getattr(self, "target", None)
        if target is None:
            return
        try:
            self.sketch.constraints.remove(target)
        except (ValueError, RuntimeError):
            pass
        self.target = None

    def _create_constraint(self, context: Context):
        """Infer and create the dimensional constraint from the current picks."""
        e1 = self.entity1
        e2 = getattr(self, "entity2", None)
        constraints = self.sketch.constraints
        init = not self.initialized

        if e2 is None:
            if isinstance(e1, (CircleRef, ArcRef)):
                if not self.exists(context, SlvsDiameter):
                    self.target = constraints.add_diameter(
                        init=init, curve_id_1=e1.curve_id
                    )
                    logger.debug("Dimension -> diameter on %s", e1.curve_id)
            elif isinstance(e1, LineRef):
                # The native solver needs two point ids, so measure the line as
                # the distance between its own endpoints.
                p1, p2 = e1.p1, e1.p2
                if (
                    p1
                    and p2
                    and not self._distance_exists(context, (p1.curve_id, p2.curve_id))
                ):
                    self.target = constraints.add_distance(
                        init=init, curve_id_1=p1.curve_id, curve_id_2=p2.curve_id
                    )
                    logger.debug("Dimension -> line length on %s", e1.curve_id)
            else:
                logger.debug("Dimension: point %s needs a second entity", e1.curve_id)
                return
        elif isinstance(e1, LineRef) and isinstance(e2, LineRef):
            if not self.exists(context, SlvsAngle):
                self.target = constraints.add_angle(
                    init=init, curve_id_1=e1.curve_id, curve_id_2=e2.curve_id
                )
                logger.debug(
                    "Dimension -> angle between %s and %s", e1.curve_id, e2.curve_id
                )
        else:
            # Distance's natural form is point-to-line/point. The model collapses
            # a *line* entity1 to its endpoints, so a line+point pair must be
            # ordered point-first to measure the point-to-line distance.
            if isinstance(e1, LineRef) and isinstance(e2, PointRef):
                e1, e2 = e2, e1
            max_constraints = (
                2 if isinstance(e1, PointRef) and isinstance(e2, PointRef) else 1
            )
            if not self.exists(context, SlvsDistance, max_constraints):
                self.target = constraints.add_distance(
                    init=init, curve_id_1=e1.curve_id, curve_id_2=e2.curve_id
                )
                logger.debug("Dimension -> distance %s -> %s", e1.curve_id, e2.curve_id)

        # Give the freshly created label a sensible default offset so it is
        # visible before the first placement move (overwritten while dragging).
        target = getattr(self, "target", None)
        if target and context.region_data:
            target.draw_offset = 0.05 * context.region_data.view_distance

    def _place_dimension(self, context: Context, coords):
        """Drag the dimension label onto the cursor, display only.

        Projects the cursor onto the constraint's draw plane and offsets the
        label there. Returns ``None`` so the placement state stores no value and
        never triggers a re-solve; confirmation happens via the state click.
        """
        target = getattr(self, "target", None)
        if not target or not hasattr(target, "update_draw_offset"):
            logger.debug("Placement: no target to place")
            return None

        origin, end_point = get_picking_origin_end(context, coords)
        pos = intersect_line_plane(origin, end_point, *target.draw_plane())
        if pos is not None:
            pos = target.matrix_basis().inverted() @ pos
            target.update_draw_offset(pos, context.preferences.system.ui_scale)
            # Full refresh (show_gizmo + redraw) so the gizmo re-reads the offset.
            refresh(context)
        # Per-move diagnostic (throttled): confirms _place_dimension keeps being
        # called as the cursor moves and that draw_offset actually changes, and
        # whether the target's index stays stable (a churned index would leave
        # the gizmo bound to a stale constraint).
        self._place_calls = getattr(self, "_place_calls", 0) + 1
        if self._place_calls % 4 == 1:
            constraints = get_active_constraints(context)
            logger.debug(
                "Placement #%d: draw_offset=%.3f outset=%.3f target=%s idx=%s n=%d",
                self._place_calls,
                getattr(target, "draw_offset", 0.0),
                getattr(target, "draw_outset", 0.0),
                target.type,
                constraints.get_index(target) if constraints else -1,
                len(list(constraints.all)) if constraints else -1,
            )
        return None

    def main(self, context: Context):
        e1 = getattr(self, "entity1", None)
        if e1 is None:
            return False

        # While placing the label the geometry is fixed and only ``draw_offset``
        # changes, so skip the recreate/solve and keep the existing constraint.
        if self.initialized and self._is_placement_state():
            return bool(getattr(self, "target", None))

        # An entity pick changed the inference -- rebuild the constraint.
        self._clear_target(context)
        self._create_constraint(context)
        return super().main(context)

    def fini(self, context: Context, succeede: bool):
        # Placement now happens in this operator's own placement state, so there
        # is no hand-off to the standalone tweak modal (unlike GenericConstraintOp).
        # Make sure gizmos end up visible and the label reflects the final offset.
        refresh(context)
        target = getattr(self, "target", None)
        if target is not None:
            logger.debug("Dimension committed: %s (succeeded=%s)", target, succeede)


register, unregister = register_stateops_factory((VIEW3D_OT_slvs_add_dimension,))
