import logging
import math

from bpy.props import FloatVectorProperty
from bpy.types import Context, Event, Operator
from mathutils import Vector

from ..curve_solver import solve_system
from ..declarations import Operators
from ..model.curve_ref import ArcRef, PointRef
from ..stateful_operator.state import state_from_args
from ..stateful_operator.utilities.register import register_stateops_factory
from ..utilities.geometry import arc_through_points, intersect_line_sphere_2d
from ..utilities.math import pol2cart
from ..utilities.view import get_blender_snap_info, get_pos_2d, get_wp_matrix
from .base_2d import Operator2d, ReplaceableOutputOp
from .constants import types_point_2d
from .placement import placement_of
from .utilities import ignore_hover

logger = logging.getLogger(__name__)


class View3D_OT_slvs_add_arc2d(Operator, ReplaceableOutputOp, Operator2d):
    """Add an arc to the active sketch"""

    bl_idname = Operators.AddArc2D
    bl_label = "Add Solvespace 2D Arc"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: Context):
        """An arc is planar geometry -- reject it in a free-3D sketch."""
        from ..model.sketch_ref import poll_active_2d_sketch

        return poll_active_2d_sketch(context)

    arc_state1_doc = ("Center", "Pick or place center point.")
    arc_state2_doc = ("Startpoint", "Pick or place starting point.")
    arc_state3_doc = ("Endpoint", "Pick or place ending point.")

    states = (
        state_from_args(
            arc_state1_doc[0],
            description=arc_state1_doc[1],
            pointer="ct",
            types=types_point_2d,
        ),
        state_from_args(
            arc_state2_doc[0],
            description=arc_state2_doc[1],
            pointer="p1",
            types=types_point_2d,
            allow_prefill=False,
        ),
        state_from_args(
            arc_state3_doc[0],
            description=arc_state3_doc[1],
            pointer="p2",
            types=types_point_2d,
            state_func="get_endpoint_pos",
            interactive=True,
        ),
    )

    def get_endpoint_pos(self, context: Context, coords):
        wp = self._get_wp()
        snap_data = get_blender_snap_info(context, coords)
        self._snap = snap_data
        # Anchor the endpoint if it landed on external geometry (see base_2d).
        placement_of(self.state_data).snapped = snap_data is not None
        mouse_pos = get_pos_2d(context, wp, coords, respect_snapping=True)
        if mouse_pos is None:
            return None

        ct = self.get_point(context, 0).co
        p1 = self.get_point(context, 1).co
        radius = (p1 - ct).length

        # Snap the endpoint onto the arc's circle where a nearby edge crosses it,
        # or to a vertex lying on the circle (visual only, no constraint).
        if snap_data and snap_data["type"] in {"EDGE", "EDGE_MIDPOINT"}:
            world_edge = snap_data.get("world_edge")
            if world_edge:
                mat_inv = get_wp_matrix(wp).inverted()
                e0, e1 = [Vector((mat_inv @ point)[:-1]) for point in world_edge]
                intersections = intersect_line_sphere_2d(e0, e1, ct, radius)
                if intersections:
                    mouse_pos = Vector(
                        min(
                            intersections,
                            key=lambda point: (Vector(point) - mouse_pos).length,
                        )
                    )
        elif snap_data and snap_data["type"] in {"VERTEX", "FACE_MIDPOINT"}:
            vertex_pos = Vector(
                (get_wp_matrix(wp).inverted() @ snap_data["world_point"])[:-1]
            )
            if abs((vertex_pos - ct).length - radius) < 1e-5:
                mouse_pos = vertex_pos

        x, y = Vector(mouse_pos) - ct
        mouse_angle = math.atan2(y, x)

        # Track cumulative angular displacement from start
        if not hasattr(self, "_prev_mouse_angle"):
            self._prev_mouse_angle = mouse_angle
            self._cumulative_angle = 0.0

        # Compute delta with wrap handling
        delta = mouse_angle - self._prev_mouse_angle
        if delta > math.pi:
            delta -= 2 * math.pi
        elif delta < -math.pi:
            delta += 2 * math.pi
        self._cumulative_angle += delta
        self._prev_mouse_angle = mouse_angle

        # Direction: negative cumulative = clockwise = invert
        self._arc_invert = self._cumulative_angle < 0

        # Snap endpoint to circle
        pos = pol2cart(radius, mouse_angle) + ct
        return pos

    def solve_state(self, context: Context, _event: Event):
        solve_system(context, sketch=self.sketch)
        return True

    preview_in_place = True

    def preview_structure(self, context: Context):
        """Also rebuild when the sweep direction flips (start and end swap)."""
        structure = super().preview_structure(context)
        if structure is None:
            return None
        return structure, getattr(self, "_arc_invert", False)

    def update_preview(self, context: Context) -> bool:
        """Drag the arc's endpoint instead of recreating the arc."""
        target = getattr(self, "target", None)
        if target is None or not target.valid:
            return False
        return self.update_preview_point(context)

    def main(self, context):
        ct, p1, p2 = (
            self.get_point(context, 0),
            self.get_point(context, 1),
            self.get_point(context, 2),
        )
        sketch = self.sketch
        construction = context.scene.sketcher.use_construction

        invert = getattr(self, "_arc_invert", False)
        start, end = (p2, p1) if invert else (p1, p2)

        self.target = ArcRef.create(sketch, ct, start, end, construction=construction)
        ignore_hover(self.target.curve_id)
        return True

    def fini(self, context: Context, succeede: bool):
        if hasattr(self, "target"):
            logger.debug("Add: {}".format(self.target))
            self.solve_state(context, self.sketch)


