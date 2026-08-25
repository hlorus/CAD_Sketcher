"""Stage 1 of the Bezier -> NURBS representation switch.

Lines are POLY, circles are exact periodic rational NURBS, arcs stay BEZIER (for
now). These verify the stored type per entity, that a NURBS circle tessellates to
a mathematically exact ring that fills, and that a mixed-type datablock keeps its
per-curve types across the teardown/rebuild refresh.
"""

import math

from ..model.constants import SketchCurveType
from ..utilities.curve_data import refresh_curve_geometry
from .test_custom_attributes import TestCustomAttributes

# Blender Curves curve_type enum values.
POLY, BEZIER, NURBS = 1, 2, 3


def _type_of(cd, kind):
    st = cd.attributes.get("sketch_type")
    ct = cd.attributes.get("curve_type")
    for i in range(len(cd.curves)):
        if st.data[i].value == kind:
            return ct.data[i].value, cd.curves[i].points_length
    return None, None


class TestNurbsCurves(TestCustomAttributes):
    def test_line_is_poly(self):
        a = self.add_point((0.0, 0.0))
        b = self.add_point((2.0, 0.0))
        self.add_line(a, b)
        ctype, npts = _type_of(self.sketch.target_object.data, SketchCurveType.LINE)
        self.assertEqual(ctype, POLY)
        self.assertEqual(npts, 2)

    def test_circle_is_exact_nurbs(self):
        center = self.add_point((0.0, 0.0))
        self.add_circle(center, 3.0)
        cd = self.sketch.target_object.data
        ctype, npts = _type_of(cd, SketchCurveType.CIRCLE)
        self.assertEqual(ctype, NURBS)
        self.assertEqual(npts, 8)

        converted = self._convert_copy(self.sketch.target_object, fill=True)
        try:
            self.assertGreater(
                len(converted.data.polygons), 0, "circle must fill to a face"
            )
            radii = [math.hypot(v.co.x, v.co.y) for v in converted.data.vertices]
            self.assertTrue(radii)
            # Rational NURBS evaluates an exact circle: every vertex on radius 3.
            for r in radii:
                self.assertAlmostEqual(r, 3.0, delta=1e-4)
        finally:
            self._remove_converted(converted)

    def test_arc_is_exact_nurbs(self):
        center = self.add_point((0.0, 0.0))
        start = self.add_point((2.0, 0.0))
        end = self.add_point((0.0, -2.0))  # 270 deg CCW -> 3 spans
        self.add_arc(center, start, end)
        cd = self.sketch.target_object.data
        ctype, npts = _type_of(cd, SketchCurveType.ARC)
        self.assertEqual(ctype, NURBS)
        self.assertEqual(npts, 7)  # 2 * 3 + 1

        converted = self._convert_copy(self.sketch.target_object, fill=False)
        try:
            radii = [math.hypot(v.co.x, v.co.y) for v in converted.data.vertices]
            self.assertTrue(radii)
            # Rational NURBS evaluates the exact arc: every vertex on radius 2.
            for r in radii:
                self.assertAlmostEqual(r, 2.0, delta=1e-4)
        finally:
            self._remove_converted(converted)

    def _rectangle(self):
        a = self.add_point((0.0, 0.0))
        b = self.add_point((4.0, 0.0))
        c = self.add_point((4.0, 3.0))
        d = self.add_point((0.0, 3.0))
        self.add_line(a, b)
        self.add_line(b, c)
        self.add_line(c, d)
        self.add_line(d, a)

    def test_simple_fill_stays_a_clean_quad(self):
        # N-gon fill: a plain rectangle converts to one quad, no diagonal edge.
        self._rectangle()
        converted = self._convert_copy(self.sketch.target_object, fill=True)
        try:
            self.assertEqual(len(converted.data.polygons), 1)
            self.assertEqual(len(converted.data.polygons[0].vertices), 4)
            self.assertEqual(len(converted.data.edges), 4)
        finally:
            self._remove_converted(converted)

    def test_holed_fill_avoids_concave_ngons(self):
        # A holed profile (rectangle around a circle) fills as concave n-gons that
        # the viewport display-triangulates unstably; the convert triangulates
        # 5+-vertex faces so the result is stable triangles, not flickering n-gons.
        self._rectangle()
        self.add_circle(self.add_point((2.0, 1.5)), 0.8)
        converted = self._convert_copy(self.sketch.target_object, fill=True)
        try:
            self.assertGreater(len(converted.data.polygons), 0)
            self.assertLessEqual(
                max(len(p.vertices) for p in converted.data.polygons), 4,
                "concave holed n-gons must be triangulated",
            )
        finally:
            self._remove_converted(converted)

    def _downgrade_to_bezier(self, kind, bezier_points):
        """Fake an old-file Bezier curve of ``kind``: retype to BEZIER, resize to a
        legacy point count, and re-add the handle attributes migration must drop."""
        cd = self.sketch.target_object.data
        st = cd.attributes.get("sketch_type")
        idx = next(i for i in range(len(cd.curves)) if st.data[i].value == kind)
        cd.set_types(type="BEZIER", indices=[idx])
        if cd.curves[idx].points_length != bezier_points:
            sizes = [cv.points_length for cv in cd.curves]
            sizes[idx] = bezier_points
            cd.resize_curves(sizes)
        for name, dtype in (
            ("handle_left", "FLOAT_VECTOR"), ("handle_right", "FLOAT_VECTOR"),
            ("handle_type_left", "INT8"), ("handle_type_right", "INT8"),
        ):
            if cd.attributes.get(name) is None:
                cd.attributes.new(name, dtype, "POINT")

    def _assert_no_handles(self):
        cd = self.sketch.target_object.data
        for name in ("handle_left", "handle_right",
                     "handle_type_left", "handle_type_right"):
            self.assertIsNone(cd.attributes.get(name), f"{name} not removed")

    def test_migrate_legacy_bezier_circle(self):
        from ..utilities.curve_data import migrate_curves_to_nurbs
        center = self.add_point((0.0, 0.0))
        self.add_circle(center, 3.0)
        self._downgrade_to_bezier(SketchCurveType.CIRCLE, 4)  # legacy 4-point circle

        migrate_curves_to_nurbs(self.sketch)

        cd = self.sketch.target_object.data
        self.assertEqual(_type_of(cd, SketchCurveType.CIRCLE), (NURBS, 8))
        self._assert_no_handles()
        converted = self._convert_copy(self.sketch.target_object, fill=True)
        try:
            self.assertGreater(len(converted.data.polygons), 0)
            for v in converted.data.vertices:
                self.assertAlmostEqual(math.hypot(v.co.x, v.co.y), 3.0, delta=1e-4)
        finally:
            self._remove_converted(converted)

    def test_migrate_legacy_bezier_arc(self):
        from ..utilities.curve_data import migrate_curves_to_nurbs
        center = self.add_point((10.0, 0.0))
        start = self.add_point((12.0, 0.0))
        end = self.add_point((10.0, 2.0))  # 90 deg
        self.add_arc(center, start, end)
        self._downgrade_to_bezier(SketchCurveType.ARC, 2)  # legacy nseg+1 = 2 points

        migrate_curves_to_nurbs(self.sketch)

        cd = self.sketch.target_object.data
        self.assertEqual(_type_of(cd, SketchCurveType.ARC), (NURBS, 3))  # 2*1+1
        self._assert_no_handles()
        converted = self._convert_copy(self.sketch.target_object, fill=False)
        try:
            self.assertGreater(len(converted.data.vertices), 0)
            for v in converted.data.vertices:
                self.assertAlmostEqual(
                    math.hypot(v.co.x - 10.0, v.co.y), 2.0, delta=1e-4
                )
        finally:
            self._remove_converted(converted)

    def test_mixed_types_survive_refresh(self):
        a = self.add_point((0.0, 0.0))
        b = self.add_point((4.0, 0.0))
        self.add_line(a, b)
        self.add_circle(self.add_point((0.0, 6.0)), 2.0)
        center = self.add_point((8.0, 2.0))
        start = self.add_point((10.0, 2.0))
        end = self.add_point((8.0, 4.0))
        self.add_arc(center, start, end)

        cd = self.sketch.target_object.data
        expected = {
            SketchCurveType.LINE: POLY,
            SketchCurveType.CIRCLE: NURBS,
            SketchCurveType.ARC: NURBS,
        }
        for kind, want in expected.items():
            self.assertEqual(_type_of(cd, kind)[0], want)

        refresh_curve_geometry(self.sketch)

        cd = self.sketch.target_object.data
        for kind, want in expected.items():
            self.assertEqual(
                _type_of(cd, kind)[0], want, f"{kind} type lost through refresh"
            )
