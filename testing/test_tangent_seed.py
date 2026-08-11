"""Regression helpers for stable circle/arc tangent branch selection."""

import unittest

from mathutils import Vector

from ..model.tangent import _curve_curve_tangent_seed


class TestTangentSeed(unittest.TestCase):
    def assert_near(self, value, expected):
        self.assertLess((Vector(value) - Vector(expected)).length, 1e-9)

    def test_external_tangent_seed(self):
        """Unequal circles that face each other keep the external branch."""
        seed = _curve_curve_tangent_seed((0, 0), (4, 0), 1, 3)
        self.assert_near(seed, (1, 0))

    def test_internal_tangent_seed(self):
        """Nested unequal circles keep the existing internal tangent branch."""
        seed = _curve_curve_tangent_seed((0, 0), (2, 0), 5, 3)
        self.assert_near(seed, (5, 0))
