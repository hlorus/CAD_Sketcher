import logging
from typing import Optional, Sequence, Tuple

from bpy.props import FloatProperty
from bpy.types import Context, Operator
from mathutils import Vector

from ..curve_solver import solve_system
from ..declarations import Operators
from ..model.curve_ref import LineRef, PointRef
from ..stateful_operator.state import state_from_args
from ..stateful_operator.utilities.register import register_stateops_factory
from .base_2d import Operator2d, ReplaceableOutputOp
from .constants import types_point_2d
from .utilities import ignore_hover

logger = logging.getLogger(__name__)


def rectangle_corners(
    start: Sequence[float], end: Sequence[float]
) -> Tuple[tuple, tuple]:
    """The derived corners of an axis-aligned rectangle spanned by two points.

    Returns ``(right_bottom, left_top)`` for a rectangle from ``start`` (left
    bottom) to ``end`` (right top), in the same order the tool links its lines:
    start, right_bottom, end, left_top.
    """
    return (end[0], start[1]), (start[0], end[1])


def centered_corners(center: Sequence[float], corner: Sequence[float]) -> Tuple[tuple]:
    """The four corners of an axis-aligned rectangle centred on ``center``.

    In link order from the picked corner: the corner, its mirror in x, the
    opposite corner, its mirror in y.
    """
    x, y = float(corner[0]), float(corner[1])
    mirror_x, mirror_y = 2 * float(center[0]) - x, 2 * float(center[1]) - y
    return ((x, y), (mirror_x, y), (mirror_x, mirror_y), (x, mirror_y))


def edge_corners(
    start: Sequence[float], end: Sequence[float], width: float
) -> Optional[Tuple[tuple]]:
    """The four corners of a rectangle built on the edge ``start`` -> ``end``.

    ``width`` is the signed offset of the opposite edge, so the rectangle can be
    pulled out to either side of that edge. None when the edge has no length and
    the rectangle is undefined.
    """
    start, end = Vector(start[:2]), Vector(end[:2])
    edge = end - start
    if not edge.length:
        return None
    offset = Vector((-edge.y, edge.x)).normalized() * width
    return (tuple(start), tuple(end), tuple(end + offset), tuple(start + offset))


def signed_offset(start: Sequence[float], end: Sequence[float], point) -> float:
    """How far ``point`` lies off the line ``start`` -> ``end``, with its side."""
    start, end = Vector(start[:2]), Vector(end[:2])
    edge = end - start
    if not edge.length:
        return 0.0
    normal = Vector((-edge.y, edge.x)).normalized()
    return (Vector(point[:2]) - start).dot(normal)


class View3D_OT_slvs_add_rectangle(Operator, ReplaceableOutputOp, Operator2d):
    """Add a rectangle to the active sketch"""

    bl_idname = Operators.AddRectangle
    bl_label = "Add Corner Rectangle"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: Context):
        """A rectangle is planar geometry -- reject it in a free-3D sketch."""
        from ..model.sketch_ref import poll_active_2d_sketch

        return poll_active_2d_sketch(context)

    rect_state1_doc = ("Startpoint", "Pick or place starting point.")
    rect_state2_doc = ("Endpoint", "Pick or place ending point.")

    states = (
        state_from_args(
            rect_state1_doc[0],
            description=rect_state1_doc[1],
            pointer="p1",
            types=types_point_2d,
        ),
        state_from_args(
            rect_state2_doc[0],
            description=rect_state2_doc[1],
            pointer="p2",
            types=types_point_2d,
            interactive=True,
            create_element="create_point",
        ),
    )

    preview_in_place = True

    def update_preview(self, context: Context) -> bool:
        """Drag the rectangle's corners instead of recreating it."""
        corners = getattr(self, "_derived_corners", None)
        if not corners or not all(ref.valid for ref in corners):
            return False
        if not self.update_preview_point(context):
            return False
        p_lb, p_rt = self.get_point(context, 0), self.get_point(context, 1)
        for ref, co in zip(corners, rectangle_corners(p_lb.co, p_rt.co)):
            ref.co = co
        return True

    def main(self, context: Context):
        sketch = self.sketch
        construction = context.scene.sketcher.use_construction

        p_lb, p_rt = self.get_point(context, 0), self.get_point(context, 1)

        # Create the two extra corner points
        co_rb, co_lt = rectangle_corners(p_lb.co, p_rt.co)
        p_rb = PointRef.create(sketch, co_rb, construction=construction)
        p_lt = PointRef.create(sketch, co_lt, construction=construction)

        if construction:
            p_lb.construction = True
            p_rt.construction = True

        # Create 4 lines
        points = (p_lb, p_rb, p_rt, p_lt)
        lines = []
        for i, start in enumerate(points):
            end = points[(i + 1) % 4]
            line = LineRef.create(sketch, start, end, construction=construction)
            lines.append(line)

        self.lines = lines
        self._derived_corners = (p_rb, p_lt)

        for ref in (*points, *lines):
            ignore_hover(ref.curve_id)
        return True

    def fini(self, context: Context, succeede: bool):
        if succeede and hasattr(self, "lines") and self.lines:
            sc = self.sketch.constraints
            # Auto axis-alignment constraints (inferred) respect the toggle and
            # Shift bypass; the numeric distance constraints below are explicit.
            if self.use_auto_constraints(context):
                for i, line_ref in enumerate(self.lines):
                    func = sc.add_horizontal if (i % 2) == 0 else sc.add_vertical
                    self.add_auto_constraint(
                        context, func, curve_id_1=line_ref.curve_id
                    )

            data = self._state_data.get(1)
            if data.get("is_numeric_edit", False):
                input = data.get("numeric_input")

                startpoint = getattr(self, self.get_states()[0].pointer)
                sp_cid = startpoint.curve_id if hasattr(startpoint, "curve_id") else ""
                for val, line_ref in zip(input, (self.lines[1], self.lines[2])):
                    if val is None:
                        continue
                    sc.add_distance(
                        init=True,
                        curve_id_1=sp_cid,
                        curve_id_2=line_ref.curve_id,
                    )

        if succeede:
            if self.has_coincident():
                solve_system(context, sketch=self.sketch)
            self.sketch.geometry_solved = False

    def create_point(self, context: Context, values, state, state_data):
        value = values[0]

        if state_data.get("is_numeric_edit", False):
            data = self._state_data.get(1)
            input = data.get("numeric_input")
            # use relative coordinates
            orig = getattr(self, self.get_states()[0].pointer).co

            for i, val in enumerate(input):
                if val is None:
                    continue
                value[i] = orig[i] + val

        # The shared creation path, so the corner keeps its id across a re-run
        # (main applies construction to it, see above).
        return self.create_element(context, [value], state, state_data)


