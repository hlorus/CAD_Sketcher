"""Dimension values ignore non-finite input; a diameter never goes negative."""

import math

from .utils import Sketch2dTestCase


class TestDimensionValueInput(Sketch2dTestCase):
    def setUp(self):
        super().setUp()
        p0 = self.add_point((0, 0))
        self.line = self.add_line(p0, self.add_point((4, 0)))
        circle = self.add_circle(self.add_point((2, 2)), 1.0)
        sc = self.sketch.constraints
        self.dist = sc.add_distance(init=True, curve_id_1=self.line.curve_id)
        self.dia = sc.add_diameter(init=True, curve_id_1=circle.curve_id)

    def test_non_finite_values_are_ignored(self):
        for c in (self.dist, self.dia):
            before = c.value
            for bad in (math.nan, math.inf, -math.inf):
                c.value = bad
                self.assertEqual(c.value, before)

    def test_negative_diameter_clamps_to_zero(self):
        self.dia.value = -1.0
        self.assertEqual(self.dia.value, 0.0)

    def test_finite_values_still_apply(self):
        self.dist.value = 2.5
        self.dia.value = 3.0
        self.assertAlmostEqual(self.dist.value, 2.5, places=5)
        self.assertAlmostEqual(self.dia.value, 3.0, places=5)
        self.dist.value = -1.0
        self.assertAlmostEqual(self.dist.value, 1.0, places=5)
