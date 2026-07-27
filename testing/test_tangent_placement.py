"""Regression: a tangent constraint shows a single marker (#533 follow-up).

The default per-curve placement drew a tangent icon on both referenced curves
(the line and the arc). The tangent marker should appear once, at the tangent
point -- the arc/circle side, whose placement is its start point.
"""

from .utils import Sketch2dTestCase
from ..utilities.curve_data import get_curve_type
from ..model.constants import SketchCurveType


class TestTangentPlacement(Sketch2dTestCase):
    def _setup_line_arc_tangent(self, line_first):
        sc = self.sketch.constraints
        a = self.add_point((0, 0), fixed=True)
        b = self.add_point((4, 0))
        line = self.add_line(a, b)
        sc.add_horizontal(curve_id_1=line.curve_id)
        ct = self.add_point((4, 1))
        arc = self.add_arc(ct, b, self.add_point((5, 1)))
        if line_first:
            t = sc.add_tangent(curve_id_1=line.curve_id, curve_id_2=arc.curve_id)
        else:
            t = sc.add_tangent(curve_id_1=arc.curve_id, curve_id_2=line.curve_id)
        self.solve()
        return t, arc

    def test_single_marker_on_arc(self):
        for line_first in (True, False):
            t, arc = self._setup_line_arc_tangent(line_first)
            placements = t.curve_id_placements()
            self.assertEqual(len(placements), 1, "tangent must show a single marker")
            self.assertEqual(
                get_curve_type(self.sketch, placements[0]),
                SketchCurveType.ARC,
                "the marker should sit on the curved side (the tangent point)",
            )
