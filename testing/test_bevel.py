"""Tests for the bevel operator."""

import math
from mathutils import Vector
from .utils import Sketch2dTestCase


class TestBevel(Sketch2dTestCase):
    """Test bevel creates arc at corner."""

    def test_bevel_right_angle(self):
        """Bevel a 90-degree corner between two lines."""
        # Create L-shape: horizontal + vertical
        p1 = self.add_point((0, 0))
        p2 = self.add_point((4, 0))
        p3 = self.add_point((4, 4))
        l1 = self.add_line(p1, p2)
        l2 = self.add_line(p2, p3)

        topo = self.sketch.topology

        # Verify connectivity at corner point
        connected = topo.get_connected_segments(p2.curve_id)
        self.assertEqual(len(connected), 2)

        # Simulate what bevel does: find center, tangent points, create arc
        radius = 1.0
        from ..utilities.intersect import get_intersections, ElementTypes

        def _offset(ref, offset):
            if ref.is_line():
                n = topo.normal_at(ref)
                return (ElementTypes.Line, (ref.p1.co + n * offset, ref.p2.co + n * offset))
            return None

        intersections = sorted(
            get_intersections(
                _offset(l1, radius), _offset(l1, -radius),
                _offset(l2, radius), _offset(l2, -radius),
                segment=True,
            ),
            key=lambda i: (i - p2.co).length,
        )

        self.assertGreater(len(intersections), 0, "Should find at least one intersection")

        # Center should be near (3, 1) for radius=1 at corner (4,0)
        center = intersections[0]
        self.assertAlmostEqual(center.x, 3.0, places=1)
        self.assertAlmostEqual(center.y, 1.0, places=1)

        # Project center onto segments to get tangent points
        t1 = topo.project_point(l1, center)
        t2 = topo.project_point(l2, center)
        self.assertIsNotNone(t1)
        self.assertIsNotNone(t2)

        # Tangent points should be at distance=radius from center
        self.assertAlmostEqual((Vector(t1) - center).length, radius, places=2)
        self.assertAlmostEqual((Vector(t2) - center).length, radius, places=2)

    def test_bevel_replaces_endpoint(self):
        """Bevel should replace the corner point with arc endpoints."""
        p1 = self.add_point((0, 0))
        p2 = self.add_point((4, 0))
        p3 = self.add_point((4, 4))
        l1 = self.add_line(p1, p2)
        l2 = self.add_line(p2, p3)

        topo = self.sketch.topology

        # Create bevel points and replace
        ct = self.add_point((3, 1))
        bp1 = self.add_point((3, 0))
        bp2 = self.add_point((4, 1))

        topo.replace_point(l1, p2.curve_id, bp1.curve_id)
        topo.replace_point(l2, p2.curve_id, bp2.curve_id)

        # Verify l1 now ends at bp1
        from ..model.curve_ref import curve_ref
        l1_updated = curve_ref(self.sketch, l1.curve_id)
        self.assertEqual(l1_updated.p2.curve_id, bp1.curve_id)

        # Verify l2 now starts at bp2
        l2_updated = curve_ref(self.sketch, l2.curve_id)
        self.assertEqual(l2_updated.p1.curve_id, bp2.curve_id)

    def test_bevel_connection_angle(self):
        """Connection angle should determine arc direction."""
        p1 = self.add_point((0, 0))
        p2 = self.add_point((4, 0))
        p3 = self.add_point((4, 4))
        l1 = self.add_line(p1, p2)
        l2 = self.add_line(p2, p3)

        topo = self.sketch.topology
        angle = topo.connection_angle(l1, l2, p2.curve_id)
        self.assertIsNotNone(angle)
        # Left turn = positive, right turn = negative
        self.assertNotEqual(angle, 0)
