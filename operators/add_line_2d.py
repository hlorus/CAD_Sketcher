import logging

from bpy.types import Operator, Context
from bpy.props import BoolProperty
from mathutils import Vector

from ..utilities.constants import HALF_TURN, QUARTER_TURN

from ..declarations import Operators
from ..stateful_operator.utilities.register import register_stateops_factory
from ..stateful_operator.state import state_from_args
from ..solver import solve_system
from .base_2d import Operator2d
from .constants import types_point_2d
from .utilities import ignore_hover

logger = logging.getLogger(__name__)


class View3D_OT_slvs_add_line2d(Operator, Operator2d):
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

    def main(self, context: Context):
        wp = self.sketch.wp
        p1, p2 = self.get_point(context, 0), self.get_point(context, 1)

        self.target = context.scene.sketcher.entities.add_line_2d(p1, p2, self.sketch)
        if context.scene.sketcher.use_construction:
            self.target.construction = True

        # auto vertical/horizontal constraint
        self.has_alignment = False
        constraints = context.scene.sketcher.constraints
        vec_dir = self.target.direction_vec()
        if vec_dir.length:
            angle = vec_dir.angle(Vector((1, 0)))

            threshold = 0.1
            if angle < threshold or angle > HALF_TURN - threshold:
                constraints.add_horizontal(self.target, sketch=self.sketch)
                self.has_alignment = True
            elif (QUARTER_TURN - threshold) < angle < (QUARTER_TURN + threshold):
                constraints.add_vertical(self.target, sketch=self.sketch)
                self.has_alignment = True

        ignore_hover(self.target)
        return True

    def continue_draw(self):
        last_state = self._state_data[1]
        if last_state["is_existing_entity"]:
            return False

        # also not when last state has coincident constraint
        if last_state.get("coincident"):
            return False
        return True

    def fini(self, context: Context, succeede: bool):
        if hasattr(self, "target"):
            logger.debug("Add: {}".format(self.target))

        if succeede:
            if self.has_coincident() or self.has_alignment:
                solve_system(context, sketch=self.sketch)


register, unregister = register_stateops_factory((View3D_OT_slvs_add_line2d,))
