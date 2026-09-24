import logging
import math

from bpy.props import BoolProperty, FloatVectorProperty
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
from .placement import ChainDraw, placement_of
from .utilities import ignore_hover

logger = logging.getLogger(__name__)


class ArcJoints:
    """Shared by both arc tools: the tangencies the arc's ends would pick up.

    Part of the preview structure, so the constraint is added while the arc is
    still being placed rather than only once it is confirmed.
    """

    def arc_joint_key(self, context: Context, center, start, end):
        joints = []
        center = getattr(center, "co", center)
        if center is None:
            return ()
        for point in (start, end):
            if point is None or not getattr(point, "valid", False):
                continue
            radial = point.co - center
            if radial.length < 1e-9:
                continue
            # An arc runs square to its radius, which is all a joint needs.
            joints.append((point.curve_id, Vector((-radial.y, radial.x)), True))
        return self.joint_relation_key(context, joints)


class View3D_OT_slvs_add_arc2d(Operator, ArcJoints, ReplaceableOutputOp, Operator2d):
    """Add an arc to the active sketch"""

    bl_idname = Operators.AddArc2D
    bl_label = "Add Center Arc"
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
        """Also rebuild when the sweep flips or an inferred tangency changes."""
        structure = super().preview_structure(context)
        if structure is None:
            return None
        ct, p1, p2 = (self.get_point(context, i) for i in range(3))
        return (
            structure,
            getattr(self, "_arc_invert", False),
            self.arc_joint_key(context, ct, p1, p2),
        )

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
        # Tangent where it carries on from a segment it starts at or ends on.
        self.add_joint_constraints(context, self.target)
        ignore_hover(self.target.curve_id)
        return True

    def fini(self, context: Context, succeede: bool):
        if hasattr(self, "target"):
            logger.debug("Add: {}".format(self.target))
            self.solve_state(context, self.sketch)


