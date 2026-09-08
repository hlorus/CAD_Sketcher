"""Regression for #560: a shape built from coincided lines is fillable.

Reported (on the pre-native-curves build) that a square drawn as four separate
lines whose endpoints are joined with coincidence constraints would not fill
with a mesh -- only the box tool's single closed curve filled.

The generated mesh comes from a Geometry Nodes pipeline that merges points by
distance and fills the resulting closed curve, so the fill only works when the
coincided endpoints actually solve to the *same* position. Under the native
curve model they do; this guards that precondition.

Note: ``to_mesh``/``new_from_object`` can't read a Curves-type object in
``--background``, but ``bpy.ops.object.convert(target="MESH")`` on a copy applies
the GN modifier and yields a readable mesh -- so the end-to-end tests here
measure the actual filled area, not just the merge precondition.
"""

import math

import bpy
from mathutils import Vector

from ..model.constants import SketchCurveType
from ..utilities.curve_data import compute_merge_ids, get_uuid, refresh_curve_geometry
from .utils import Sketch2dTestCase


class TestFillCoincident(Sketch2dTestCase):
    def _build_coincided_square(self):
        """Four independent lines whose corners are joined by coincidence."""
        sc = self.sketch.constraints
        corners = [(0, 0), (4, 0), (4, 4), (0, 4)]
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
        return lines

    def _filled_area(self):
        """Total area of the real GN fill for the active sketch.

        ``to_mesh`` can't read a Curves object headless, but converting a copy to
        a mesh applies the same ``CAD Sketcher Convert`` modifier and is readable.
        """
        ob = self.sketch.target_object
        scene = self.context.scene
        dup = ob.copy()
        dup.data = ob.data.copy()
        scene.collection.objects.link(dup)
        for other in scene.collection.objects:
            other.select_set(False)
        dup.select_set(True)
        self.context.view_layer.objects.active = dup
        bpy.ops.object.convert(target="MESH")
        area = sum(p.area for p in dup.data.polygons)
        bpy.data.objects.remove(dup, do_unlink=True)
        return area

    def _endpoint_merge_id(self, point_curve_id):
        """The weld id of the segment endpoint vertex referencing ``point_curve_id``."""
        cd = self.sketch.target_object.data
        ta = cd.attributes.get("sketch_type")
        mid = cd.attributes.get("merge_id")
        for i in range(len(cd.curves)):
            if ta.data[i].value != SketchCurveType.LINE:
                continue
            cv = cd.curves[i]
            last = cv.points_length - 1
            if get_uuid(cd, "start_point_id", i) == point_curve_id:
                return mid.data[cv.points[0].index].value
            if get_uuid(cd, "end_point_id", i) == point_curve_id:
                return mid.data[cv.points[last].index].value
        return None

    def test_coincided_square_endpoints_merge(self):
        lines = self._build_coincided_square()

        self.solve()
        refresh_curve_geometry(self.sketch)

        self.assertEqual(self.sketch.solver_state, "OKAY")

        # Each coincided endpoint pair must solve to an identical position, so
        # the GN weld closes the loop and the fill succeeds.
        for i in range(4):
            end = Vector(lines[i][1].co[:2])
            start = Vector(lines[(i + 1) % 4][0].co[:2])
            self.assertLess(
                (end - start).length,
                1e-4,
                f"corner {i} endpoints did not merge -> shape would not fill",
            )

    def test_coincided_square_corners_share_weld_id(self):
        """Coincidence-joined corners must weld under the 5.2 identity path.

        The convert node group welds mesh vertices by ``merge_id`` (Merge Points),
        fusing only vertices that share an id. Two endpoints tied by a coincidence
        constraint sit at the same position but belong to distinct point entities,
        so unless the coincidence is folded into ``merge_id`` they get different
        ids, never weld, and the loop stays open -- FillCurve then fills only any
        inner shape, not the square. Guards that regression (fundamental fill).
        """
        lines = self._build_coincided_square()

        self.solve()
        refresh_curve_geometry(self.sketch)
        compute_merge_ids(self.sketch)

        for i in range(4):
            end_id = self._endpoint_merge_id(lines[i][1].curve_id)
            start_id = self._endpoint_merge_id(lines[(i + 1) % 4][0].curve_id)
            self.assertIsNotNone(end_id)
            self.assertIsNotNone(start_id)
            self.assertGreater(
                end_id, 0, f"corner {i} endpoint has no weld id (id 0 -> never welds)"
            )
            self.assertEqual(
                end_id,
                start_id,
                f"corner {i} coincided endpoints have different merge_ids "
                f"({end_id} != {start_id}) -> corner never welds, square will not fill",
            )

    def test_coincided_square_actually_fills(self):
        """End-to-end: the coincidence-joined square produces a filled face.

        Reads the real GN fill (not just the weld precondition); before the
        merge_id union fix the corners stayed open and the area was ~0.
        """
        self._build_coincided_square()
        self.solve()
        refresh_curve_geometry(self.sketch)

        self.assertAlmostEqual(
            self._filled_area(),
            16.0,  # 4 x 4 square
            delta=0.1,
            msg="coincidence-joined square did not fill (loop stayed open)",
        )

    def test_rectangle_with_inner_circle_fills_as_ring(self):
        """End-to-end: a rectangle with an inner circle fills as a ring.

        Exercises the winding normalization through the real convert group: the
        square minus the circular hole, independent of loop winding/order.
        """
        # Rectangle from four lines sharing corner points (rectangle-tool style).
        corners = [(0, 0), (6, 0), (6, 4), (0, 4)]
        pts = [self.add_point(c) for c in corners]
        for i in range(4):
            self.add_line(pts[i], pts[(i + 1) % 4])
        center = self.add_point((3, 2))
        self.add_circle(center, 1.0)

        self.solve()
        refresh_curve_geometry(self.sketch)

        ring = 6 * 4 - math.pi * 1.0**2
        self.assertAlmostEqual(
            self._filled_area(),
            ring,
            delta=0.2,
            msg="rectangle+circle did not fill as a ring (winding flip or open loop)",
        )
