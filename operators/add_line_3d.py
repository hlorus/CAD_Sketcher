"""Stateful line placement for native free-3D sketches (#607)."""

import logging

from bpy.props import FloatVectorProperty
from bpy.types import Context, Operator

from ..declarations import Operators
from ..model.curve_ref import PointRef
from ..model.native_3d import create_line_3d
from ..stateful_operator.state import state_from_args
from ..stateful_operator.utilities.register import register_stateops_factory
from .base_sketch_3d import OperatorSketch3d

logger = logging.getLogger(__name__)


class View3D_OT_slvs_add_line3d(Operator, OperatorSketch3d):
    """Add a line to the active native 3D sketch."""

    bl_idname = Operators.AddLine3D
    bl_label = "Add 3D Line"
    bl_options = {"REGISTER", "UNDO"}

    p1_coordinates: FloatVectorProperty(
        name="Start Coordinates",
        size=3,
        subtype="XYZ",
        unit="LENGTH",
        precision=5,
    )
    p2_coordinates: FloatVectorProperty(
        name="End Coordinates",
        size=3,
        subtype="XYZ",
        unit="LENGTH",
        precision=5,
    )

    states = (
        state_from_args(
            "Startpoint",
            description=(
                "Pick an existing 3D sketch point or place on the view-aligned "
                "plane through the sketch origin."
            ),
            pointer="p1",
            types=(PointRef,),
            property="p1_coordinates",
            interactive=True,
            axis_lock=True,
        ),
        state_from_args(
            "Endpoint",
            description=(
                "Pick/place relative to the start point. X/Y/Z locks an axis; "
                "Shift+X/Y/Z locks YZ/XZ/XY; numeric XYZ is supported."
            ),
            pointer="p2",
            types=(PointRef,),
            property="p2_coordinates",
            interactive=True,
            axis_lock=True,
        ),
    )

    def main(self, context: Context):
        p1 = self.get_point(context, 0)
        p2 = self.get_point(context, 1)
        if not p1 or not p2:
            return False

        construction = context.scene.sketcher.use_construction
        self.target = create_line_3d(
            self.sketch,
            p1,
            p2,
            construction=construction,
        )
        return self.target is not None

    def fini(self, context: Context, succeede: bool):
        if hasattr(self, "target"):
            logger.debug("Add 3D line: %s", self.target)
        if succeede:
            self.sketch.geometry_solved = False


register, unregister = register_stateops_factory((View3D_OT_slvs_add_line3d,))
