import logging

from bpy.types import Operator, Context

from ..model.categories import SEGMENT
from ..declarations import Operators
from ..stateful_operator.utilities.register import register_stateops_factory
from ..stateful_operator.state import state_from_args
from ..utilities.trimming import TrimSegment
from .base_2d import Operator2d
from ..utilities.view import refresh, get_pos_2d

logger = logging.getLogger(__name__)


class View3D_OT_slvs_trim(Operator, Operator2d):
    """Trim segment to its closest intersections"""

    bl_idname = Operators.Trim
    bl_label = "Trim Segment"
    bl_options = {"REGISTER", "UNDO"}

    trim_state1_doc = ("Segment", "Segment to trim.")

    states = (
        state_from_args(
            trim_state1_doc[0],
            description=trim_state1_doc[1],
            pointer="segment",
            types=SEGMENT,
            pick_element="pick_element_coords",
            use_create=False,
            # interactive=True
        ),
    )

    # TODO: Disable execution based on selection
    # NOTE: That does not work if run with select -> action
    def pick_element_coords(self, context, coords):
        data = self.state_data
        data["mouse_pos"] = get_pos_2d(context, self.sketch.wp, coords)
        return super().pick_element(context, coords)

    def main(self, context: Context):
        return True

    def fini(self, context: Context, succeede: bool):
        if not succeede:
            return False

        sketch = context.scene.sketcher.active_sketch
        segment = self.segment

        mouse_pos = self._state_data[0].get("mouse_pos")
        if mouse_pos is None:
            return False

        trim = TrimSegment(segment, mouse_pos)

        # Find intersections
        for e in sketch.sketch_entities(context):
            if not e.is_segment():
                continue
            if e == segment:
                continue

            for co in segment.intersect(e):
                # print("intersect", co)
                trim.add(e, co)

        # Find points that are connected to the segment through a coincident constraint
        for c in (
            *context.scene.sketcher.constraints.coincident,
            *context.scene.sketcher.constraints.midpoint,
        ):
            ents = c.entities()
            if segment not in ents:
                continue
            p = ents[0]
            trim.add(c, p.co)

        # TODO: Get rid of the coincident constraint as it will be a shared connection point

        if not trim.check():
            return

        trim.replace(context)
        refresh(context)


register, unregister = register_stateops_factory((View3D_OT_slvs_trim,))
