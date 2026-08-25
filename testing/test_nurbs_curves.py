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
            SketchCurveType.ARC: BEZIER,
        }
        for kind, want in expected.items():
            self.assertEqual(_type_of(cd, kind)[0], want)

        refresh_curve_geometry(self.sketch)

        cd = self.sketch.target_object.data
        for kind, want in expected.items():
            self.assertEqual(
                _type_of(cd, kind)[0], want, f"{kind} type lost through refresh"
            )
