"""Distance initialization must preserve the side of a translated line."""

from unittest import TestCase

from mathutils import Vector

from ..model.distance import get_side_of_line
from .utils import Sketch2dTestCase


class TestSideOfLine(TestCase):
    def test_translation_and_endpoint_order(self):
        # Keep a scalar result for both 2D and 3D vectors: Vector.cross returns
        # a vector in 3D, which cannot be passed to math.copysign by the callers.
        cases = (
            ((0, 0), (2, 0), (1, 3), -6.0),
            ((0, 0), (0, 2), (3, 1), 6.0),
            ((1, 2), (4, 6), (2, 5), -5.0),
            ((1, 2), (4, 6), (7, 10), 0.0),
        )
        for start, end, point, expected in cases:
            for offset in ((0, 0), (10, 10), (-10, -20)):
                for dimensions in (2, 3):
                    with self.subTest(
                        start=start, end=end, offset=offset, dimensions=dimensions
                    ):
                        vectors = [
                            Vector(
                                (co[0] + offset[0], co[1] + offset[1])
                                + (0.0,) * (dimensions - 2)
                            )
                            for co in (start, end, point)
                        ]
                        a, b, p = vectors
                        self.assertEqual(get_side_of_line(a, b, p), expected)
                        self.assertEqual(get_side_of_line(b, a, p), -expected)


class TestDistanceSide(Sketch2dTestCase):
    def _check_distance(self, kind):
        for offset in (0, 10, -10):
            for reverse in (False, True):
                with self.subTest(kind=kind, offset=offset, reverse=reverse):
                    a = self.add_point((offset, offset), fixed=True)
                    b = self.add_point((offset + 2, offset), fixed=True)
                    line = self.add_line(b, a) if reverse else self.add_line(a, b)
                    point = self.add_point((offset + 1, offset + 3))
                    before = point.co.copy()
                    if kind == "point":
                        ref = point
                        gap = 3.0
                    else:
                        if kind == "circle":
                            ref = self.add_circle(point, 1.0)
                        else:
                            start = self.add_point((offset + 2, offset + 3))
                            end = self.add_point((offset + 1, offset + 4))
                            ref = self.add_arc(point, start, end)
                        self.sketch.constraints.add_diameter(
                            init=True, curve_id_1=ref.curve_id, value=2.0
                        )
                        gap = 2.0

                    distance = self.sketch.constraints.add_distance(
                        init=True, curve_id_1=ref.curve_id, curve_id_2=line.curve_id
                    )
                    self.assertAlmostEqual(distance.value, gap, places=5)
                    self.solve()
                    self.assertLess((point.co - before).length, 1e-5)
                    self.assertEqual(distance.flip, not reverse)

    def test_point_stays_on_its_side(self):
        self._check_distance("point")

    def test_circle_stays_on_its_side(self):
        self._check_distance("circle")

    def test_arc_stays_on_its_side(self):
        self._check_distance("arc")
