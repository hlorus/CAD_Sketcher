import math

from mathutils import Vector

from .utils import Sketch2dTestCase


class TestArcResolution(Sketch2dTestCase):
    """A NURBS arc's control-point count must adapt to its swept angle.

    Each rational span covers at most ~90 degrees and contributes 2 control points
    plus a shared on-circle junction, so an arc of ``nseg`` spans has ``2*nseg + 1``
    control points. The count is fixed at creation but recomputed in
    rebuild_segments as the endpoints move (drag/solve).
    """

    RADIUS = 2.0

    def _point_count(self, arc):
        from ..utilities.curve_data import get_curve_data
        cd, idx, _ = get_curve_data(self.sketch, arc.curve_id)
        return cd.curves[idx].points_length

    def _points(self, nseg):
        return 2 * nseg + 1

    def _end_at(self, degrees):
        a = math.radians(degrees)
        return Vector((self.RADIUS * math.cos(a), self.RADIUS * math.sin(a)))

    def _assert_on_circle(self, arc):
        """The on-circle control points (even offsets) lie on the arc's circle.

        Odd-offset points are off-circle shoulders (at radius / cos(span/2)), so
        they are intentionally excluded.
        """
        from ..utilities.curve_data import get_curve_data
        cd, idx, _ = get_curve_data(self.sketch, arc.curve_id)
        curve_slice = cd.curves[idx]
        for i, pt in enumerate(curve_slice.points):
            if i % 2:
                continue
            p = Vector(cd.points[pt.index].position[:2])
            self.assertAlmostEqual(p.length, self.RADIUS, places=4)

    def _make_arc(self, end_deg):
        ct = self.add_point((0, 0))
        start = self.add_point((self.RADIUS, 0))
        end = self.add_point(self._end_at(end_deg))
        arc = self.add_arc(ct, start, end)
        return arc, end

    def test_created_count_matches_angle(self):
        arc, _ = self._make_arc(30)           # <= 90 deg -> 1 span
        self.assertEqual(self._point_count(arc), self._points(1))

    def test_grow_adds_segments(self):
        arc, end = self._make_arc(30)
        self.assertEqual(self._point_count(arc), self._points(1))

        end.co = self._end_at(300)            # ~300 deg -> 4 spans
        self.assertEqual(self._point_count(arc), self._points(4))
        self._assert_on_circle(arc)

    def test_shrink_removes_segments(self):
        arc, end = self._make_arc(300)
        self.assertEqual(self._point_count(arc), self._points(4))

        end.co = self._end_at(30)             # back to a single span
        self.assertEqual(self._point_count(arc), self._points(1))
        self._assert_on_circle(arc)

    def test_intermediate_angles(self):
        arc, end = self._make_arc(30)
        for deg, nseg in ((100, 2), (200, 3), (350, 4), (80, 1)):
            end.co = self._end_at(deg)
            self.assertEqual(
                self._point_count(arc), self._points(nseg),
                f"{deg} deg should give {self._points(nseg)} points",
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
