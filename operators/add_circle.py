import logging

from bpy.types import Operator, Context
from bpy.props import FloatProperty
from mathutils import Vector
from mathutils.geometry import intersect_point_line

from ..declarations import Operators
from ..stateful_operator.utilities.register import register_stateops_factory
from ..stateful_operator.state import state_from_args
from ..solver import solve_system
from ..utilities.view import get_blender_snap_info, get_pos_2d
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
        wp = self.sketch.wp
        snap_data = get_blender_snap_info(context, coords)
        pos = get_pos_2d(context, wp, coords, respect_snapping=True)
        if snap_data and snap_data["type"] in {"EDGE", "EDGE_MIDPOINT"}:
            world_edge = snap_data.get("world_edge")
            if world_edge:
                edge_start, edge_end = [
                    Vector((wp.matrix_basis.inverted() @ point)[:-1])
                    for point in world_edge
                ]
                pos, factor = intersect_point_line(self.ct.co, edge_start, edge_end)
                factor = min(max(factor, 0.0), 1.0)
                pos = edge_start.lerp(edge_end, factor)
        elif snap_data and snap_data["type"] == "VERTEX":
            pos = Vector((wp.matrix_basis.inverted() @ snap_data["world_point"])[:-1])

        delta = Vector(pos) - self.ct.co
        radius = delta.length
        return radius

    def main(self, context: Context):
        wp = self.sketch.wp
        ct = self.get_point(context, 0)
        self.target = context.scene.sketcher.entities.add_circle(
            wp.nm, ct, self.radius, self.sketch
        )
        if context.scene.sketcher.use_construction:
            self.target.construction = True
        ignore_hover(self.target)
        return True

    def fini(self, context: Context, succeede: bool):
        if hasattr(self, "target"):
            logger.debug("Add: {}".format(self.target))

        if succeede:
            if self.has_coincident():
                solve_system(context, sketch=self.sketch)
            self.sketch.geometry_solved = False


register, unregister = register_stateops_factory((View3D_OT_slvs_add_circle2d,))
