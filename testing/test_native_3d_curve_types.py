"""Regression coverage for Blender 5.0-safe native 3D curve types (#607)."""

from .utils import BgsTestCase


class TestNative3DCurveTypes(BgsTestCase):
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

    def test_native_3d_point_and_line_are_explicit_poly_curves(self):
        from ..model.native_3d import create_line_3d, create_point_3d
        from ..utilities.curve_data import get_curve_data

        p1 = create_point_3d(self.sketch, (1.0, 2.0, 3.0), fixed=True)
        p2 = create_point_3d(self.sketch, (4.0, 5.0, 6.0))
        line = create_line_3d(self.sketch, p1, p2)

        # Blender 5.0 defaults Curves.set_types() to CATMULL_ROM (0). Native
        # 3D point/line primitives are linear and must be explicit POLY (1),
        # avoiding degenerate one/two-point nonlinear splines in the viewport
        # curve evaluation path.
        for ref in (p1, p2, line):
            curve_data, curve_idx, _curve = get_curve_data(self.sketch, ref.curve_id)
            self.assertIsNotNone(curve_data)
            curve_type = curve_data.attributes.get("curve_type")
            self.assertIsNotNone(curve_type)
            self.assertEqual(curve_type.domain, "CURVE")
            self.assertEqual(curve_type.data[curve_idx].value, 1)

    def test_refresh_preserves_poly_curve_types_and_xyz(self):
        """The shared topology refresh must not planarize or retype free-3D data."""
        from ..model.native_3d import create_line_3d, create_point_3d
        from ..utilities.curve_data import get_curve_data, refresh_curve_geometry

        p1 = create_point_3d(self.sketch, (1.25, -2.5, 3.75), fixed=True)
        p2 = create_point_3d(self.sketch, (-4.5, 5.25, 6.5))
        line = create_line_3d(self.sketch, p1, p2)
        refs = (p1, p2, line)

        def snapshot(ref):
            curve_data, curve_idx, curve = get_curve_data(self.sketch, ref.curve_id)
            self.assertIsNotNone(curve_data)
            curve_type = curve_data.attributes.get("curve_type")
            self.assertIsNotNone(curve_type)
            positions = [
                tuple(curve_data.points[point.index].position) for point in curve.points
            ]
            return curve_type.data[curve_idx].value, positions

        before = {ref.curve_id: snapshot(ref) for ref in refs}

        refresh_curve_geometry(self.sketch)

        for ref in refs:
            curve_type, positions = snapshot(ref)
            before_type, before_positions = before[ref.curve_id]
            self.assertEqual(before_type, 1)
            self.assertEqual(curve_type, 1)
            self.assertEqual(len(positions), len(before_positions))
            for actual, expected in zip(positions, before_positions):
                for actual_axis, expected_axis in zip(actual, expected):
                    self.assertAlmostEqual(actual_axis, expected_axis, places=6)
