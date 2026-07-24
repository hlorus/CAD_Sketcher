import logging

from bpy.types import Operator, Context
from bpy.props import FloatVectorProperty

from .. import global_data
from ..declarations import Operators
from ..stateful_operator.utilities.register import register_stateops_factory
from ..stateful_operator.state import state_from_args
from ..curve_solver import solve_system
from ..model.curve_ref import PointRef
from .base_2d import Operator2d

logger = logging.getLogger(__name__)


class View3D_OT_slvs_add_point2d(Operator, Operator2d):
    """Add a point to the active sketch"""

    bl_idname = Operators.AddPoint2D
    bl_label = "Add Solvespace 2D Point"
    bl_options = {"REGISTER", "UNDO"}

    p2d_state1_doc = ("Coordinates", "Set point's coordinates on the sketch.")

    coordinates: FloatVectorProperty(name="Coordinates", size=2, precision=5)

    states = (
        state_from_args(
            p2d_state1_doc[0],
            description=p2d_state1_doc[1],
            property="coordinates",
        ),
    )

    def main(self, context: Context):
        sketch = self.sketch
        construction = context.scene.sketcher.use_construction

        self.target = PointRef.create(sketch, self.coordinates, construction=construction)

        # Store hovered curve_id for auto-coincident
        hovered = global_data.hover
        if hovered and self._check_constrain(context, hovered):
            self.state_data["hovered"] = hovered

        self.add_coincident(context, self.target, self.state, self.state_data)
        return True

    def fini(self, context: Context, succeede: bool):
        if hasattr(self, "target"):
            logger.debug("Add: {}".format(self.target))

        if succeede:
            if self.has_coincident():
                solve_system(context, sketch=self.sketch)
            self.sketch.geometry_solved = False


register, unregister = register_stateops_factory((View3D_OT_slvs_add_point2d,))
