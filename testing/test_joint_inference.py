"""Constraints inferred from how a new segment meets the ones it joins.

A chain of segments is connected but free to pivot, so an arc that carries on
from a line smoothly, or a line drawn square to the last one, only looks that way
until something moves. The joint is read and constrained (see
operators.inference); as with every inferred constraint, one is kept only when it
solves and takes a degree of freedom away.
"""

import math

from mathutils import Vector

from ..model.curve_ref import ArcRef
from ..operators.inference import (
    PARALLEL,
    PERPENDICULAR,
    TANGENT,
    joint_relations,
    ordered_for,
    relation_for,
)
from .live_harness import LiveOpHarness
from .utils import OpHarness, Sketch2dTestCase


def _polar(length, degrees):
    angle = math.radians(degrees)
    return Vector((length * math.cos(angle), length * math.sin(angle)))


class TestRelationFor(Sketch2dTestCase):
    def setUp(self):
        super().setUp()
        a, b = self.add_point((0.0, 0.0)), self.add_point((1.0, 0.0))
        self.line = self.add_line(a, b)
        center = self.add_point((1.0, 1.0))
        self.arc = self.add_arc(center, b, self.add_point((2.0, 1.0)))

    def test_two_lines_running_the_same_way_are_parallel(self):
        self.assertEqual(relation_for(self.line, self.line, 1.0), PARALLEL)

    def test_two_lines_at_a_right_angle_are_perpendicular(self):
        self.assertEqual(relation_for(self.line, self.line, 0.0), PERPENDICULAR)

    def test_a_curve_carrying_on_smoothly_is_tangent(self):
        self.assertEqual(relation_for(self.line, self.arc, 1.0), TANGENT)
        self.assertEqual(relation_for(self.arc, self.arc, 1.0), TANGENT)

    def test_a_curve_at_a_right_angle_suggests_nothing(self):
        # There is no perpendicular constraint for a curve.
        self.assertIsNone(relation_for(self.line, self.arc, 0.0))

    def test_a_joint_in_between_suggests_nothing(self):
        self.assertIsNone(relation_for(self.line, self.line, 0.5))

    def test_a_tangency_names_the_curve_first(self):
        # Solvespace aborts Blender outright on a constraint whose arguments are
        # of the wrong kind, so the order is not cosmetic.
        self.assertEqual(
            ordered_for(TANGENT, self.line, self.arc),
            (self.arc.curve_id, self.line.curve_id),
        )
        self.assertEqual(
            ordered_for(TANGENT, self.arc, self.line),
            (self.arc.curve_id, self.line.curve_id),
        )


class TestJointRelations(Sketch2dTestCase):
    def _chain(self, first_degrees, second_degrees):
        """Two lines sharing a point, each at the given angle."""
        start = self.add_point(_polar(1.0, first_degrees + 180.0))
        joint = self.add_point((0.0, 0.0))
        end = self.add_point(_polar(1.0, second_degrees))
        return self.add_line(start, joint), self.add_line(joint, end)

    def test_a_straight_continuation_is_parallel(self):
        _first, second = self._chain(30.0, 30.0)

        self.assertEqual(
            [relation for relation, _other in joint_relations(self.sketch, second)],
            [PARALLEL],
        )

    def test_a_square_corner_is_perpendicular(self):
        _first, second = self._chain(30.0, 120.0)

        self.assertEqual(
            [relation for relation, _other in joint_relations(self.sketch, second)],
            [PERPENDICULAR],
        )

    def test_a_corner_in_between_suggests_nothing(self):
        _first, second = self._chain(30.0, 75.0)

        self.assertEqual(list(joint_relations(self.sketch, second)), [])

    def test_only_segments_at_a_shared_point_count(self):
        # A second line running the same way but not joined suggests nothing: the
        # joint is what makes the relation obvious.
        a, b = self.add_point((0.0, 0.0)), self.add_point((1.0, 0.0))
        line = self.add_line(a, b)
        c, d = self.add_point((0.0, 5.0)), self.add_point((1.0, 5.0))
        self.add_line(c, d)

        self.assertEqual(list(joint_relations(self.sketch, line)), [])


