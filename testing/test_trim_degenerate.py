"""Degenerate (zero-sweep) arc handling from trimming a circle to nothing.

Trimming a circle down could leave arcs whose start and end points coincide;
their bezier degenerates into a stray sliver (the "trim leftover" lens). The
self-heal removes such arcs and their orphaned points; the trim operation
itself no longer creates them.
"""

from ..model.constants import SketchCurveType
from ..utilities.curve_data import get_uuid
from .utils import Sketch2dTestCase


class TestTrimDegenerate(Sketch2dTestCase):
    def _count(self, kind):
        cd = self.sketch.data
        ta = cd.attributes.get("sketch_type")
        return sum(1 for i in range(len(cd.curves)) if ta.data[i].value == kind)

    def test_points_coincident_helper(self):
        from ..utilities.trimming import _points_coincident

        p_a = self.add_point((1.0, 1.0))
        p_b = self.add_point((1.0, 1.0))  # same location, different entity
        p_c = self.add_point((2.0, 0.0))
        self.assertTrue(_points_coincident(p_a, p_a))  # same entity
        self.assertTrue(_points_coincident(p_a, p_b))  # coincident coords
        self.assertFalse(_points_coincident(p_a, p_c))  # distinct
        self.assertTrue(_points_coincident(p_a, None))  # missing -> treat as degenerate

    def test_validate_removes_degenerate_arc(self):
        from ..model.curve_ref import ArcRef, curve_ref
        from ..utilities.validate import validate_all_sketches

        # A well-formed arc survives.
        ct = self.add_point((0, 0))
        good = ArcRef.create(
            ct=ct,
            sketch=self.sketch,
            start=self.add_point((2, 0)),
            end=self.add_point((0, 2)),
        )
        # A degenerate arc: start and end at the same location.
        ct2 = self.add_point((5, 0))
        s = self.add_point((7, 0))
        e = self.add_point((7, 0))  # coincident with start
        bad = ArcRef.create(ct=ct2, sketch=self.sketch, start=s, end=e)

        self.assertEqual(self._count(SketchCurveType.ARC), 2)

        changed = validate_all_sketches(self.context.scene)
        self.assertTrue(changed)

        # Degenerate arc gone, good arc kept.
        self.assertEqual(self._count(SketchCurveType.ARC), 1)
        self.assertTrue(curve_ref(self.sketch, good.curve_id).valid)
        self.assertFalse(curve_ref(self.sketch, bad.curve_id).valid)

        # Its orphaned points (start/end/center) are cleaned up too.
        cd = self.sketch.data
        remaining = {get_uuid(cd, "curve_id", i) for i in range(len(cd.curves))}
        for orphan in (s.curve_id, e.curve_id, ct2.curve_id):
            self.assertNotIn(orphan, remaining)