class _RectangleVariant(ReplaceableOutputOp, Operator2d):
    """Shared build for the rectangle variants: four corners, four lines.

    A subclass says where the corners are (``_corner_cos``), which of them the
    user placed (``_placed_corners``) and what holds the shape together
    (``_auto_constrain``).
    """

    preview_in_place = True
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: Context):
        """A rectangle is planar geometry -- reject it in a free-3D sketch."""
        from ..model.sketch_ref import poll_active_2d_sketch

        return poll_active_2d_sketch(context)

    def _corner_cos(self, context: Context):
        """The four corner positions in link order, or None while undefined."""
        raise NotImplementedError

    def _placed_corners(self, context: Context) -> dict:
        """Corner index -> the point the user placed there."""
        raise NotImplementedError

    def _auto_constrain(self, context: Context, constraints, lines) -> None:
        """Inferred constraints that keep the shape a rectangle."""

    def update_preview(self, context: Context) -> bool:
        """Drag the corners instead of rebuilding the rectangle."""
        derived = getattr(self, "_derived_corners", None)
        if not derived or not all(ref.valid for ref, _i in derived):
            return False
        if self.state.pointer and not self.update_preview_point(context):
            return False
        corner_cos = self._corner_cos(context)
        if corner_cos is None:
            return False
        for ref, index in derived:
            ref.co = corner_cos[index]
        return True

    def main(self, context: Context):
        sketch = self.sketch
        construction = context.scene.sketcher.use_construction
        corner_cos = self._corner_cos(context)
        if corner_cos is None:
            return False

        placed = self._placed_corners(context)
        corners, derived = [], []
        for index, co in enumerate(corner_cos):
            ref = placed.get(index)
            if ref is None:
                ref = PointRef.create(sketch, co, construction=construction)
                derived.append((ref, index))
            elif construction:
                ref.construction = True
            corners.append(ref)

        lines = []
        for i, start in enumerate(corners):
            end = corners[(i + 1) % 4]
            lines.append(LineRef.create(sketch, start, end, construction=construction))

        self.lines = lines
        self._derived_corners = derived

        for ref in (*corners, *lines):
            ignore_hover(ref.curve_id)
        return True

    def fini(self, context: Context, succeede: bool):
        if succeede and getattr(self, "lines", None):
            if self.use_auto_constraints(context):
                self._auto_constrain(context, self.sketch.constraints, self.lines)

        if succeede:
            if self.has_coincident():
                solve_system(context, sketch=self.sketch)
            self.sketch.geometry_solved = False


