"""Regression for #532: tangent constraints converge on any workplane.

Reported (on the pre-native-curves build) that tangent constraints between a
line and an arc failed to converge on the XZ/YZ workplanes -- and, for several
users, even on XY -- producing "Didn't converge" and red tangent icons. The
native solver builds tangency as a perpendicular between the line and the
radius line (center -> tangent point), which is stable on every workplane.
"""

from .utils import BgsTestCase
from ..model import sketch_ref as sr
from ..model import curve_ref as cr
from ..utilities import curve_data as cd_mod


class TestTangentWorkplanes(BgsTestCase):
    def _sketch_on(self, plane_attr):
        self.entities.ensure_origin_elements(self.context)
        entity_sketch = self.entities.add_sketch(getattr(self.entities, plane_attr))
        cd_mod.ensure_sketch_curve_object(entity_sketch)
        sr.stamp_sketch_props(entity_sketch.target_object)
        sketch = sr.Sketch(entity_sketch.target_object)
        sr.set_active_sketch(self.context, entity_sketch.target_object)
        return sketch

    def _line_arc_tangent(self, plane):
        sketch = self._sketch_on(plane)
        sc = sketch.constraints
        a = cr.PointRef.create(sketch, (0, 0), fixed=True)
        b = cr.PointRef.create(sketch, (4, 0))
        line = cr.LineRef.create(sketch, a, b)
        sc.add_horizontal(curve_id_1=line.curve_id)
        ct = cr.PointRef.create(sketch, (4, 1))
        end = cr.PointRef.create(sketch, (5, 1))
        arc = cr.ArcRef.create(sketch, ct, b, end)
        sc.add_tangent(curve_id_1=arc.curve_id, curve_id_2=line.curve_id)
        return sketch

    def test_line_arc_tangent_converges_on_all_planes(self):
        for plane in ("origin_plane_XY", "origin_plane_XZ", "origin_plane_YZ"):
            sketch = self._line_arc_tangent(plane)
            self.assertTrue(sketch.solve(self.context), f"tangent failed on {plane}")
            self.assertEqual(sketch.solver_state, "OKAY", plane)

    def test_arc_arc_tangent_converges_off_axis(self):
        for plane in ("origin_plane_XZ", "origin_plane_YZ"):
            sketch = self._sketch_on(plane)
            sc = sketch.constraints
            c1 = cr.PointRef.create(sketch, (0, 0), fixed=True)
            arc1 = cr.ArcRef.create(
                sketch, c1, cr.PointRef.create(sketch, (2, 0)), cr.PointRef.create(sketch, (0, 2))
            )
            c2 = cr.PointRef.create(sketch, (5, 0))
            arc2 = cr.ArcRef.create(
                sketch, c2, cr.PointRef.create(sketch, (7, 0)), cr.PointRef.create(sketch, (5, 2))
            )
            sc.add_tangent(curve_id_1=arc1.curve_id, curve_id_2=arc2.curve_id)
            self.assertTrue(sketch.solve(self.context), plane)
            self.assertEqual(sketch.solver_state, "OKAY", plane)
