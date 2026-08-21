import logging

from bpy.props import FloatVectorProperty
from bpy.types import Context, Operator

from ..curve_solver import solve_system
from ..declarations import Operators
from ..drawing import selection
from ..model.curve_ref import PointRef
from ..stateful_operator.state import state_from_args
from ..stateful_operator.utilities.register import register_stateops_factory
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
        state_data = self.state_data

        # Snapped onto external mesh geometry: live-project it and coincide so the
        # point tracks the source (same path the pointer tools take in
        # create_element). This is a plain coordinate state, so it never runs
        # create_element -- do the link here or Add Point would only ever snap
        # statically.
        self._maybe_link_projected_snap(context, state_data)

        # Fall back to an existing sketch entity under the cursor when the snap
        # did not live-project onto external geometry.
        if not state_data.get("hovered"):
            hovered = selection.hover
            if hovered and self._check_constrain(context, hovered):
                state_data["hovered"] = hovered

        # A point snapped to external geometry is fixed to hold it there; one
        # pinned by a coincident constraint (sketch entity or projected ref) is
        # not, so the constraint drives it.
        fixed = state_data.get("snapped", False) and not state_data.get("hovered")

        self.target = PointRef.create(
            sketch, self.coordinates, construction=construction, fixed=fixed
        )

        self.add_coincident(context, self.target, self.state, state_data)
        return True

    def fini(self, context: Context, succeede: bool):
        if hasattr(self, "target"):
            logger.debug("Add: {}".format(self.target))

        if succeede:
            if self.has_coincident():
                solve_system(context, sketch=self.sketch)
            self.sketch.geometry_solved = False


register, unregister = register_stateops_factory((View3D_OT_slvs_add_point2d,))
