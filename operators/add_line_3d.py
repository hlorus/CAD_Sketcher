import logging

from bpy.types import Operator, Context
from bpy.props import BoolProperty

from ..declarations import Operators
from ..stateful_operator.utilities.register import register_stateops_factory
from ..stateful_operator.state import state_from_args
from ..solver import solve_system
from .base_3d import Operator3d
from .constants import types_point_3d
from .utilities import ignore_hover

logger = logging.getLogger(__name__)


class View3D_OT_slvs_add_line3d(Operator, Operator3d):
    """Add a line in 3d space"""

    bl_idname = Operators.AddLine3D
    bl_label = "Add Solvespace 3D Line"
    bl_options = {"REGISTER", "UNDO"}

    l3d_state1_doc = ("Startpoint", "Pick or place line's starting point.")
    l3d_state2_doc = ("Endpoint", "Pick or place line's ending point.")

    continuous_draw: BoolProperty(name="Continuous Draw", default=True)

    states = (
        state_from_args(
            l3d_state1_doc[0],
            description=l3d_state1_doc[1],
            pointer="p1",
            types=types_point_3d,
        ),
        state_from_args(
            l3d_state2_doc[0],
            description=l3d_state2_doc[1],
            pointer="p2",
            types=types_point_3d,
            interactive=True,
        ),
    )

    def main(self, context: Context):
        p1, p2 = self.get_point(context, 0), self.get_point(context, 1)

        self.target = context.scene.sketcher.entities.add_line_3d(p1, p2)
        if context.scene.sketcher.use_construction:
            self.target.construction = True
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
            if self.has_coincident():
                solve_system(context)


register, unregister = register_stateops_factory((View3D_OT_slvs_add_line3d,))
