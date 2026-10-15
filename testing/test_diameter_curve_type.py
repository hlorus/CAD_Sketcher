"""A diameter is refused on curves that aren't circles or arcs."""

from .utils import Sketch2dTestCase


class TestDiameterCurveType(Sketch2dTestCase):
    def setUp(self):
        super().setUp()
        p0 = self.add_point((0, 0))
        self.p0 = p0
        self.line = self.add_line(p0, self.add_point((4, 0)))
        self.circle = self.add_circle(self.add_point((2, 2)), 1.0)

    def test_line_and_point_are_refused(self):
        sc = self.sketch.constraints
        for ref in (self.line, self.p0):
            with self.assertRaises(ValueError):
                sc.add_diameter(init=True, curve_id_1=ref.curve_id)
        self.assertEqual(len(sc.diameter), 0)

    def test_circle_is_accepted(self):
        d = self.sketch.constraints.add_diameter(
            init=True, curve_id_1=self.circle.curve_id
        )
        self.assertAlmostEqual(d.value, 2.0, places=4)
