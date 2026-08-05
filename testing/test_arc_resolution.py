import math

from mathutils import Vector

from .utils import Sketch2dTestCase


class TestArcResolution(Sketch2dTestCase):
    """An arc's bezier control-point count must adapt to its swept angle.

    The count is fixed at creation, but the endpoints move (drag/solve), so it
    is recomputed in rebuild_segments -- one segment per ~90 degrees of sweep.
    """

    RADIUS = 2.0

    def _point_count(self, arc):
        from ..utilities.curve_data import get_curve_data
        cd, idx, _ = get_curve_data(self.sketch, arc.curve_id)
        return cd.curves[idx].points_length

    def _end_at(self, degrees):
        a = math.radians(degrees)
        return Vector((self.RADIUS * math.cos(a), self.RADIUS * math.sin(a)))

    def _assert_on_circle(self, arc):
        """Every control point must lie on the arc's circle."""
        from ..utilities.curve_data import get_curve_data
        cd, idx, _ = get_curve_data(self.sketch, arc.curve_id)
        curve_slice = cd.curves[idx]
        center = Vector((0.0, 0.0))
        for pt in curve_slice.points:
            p = Vector(cd.points[pt.index].position[:2])
            self.assertAlmostEqual((p - center).length, self.RADIUS, places=4)

    def _make_arc(self, end_deg):
        ct = self.add_point((0, 0))
        start = self.add_point((self.RADIUS, 0))
        end = self.add_point(self._end_at(end_deg))
        arc = self.add_arc(ct, start, end)
        return arc, end

    def test_created_count_matches_angle(self):
        arc, _ = self._make_arc(30)           # <= 90 deg -> 1 segment
        self.assertEqual(self._point_count(arc), 2)

    def test_grow_adds_segments(self):
        arc, end = self._make_arc(30)
        self.assertEqual(self._point_count(arc), 2)

        end.co = self._end_at(300)            # ~300 deg -> 4 segments
        self.assertEqual(self._point_count(arc), 5)
        self._assert_on_circle(arc)

    def test_shrink_removes_segments(self):
        arc, end = self._make_arc(300)
        self.assertEqual(self._point_count(arc), 5)

        end.co = self._end_at(30)             # back to a single segment
        self.assertEqual(self._point_count(arc), 2)
        self._assert_on_circle(arc)

    def test_intermediate_angles(self):
        arc, end = self._make_arc(30)
        for deg, expected_points in ((100, 3), (200, 4), (350, 5), (80, 2)):
            end.co = self._end_at(deg)
            self.assertEqual(
                self._point_count(arc), expected_points,
                f"{deg} deg should give {expected_points} points",
            )
            self._assert_on_circle(arc)

    def test_boundary_does_not_thrash(self):
        """Sitting right on a 90 degree boundary keeps a stable count."""
        arc, end = self._make_arc(30)
        end.co = self._end_at(90.0)
        count = self._point_count(arc)
        # Re-applying the same angle must not flip the segment count.
        for _ in range(3):
            end.co = self._end_at(90.0)
            self.assertEqual(self._point_count(arc), count)
