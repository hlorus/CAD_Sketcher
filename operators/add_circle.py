import logging

from bpy.props import FloatProperty
from bpy.types import Context, Operator
from mathutils import Vector
from mathutils.geometry import intersect_point_line

from ..curve_solver import solve_system
from ..declarations import Operators
from ..model.curve_ref import CircleRef
from ..stateful_operator.state import state_from_args
from ..stateful_operator.utilities.register import register_stateops_factory
from ..utilities.view import get_blender_snap_info, get_pos_2d, get_wp_matrix
from .base_2d import Operator2d
from .constants import types_point_2d
from .utilities import ignore_hover

logger = logging.getLogger(__name__)


class View3D_OT_slvs_add_circle2d(Operator, Operator2d):
    """Add a circle to the active sketch"""

    bl_idname = Operators.AddCircle2D
    bl_label = "Add Solvespace 2D Circle"
    bl_options = {"REGISTER", "UNDO"}

    circle_state1_doc = ("Center", "Pick or place circle's center point.")
    circle_state2_doc = ("Radius", "Set circle's radius.")

    radius: FloatProperty(
        name="Radius",
        subtype="DISTANCE",
        unit="LENGTH",
        precision=5,
        # precision=get_prefs().decimal_precision,
    )

    states = (
        state_from_args(
            circle_state1_doc[0],
            description=circle_state1_doc[1],
            pointer="ct",
            types=types_point_2d,
        ),
        state_from_args(
            circle_state2_doc[0],
            description=circle_state2_doc[1],
            property="radius",
            state_func="get_radius",
            interactive=True,
            allow_prefill=False,
        ),
    )

    def get_radius(self, context: Context, coords):
        wp = self._get_wp()
        snap_data = get_blender_snap_info(context, coords)
        self._snap = snap_data
        pos = get_pos_2d(context, wp, coords, respect_snapping=True)

        # Snap the radius so the circle is tangent to an edge or coincident with
        # a vertex (visual only — no constraint is created).
        if snap_data and snap_data["type"] in {"EDGE", "EDGE_MIDPOINT"}:
            world_edge = snap_data.get("world_edge")
            if world_edge:
                mat_inv = get_wp_matrix(wp).inverted()
                edge_start, edge_end = [
                    Vector((mat_inv @ point)[:-1]) for point in world_edge
                ]
                _, factor = intersect_point_line(self.ct.co, edge_start, edge_end)
                factor = min(max(factor, 0.0), 1.0)
                pos = edge_start.lerp(edge_end, factor)
        elif snap_data and snap_data["type"] in {"VERTEX", "FACE_MIDPOINT"}:
            pos = Vector((get_wp_matrix(wp).inverted() @ snap_data["world_point"])[:-1])

        delta = Vector(pos) - self.ct.co
        radius = delta.length
        return radius

    def main(self, context: Context):
        ct = self.get_point(context, 0)
        sketch = self.sketch
        construction = context.scene.sketcher.use_construction

        self.target = CircleRef.create(sketch, ct, self.radius, construction=construction)
        ignore_hover(self.target.curve_id)
        return True

    def fini(self, context: Context, succeede: bool):
        if hasattr(self, "target"):
            logger.debug("Add: {}".format(self.target))

        if succeede:
            if self.has_coincident():
                solve_system(context, sketch=self.sketch)


register, unregister = register_stateops_factory((View3D_OT_slvs_add_circle2d,))