class TestInferredJointConstraints(Sketch2dTestCase):
    def setUp(self):
        super().setUp()
        self.context.scene.sketcher.auto_axis_constraints = True

    def _kinds(self):
        return [c.type for c in self.sketch.constraints.all]

    def test_a_line_square_to_the_one_before_gets_perpendicular(self):
        from ..operators.add_line_2d import View3D_OT_slvs_add_line2d

        # Off-axis, so the axis alignment does not claim the freedom first.
        joint = self.add_point((0.0, 0.0))
        self.add_line(self.add_point(_polar(1.0, 210.0)), joint)

        harness = OpHarness(View3D_OT_slvs_add_line2d, self.sketch, self.context)
        harness.pick(joint).place_point(_polar(1.0, 120.0))
        self.assertTrue(harness.finish())

        self.assertIn(PERPENDICULAR, self._kinds())

    def test_a_line_carrying_straight_on_gets_parallel(self):
        from ..operators.add_line_2d import View3D_OT_slvs_add_line2d

        joint = self.add_point((0.0, 0.0))
        self.add_line(self.add_point(_polar(1.0, 210.0)), joint)

        harness = OpHarness(View3D_OT_slvs_add_line2d, self.sketch, self.context)
        harness.pick(joint).place_point(_polar(1.0, 30.0))
        self.assertTrue(harness.finish())

        self.assertIn(PARALLEL, self._kinds())

    def test_an_arc_carrying_on_from_a_line_gets_tangent(self):
        from ..operators.add_arc import View3D_OT_slvs_add_arc3pt2d

        # A line running along +X into the joint; the arc leaves along +X too.
        joint = self.add_point((0.0, 0.0))
        self.add_line(self.add_point((-1.0, 0.0)), joint)

        harness = OpHarness(View3D_OT_slvs_add_arc3pt2d, self.sketch, self.context)
        harness.pick(joint)
        harness.op._start_dir = Vector((1.0, 0.0))
        harness.place_point((2.0, 2.0))
        self.assertTrue(harness.finish())

        self.assertIsInstance(harness.op.target, ArcRef)
        self.assertIn(TANGENT, self._kinds())

    def test_an_arc_turning_off_a_line_gets_no_tangent(self):
        from ..operators.add_arc import View3D_OT_slvs_add_arc3pt2d

        joint = self.add_point((0.0, 0.0))
        self.add_line(self.add_point((-1.0, 0.0)), joint)

        harness = OpHarness(View3D_OT_slvs_add_arc3pt2d, self.sketch, self.context)
        harness.pick(joint)
        harness.op._start_dir = Vector((0.0, 1.0))  # straight up, off the line
        harness.place_point((2.0, 2.0))
        self.assertTrue(harness.finish())

        self.assertNotIn(TANGENT, self._kinds())

    def test_nothing_is_inferred_with_auto_constraints_off(self):
        from ..operators.add_line_2d import View3D_OT_slvs_add_line2d

        self.context.scene.sketcher.auto_axis_constraints = False
        joint = self.add_point((0.0, 0.0))
        self.add_line(self.add_point(_polar(1.0, 210.0)), joint)

        harness = OpHarness(View3D_OT_slvs_add_line2d, self.sketch, self.context)
        harness.pick(joint).place_point(_polar(1.0, 120.0))
        self.assertTrue(harness.finish())

        self.assertNotIn(PERPENDICULAR, self._kinds())

    def test_a_square_corner_on_an_axis_line_needs_no_perpendicular(self):
        # The line before it is already horizontal and the new one comes out
        # vertical, so the perpendicular they also form constrains nothing new and
        # the guard declines it.
        from ..operators.add_line_2d import View3D_OT_slvs_add_line2d

        joint = self.add_point((0.0, 0.0))
        first = self.add_line(self.add_point((-1.0, 0.0)), joint)
        self.sketch.constraints.add_horizontal(curve_id_1=first.curve_id)

        harness = OpHarness(View3D_OT_slvs_add_line2d, self.sketch, self.context)
        harness.pick(joint).place_point((0.0, 1.0))
        self.assertTrue(harness.finish())

        kinds = self._kinds()
        self.assertIn("VERTICAL", kinds)
        self.assertNotIn(PERPENDICULAR, kinds)

    def test_a_square_corner_on_a_free_line_still_gets_perpendicular(self):
        # Nothing holds the line before it, so the corner is square only while
        # the perpendicular says so: it takes a real degree of freedom.
        from ..operators.add_line_2d import View3D_OT_slvs_add_line2d

        joint = self.add_point((0.0, 0.0))
        self.add_line(self.add_point((-1.0, 0.0)), joint)

        harness = OpHarness(View3D_OT_slvs_add_line2d, self.sketch, self.context)
        harness.pick(joint).place_point((0.0, 1.0))
        self.assertTrue(harness.finish())

        kinds = self._kinds()
        self.assertIn("VERTICAL", kinds)
        self.assertIn(PERPENDICULAR, kinds)


class TestInferredWhileDrawing(Sketch2dTestCase):
    """The constraint appears while the segment is still being dragged.

    That is the point of inferring it: seeing the relation land is what tells you
    the corner is square before you commit to it. Solving stays deferred, so
    nothing already drawn moves until the segment is confirmed.
    """

    def setUp(self):
        super().setUp()
        self.context.scene.sketcher.auto_axis_constraints = True
        # A free line running into the origin at an angle, so neither an axis
        # alignment nor anything else already fixes the corner.
        self.tail = self.add_point(_polar(1.0, 210.0))
        self.joint = self.add_point((0.0, 0.0))
        self.first = self.add_line(self.tail, self.joint)

    def _kinds(self):
        return [c.type for c in self.sketch.constraints.all]

    def _drag_square(self):
        """Click the joint, then drag out square to the first line."""
        from ..operators.add_line_2d import View3D_OT_slvs_add_line2d

        harness = LiveOpHarness(View3D_OT_slvs_add_line2d, self.sketch, self.context)
        harness.click((0.0, 0.0), hover=self.joint.curve_id)
        harness.move(_polar(1.0, 120.0))
        return harness

    def test_the_constraint_is_there_before_the_segment_is_confirmed(self):
        harness = self._drag_square()
        try:
            self.assertIn(PERPENDICULAR, self._kinds())
        finally:
            harness.cancel()

    def test_it_goes_away_again_when_the_corner_is_not_square(self):
        harness = self._drag_square()
        try:
            harness.move(_polar(1.0, 75.0))
            self.assertNotIn(PERPENDICULAR, self._kinds())
        finally:
            harness.cancel()

    def test_nothing_already_drawn_moves_while_dragging(self):
        # The trial solve never writes positions: the first line stays exactly
        # where it was until the new segment is confirmed.
        before = self.tail.co.copy()
        harness = self._drag_square()
        try:
            self.assertEqual(self.tail.co, before)
        finally:
            harness.cancel()

    def test_confirming_solves_for_it(self):
        harness = self._drag_square()
        harness.click(_polar(1.0, 120.0))

        # Exactly square now, which only a solve can deliver.
        second = harness.op.target
        first = (self.joint.co - self.tail.co).normalized()
        along = (second.p2.co - second.p1.co).normalized()
        self.assertAlmostEqual(first.dot(along), 0.0, places=5)
