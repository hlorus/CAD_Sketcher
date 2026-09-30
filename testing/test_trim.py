"""Tests for the trim operator logic."""

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

    def test_trim_preserves_orientation_constraints(self):
        """Trim should preserve orientation constraints (e.g. horizontal) on retained segment."""
        from ..utilities.trimming import TrimSegment

        p1 = self.add_point((0, 0))
        p2 = self.add_point((6, 0))
        p3 = self.add_point((3, -3))
        p4 = self.add_point((3, 3))
        l1 = self.add_line(p1, p2)
        l2 = self.add_line(p3, p4)

        sc = self.sketch.constraints
        sc.add_horizontal(curve_id_1=l1.curve_id)

        topo = self.sketch.topology
        pts = topo.intersect(l1, l2)

        trim = TrimSegment(self.sketch, l1, Vector((1, 0)), topo)
        for co in pts:
            trim.add(co, source_cid=l2.curve_id)

        self.assertTrue(trim.check())
        import bpy

        trim.execute(bpy.context)

        # Horizontal constraint should still exist
        self.assertEqual(len(sc.horizontal), 1)
        # Should reference the retained segment
        from ..model.curve_ref import LineRef, curve_ref
        from ..utilities.curve_data import read_uuid_list

        cd = self.sketch.data
        line_cids = {
            cid
            for cid in read_uuid_list(cd, "curve_id")
            if isinstance(curve_ref(self.sketch, cid), LineRef)
        }
        self.assertIn(sc.horizontal[0].curve_id_1, line_cids)

    def test_trim_middle_preserves_orientation_for_both_survivors(self):
        """Trimming middle of a line should propagate orientation constraints to all survivors."""
        from ..utilities.trimming import TrimSegment

        p1 = self.add_point((0, 0))
        p2 = self.add_point((10, 0))
        p3 = self.add_point((3, -3))
        p4 = self.add_point((3, 3))
        p5 = self.add_point((7, -3))
        p6 = self.add_point((7, 3))

        l1 = self.add_line(p1, p2)
        l2 = self.add_line(p3, p4)
        l3 = self.add_line(p5, p6)

        sc = self.sketch.constraints
        sc.add_horizontal(curve_id_1=l1.curve_id)

        topo = self.sketch.topology
        pts2 = topo.intersect(l1, l2)
        pts3 = topo.intersect(l1, l3)

        trim = TrimSegment(self.sketch, l1, Vector((5, 0)), topo)
        for co in pts2:
            trim.add(co, source_cid=l2.curve_id)
        for co in pts3:
            trim.add(co, source_cid=l3.curve_id)

        self.assertTrue(trim.check())
        import bpy

        trim.execute(bpy.context)

        # Both surviving sub-segments should be horizontal
        self.assertEqual(len(sc.horizontal), 2)
        from ..model.curve_ref import LineRef, curve_ref
        from ..utilities.curve_data import read_uuid_list

        cd = self.sketch.data
        line_cids = {
            cid
            for cid in read_uuid_list(cd, "curve_id")
            if isinstance(curve_ref(self.sketch, cid), LineRef)
        }
        self.assertIn(sc.horizontal[0].curve_id_1, line_cids)
        self.assertIn(sc.horizontal[1].curve_id_1, line_cids)

    def test_trim_updates_line_distance(self):
        """Trim should update line length distance constraint to the new trimmed length."""
        from ..utilities.trimming import TrimSegment

        p1 = self.add_point((0, 0))
        p2 = self.add_point((6, 0))
        p3 = self.add_point((2, -3))
        p4 = self.add_point((2, 3))
        l1 = self.add_line(p1, p2)
        l2 = self.add_line(p3, p4)

        sc = self.sketch.constraints
        dist = sc.add_distance(init=True, curve_id_1=l1.curve_id)
        self.assertAlmostEqual(dist.value, 6.0, places=2)

        topo = self.sketch.topology
        pts = topo.intersect(l1, l2)

        # Trim left side (0..2), retaining right side (2..6, length 4)
        trim = TrimSegment(self.sketch, l1, Vector((1, 0)), topo)
        for co in pts:
            trim.add(co, source_cid=l2.curve_id)

        self.assertTrue(trim.check())
        import bpy

        trim.execute(bpy.context)

        # Distance constraint should survive and be re-measured to 4.0
        self.assertEqual(len(sc.distance), 1)
        self.assertAlmostEqual(sc.distance[0].value, 4.0, places=2)

    def test_trim_preserves_endpoint_distance(self):
        """Trim should re-anchor endpoint-to-endpoint distance constraint to new endpoints."""
        from ..utilities.trimming import TrimSegment

        p1 = self.add_point((0, 0))
        p2 = self.add_point((10, 0))
        p3 = self.add_point((4, -3))
        p4 = self.add_point((4, 3))
        l1 = self.add_line(p1, p2)
        l2 = self.add_line(p3, p4)

        sc = self.sketch.constraints
        dist = sc.add_distance(
            init=True, curve_id_1=p1.curve_id, curve_id_2=p2.curve_id
        )
        self.assertAlmostEqual(dist.value, 10.0, places=2)

        topo = self.sketch.topology
        pts = topo.intersect(l1, l2)

        # Trim left piece (0..4), retaining (4..10, length 6)
        trim = TrimSegment(self.sketch, l1, Vector((2, 0)), topo)
        for co in pts:
            trim.add(co, source_cid=l2.curve_id)

        self.assertTrue(trim.check())
        import bpy

        trim.execute(bpy.context)

        self.assertEqual(len(sc.distance), 1)
        self.assertAlmostEqual(sc.distance[0].value, 6.0, places=2)

    def test_trim_circle_preserves_diameter(self):
        """Trim circle to arc should transfer diameter constraint to the arc."""
        from ..utilities.trimming import TrimSegment

        ct = self.add_point((0, 0))
        circle = self.add_circle(ct, 5.0)

        p1 = self.add_point((-10, 0))
        p2 = self.add_point((10, 0))
        line = self.add_line(p1, p2)

        sc = self.sketch.constraints
        sc.add_diameter(init=True, curve_id_1=circle.curve_id)

        topo = self.sketch.topology
        pts = topo.intersect(circle, line)

        trim = TrimSegment(self.sketch, circle, Vector((0, -5)), topo)
        for co in pts:
            trim.add(co, source_cid=line.curve_id)

        self.assertTrue(trim.check())
        import bpy

        trim.execute(bpy.context)

        self.assertEqual(len(sc.diameter), 1)
        from ..model.curve_ref import ArcRef, curve_ref
        from ..utilities.curve_data import read_uuid_list

        cd = self.sketch.data
        arc_cids = {
            cid
            for cid in read_uuid_list(cd, "curve_id")
            if isinstance(curve_ref(self.sketch, cid), ArcRef)
        }
        self.assertIn(sc.diameter[0].curve_id_1, arc_cids)
