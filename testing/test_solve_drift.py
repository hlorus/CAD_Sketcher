"""Re-solving an unchanged, under-constrained sketch must not move geometry.

Solvespace's point-on-line constraint starts a hidden parameter at 0 on every
fresh system, which used to pull geometry on each solve
(solvespace/solvespace#1775). Coincident (point on line) and tangent build on
it, so each is solved repeatedly here and must stay put.
"""

from mathutils import Vector

from .utils import Sketch2dTestCase

SOLVES = 10


class TestSolveDrift(Sketch2dTestCase):
    def assertStable(self, points):
        self.solve()
        start = [Vector(p.co) for p in points]
        for _ in range(SOLVES):
            self.solve()
        moved = max((Vector(p.co) - s).length for p, s in zip(points, start))
        self.assertLess(moved, 1e-5)

    def test_coincident_point_line(self):
        a, b = self.add_point((0, 0)), self.add_point((5, 1))
        p = self.add_point((2.3, 2.0))
        line = self.add_line(a, b)
        self.sketch.constraints.add_coincident(
            curve_id_1=p.curve_id, curve_id_2=line.curve_id
        )
        self.assertStable([a, b, p])

    def test_first_solve_keeps_satisfied_point_on_line(self):
        """A point already on the line is not moved by the first solve either."""
        a, b = self.add_point((0, 0)), self.add_point((5, 1))
        p = self.add_point((2.5, 0.5))
        line = self.add_line(a, b)
        self.sketch.constraints.add_coincident(
            curve_id_1=p.curve_id, curve_id_2=line.curve_id
        )
        self.solve()
        self.assertLess((Vector(a.co) - Vector((0, 0))).length, 1e-6)
        self.assertLess((Vector(p.co) - Vector((2.5, 0.5))).length, 1e-6)

    def test_coincident_point_on_degenerate_line(self):
        """A zero-length line keeps solving (it can't use a point-line distance)."""
        a, b = self.add_point((1, 1)), self.add_point((1, 1))
        p = self.add_point((2, 2))
        line = self.add_line(a, b)
        self.sketch.constraints.add_coincident(
            curve_id_1=p.curve_id, curve_id_2=line.curve_id
        )
        self.solve()

    def test_tangent_circle_line(self):
        ct = self.add_point((0, 0))
        circle = self.add_circle(ct, 2.0)
        a, b = self.add_point((-3, 2.5)), self.add_point((3, 2.2))
        line = self.add_line(a, b)
        self.sketch.constraints.add_tangent(
            curve_id_1=circle.curve_id, curve_id_2=line.curve_id
        )
        self.assertStable([ct, a, b])

    def test_tangent_circle_circle(self):
        c1 = self.add_point((0, 0))
        circle1 = self.add_circle(c1, 2.0)
        c2 = self.add_point((3.5, 0.5))
        circle2 = self.add_circle(c2, 1.0)
        self.sketch.constraints.add_tangent(
            curve_id_1=circle1.curve_id, curve_id_2=circle2.curve_id
        )
        self.assertStable([c1, c2])


class TestTangentTopologies(Sketch2dTestCase):
    """Tangency at a point already constrained onto both curves (a fillet) must
    solve cleanly: not flagged redundant, correct dof, and nothing moved."""

    def _line(self):
        a = self.add_point((0, 0), fixed=True)
        b = self.add_point((4, 0))
        line = self.add_line(a, b)
        self.sketch.constraints.add_horizontal(curve_id_1=line.curve_id)
        return a, b, line

    def assertClean(self, points, dof):
        start = [Vector(p.co) for p in points]
        self.solve()
        self.assertEqual(self.sketch.solver_state, "OKAY")
        self.assertEqual(self.sketch.dof, dof)
        moved = max((Vector(p.co) - s).length for p, s in zip(points, start))
        self.assertLess(moved, 1e-5)

    def test_line_arc_shared_endpoint(self):
        _, b, line = self._line()
        ct, end = self.add_point((4, 1)), self.add_point((5, 1))
        arc = self.add_arc(ct, b, end)
        self.sketch.constraints.add_tangent(
            curve_id_1=arc.curve_id, curve_id_2=line.curve_id
        )
        self.assertClean([b, ct, end], dof=3)

    def test_line_arc_coincident_endpoints(self):
        _, b, line = self._line()
        start = self.add_point((4, 0))
        ct, end = self.add_point((4, 1)), self.add_point((5, 1))
        arc = self.add_arc(ct, start, end)
        sc = self.sketch.constraints
        sc.add_coincident(curve_id_1=start.curve_id, curve_id_2=b.curve_id)
        sc.add_tangent(curve_id_1=arc.curve_id, curve_id_2=line.curve_id)
        self.assertClean([b, start, ct, end], dof=3)

    def test_line_arc_endpoint_on_line(self):
        a = self.add_point((0, 0), fixed=True)
        b = self.add_point((8, 0))
        line = self.add_line(a, b)
        sc = self.sketch.constraints
        sc.add_horizontal(curve_id_1=line.curve_id)
        start = self.add_point((4, 0))
        ct, end = self.add_point((4, 1)), self.add_point((5, 1))
        arc = self.add_arc(ct, start, end)
        sc.add_coincident(curve_id_1=start.curve_id, curve_id_2=line.curve_id)
        sc.add_tangent(curve_id_1=arc.curve_id, curve_id_2=line.curve_id)
        self.assertClean([b, start, ct, end], dof=4)

    def test_arc_arc_shared_endpoint(self):
        c1 = self.add_point((0, 0), fixed=True)
        t = self.add_point((2, 0))
        arc1 = self.add_arc(c1, t, self.add_point((0, 2)))
        c2 = self.add_point((4, 0))
        arc2 = self.add_arc(c2, self.add_point((4, -2)), t)
        self.sketch.constraints.add_tangent(
            curve_id_1=arc1.curve_id, curve_id_2=arc2.curve_id
        )
        self.assertClean([t, c2], dof=5)

    def test_circle_line_free(self):
        ct = self.add_point((0, 0), fixed=True)
        circle = self.add_circle(ct, 1.0)
        a, b = self.add_point((-3, 1)), self.add_point((3, 1))
        line = self.add_line(a, b)
        self.sketch.constraints.add_tangent(
            curve_id_1=circle.curve_id, curve_id_2=line.curve_id
        )
        self.assertClean([a, b], dof=4)
