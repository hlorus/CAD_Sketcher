"""Carrying a chain of segments from one tool to the next.

Drawing lines chains segment to segment on its own. Reaching for another tool
mid-chain used to end the run and start the next tool empty-handed, so the run of
geometry stopped there; the point the chain reached is handed over instead (see
stateful_operator.utilities.continuation), and a tool that can start from a point
carries on from it.
"""

from unittest import TestCase

from mathutils import Vector

from ..model.curve_ref import ArcRef, PointRef
from ..operators.add_arc import View3D_OT_slvs_add_arc2d, View3D_OT_slvs_add_arc3pt2d
from ..operators.add_circle import View3D_OT_slvs_add_circle2d
from ..operators.add_line_2d import View3D_OT_slvs_add_line2d
from ..stateful_operator.utilities import continuation
from .utils import OpHarness, Sketch2dTestCase


class TestContinuationOffer(TestCase):
    def tearDown(self):
        continuation.clear()

    def test_it_is_taken_up_once(self):
        continuation.publish(["abc"], PointRef, "Sketch")

        self.assertEqual(continuation.take("Sketch"), (["abc"], PointRef))
        self.assertIsNone(continuation.take("Sketch"))

    def test_another_scope_does_not_get_it(self):
        # And it is gone either way: an offer not taken up straight away is stale.
        continuation.publish(["abc"], PointRef, "Sketch")

        self.assertIsNone(continuation.take("Other"))
        self.assertFalse(continuation.pending())


class TestChainHandover(Sketch2dTestCase):
    def tearDown(self):
        continuation.clear()
        super().tearDown()

    def _drawing(self, cls, end_point):
        """A chain-capable run standing where ``end_point`` is its first state."""
        harness = OpHarness(cls, self.sketch, self.context)
        op = harness.op
        op._chain_committed = True
        data = op.get_state_data(0)
        data["type"] = PointRef
        data["is_existing_entity"] = True
        op.set_state_pointer([end_point.curve_id], index=0, implicit=True)
        op.state_index = 1
        return harness

    def _offer_from_line(self):
        """What pressing another tool's key mid-chain leaves behind."""
        point = self.add_point((1.0, 0.0))
        self._drawing(View3D_OT_slvs_add_line2d, point).op._offer_chain(self.context)
        return point

    def test_a_switch_mid_chain_offers_the_point_it_reached(self):
        self._offer_from_line()

        self.assertTrue(continuation.pending())

    def test_a_run_that_has_committed_nothing_offers_nothing(self):
        # The segment in progress is rolled back when the run ends, so the points
        # it placed itself would not be there to carry on from.
        point = self.add_point((1.0, 0.0))
        harness = self._drawing(View3D_OT_slvs_add_line2d, point)
        harness.op._chain_committed = False

        harness.op._offer_chain(self.context)

        self.assertFalse(continuation.pending())

    def test_the_arc_carries_on_from_the_offered_point(self):
        point = self._offer_from_line()
        op = OpHarness(View3D_OT_slvs_add_arc3pt2d, self.sketch, self.context).op

        self.assertTrue(op._seed_from_chain(self.context))
        # Standing at the endpoint, with the line's end as the arc's start.
        self.assertEqual(op.state_index, 1)
        self.assertEqual(op.get_point(self.context, 0).curve_id, point.curve_id)
        self.assertFalse(continuation.pending())

    def test_the_arc_really_shares_that_point(self):
        # Not a second point on top of it: the line and the arc are connected.
        point = self._offer_from_line()
        harness = OpHarness(View3D_OT_slvs_add_arc3pt2d, self.sketch, self.context)
        harness.op._seed_from_chain(self.context)
        harness.op._start_dir = Vector((0.0, 1.0))
        harness.place_point((3.0, 0.0))

        self.assertTrue(harness.finish())
        arc = harness.op.target
        self.assertIsInstance(arc, ArcRef)
        self.assertIn(point.curve_id, (arc.start.curve_id, arc.end.curve_id))

    def test_each_segment_of_an_arc_chain_aims_anew(self):
        # Which way an arc curves is the direction that segment set off in, so a
        # new segment must not inherit the last one's.
        harness = OpHarness(View3D_OT_slvs_add_arc3pt2d, self.sketch, self.context)
        harness.op._start_dir = Vector((0.0, 1.0))

        harness.op._reset_op()

        self.assertIsNone(harness.op._start_dir)

    def test_a_tool_that_cannot_start_from_a_point_drops_the_offer(self):
        # A circle starts from its center, which is not where a chain left off.
        self._offer_from_line()
        op = OpHarness(View3D_OT_slvs_add_circle2d, self.sketch, self.context).op

        self.assertFalse(op._seed_from_chain(self.context))
        self.assertFalse(continuation.pending())

    def test_the_center_first_arc_does_not_take_it_either(self):
        self._offer_from_line()
        op = OpHarness(View3D_OT_slvs_add_arc2d, self.sketch, self.context).op

        self.assertFalse(op._seed_from_chain(self.context))

    def test_an_offer_whose_point_is_gone_is_not_taken_up(self):
        point = self._offer_from_line()
        point.remove()
        op = OpHarness(View3D_OT_slvs_add_arc3pt2d, self.sketch, self.context).op

        self.assertFalse(op._seed_from_chain(self.context))
        self.assertEqual(op.state_index, 0)

    def test_a_point_from_another_sketch_is_not_carried_over(self):
        self._offer_from_line()
        other = self.new_sketch()
        from ..model.sketch_ref import set_active_sketch

        set_active_sketch(self.context, other.target_object)
        op = OpHarness(View3D_OT_slvs_add_arc3pt2d, other, self.context).op

        self.assertFalse(op._seed_from_chain(self.context))
