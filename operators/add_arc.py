import logging
import math

from bpy.types import Operator, Context, Event
from mathutils import Vector

from ..declarations import Operators
from ..stateful_operator.utilities.register import register_stateops_factory
from ..stateful_operator.state import state_from_args
from ..curve_solver import solve_system
from ..utilities.math import pol2cart
from ..model.curve_ref import ArcRef
from .base_2d import Operator2d
from .constants import types_point_2d
from .utilities import ignore_hover
from ..utilities.view import get_pos_2d

logger = logging.getLogger(__name__)


class View3D_OT_slvs_add_arc2d(Operator, Operator2d):
    """Add an arc to the active sketch"""

    bl_idname = Operators.AddArc2D
    bl_label = "Add Solvespace 2D Arc"
    bl_options = {"REGISTER", "UNDO"}

    arc_state1_doc = ("Center", "Pick or place center point.")
    arc_state2_doc = ("Startpoint", "Pick or place starting point.")
    arc_state3_doc = ("Endpoint", "Pick or place ending point.")

    states = (
        state_from_args(
            arc_state1_doc[0],
            description=arc_state1_doc[1],
            pointer="ct",
            types=types_point_2d,
        ),
        state_from_args(
            arc_state2_doc[0],
            description=arc_state2_doc[1],
            pointer="p1",
            types=types_point_2d,
            allow_prefill=False,
        ),
        state_from_args(
            arc_state3_doc[0],
            description=arc_state3_doc[1],
            pointer="p2",
            types=types_point_2d,
            state_func="get_endpoint_pos",
            interactive=True,
        ),
    )

    def get_endpoint_pos(self, context: Context, coords):
        mouse_pos = get_pos_2d(context, self._get_wp(), coords)
        if mouse_pos is None:
            return None

        ct = self.get_point(context, 0).co
        p1 = self.get_point(context, 1).co

        x, y = Vector(mouse_pos) - ct
        mouse_angle = math.atan2(y, x)
        start_angle = math.atan2((p1 - ct).y, (p1 - ct).x)

        # Track cumulative angular displacement from start
        if not hasattr(self, "_prev_mouse_angle"):
            self._prev_mouse_angle = mouse_angle
            self._cumulative_angle = 0.0

        # Compute delta with wrap handling
        delta = mouse_angle - self._prev_mouse_angle
        if delta > math.pi:
            delta -= 2 * math.pi
        elif delta < -math.pi:
            delta += 2 * math.pi
        self._cumulative_angle += delta
        self._prev_mouse_angle = mouse_angle

        # Direction: negative cumulative = clockwise = invert
        self._arc_invert = self._cumulative_angle < 0

        # Snap endpoint to circle
        radius = (p1 - ct).length
        pos = pol2cart(radius, mouse_angle) + ct
        return pos

    def solve_state(self, context: Context, _event: Event):
        solve_system(context, sketch=self.sketch)
        return True

    def main(self, context):
        ct, p1, p2 = (
            self.get_point(context, 0),
            self.get_point(context, 1),
            self.get_point(context, 2),
        )
        sketch = self.sketch
        construction = context.scene.sketcher.use_construction

        invert = getattr(self, "_arc_invert", False)
        start, end = (p2, p1) if invert else (p1, p2)

        self.target = ArcRef.create(sketch, ct, start, end, construction=construction)
        ignore_hover(self.target.curve_id)
        return True

    def fini(self, context: Context, succeede: bool):
        if hasattr(self, "target"):
            logger.debug("Add: {}".format(self.target))
            self.solve_state(context, self.sketch)


register, unregister = register_stateops_factory((View3D_OT_slvs_add_arc2d,))
