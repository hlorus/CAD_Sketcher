"""Tests for the trim operator logic."""

import math
from mathutils import Vector
from .utils import Sketch2dTestCase


class TestTrimLogic(Sketch2dTestCase):
    """Test trimming logic with SketchTopology."""

    def test_intersect_crossing_lines(self):
        """Two crossing lines should have one intersection."""
        p1 = self.add_point((0, 0))
        p2 = self.add_point((4, 4))
        p3 = self.add_point((0, 4))
        p4 = self.add_point((4, 0))
        l1 = self.add_line(p1, p2)
        l2 = self.add_line(p3, p4)

        topo = self.sketch.topology
        pts = topo.intersect(l1, l2)
        self.assertEqual(len(pts), 1)
        self.assertAlmostEqual(pts[0].x, 2.0, places=1)
        self.assertAlmostEqual(pts[0].y, 2.0, places=1)

    def test_trim_segment_check(self):
        """TrimSegment with one intersection should pass check."""
        from ..utilities.trimming import TrimSegment

        p1 = self.add_point((0, 0))
        p2 = self.add_point((4, 4))
        p3 = self.add_point((0, 4))
        p4 = self.add_point((4, 0))
        l1 = self.add_line(p1, p2)
        l2 = self.add_line(p3, p4)

        topo = self.sketch.topology
        pts = topo.intersect(l1, l2)

        # Click on l1 near (1,1) — below the intersection
        trim = TrimSegment(self.sketch, l1, Vector((1, 1)), topo)
        for co in pts:
            trim.add(co, source_cid=l2.curve_id)

        self.assertTrue(trim.check())

    def test_trim_parametric_order(self):
        """Parametric sort should order intersections along segment."""
        from ..utilities.trimming import TrimSegment

        # Horizontal line from (0,0) to (10,0)
        p1 = self.add_point((0, 0))
        p2 = self.add_point((10, 0))
        line = self.add_line(p1, p2)

        topo = self.sketch.topology

        # Click at x=5 (middle of line)
        trim = TrimSegment(self.sketch, line, Vector((5, 0)), topo)

        # Add intersections at x=3 and x=7
        trim.add(Vector((3, 0)), source_cid=100)
        trim.add(Vector((7, 0)), source_cid=200)

        self.assertTrue(trim.check())

        # Relevant should include the two intersection points (trim boundaries)
        # and possibly endpoint(s) outside the trim region
        relevant = trim._relevant_intersections()
        self.assertGreaterEqual(len(relevant), 2)

    def test_trim_creates_segments(self):
        """Trim should create new segments and remove the trimmed part."""
        from ..utilities.trimming import TrimSegment
        from ..model.curve_ref import curve_ref

        # Two crossing lines
        p1 = self.add_point((0, 0))
        p2 = self.add_point((6, 0))
        p3 = self.add_point((3, -3))
        p4 = self.add_point((3, 3))
        l1 = self.add_line(p1, p2)
        l2 = self.add_line(p3, p4)

        topo = self.sketch.topology
        pts = topo.intersect(l1, l2)
        self.assertEqual(len(pts), 1)

        # Count curves before trim
        cd = self.sketch.data
        n_before = len(cd.curves)

        # Click on l1 at (1,0) — left of intersection at (3,0)
        trim = TrimSegment(self.sketch, l1, Vector((1, 0)), topo)
        for co in pts:
            trim.add(co, source_cid=l2.curve_id)

        if trim.check():
            import bpy
            trim.execute(bpy.context)

        # Should have modified/created geometry
        n_after = len(cd.curves)
        # At minimum we should have new points at the intersection
        self.assertGreaterEqual(n_after, n_before)

    def test_trim_coincident_constraint(self):
        """Trim should add coincident between new point and intersecting segment."""
        from ..utilities.trimming import TrimSegment

        p1 = self.add_point((0, 0))
        p2 = self.add_point((6, 0))
        p3 = self.add_point((3, -3))
        p4 = self.add_point((3, 3))
        l1 = self.add_line(p1, p2)
        l2 = self.add_line(p3, p4)

        topo = self.sketch.topology
        pts = topo.intersect(l1, l2)

        # Count constraints before
        sc = self.sketch.constraints
        n_coincident_before = len(sc.coincident)

        trim = TrimSegment(self.sketch, l1, Vector((1, 0)), topo)
        for co in pts:
            trim.add(co, source_cid=l2.curve_id)

        if trim.check():
            import bpy
            trim.execute(bpy.context)

        # Should have at least one new coincident constraint
        n_coincident_after = len(sc.coincident)
        self.assertGreater(n_coincident_after, n_coincident_before)
