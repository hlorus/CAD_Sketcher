import logging

from bpy.types import Operator, Context
from bpy.props import FloatVectorProperty

from .. import global_data
from ..declarations import Operators
from ..stateful_operator.utilities.register import register_stateops_factory
from ..stateful_operator.state import state_from_args
from .base_3d import Operator3d

logger = logging.getLogger(__name__)


class View3D_OT_slvs_add_point3d(Operator, Operator3d):
    """Add a point in 3d space"""

    bl_idname = Operators.AddPoint3D
    bl_label = "Add Solvespace 3D Point"
    bl_options = {"REGISTER", "UNDO"}

    p3d_state1_doc = ("Location", "Set point's location.")

    location: FloatVectorProperty(name="Location", subtype="XYZ", precision=5)

    states = (
        state_from_args(
            p3d_state1_doc[0],
            description=p3d_state1_doc[1],
            property="location",
        ),
    )

    def main(self, context: Context):
        self.target = context.scene.sketcher.entities.add_point_3d(self.location)
        if context.scene.sketcher.use_construction:
            self.target.construction = True

        # Store hovered entity to use for auto-coincident since it doesn't get
        # stored for non-interactive tools
        hovered = global_data.hover
        if self._check_constrain(context, hovered):
            self.state_data["hovered"] = hovered

        self.add_coincident(context, self.target, self.state, self.state_data)
        return True

    def fini(self, context: Context, succeede: bool):
        if hasattr(self, "target"):
            logger.debug("Add: {}".format(self.target))


register, unregister = register_stateops_factory((View3D_OT_slvs_add_point3d,))
