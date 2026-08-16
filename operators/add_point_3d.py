"""Stateful point placement for native free-3D sketches (#607)."""

import logging

from bpy.props import FloatVectorProperty
from bpy.types import Context, Operator
from bpy.utils import register_classes_factory

from ..declarations import Operators
from ..model.native_3d import create_point_3d
from ..stateful_operator.state import state_from_args
from .base_sketch_3d import OperatorSketch3d

logger = logging.getLogger(__name__)


class View3D_OT_slvs_add_point3d(Operator, OperatorSketch3d):
    """Add a point to the active native 3D sketch."""

    bl_idname = Operators.AddPoint3D
    bl_label = "Add 3D Point"
    bl_options = {"REGISTER", "UNDO"}

    coordinates: FloatVectorProperty(
        name="Coordinates",
        size=3,
        subtype="XYZ",
        unit="LENGTH",
        precision=5,
    )

    states = (
        state_from_args(
            "Coordinates",
            description=(
                "Place on a view-aligned plane. X/Y/Z locks an axis; "
                "Shift+X/Y/Z locks YZ/XZ/XY; type XYZ values for precision."
            ),
            property="coordinates",
            interactive=True,
            axis_lock=True,
        ),
    )

    def main(self, context: Context):
        construction = context.scene.sketcher.use_construction
        fixed = bool(self.state_data.get("snapped_external", False))
        self.target = create_point_3d(
            self.sketch,
            self.coordinates,
            construction=construction,
            fixed=fixed,
        )
        return self.target is not None

    def fini(self, context: Context, succeede: bool):
        if hasattr(self, "target"):
            logger.debug("Add 3D point: %s", self.target)
        if succeede:
            self.sketch.geometry_solved = False


register, unregister = register_classes_factory((View3D_OT_slvs_add_point3d,))
