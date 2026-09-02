"""The unified Dimension tool infers the constraint type from the selection.

Driven through the interaction harness (select entities, prefill, run main) so
each selection combo is asserted to produce the right dimensional constraint.
``run_fini=False`` skips the label-placement modal handoff (not headless-safe).
"""

from ..drawing import selection
from .utils import OpHarness, Sketch2dTestCase


class TestDimensionOp(Sketch2dTestCase):
    def _harness(self):
        from ..operators.add_dimension import VIEW3D_OT_slvs_add_dimension

        return OpHarness(VIEW3D_OT_slvs_add_dimension, self.sketch, self.context)

    def _line(self, p1, p2):
        return self.add_line(self.add_point(p1), self.add_point(p2))

    def _select(self, *refs):
        selection.selected.clear()
        for r in refs:
            selection.selected.append(r.curve_id)

    def _dispatch(self, *refs):
        self._select(*refs)
        h = self._harness()
        h.prefill()
        h.finish(run_fini=False)
        return h.op.target

    def test_single_line_infers_distance(self):
        from ..model.distance import SlvsDistance

        line = self._line((0.0, 0.0), (4.0, 0.0))
        self.assertIsInstance(self._dispatch(line), SlvsDistance)

    def test_two_lines_infer_angle(self):
        from ..model.angle import SlvsAngle

        l1 = self._line((0.0, 0.0), (4.0, 0.0))
        l2 = self._line((0.0, 0.0), (3.0, 3.0))
        self.assertIsInstance(self._dispatch(l1, l2), SlvsAngle)

    def test_two_points_infer_distance(self):
        from ..model.distance import SlvsDistance

        p1 = self.add_point((0.0, 0.0))
        p2 = self.add_point((3.0, 0.0))
        self.assertIsInstance(self._dispatch(p1, p2), SlvsDistance)

    def test_circle_infers_diameter(self):
        from ..model.diameter import SlvsDiameter

        c = self.add_circle(self.add_point((0.0, 0.0)), 2.0)
        self.assertIsInstance(self._dispatch(c), SlvsDiameter)

    def tearDown(self):
        selection.selected.clear()
        return super().tearDown()
