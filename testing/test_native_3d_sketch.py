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
