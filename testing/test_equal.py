from .utils import Sketch2dTestCase, OpHarness
from ..drawing import selection


class TestEqual(Sketch2dTestCase):
    def test_equal_lines(self):
        sc = self.sketch.constraints

        p0 = self.add_point((0, 0), fixed=True)

        # Line 1: fixed length 3
        p1 = self.add_point((3, 0), fixed=True)
        line1 = self.add_line(p0, p1)

        # Line 2: free endpoint, initial length 1
        p2 = self.add_point((0, 1))
        line2 = self.add_line(p0, p2)

        sc.add_equal(curve_id_1=line1.curve_id, curve_id_2=line2.curve_id)
        self.solve()

        self.assertAlmostEqual(line2.length, 3.0)

    def test_equal_circles(self):
        sc = self.sketch.constraints

        p0 = self.add_point((0, 0), fixed=True)
        p1 = self.add_point((5, 0), fixed=True)

        c1 = self.add_circle(p0, 2.0)
        sc.add_diameter(curve_id_1=c1.curve_id, init=True, value=4.0)

        c2 = self.add_circle(p1, 1.0)

        sc.add_equal(curve_id_1=c1.curve_id, curve_id_2=c2.curve_id)
        self.solve()

        self.assertAlmostEqual(c2.radius, 2.0)

    # -- preselect a circle + a line, invoke equal (issue #569 follow-up) -----
    def test_equal_prefill_rejects_circle_and_line(self):
        """Selection prefill must apply the same type narrowing as picking.

        A circle and a line can't be made equal (length vs radius). The first
        slot takes the circle; the second must then reject the line instead of
        filling both slots (which used to feed an invalid pair to the solver
        and crash it).
        """
        from ..operators.add_geometric_constraints import (
            VIEW3D_OT_slvs_add_equal,
        )

        p0 = self.add_point((0, 0))
        p1 = self.add_point((3, 0))
        line = self.add_line(p0, p1)

        pc = self.add_point((6, 0))
        circle = self.add_circle(pc, 1.0)

        selection.selected.clear()
        selection.selected.append(circle.curve_id)
        selection.selected.append(line.curve_id)

        h = OpHarness(VIEW3D_OT_slvs_add_equal, self.sketch, self.context)
        h.prefill()

        # First slot filled with the circle...
        self.assertTrue(h.op.get_state_data(0).get("is_existing_entity", False))
        # ...but the incompatible line is rejected for the second slot.
        self.assertFalse(h.op.get_state_data(1).get("is_existing_entity", False))
        self.assertFalse(h.op.check_props())

    # -- solver safety net: an incompatible pair (e.g. from a loaded file or a
    #    script) must be skipped, never crash the solver ----------------------
    def test_equal_incompatible_pair_does_not_crash_solver(self):
        sc = self.sketch.constraints

        p0 = self.add_point((0, 0), fixed=True)
        p1 = self.add_point((3, 0), fixed=True)
        line = self.add_line(p0, p1)

        pc = self.add_point((6, 0), fixed=True)
        circle = self.add_circle(pc, 1.0)

        c = sc.add_equal(curve_id_1=line.curve_id, curve_id_2=circle.curve_id)
        # Must not crash; the constraint is skipped and marked failed.
        self.solve()
        self.assertTrue(c.failed)

    def tearDown(self):
        selection.selected.clear()
        return super().tearDown()
