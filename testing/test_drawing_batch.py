"""Drawing stays fast as a sketch grows, without changing what gets drawn.

Two per-mouse-move costs grew with every shape already in the sketch:

- A live update (undo the previous preview, rebuild it) creates several curves,
  and each creation recomputed the whole sketch's weld ids. ``batched_changes``
  folds that into one pass per update.
- The constraint gizmo group recreated every gizmo on every refresh. It now
  rebuilds only when the gizmo layout changes.

The equivalence checks matter as much as the counts: skipped bookkeeping fails
silently (a corner stops welding, a marker sits in the wrong place).
"""

import unittest.mock as mock

import numpy as np

from ..operators.base_2d import Operator2d
from ..utilities import curve_data
from ..utilities.curve_data import (
    batch_update,
    compute_merge_ids,
    is_batching,
    rebuild_segments,
)
from .utils import Sketch2dTestCase


class TestLiveUpdateBatching(Sketch2dTestCase):
    def _probe(self):
        probe = Operator2d.__new__(Operator2d)
        probe._active_sketch = self.sketch
        return probe

    def _draw_rectangle(self, x=0.0, y=0.0):
        """What the rectangle tool's main() creates: 4 corners, 4 edges."""
        corners = [
            self.add_point(co)
            for co in ((x, y), (x + 2, y), (x + 2, y + 1), (x, y + 1))
        ]
        return [self.add_line(corners[i], corners[(i + 1) % 4]) for i in range(4)]

    def _merge_passes(self, fn):
        """How many real weld-id recomputes ``fn`` triggers."""
        real = curve_data.compute_generated_id_seeds
        calls = []

        def spy(sketch):
            calls.append(sketch)
            return real(sketch)

        with mock.patch.object(curve_data, "compute_generated_id_seeds", spy):
            fn()
        return len(calls)

    def _merge_ids(self):
        cd = self.sketch.target_object.data
        ids = np.empty(len(cd.points), dtype=np.int32)
        cd.attributes["merge_id"].data.foreach_get("value", ids)
        return ids

    def test_a_live_update_recomputes_weld_ids_once(self):
        self._draw_rectangle(10, 10)  # something already in the sketch
        probe = self._probe()

        def batched():
            with probe.batched_changes(self.context):
                self._draw_rectangle()

        unbatched = self._merge_passes(lambda: self._draw_rectangle(5, 0))
        self.assertGreater(unbatched, 1, "control: unbatched creation should repeat")
        self.assertEqual(self._merge_passes(batched), 1)

    def test_batched_result_matches_a_full_recompute(self):
        self._draw_rectangle(10, 10)
        with self._probe().batched_changes(self.context):
            self._draw_rectangle()

        batched = self._merge_ids()
        compute_merge_ids(self.sketch, force=True)
        np.testing.assert_array_equal(
            batched, self._merge_ids(), err_msg="batched weld ids were stale"
        )

        cd = self.sketch.target_object.data
        before = np.empty(len(cd.points) * 3, dtype=np.float32)
        cd.points.foreach_get("position", before)
        rebuild_segments(self.sketch)
        after = np.empty(len(cd.points) * 3, dtype=np.float32)
        cd.points.foreach_get("position", after)
        np.testing.assert_allclose(after, before, atol=1e-5)

    def test_does_not_end_an_outer_batch(self):
        """An inner batch would close the outer one early; the hook must defer."""
        with batch_update(self.sketch):
            with self._probe().batched_changes(self.context):
                self._draw_rectangle()
            self.assertTrue(is_batching(self.sketch), "the outer batch was ended early")


class TestConstraintGizmoLayout(Sketch2dTestCase):
    """The gizmo group rebuilds exactly when its layout signature changes."""

    def _signature(self):
        from ..gizmos.constraint import VIEW3D_GGT_slvs_constraint

        _mapping, signature = VIEW3D_GGT_slvs_constraint._layout(
            None, self.context, self.sketch
        )
        return signature

    def _line(self):
        p0 = self.add_point((0, 0))
        p1 = self.add_point((2, 0))
        return p0, p1, self.add_line(p0, p1)

    def test_moving_geometry_keeps_the_layout(self):
        _p0, p1, line = self._line()
        self.sketch.constraints.add_horizontal(curve_id_1=line.curve_id)
        before = self._signature()
        p1.co = (3.0, 1.0)
        self.assertEqual(before, self._signature())

    def test_adding_or_removing_a_constraint_changes_the_layout(self):
        p0, p1, line = self._line()
        empty = self._signature()
        c = self.sketch.constraints.add_horizontal(curve_id_1=line.curve_id)
        with_one = self._signature()
        self.assertNotEqual(empty, with_one)

        self.sketch.constraints.add_coincident(
            curve_id_1=p0.curve_id, curve_id_2=p1.curve_id
        )
        self.assertNotEqual(with_one, self._signature())

        self.sketch.constraints.remove(c)
        self.assertNotEqual(with_one, self._signature())

    def test_gizmo_scale_changes_the_layout(self):
        from ..utilities.preferences import get_prefs

        _p0, _p1, line = self._line()
        self.sketch.constraints.add_horizontal(curve_id_1=line.curve_id)
        prefs = get_prefs()
        previous = prefs.gizmo_scale
        before = self._signature()
        try:
            prefs.gizmo_scale = previous * 2.0
            self.assertNotEqual(before, self._signature())
        finally:
            prefs.gizmo_scale = previous
