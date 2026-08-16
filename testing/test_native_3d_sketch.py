"""Regression coverage for native free-3D sketches (#607)."""

from mathutils import Vector

from .utils import BgsTestCase


class TestNative3DSketch(BgsTestCase):
    def setUp(self):
        from ..model.native_3d import create_3d_sketch
        from ..model.sketch_ref import set_active_sketch

        self.sketch = create_3d_sketch(self.context, self._testMethodName)
        set_active_sketch(self.context, self.sketch)
        return super().setUp()

    def tearDown(self):
        from ..model.sketch_ref import set_active_sketch

        set_active_sketch(self.context, None)
        self.sketch.remove_objects()
        return super().tearDown()

    def test_sketch_uses_origin_empty_without_workplane_constraint(self):
        obj = self.sketch.target_object
        origin = obj.parent

        self.assertIsNotNone(origin)
        self.assertEqual(origin.type, "EMPTY")
        self.assertTrue(origin.get("is_3d_sketch_origin", False))
        self.assertEqual(self.sketch.workplane_object, origin)
        self.assertEqual(tuple(obj.lock_location), (True, True, True))
        self.assertEqual(tuple(obj.lock_rotation), (True, True, True))
        self.assertEqual(tuple(obj.lock_scale), (True, True, True))

    def test_axis_and_plane_lock_geometry(self):
        from ..operators.base_sketch_3d import resolve_locked_position

        anchor = Vector((1.0, 1.0, 1.0))
        point = Vector((2.0, 3.0, 4.0))

        x_axis = resolve_locked_position(point, anchor, axis_lock=0)
        self.assertLess((x_axis - Vector((2.0, 1.0, 1.0))).length, 1e-6)

        yz_plane = resolve_locked_position(point, anchor, plane_lock=0)
        self.assertLess((yz_plane - Vector((1.0, 3.0, 4.0))).length, 1e-6)

        xy_plane = resolve_locked_position(point, anchor, plane_lock=2)
        self.assertLess((xy_plane - Vector((2.0, 3.0, 1.0))).length, 1e-6)

    def test_points_and_lines_preserve_xyz(self):
        from ..model.native_3d import create_line_3d, create_point_3d, is_3d_sketch

        p1 = create_point_3d(self.sketch, (1.0, 2.0, 3.0), fixed=True)
        p2 = create_point_3d(self.sketch, (4.0, 6.0, 8.0))
        line = create_line_3d(self.sketch, p1, p2)

        self.assertTrue(is_3d_sketch(self.sketch))
        self.assertAlmostEqual(p1.location.z, 3.0)
        self.assertAlmostEqual(p2.location.z, 8.0)
        self.assertAlmostEqual(
            (line.p2.location - line.p1.location).length, 7.0710678, places=5
        )

    def test_distance_solves_in_free_3d_and_dimension_is_world_space(self):
        from ..model.native_3d import create_line_3d, create_point_3d

        p1 = create_point_3d(self.sketch, (0.0, 0.0, 0.0), fixed=True)
        p2 = create_point_3d(self.sketch, (0.0, 0.0, 4.0))
        create_line_3d(self.sketch, p1, p2)

        distance = self.sketch.constraints.add_distance(
            curve_id_1=p1.curve_id,
            curve_id_2=p2.curve_id,
            value=5.0,
        )

        self.assertFalse(distance.use_align())
        self.assertTrue(self.sketch.solve(self.context))
        self.assertAlmostEqual((p2.location - p1.location).length, 5.0, places=4)
        self.assertGreater(abs(p2.location.z), 1e-4)

        matrix = distance.matrix_basis()
        expected_midpoint = (p1.location + p2.location) / 2.0
        self.assertLess((matrix.translation - expected_midpoint).length, 1e-5)

        dimension_axis = Vector(matrix.col[0][:3]).normalized()
        solved_axis = (p2.location - p1.location).normalized()
        self.assertAlmostEqual(abs(dimension_axis.dot(solved_axis)), 1.0, places=5)