class View3D_OT_slvs_add_rectangle_center(Operator, _RectangleVariant):
    """Add a rectangle from its center and one corner"""

    bl_idname = Operators.AddRectangleCenter
    bl_label = "Add Center Rectangle"

    states = (
        state_from_args(
            "Center",
            description="Pick or place the rectangle's center.",
            pointer="p1",
            types=types_point_2d,
        ),
        state_from_args(
            "Corner",
            description="Pick or place a corner.",
            pointer="p2",
            types=types_point_2d,
            interactive=True,
        ),
    )

    def _corner_cos(self, context: Context):
        center, corner = self.get_point(context, 0), self.get_point(context, 1)
        if center is None or corner is None or not center.valid or not corner.valid:
            return None
        return centered_corners(center.co, corner.co)

    def _placed_corners(self, context: Context) -> dict:
        # The center is not a corner of its own rectangle, only the picked one is.
        return {0: self.get_point(context, 1)}

    def _auto_constrain(self, context: Context, constraints, lines) -> None:
        """Axis-align the sides, and hold the center on the diagonal.

        Without the diagonal the center point is only where the rectangle
        happened to start: nothing would keep it centred once the sketch solves,
        and a center picked on existing geometry would come loose.
        """
        for i, line in enumerate(lines):
            add = constraints.add_horizontal if (i % 2) else constraints.add_vertical
            self.add_auto_constraint(context, add, curve_id_1=line.curve_id)

        center = self.get_point(context, 0)
        corner, opposite = lines[0].p1, lines[2].p1
        if center is None or not center.valid:
            return
        diagonal = LineRef.create(self.sketch, corner, opposite, construction=True)
        ignore_hover(diagonal.curve_id)
        self.add_auto_constraint(
            context,
            constraints.add_midpoint,
            curve_id_1=center.curve_id,
            curve_id_2=diagonal.curve_id,
        )


class View3D_OT_slvs_add_rectangle_3point(Operator, _RectangleVariant):
    """Add a rectangle from one edge and its width, at any angle"""

    bl_idname = Operators.AddRectangle3Point
    bl_label = "Add 3-Point Rectangle"

    # Signed, so the rectangle can be pulled out to either side of its edge.
    width: FloatProperty(
        name="Width",
        description="Distance from the drawn edge to the opposite one",
        subtype="DISTANCE",
        unit="LENGTH",
        precision=5,
    )

    states = (
        state_from_args(
            "Startpoint",
            description="Pick or place the first corner of one edge.",
            pointer="p1",
            types=types_point_2d,
        ),
        state_from_args(
            "Endpoint",
            description="Pick or place the other corner of that edge.",
            pointer="p2",
            types=types_point_2d,
            interactive=True,
        ),
        state_from_args(
            "Width",
            description="Move to set the width, click to confirm.",
            property="width",
            state_func="get_width",
            interactive=True,
            allow_prefill=False,
        ),
    )

    def get_width(self, context: Context, coords):
        """How far the cursor is off the drawn edge, and on which side."""
        from ..utilities.view import get_pos_2d

        pos = get_pos_2d(context, self._get_wp(), coords, respect_snapping=True)
        edge = self._edge(context)
        if pos is None or edge is None:
            return None
        return signed_offset(edge[0].co, edge[1].co, pos)

    def _edge(self, context: Context):
        start, end = self.get_point(context, 0), self.get_point(context, 1)
        if start is None or end is None or not start.valid or not end.valid:
            return None
        return start, end

    # The width stood in for while the edge is drawn, as a share of its length.
    # A square reads as one shape being dragged; half that reads as a rectangle
    # whose width is still to come.
    _ASSUMED_WIDTH = 0.5

    def _width_value(self, context: Context) -> Optional[float]:
        """The width in use: a share of the edge until the state is reached."""
        edge = self._edge(context)
        if edge is None:
            return None
        if self.state_index >= 2:
            return self.width
        return (edge[1].co - edge[0].co).length * self._ASSUMED_WIDTH

    def set_state(self, context: Context, index: int):
        if index == 1:
            # A preview runs only once every state has a value (check_props), so
            # mark the width as set while the edge is still being drawn.
            try:
                self.width = self.width
            except (AttributeError, TypeError):
                pass  # a non-registered twin (tests) has no RNA props
        elif index == 2:
            assumed = self._width_value(context)
            if assumed is not None:
                try:
                    self.width = assumed
                except (AttributeError, TypeError):
                    pass
        super().set_state(context, index)

    def _corner_cos(self, context: Context):
        edge = self._edge(context)
        width = self._width_value(context)
        if edge is None or width is None:
            return None
        return edge_corners(edge[0].co, edge[1].co, width)

    def _placed_corners(self, context: Context) -> dict:
        return {0: self.get_point(context, 0), 1: self.get_point(context, 1)}

    def _auto_constrain(self, context: Context, constraints, lines) -> None:
        """Parallel opposite sides plus one right angle: a rectangle at any angle.

        The axis-aligned variants use horizontal/vertical, which say nothing
        about a rotated shape.
        """
        self.add_auto_constraint(
            context,
            constraints.add_parallel,
            curve_id_1=lines[0].curve_id,
            curve_id_2=lines[2].curve_id,
        )
        self.add_auto_constraint(
            context,
            constraints.add_parallel,
            curve_id_1=lines[1].curve_id,
            curve_id_2=lines[3].curve_id,
        )
        self.add_auto_constraint(
            context,
            constraints.add_perpendicular,
            curve_id_1=lines[0].curve_id,
            curve_id_2=lines[1].curve_id,
        )


register, unregister = register_stateops_factory(
    (
        View3D_OT_slvs_add_rectangle,
        View3D_OT_slvs_add_rectangle_center,
        View3D_OT_slvs_add_rectangle_3point,
    )
)
