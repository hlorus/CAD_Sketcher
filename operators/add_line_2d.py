import logging
from typing import Optional

import numpy as np
from bpy.props import BoolProperty
from bpy.types import Context, Operator
from mathutils import Vector

from ..curve_solver import solve_system
from ..declarations import Operators
from ..model.curve_ref import LineRef
from ..stateful_operator.state import state_from_args
from ..stateful_operator.utilities.register import register_stateops_factory
from ..utilities.constants import HALF_TURN, QUARTER_TURN
from .base_2d import Operator2d, ReplaceableOutputOp
from .constants import types_point_2d
from .placement import placement_of
from .utilities import ignore_hover

logger = logging.getLogger(__name__)


def _alignment(vec: Vector) -> Optional[str]:
    """``HORIZONTAL`` or ``VERTICAL`` for a nearly axis-aligned line, else None."""
    if not vec.length:
        # A zero-length line counts as horizontal, as its direction does.
        return "HORIZONTAL"
    angle = vec.angle(Vector((1, 0)))
    threshold = 0.1
    if angle < threshold or angle > HALF_TURN - threshold:
        return "HORIZONTAL"
    if (QUARTER_TURN - threshold) < angle < (QUARTER_TURN + threshold):
        return "VERTICAL"
    return None


class View3D_OT_slvs_add_line2d(Operator, ReplaceableOutputOp, Operator2d):
    """Add a line to the active sketch"""

    bl_idname = Operators.AddLine2D
    bl_label = "Add Solvespace 2D Line"
    bl_options = {"REGISTER", "UNDO"}

    l2d_state1_doc = ("Startpoint", "Pick or place line's starting Point.")
    l2d_state2_doc = ("Endpoint", "Pick or place line's ending Point.")

    continuous_draw: BoolProperty(name="Continuous Draw", default=True)

    states = (
        state_from_args(
            l2d_state1_doc[0],
            description=l2d_state1_doc[1],
            pointer="p1",
            types=types_point_2d,
        ),
        state_from_args(
            l2d_state2_doc[0],
            description=l2d_state2_doc[1],
            pointer="p2",
            types=types_point_2d,
            interactive=True,
        ),
    )

    @classmethod
    def poll(cls, context: Context):
        """Never let a stale 2D hotkey/operator path create XY geometry in 3D."""
        from ..model.sketch_ref import poll_active_2d_sketch

        return poll_active_2d_sketch(context)

    preview_in_place = True

    def preview_structure(self, context: Context):
        """Also rebuild when the inferred alignment changes, so it shows live."""
        structure = super().preview_structure(context)
        if structure is None or self.state_index != 1:
            return structure
        start = self.get_point(context, 0)
        if self.state_data.get("is_existing_entity", False):
            end = self.get_point(context, 1).co
        else:
            # The endpoint is recreated from this value, stored as float32.
            end = [float(np.float32(c)) for c in getattr(self, self.get_property()[0])]
        if start is None or not start.valid:
            return None
        return structure, _alignment(Vector(end[:2]) - start.co)

    def update_preview(self, context: Context) -> bool:
        """Drag the line's endpoint instead of recreating the line."""
        target = getattr(self, "target", None)
        if target is None or not target.valid:
            return False
        return self.update_preview_point(context)

    def main(self, context: Context):
        p1, p2 = self.get_point(context, 0), self.get_point(context, 1)
        sketch = self.sketch
        construction = context.scene.sketcher.use_construction

        self.target = LineRef.create(sketch, p1, p2, construction=construction)
        line_cid = self.target.curve_id

        # auto vertical/horizontal constraint. Skip it when both endpoints are
        # anchored (e.g. both snapped to external geometry): the alignment can't
        # move either point, so adding it would just make the sketch inconsistent.
        # An endpoint counts as anchored if it is fixed, or if it was live-projected
        # onto a fixed vertex/midpoint (coincident to a fixed point -> immovable,
        # even though the endpoint itself is not flagged fixed).
        #
        # Added during the preview so it shows while dragging. An in-place update
        # skips main, so this trial solves only when the alignment changes (see
        # preview_structure); the solve that moves geometry still runs in fini.
        self.has_alignment = False
        p1_anchored = self.target.p1.fixed or self.point_is_anchored(0)
        p2_anchored = self.target.p2.fixed or self.point_is_anchored(1)
        both_fixed = p1_anchored and p2_anchored
        kind = _alignment(self.target.p2.co - self.target.p1.co)
        if kind and self.use_auto_constraints(context) and not both_fixed:
            constraints = sketch.constraints
            add = (
                constraints.add_horizontal
                if kind == "HORIZONTAL"
                else constraints.add_vertical
            )
            self.has_alignment = bool(
                self.add_auto_constraint(context, add, curve_id_1=line_cid)
            )

        ignore_hover(line_cid)
        return True

    def continue_draw(self):
        last_state = self._state_data[1]
        if last_state["is_existing_entity"]:
            return False

        # also not when last state has coincident constraint
        if placement_of(last_state).coincident:
            return False
        return True

    def fini(self, context: Context, succeede: bool):
        if hasattr(self, "target"):
            logger.debug("Add: {}".format(self.target))

        if succeede:
            if self.has_coincident() or self.has_alignment:
                solve_system(context, sketch=self.sketch)


register, unregister = register_stateops_factory((View3D_OT_slvs_add_line2d,))
