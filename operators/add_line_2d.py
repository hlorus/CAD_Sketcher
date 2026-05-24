import logging

from bpy.types import Operator, Context, Event
from bpy.props import BoolProperty
from mathutils import Vector

from ..utilities.constants import HALF_TURN, QUARTER_TURN

from ..declarations import Operators
from ..stateful_operator.utilities.register import register_stateops_factory
from ..stateful_operator.state import state_from_args
from ..solver import solve_system
from .base_2d import Operator2d
from .constants import types_point_2d
from .utilities import ignore_hover

logger = logging.getLogger(__name__)


class View3D_OT_slvs_add_line2d(Operator, Operator2d):
    """Add a line to the active sketch"""

    bl_idname = Operators.AddLine2D
    bl_label = "Add Solvespace 2D Line"
    bl_options = {"REGISTER", "UNDO"}

    l2d_state1_doc = ("Startpoint", "Pick or place line's starting Point.")
    l2d_state2_doc = ("Endpoint", "Pick or place line's ending Point.")

    continuous_draw: BoolProperty(name="Continuous Draw", default=True)

    states = (
        state_from_args(
            l2d_state1_doc[0],
            description=l2d_state1_doc[1],
            pointer="p1",
            types=types_point_2d,
        ),
        state_from_args(
            l2d_state2_doc[0],
            description=l2d_state2_doc[1],
            pointer="p2",
            types=types_point_2d,
            interactive=True,
        ),
    )

    def init(self, context: Context, event: Event):
        result = super().init(context, event)
        self._polyline_segments = []
        self._in_continuous_draw = False
        self._polyline_index = -1
        return result

    def main(self, context: Context):
        wp = self.sketch.wp
        p1, p2 = self.get_point(context, 0), self.get_point(context, 1)

        self.target = context.scene.sketcher.entities.add_line_2d(p1, p2, self.sketch)
        if context.scene.sketcher.use_construction:
            self.target.construction = True

        # auto vertical/horizontal constraint
        self.has_alignment = False
        constraints = context.scene.sketcher.constraints
        vec_dir = self.target.direction_vec()
        if vec_dir.length:
            angle = vec_dir.angle(Vector((1, 0)))

            threshold = 0.1
            if angle < threshold or angle > HALF_TURN - threshold:
                constraints.add_horizontal(self.target, sketch=self.sketch)
                self.has_alignment = True
            elif (QUARTER_TURN - threshold) < angle < (QUARTER_TURN + threshold):
                constraints.add_vertical(self.target, sketch=self.sketch)
                self.has_alignment = True

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

    def do_continuous_draw(self, context):
        if hasattr(self, "target") and self.target is not None:
            self._polyline_segments.append(self.target.slvs_index)
        self._in_continuous_draw = True
        super().do_continuous_draw(context)
        self._in_continuous_draw = False

    def _apply_polyline(self, context, segments):
        """Create or update the running polyline with the given segment indices.

        If the polyline spans the two endpoints of the sketch's linked geometry
        line (linked-sketch case), the linked line is appended to close the
        loop and the source line's GUID is inherited by the polyline.
        """
        if len(segments) < 2:
            return
        sse = context.scene.sketcher.entities
        first_seg = sse.get(segments[0])
        last_seg = sse.get(segments[-1])
        is_closed = (
            first_seg is not None
            and last_seg is not None
            and first_seg.p1.slvs_index == last_seg.p2.slvs_index
        )

        # --- Linked-geometry auto-close ---
        # When this sketch was created by "add linked sketch" it carries a
        # fixed linked line.  If the user's chain touches both endpoints of
        # that linked line we append it to the segment list and mark the
        # polyline as closed.  The polyline also inherits the GUID of the
        # original source line so downstream tools (e.g. IFC export) can link
        # the elevation loop back to its originating element.
        inherited_guid = ""
        linked_line_i = getattr(self.sketch, "source_linked_line_i", -1)
        if linked_line_i != -1 and first_seg is not None and last_seg is not None:
            linked_line = sse.get(linked_line_i)
            if linked_line is not None:
                ext_pts = {linked_line.p1.slvs_index, linked_line.p2.slvs_index}
                user_pts = {first_seg.p1.slvs_index, last_seg.p2.slvs_index}
                if user_pts == ext_pts and linked_line_i not in segments:
                    segments = list(segments) + [linked_line_i]
                    is_closed = True
                    src_line_i = getattr(self.sketch, "source_line_i", -1)
                    if src_line_i != -1:
                        src_line = sse.get(src_line_i)
                        if src_line is not None:
                            inherited_guid = src_line.guid

        if self._polyline_index == -1:
            poly = sse.add_polyline(segments, is_closed, self.sketch)
            self._polyline_index = poly.slvs_index
        else:
            poly = sse.get(self._polyline_index)
            if poly is not None:
                count = min(len(segments), 32)
                for i in range(count):
                    poly.segment_indices[i] = segments[i]
                poly.segment_count = count
                poly.closed = is_closed

        if inherited_guid:
            poly = sse.get(self._polyline_index)
            if poly is not None:
                poly.guid = inherited_guid

    def fini(self, context: Context, succeede: bool):
        if hasattr(self, "target"):
            logger.debug("Add: {}".format(self.target))

        if succeede:
            if self.has_coincident() or self.has_alignment:
                solve_system(context, sketch=self.sketch)
            self.sketch.geometry_solved = False

        if not context.scene.sketcher.auto_create_polylines:
            return

        if self._in_continuous_draw:
            # Intermediate step: create/update polyline with all committed segments.
            # This runs before undo_push so the polyline is included in the checkpoint.
            if succeede:
                self._apply_polyline(context, self._polyline_segments[:])
        else:
            # Final step (right-click/enter to confirm last segment)
            if succeede and hasattr(self, "target") and self.target is not None:
                self._apply_polyline(
                    context, self._polyline_segments + [self.target.slvs_index]
                )
            # On cancel: polyline already holds all committed segments — nothing to do.


register, unregister = register_stateops_factory((View3D_OT_slvs_add_line2d,))
