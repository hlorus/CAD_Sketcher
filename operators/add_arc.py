import logging
import math

from bpy.types import Operator, Context, Event
from mathutils import Vector

from ..declarations import Operators
from ..stateful_operator.utilities.register import register_stateops_factory
from ..stateful_operator.state import state_from_args
from ..solver import solve_system
from ..utilities.geometry import intersect_line_sphere_2d
from ..utilities.math import pol2cart
from .base_2d import Operator2d
from .constants import types_point_2d
from .utilities import ignore_hover
from ..utilities.view import get_blender_snap_info, get_pos_2d

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
        snap_data = get_blender_snap_info(context, coords)
        mouse_pos = get_pos_2d(
            context, self.sketch.wp, coords, respect_snapping=True
        )
        if mouse_pos is None:
            return None

        # Get angle to mouse pos
        ct = self.get_point(context, 0).co
        x, y = Vector(mouse_pos) - ct
        angle = math.atan2(y, x)

        # Get radius from distance ct - p1
        p1 = self.get_point(context, 1).co
        radius = (p1 - ct).length

        if snap_data and snap_data["type"] in {"EDGE", "EDGE_MIDPOINT"}:
            world_edge = snap_data.get("world_edge")
            if world_edge:
                edge_points = [
                    Vector((self.sketch.wp.matrix_basis.inverted() @ point)[:-1])
                    for point in world_edge
                ]
                intersections = intersect_line_sphere_2d(
                    edge_points[0], edge_points[1], ct, radius
                )
                if intersections:
                    return min(
                        intersections,
                        key=lambda point: (Vector(point) - mouse_pos).length,
                    )

        if snap_data and snap_data["type"] == "VERTEX":
            vertex_pos = Vector(
                (
                    self.sketch.wp.matrix_basis.inverted() @ snap_data["world_point"]
                )[:-1]
            )
            if abs((vertex_pos - ct).length - radius) < 1e-5:
                return vertex_pos

        pos = pol2cart(radius, angle) + ct
        return pos

    def solve_state(self, context: Context, _event: Event):
        sketch = context.scene.sketcher.active_sketch
        solve_system(context, sketch=sketch)
        return True

    def main(self, context):
        ct, p1, p2 = (
            self.get_point(context, 0),
            self.get_point(context, 1),
            self.get_point(context, 2),
        )
        sketch = self.sketch
        sse = context.scene.sketcher.entities
        arc = sse.add_arc(sketch.wp.nm, ct, p1, p2, sketch)

        center = ct.co
        start = p1.co - center
        end = p2.co - center
        a = end.angle_signed(start)
        arc.invert_direction = a < 0

        ignore_hover(arc)
        self.target = arc
        if context.scene.sketcher.use_construction:
            self.target.construction = True
        return True

    def fini(self, context: Context, succeede: bool):
        if hasattr(self, "target"):
            logger.debug("Add: {}".format(self.target))
            self.solve_state(context, self.sketch)


register, unregister = register_stateops_factory((View3D_OT_slvs_add_arc2d,))
