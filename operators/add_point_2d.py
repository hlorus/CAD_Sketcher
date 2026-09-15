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
from .placement import placement_of

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

    @classmethod
    def poll(cls, context: Context):
        """Never let a stale 2D hotkey/operator path mutate a 3D sketch."""
        from ..model.sketch_ref import poll_active_2d_sketch

        return poll_active_2d_sketch(context)

    def main(self, context: Context):
        from ..model.curve_ref import curve_ref

        sketch = self.sketch
        construction = context.scene.sketcher.use_construction
        placement = placement_of(self.state_data)

        # Entity picking wins over geometry snapping. Add Point is a coordinate
        # state with no pick_element, so re-derive the hovered sketch entity each
        # call: a pickable entity under the cursor (a point, an already-projected
        # reference, or a constrainable curve) is preferred to projecting the mesh
        # behind it. Only when nothing is pickable do we live-project the snap.
        picked = selection.hover
        ref = curve_ref(sketch, picked) if picked else None
        if ref is not None and ref.valid:
            # A projected reference forces its link (bypasses Auto Constraints); a
            # plain pick respects the toggle. Anchored only if the target is fixed.
            placement.link_existing(
                picked,
                fixed=bool(getattr(ref, "fixed", False)),
                projected=self._is_projected_reference(picked),
            )
        else:
            placement.hovered = ""
            self._link_placement(context, placement)

        # A point snapped to external geometry is fixed to hold it there; one
        # pinned by a coincident constraint (sketch entity or projected ref) is
        # not, so the constraint drives it.
        fixed = placement.snapped and not placement.hovered

        self.target = PointRef.create(
            sketch, self.coordinates, construction=construction, fixed=fixed
        )

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
