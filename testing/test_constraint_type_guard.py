"""Constraints on curve types they can't solve fail instead of reaching the solver."""

from ..curve_solver import solve_system
from .utils import Sketch2dTestCase


class TestConstraintTypeGuard(Sketch2dTestCase):
    def setUp(self):
        super().setUp()
        self.p0 = self.add_point((0, 0))
        self.p1 = self.add_point((4, 0))
        self.line = self.add_line(self.p0, self.p1)
        self.p2 = self.add_point((0, 3))
        self.p3 = self.add_point((4, 3))
        self.line2 = self.add_line(self.p2, self.p3)
        self.circle = self.add_circle(self.add_point((2, 2)), 1.0)

    def _solve(self):
        return solve_system(self.context, sketch=self.sketch)

    def test_unsupported_pairs_fail(self):
        sc = self.sketch.constraints
        bad = [
            sc.add_tangent(
                curve_id_1=self.line.curve_id, curve_id_2=self.line2.curve_id
            ),
            sc.add_tangent(
                curve_id_1=self.circle.curve_id, curve_id_2=self.p0.curve_id
            ),
            sc.add_equal(curve_id_1=self.p0.curve_id, curve_id_2=self.line.curve_id),
            sc.add_perpendicular(
                curve_id_1=self.circle.curve_id, curve_id_2=self.line.curve_id
            ),
            sc.add_parallel(
                curve_id_1=self.circle.curve_id, curve_id_2=self.circle.curve_id
            ),
            sc.add_midpoint(curve_id_1=self.line.curve_id, curve_id_2=self.p0.curve_id),
            sc.add_coincident(
                curve_id_1=self.line.curve_id, curve_id_2=self.circle.curve_id
            ),
        ]
        self._solve()
        for c in bad:
            self.assertTrue(c.failed, c.type)

    def test_tangent_line_first_matches_curve_first(self):
        sc = self.sketch.constraints
        t = sc.add_tangent(
            curve_id_1=self.line.curve_id, curve_id_2=self.circle.curve_id
        )
        self.assertTrue(self._solve())
        self.assertFalse(t.failed)
        a, b, ct = self.p0.co, self.p1.co, self.circle.ct.co
        d = b - a
        dist = abs(d.x * (ct.y - a.y) - d.y * (ct.x - a.x)) / d.length
        self.assertAlmostEqual(dist, self.circle.radius, places=4)

    def test_supported_pairs_unchanged(self):
        sc = self.sketch.constraints
        ok = [
            sc.add_tangent(
                curve_id_1=self.circle.curve_id, curve_id_2=self.line.curve_id
            ),
            sc.add_parallel(
                curve_id_1=self.line.curve_id, curve_id_2=self.line2.curve_id
            ),
            sc.add_coincident(
                curve_id_1=self.p0.curve_id, curve_id_2=self.line2.curve_id
            ),
        ]
        self.assertTrue(self._solve())
        for c in ok:
            self.assertFalse(c.failed, c.type)
