import logging

from bpy.types import Operator, Context
from bpy.props import FloatProperty
from mathutils import Vector

from ..declarations import Operators
from ..stateful_operator.utilities.register import register_stateops_factory
from ..stateful_operator.state import state_from_args
from ..curve_solver import solve_system
from ..utilities.view import get_pos_2d
from ..model.curve_ref import CircleRef
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
        pos = get_pos_2d(context, wp, coords)
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
