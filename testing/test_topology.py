"""Tests for SketchTopology — connectivity, geometry, path walking, modification."""

import math
from mathutils import Vector
from .utils import Sketch2dTestCase


class TestTopologyConnectivity(Sketch2dTestCase):
    """Test connectivity queries."""

    def test_connected_segments_single_line(self):
        p1 = self.add_point((0, 0))
        p2 = self.add_point((3, 0))
        line = self.add_line(p1, p2)

        topo = self.sketch.topology
        connected = topo.get_connected_segments(p1.curve_id)
        self.assertEqual(len(connected), 1)
        self.assertEqual(connected[0][0].curve_id, line.curve_id)
        self.assertEqual(connected[0][1], "start")

    def test_connected_segments_corner(self):
        p1 = self.add_point((0, 0))
        p2 = self.add_point((3, 0))
        p3 = self.add_point((3, 4))
        l1 = self.add_line(p1, p2)
        l2 = self.add_line(p2, p3)

        topo = self.sketch.topology
        # p2 connects to both lines
        connected = topo.get_connected_segments(p2.curve_id)
        self.assertEqual(len(connected), 2)
        cids = {c[0].curve_id for c in connected}
        self.assertIn(l1.curve_id, cids)
        self.assertIn(l2.curve_id, cids)

    def test_connection_point(self):
        p1 = self.add_point((0, 0))
        p2 = self.add_point((3, 0))
        p3 = self.add_point((3, 4))
        l1 = self.add_line(p1, p2)
        l2 = self.add_line(p2, p3)

        topo = self.sketch.topology
        shared = topo.get_connection_point(l1, l2)
        self.assertIsNotNone(shared)
        self.assertEqual(shared.curve_id, p2.curve_id)

    def test_no_connection_point(self):
        p1 = self.add_point((0, 0))
        p2 = self.add_point((3, 0))
        p3 = self.add_point((5, 5))
        p4 = self.add_point((8, 5))
        l1 = self.add_line(p1, p2)
        l2 = self.add_line(p3, p4)

        topo = self.sketch.topology
        shared = topo.get_connection_point(l1, l2)
        self.assertIsNone(shared)

    def test_connection_points_line(self):
        p1 = self.add_point((0, 0))
        p2 = self.add_point((3, 0))
        line = self.add_line(p1, p2)

        topo = self.sketch.topology
        pts = topo.connection_points(line)
        self.assertEqual(len(pts), 2)

    def test_connection_points_circle(self):
        ct = self.add_point((0, 0))
        circle = self.add_circle(ct, 2.0)

        topo = self.sketch.topology
        pts = topo.connection_points(circle)
        self.assertEqual(len(pts), 0)


class TestTopologyDirection(Sketch2dTestCase):
    """Test direction and angle queries."""

    def test_direction_at_start(self):
        p1 = self.add_point((0, 0))
        p2 = self.add_point((3, 0))
        line = self.add_line(p1, p2)

        topo = self.sketch.topology
        d = topo.direction_at_point(line, p1.curve_id)
        self.assertAlmostEqual(d.x, 1.0, places=3)
        self.assertAlmostEqual(d.y, 0.0, places=3)

    def test_direction_at_end(self):
        p1 = self.add_point((0, 0))
        p2 = self.add_point((3, 0))
        line = self.add_line(p1, p2)

        topo = self.sketch.topology
        d = topo.direction_at_point(line, p2.curve_id)
        self.assertAlmostEqual(d.x, -1.0, places=3)
        self.assertAlmostEqual(d.y, 0.0, places=3)

    def test_connection_angle_right_angle(self):
        p1 = self.add_point((0, 0))
        p2 = self.add_point((3, 0))
        p3 = self.add_point((3, 4))
        l1 = self.add_line(p1, p2)
        l2 = self.add_line(p2, p3)

        topo = self.sketch.topology
        angle = topo.connection_angle(l1, l2, p2.curve_id)
        self.assertIsNotNone(angle)
        self.assertAlmostEqual(abs(angle), math.pi / 2, places=2)


