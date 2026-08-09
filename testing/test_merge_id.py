"""Weld-identity ids for the 5.2 Merge Points fill path.

``compute_merge_ids`` assigns each curve point an integer so that segment
endpoints meeting at a junction share one id. The convert node group welds mesh
vertices by this id (gated to true endpoints via valence), closing loops by
identity rather than proximity. These tests check the id assignment itself; the
node-group weld is verified separately (and in the viewport on 5.2).
"""

from ..model.constants import SketchCurveType
from ..utilities.curve_data import compute_merge_ids, get_uuid
from .utils import Sketch2dTestCase


class TestMergeIds(Sketch2dTestCase):
    def _endpoint_ids(self):
        """Map each endpoint point-curve id -> set of merge_ids seen for it."""
        cd = self.sketch.target_object.data
        ta = cd.attributes.get("sketch_type")
        mid = cd.attributes.get("merge_id")
        seen = {}
        for i in range(len(cd.curves)):
            if ta.data[i].value not in (SketchCurveType.LINE, SketchCurveType.ARC):
                continue
            cv = cd.curves[i]
            npt = cv.points_length
            ends = (
                ("start_point_id", cv.points[0].index),
                ("end_point_id", cv.points[npt - 1].index),
            )
            for field, pidx in ends:
                pid = get_uuid(cd, field, i)
                seen.setdefault(pid, set()).add(mid.data[pidx].value)
        return seen

    def test_shared_junction_same_id(self):
        """Segments meeting at a corner get the same id at that endpoint."""
        a = self.add_point((0, 0))
        b = self.add_point((4, 0))
        c = self.add_point((2, 3))
        self.add_line(a, b)
        self.add_line(b, c)
        self.add_line(c, a)
        compute_merge_ids(self.sketch)

        seen = self._endpoint_ids()
        # each junction point resolves to exactly one weld id ...
        for pid, ids in seen.items():
            self.assertEqual(len(ids), 1, f"{pid}: inconsistent merge_ids {ids}")
        # ... and there are three distinct, non-zero junctions.
        junctions = {next(iter(ids)) for ids in seen.values()}
        self.assertEqual(len(junctions), 3)
        self.assertNotIn(0, junctions)

    def test_disconnected_segments_distinct_ids(self):
        """Two unconnected lines yield four distinct endpoint ids (no weld)."""
        a = self.add_point((0, 0))
        b = self.add_point((1, 0))
        self.add_line(a, b)
        c = self.add_point((5, 0))
        d = self.add_point((6, 0))
        self.add_line(c, d)
        compute_merge_ids(self.sketch)

        junctions = {next(iter(ids)) for ids in self._endpoint_ids().values()}
        self.assertEqual(len(junctions), 4)

    def test_interior_and_center_points_stay_zero(self):
        """Only segment endpoints carry a weld id; centers/points keep 0."""
        p0 = self.add_point((0, 0), fixed=True)
        p1 = self.add_point((3, 0))
        p2 = self.add_point((0, 3))
        self.add_arc(p0, p1, p2)  # p0 is the arc center -> id 0
        compute_merge_ids(self.sketch)

        cd = self.sketch.target_object.data
        ta = cd.attributes.get("sketch_type")
        mid = cd.attributes.get("merge_id")
        for i in range(len(cd.curves)):
            if ta.data[i].value != SketchCurveType.POINT:
                continue
            # the center point curve (p0) participates in no segment endpoint
            cid = get_uuid(cd, "curve_id", i)
            if cid == p0.curve_id:
                pidx = cd.curves[i].points[0].index
                self.assertEqual(mid.data[pidx].value, 0)
