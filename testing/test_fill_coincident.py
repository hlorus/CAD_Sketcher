"""Regression for #560: a shape built from coincided lines is fillable.

Reported (on the pre-native-curves build) that a square drawn as four separate
lines whose endpoints are joined with coincidence constraints would not fill
with a mesh -- only the box tool's single closed curve filled.

The generated mesh comes from a Geometry Nodes pipeline that merges points by
distance and fills the resulting closed curve, so the fill only works when the
coincided endpoints actually solve to the *same* position. Under the native
curve model they do; this guards that precondition.

Note: the filled mesh itself is produced by the GN modifier on a Curves-type
object, which Blender cannot convert to a readable mesh in ``--background``
(``to_mesh``/``new_from_object`` support mesh objects only). The fill is verified
interactively; here we assert the merge precondition that was actually broken.
"""

from mathutils import Vector

from .utils import Sketch2dTestCase
from ..utilities.curve_data import refresh_curve_geometry


class TestFillCoincident(Sketch2dTestCase):
    def test_coincided_square_endpoints_merge(self):
        sc = self.sketch.constraints
        corners = [(0, 0), (4, 0), (4, 4), (0, 4)]

        # Four independent lines, each with its own endpoints.
        lines = []
        for i in range(4):
            p0 = self.add_point(corners[i])
            p1 = self.add_point(corners[(i + 1) % 4])
            lines.append((p0, p1, self.add_line(p0, p1)))

        # Join consecutive corners: line[i].end coincident with line[i+1].start.
        for i in range(4):
            sc.add_coincident(
                curve_id_1=lines[i][1].curve_id,
                curve_id_2=lines[(i + 1) % 4][0].curve_id,
            )

        self.solve()
        refresh_curve_geometry(self.sketch)

        self.assertEqual(self.sketch.solver_state, "OKAY")

        # Each coincided endpoint pair must solve to an identical position, so
        # the GN merge-by-distance closes the loop and the fill succeeds.
        for i in range(4):
            end = Vector(lines[i][1].co[:2])
            start = Vector(lines[(i + 1) % 4][0].co[:2])
            self.assertLess(
                (end - start).length,
                1e-4,
                f"corner {i} endpoints did not merge -> shape would not fill",
            )
