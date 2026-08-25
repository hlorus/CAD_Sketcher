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
        from ..model.curve_ref import curve_ref

        sketch = self.sketch
        construction = context.scene.sketcher.use_construction
        state_data = self.state_data

        # Entity picking wins over geometry snapping. Add Point is a coordinate
        # state with no pick_element, so re-derive the hovered sketch entity each
        # call: a pickable entity under the cursor (a point, an already-projected
        # reference, or a constrainable curve) is preferred to projecting the mesh
        # behind it. Only when nothing is pickable do we live-project the snap.
        picked = selection.hover
        ref = curve_ref(sketch, picked) if picked else None
        if ref is not None and ref.valid:
            state_data["hovered"] = picked
            state_data["snap_link_kind"] = "COINCIDENT"
            # A projected reference forces its link (bypasses Auto Constraints); a
            # plain pick respects the toggle. Anchored only if the target is fixed.
            state_data["snap_projected"] = self._is_projected_reference(picked)
            state_data["snap_anchored"] = bool(getattr(ref, "fixed", False))
        else:
            state_data["hovered"] = ""
            self._maybe_link_projected_snap(context, state_data)

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