class TestTopologyGeometry(Sketch2dTestCase):
    """Test geometric queries."""

    def test_intersect_crossing_lines(self):
        p1 = self.add_point((0, 0))
        p2 = self.add_point((4, 4))
        p3 = self.add_point((0, 4))
        p4 = self.add_point((4, 0))
        l1 = self.add_line(p1, p2)
        l2 = self.add_line(p3, p4)

        topo = self.sketch.topology
        pts = topo.intersect(l1, l2)
        self.assertEqual(len(pts), 1)
        self.assertAlmostEqual(pts[0].x, 2.0, places=2)
        self.assertAlmostEqual(pts[0].y, 2.0, places=2)

    def test_intersect_parallel_lines(self):
        p1 = self.add_point((0, 0))
        p2 = self.add_point((4, 0))
        p3 = self.add_point((0, 2))
        p4 = self.add_point((4, 2))
        l1 = self.add_line(p1, p2)
        l2 = self.add_line(p3, p4)

        topo = self.sketch.topology
        pts = topo.intersect(l1, l2)
        self.assertEqual(len(pts), 0)

    def test_intersect_line_circle(self):
        p1 = self.add_point((-5, 0))
        p2 = self.add_point((5, 0))
        ct = self.add_point((0, 0))
        line = self.add_line(p1, p2)
        circle = self.add_circle(ct, 2.0)

        topo = self.sketch.topology
        pts = topo.intersect(line, circle)
        self.assertEqual(len(pts), 2)

    def test_project_point_on_line(self):
        p1 = self.add_point((0, 0))
        p2 = self.add_point((4, 0))
        line = self.add_line(p1, p2)

        topo = self.sketch.topology
        proj = topo.project_point(line, Vector((2, 3)))
        self.assertAlmostEqual(proj.x, 2.0, places=3)
        self.assertAlmostEqual(proj.y, 0.0, places=3)

    def test_project_point_on_circle(self):
        ct = self.add_point((0, 0))
        circle = self.add_circle(ct, 3.0)

        topo = self.sketch.topology
        proj = topo.project_point(circle, Vector((5, 0)))
        self.assertAlmostEqual(proj.x, 3.0, places=3)
        self.assertAlmostEqual(proj.y, 0.0, places=3)

    def test_distance_along_line(self):
        p1 = self.add_point((0, 0))
        p2 = self.add_point((4, 0))
        line = self.add_line(p1, p2)

        topo = self.sketch.topology
        d = topo.distance_along(line, Vector((1, 0)), Vector((3, 0)))
        self.assertAlmostEqual(d, 2.0, places=3)

    def test_normal_line(self):
        p1 = self.add_point((0, 0))
        p2 = self.add_point((4, 0))
        line = self.add_line(p1, p2)

        topo = self.sketch.topology
        n = topo.normal_at(line)
        self.assertAlmostEqual(abs(n.y), 1.0, places=3)
        self.assertAlmostEqual(n.x, 0.0, places=3)

    def test_normal_circle(self):
        ct = self.add_point((0, 0))
        circle = self.add_circle(ct, 3.0)

        topo = self.sketch.topology
        n = topo.normal_at(circle, Vector((3, 0)))
        self.assertAlmostEqual(n.x, 1.0, places=3)
        self.assertAlmostEqual(n.y, 0.0, places=3)


class TestTopologyPathWalking(Sketch2dTestCase):
    """Test path walking."""

    def test_walk_single_line(self):
        p1 = self.add_point((0, 0))
        p2 = self.add_point((3, 0))
        line = self.add_line(p1, p2)

        topo = self.sketch.topology
        path = topo.walk_path(line)
        self.assertEqual(len(path.segments), 1)
        self.assertFalse(path.is_cyclic)

    def test_walk_connected_lines(self):
        p1 = self.add_point((0, 0))
        p2 = self.add_point((3, 0))
        p3 = self.add_point((3, 4))
        l1 = self.add_line(p1, p2)
        l2 = self.add_line(p2, p3)

        topo = self.sketch.topology
        path = topo.walk_path(l1)
        self.assertEqual(len(path.segments), 2)
        self.assertFalse(path.is_cyclic)

    def test_walk_triangle_cyclic(self):
        p1 = self.add_point((0, 0))
        p2 = self.add_point((3, 0))
        p3 = self.add_point((1.5, 3))
        l1 = self.add_line(p1, p2)
        l2 = self.add_line(p2, p3)
        l3 = self.add_line(p3, p1)

        topo = self.sketch.topology
        path = topo.walk_path(l1)
        self.assertEqual(len(path.segments), 3)
        self.assertTrue(path.is_cyclic)

    def test_limit_points(self):
        p1 = self.add_point((0, 0))
        p2 = self.add_point((3, 0))
        p3 = self.add_point((6, 0))
        l1 = self.add_line(p1, p2)
        l2 = self.add_line(p2, p3)

        topo = self.sketch.topology
        path = topo.walk_path(l1)
        limits = topo.get_limit_points(path)
        self.assertIsNotNone(limits)
        limit_ids = {limits[0].curve_id, limits[1].curve_id}
        self.assertIn(p1.curve_id, limit_ids)
        self.assertIn(p3.curve_id, limit_ids)

    def test_walk_all_paths(self):
        # Two separate lines
        p1 = self.add_point((0, 0))
        p2 = self.add_point((3, 0))
        p3 = self.add_point((5, 5))
        p4 = self.add_point((8, 5))
        l1 = self.add_line(p1, p2)
        l2 = self.add_line(p3, p4)

        topo = self.sketch.topology
        paths = topo.walk_all_paths()
        self.assertEqual(len(paths), 2)


class TestTopologyModification(Sketch2dTestCase):
    """Test modification helpers."""

    def test_replace_point(self):
        p1 = self.add_point((0, 0))
        p2 = self.add_point((3, 0))
        p3 = self.add_point((5, 0))
        line = self.add_line(p1, p2)

        topo = self.sketch.topology
        topo.replace_point(line, p2.curve_id, p3.curve_id)

        # Re-read the line
        from ..model.curve_ref import curve_ref
        updated = curve_ref(self.sketch, line.curve_id)
        self.assertEqual(updated.p2.curve_id, p3.curve_id)

    def test_create_like_line(self):
        p1 = self.add_point((0, 0))
        p2 = self.add_point((3, 0))
        p3 = self.add_point((5, 0))
        p4 = self.add_point((8, 0))
        line = self.add_line(p1, p2)

        topo = self.sketch.topology
        new_line = topo.create_like(line, p3, p4)
        self.assertIsNotNone(new_line)
        self.assertTrue(new_line.is_line())

    def test_split_segment(self):
        p1 = self.add_point((0, 0))
        p2 = self.add_point((6, 0))
        line = self.add_line(p1, p2)

        mid = self.add_point((3, 0))

        topo = self.sketch.topology
        new_refs = topo.split_segment(line, [mid])
        self.assertEqual(len(new_refs), 1)
        # Original line should now end at mid
        from ..model.curve_ref import curve_ref
        updated = curve_ref(self.sketch, line.curve_id)
        self.assertEqual(updated.p2.curve_id, mid.curve_id)