class View3D_OT_slvs_add_arc3pt2d(Operator, Operator2d):
    """Add an arc through a start point, an end point and a point on the arc"""

    bl_idname = Operators.AddArc3Point2D
    bl_label = "Add 3-Point Arc"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: Context):
        """An arc is planar geometry -- reject it in a free-3D sketch."""
        from ..model.sketch_ref import poll_active_2d_sketch

        return poll_active_2d_sketch(context)

    # Where the arc passes through. Only shapes the arc, nothing is placed there.
    through: FloatVectorProperty(
        name="Through",
        description="A point the arc passes through",
        size=2,
        subtype="XYZ",
        unit="LENGTH",
        precision=5,
    )

    states = (
        state_from_args(
            "Startpoint",
            description="Pick or place starting point.",
            pointer="p1",
            types=types_point_2d,
        ),
        state_from_args(
            "Endpoint",
            description="Pick or place ending point.",
            pointer="p2",
            types=types_point_2d,
            # Follow the cursor, so the assumed arc is live while it is placed.
            interactive=True,
        ),
        state_from_args(
            "Through",
            description="Move to shape the arc, click to confirm.",
            property="through",
            state_func="get_through_pos",
            interactive=True,
            allow_prefill=False,
        ),
    )

    def get_through_pos(self, context: Context, coords):
        """The workplane position under the mouse, if it bends the arc."""
        wp = self._get_wp()
        self._snap = get_blender_snap_info(context, coords)
        pos = get_pos_2d(context, wp, coords, respect_snapping=True)
        if pos is None:
            return None
        p1 = self.get_point(context, 0).co
        p2 = self.get_point(context, 1).co
        # On the chord no arc exists: keep the last valid shape.
        if arc_through_points(p1, p2, pos) is None:
            return None
        return Vector(pos[:2])

    # Sagitta as a fraction of the chord for the arc shown before it is shaped:
    # (1 - cos45) / (2 sin45), a 90 degree arc.
    _ASSUMED_BULGE = 0.2071

    def _assumed_through(self, p1, p2):
        """Where the arc passes through until the user shapes it.

        The endpoint is then placed against a real arc rather than against two
        loose points. A 90 degree arc bulging to the left of start -> end reads
        as an arc at a glance and is short to bend either way afterwards.
        """
        chord = Vector(p2) - Vector(p1)
        if not chord.length:
            return None
        return (Vector(p1) + Vector(p2)) / 2 + Vector(
            (-chord.y, chord.x)
        ) * self._ASSUMED_BULGE

    def _points(self, context: Context):
        """The start and end points, or None while the endpoint is not placed."""
        p1, p2 = self.get_point(context, 0), self.get_point(context, 1)
        if p1 is None or p2 is None or not p1.valid or not p2.valid:
            return None
        return p1, p2

    def _through_value(self, context: Context):
        """The through point in use: the assumed one until the state is reached."""
        if self.state_index >= 2:
            return Vector(self.through)
        points = self._points(context)
        if points is None:
            return None
        return self._assumed_through(points[0].co, points[1].co)

    def set_state(self, context: Context, index: int):
        if index == 1:
            # A preview runs only once every state has a value (check_props), so
            # mark the shaping state's property as set while the endpoint is
            # still moving. _through_value ignores it until that state is active.
            try:
                self.through = tuple(self.through)
            except (AttributeError, TypeError):
                pass  # a non-registered twin (tests) has no RNA props
        elif index == 2:
            # Take over the arc already on screen instead of jumping to the
            # property's stale value until the first move shapes it.
            assumed = self._through_value(context)
            if assumed is not None:
                try:
                    self.through = assumed
                except (AttributeError, TypeError):
                    pass
        super().set_state(context, index)

    def _arc_geometry(self, context: Context):
        """``(start, end, center, reversed)`` of the arc, or None while undefined."""
        points = self._points(context)
        through = self._through_value(context)
        if points is None or through is None:
            return None
        p1, p2 = points
        result = arc_through_points(p1.co, p2.co, through)
        if result is None:
            return None
        center, reverse = result
        start, end = (p2, p1) if reverse else (p1, p2)
        return start, end, center, reverse

    def solve_state(self, context: Context, _event: Event):
        solve_system(context, sketch=self.sketch)
        return True

    preview_in_place = True

    def preview_structure(self, context: Context):
        """Also rebuild when the arc flips to the other side of its chord."""
        structure = super().preview_structure(context)
        if structure is None:
            return None
        geometry = self._arc_geometry(context)
        if geometry is None:
            return None
        return structure, geometry[3]

    def update_preview(self, context: Context) -> bool:
        """Move the arc's center instead of recreating the arc."""
        target = getattr(self, "target", None)
        center = getattr(self, "_center", None)
        if target is None or not target.valid or center is None or not center.valid:
            return False
        # While the endpoint is still being placed it moves with the cursor too.
        if self.state_index < 2 and not self.update_preview_point(context):
            return False
        geometry = self._arc_geometry(context)
        if geometry is None:
            return False
        center.co = geometry[2]
        return True

    def main(self, context: Context):
        geometry = self._arc_geometry(context)
        if geometry is None:
            return False
        start, end, co, _reverse = geometry
        sketch = self.sketch
        construction = context.scene.sketcher.use_construction

        ct = PointRef.create(sketch, co, construction=construction)
        self.target = ArcRef.create(sketch, ct, start, end, construction=construction)
        self._center = ct
        ignore_hover(ct.curve_id)
        ignore_hover(self.target.curve_id)
        return True

    def fini(self, context: Context, succeede: bool):
        if hasattr(self, "target"):
            logger.debug("Add: {}".format(self.target))
            self.solve_state(context, self.sketch)


register, unregister = register_stateops_factory(
    (View3D_OT_slvs_add_arc2d, View3D_OT_slvs_add_arc3pt2d)
)
