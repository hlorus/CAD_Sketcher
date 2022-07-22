import logging

from bpy.types import Operator, Context

from .. import class_defines, functions
from ..declarations import Operators
from ..stateful_operator.utilities.register import register_stateops_factory
from ..stateful_operator.state import state_from_args
from .base_2d import Operator2d


logger = logging.getLogger(__name__)


from ..utilities.trimming import TrimSegment

class View3D_OT_slvs_split(Operator, Operator2d):
    """Split segment at mouse position and insert a point"""

    bl_idname = Operators.Split
    bl_label = "Split Segment"
    bl_options = {"REGISTER", "UNDO"}

    states = (
        state_from_args(
            "Segment",
            description="Segment to be split at mouse position",
            pointer="segment",
            types=class_defines.segment,
            pick_element="pick_element_coords",
            use_create=False,
        ),
    )

    def pick_element_coords(self, context, coords):
        data = self.state_data
        data["mouse_pos"] = coords #self.state_func(context, coords)
        return super().pick_element(context, coords)

    def main(self, context: Context):
        return True

    def fini(self, context: Context, succeede: bool):
        if not succeede:
            return False

        segment = self.segment
        if segment.is_closed():
            self.report({"WARNING"}, "Splitting not supported for closed entity types")
            return False

        mouse_pos = self._state_data[0].get("mouse_pos")
        if mouse_pos == None:
            return False

        # mouse_pos is a bit misleading, it's not (region_x, region_y) but the location on the workplane

        # Get position on segment
        origin, view_vector = functions.get_picking_origin_dir(context, mouse_pos)
        pos = self.segment.closest_picking_point(origin, view_vector)
        pos = (pos).to_2d() # @ sketch.wp.matrix_basis.inverted()


        trim = TrimSegment(segment, pos)
        trim.split(context)

        functions.refresh(context)


register, unregister = register_stateops_factory((View3D_OT_slvs_split,))