class View3D_OT_slvs_add_arc3pt2d(Operator, ChainDraw, ArcJoints, Operator2d):
    """Add an arc from a start point to an end point, curving the way you set off"""

    bl_idname = Operators.AddArc3Point2D
    bl_label = "Add Endpoint Arc"
    bl_options = {"REGISTER", "UNDO"}

    continuous_draw: BoolProperty(name="Continuous Draw", default=True)

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
            state_func="get_endpoint_pos",
            # Follow the cursor, so the arc is live while the endpoint is placed.
            interactive=True,
        ),
    )

    # Sagitta as a fraction of the chord, for the arc shown before the cursor has
    # set off in a direction: (1 - cos45) / (2 sin45), a 90 degree arc.
    _ASSUMED_BULGE = 0.2071
    # How far the cursor has to leave the start point, as a fraction of the view
    # distance, before its direction is taken as the arc's tangent there.
    _TANGENT_COMMIT = 0.02
    # Direction the cursor set off in, the arc's tangent at the start point.
    _start_dir = None

    def _reset_op(self):
        super()._reset_op()
        # The next segment of a chain aims anew: its own direction decides which
        # way it curves, not the one the segment before set off in.
        self._start_dir = None

    def get_endpoint_pos(self, context: Context, coords):
        """Place the endpoint and note the direction the cursor set off in.

        That direction is the arc's tangent at the start point, so while the
        endpoint is placed the radius follows the cursor and the arc curves the
        other way once the cursor crosses the tangent. Coming back to the start
        point drops it again, to aim anew.
        """
        pos = self.state_func(context, coords)
        p1 = self.get_point(context, 0)
        if pos is None or p1 is None or not p1.valid:
            return pos
        delta = Vector(pos[:2]) - p1.co
        region_3d = getattr(context, "region_data", None)
        threshold = getattr(region_3d, "view_distance", 1.0) * self._TANGENT_COMMIT
        if delta.length > threshold:
            if self._start_dir is None:
                self._start_dir = delta.normalized()
        else:
            self._start_dir = None
        return pos

    def _assumed_through(self, p1, p2):
        """Where the arc passes through until the user shapes it.

        The endpoint is then placed against a real arc rather than against two
        loose points. Once the cursor has set off in a direction, that direction
        is the tangent at the start point and the arc follows the endpoint from
        there; until then a 90 degree arc stands in.
        """
        p1, p2 = Vector(p1), Vector(p2)
        chord = p2 - p1
        if not chord.length:
            return None
        tangent = self._start_dir
        if tangent is None:
            return (p1 + p2) / 2 + Vector((-chord.y, chord.x)) * self._ASSUMED_BULGE

        # The circle through p1 tangent to `tangent` and through p2: its center
        # sits on the tangent's normal at p1, at the signed radius below.
        normal = Vector((-tangent.y, tangent.x))
        denominator = 2 * chord.dot(normal)
        if abs(denominator) < 1e-9:
            return None  # the endpoint is on the tangent: a straight line
        radius = chord.length_squared / denominator
        center = p1 + normal * radius

        # A positive radius puts the center left of the tangent, so travel along
        # the tangent runs counter-clockwise. Take the point halfway along that
        # sweep, which also describes an arc of more than half a turn.
        start_angle = math.atan2(*(p1 - center).yx)
        end_angle = math.atan2(*(p2 - center).yx)
        direction = 1.0 if radius > 0 else -1.0
        sweep = (end_angle - start_angle) * direction % (2 * math.pi)
        half = start_angle + direction * sweep / 2
        return center + Vector((math.cos(half), math.sin(half))) * abs(radius)

    def _points(self, context: Context):
        """The start and end points, or None while the endpoint is not placed."""
        p1, p2 = self.get_point(context, 0), self.get_point(context, 1)
        if p1 is None or p2 is None or not p1.valid or not p2.valid:
            return None
        return p1, p2

    # True while the operator is rebuilt from its properties (a redo-panel
    # change or a re-pick) rather than drawn: the shape then comes from the
    # stored through point instead of being worked out from the cursor again.
    _replaying = False

    def _reapply(self, context: Context):
        self._replaying = True
        try:
            return super()._reapply(context)
        finally:
            self._replaying = False

    def _through_value(self, context: Context):
        """The point the arc passes through: worked out live, or the stored one.

        While drawing, the shape follows from the start point, the direction the
        cursor set off in and the endpoint, so there is nothing left to click.
        The result is kept in ``through`` (see _arc_geometry), which is what a
        redo-panel change or a re-pick then rebuilds from -- and what can be
        typed in there to reshape the arc afterwards.
        """
        if self._replaying:
            return Vector(self.through)
        points = self._points(context)
        if points is None:
            return None
        return self._assumed_through(points[0].co, points[1].co)

    def _arc_geometry(self, context: Context):
        """``(start, end, center, reversed)`` of the arc, or None while undefined."""
        points = self._points(context)
        through = self._through_value(context)
        if points is None or through is None:
            return None
        if not self._replaying:
            # Keep the shape for a later replay (see _through_value).
            try:
                self.through = through
            except (AttributeError, TypeError):
                pass  # a non-registered twin (tests) has no RNA props
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
        """Also rebuild when the arc flips over, or an inferred tangency changes."""
        structure = super().preview_structure(context)
        if structure is None:
            return None
        geometry = self._arc_geometry(context)
        if geometry is None:
            return None
        start, end, center, reverse = geometry
        return structure, reverse, self.arc_joint_key(context, center, start, end)

    def update_preview(self, context: Context) -> bool:
        """Move the arc's center instead of recreating the arc."""
        target = getattr(self, "target", None)
        center = getattr(self, "_center", None)
        if target is None or not target.valid or center is None or not center.valid:
            return False
        # The endpoint moves with the cursor while it is being placed.
        if not self.update_preview_point(context):
            return False
        geometry = self._arc_geometry(context)
        if geometry is None:
            return False
        # Which way round the arc runs is decided when it is created, and moving
        # the endpoint can turn it the other way: the preview structure is read
        # before that move, so it cannot see the flip coming. Ask for a rebuild.
        if geometry[3] != self._built_reversed:
            return False
        center.co = geometry[2]
        return True

    # Which way round the arc the preview was built with (see update_preview).
    _built_reversed = None

    def main(self, context: Context):
        geometry = self._arc_geometry(context)
        if geometry is None:
            return False
        start, end, co, reverse = geometry
        self._built_reversed = reverse
        sketch = self.sketch
        construction = context.scene.sketcher.use_construction

        ct = PointRef.create(sketch, co, construction=construction)
        self.target = ArcRef.create(sketch, ct, start, end, construction=construction)
        self._center = ct
        # Tangent where it carries on from a segment it starts at or ends on.
        self.add_joint_constraints(context, self.target)
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
