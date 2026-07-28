"""Regression: a tangent constraint shows a single marker at the tangent point.

Follow-up to #533. The default per-curve placement drew a tangent icon on both
referenced curves (line and arc). The marker should appear once, and sit at the
tangent point -- the foot of the perpendicular from the curved element's center
onto the line, which is independent of the arc's drawing direction.
"""

from mathutils import Vector

from .utils import Sketch2dTestCase
from ..utilities.curve_data import get_curve_type
from ..model.constants import SketchCurveType


class TestTangentPlacement(Sketch2dTestCase):
    def _setup_line_arc_tangent(self, arc_reversed):
        sc = self.sketch.constraints
        a = self.add_point((0, 0), fixed=True)
        b = self.add_point((4, 0))  # tangent point
        line = self.add_line(a, b)
        sc.add_horizontal(curve_id_1=line.curve_id)
        ct = self.add_point((4, 1))
        far = self.add_point((5, 1))
        # arc_reversed draws the arc from the far end to the tangent point.
        arc = self.add_arc(ct, far, b) if arc_reversed else self.add_arc(ct, b, far)
        t = sc.add_tangent(curve_id_1=line.curve_id, curve_id_2=arc.curve_id)
        self.solve()
        return t, arc

    def test_single_marker(self):
        t, _ = self._setup_line_arc_tangent(arc_reversed=False)
        placements = t.curve_id_placements()
        self.assertEqual(len(placements), 1, "tangent must show a single marker")
        self.assertEqual(
            get_curve_type(self.sketch, placements[0]), SketchCurveType.ARC
        )

    def test_marker_at_tangent_point_direction_independent(self):
        for arc_reversed in (False, True):
            t, _ = self._setup_line_arc_tangent(arc_reversed)
            pos = t.marker_position(self.sketch)
            self.assertIsNotNone(pos)
            self.assertLess(
                (Vector(pos[:2]) - Vector((4.0, 0.0))).length,
                1e-3,
                f"tangent marker misplaced (arc_reversed={arc_reversed})",
            )
