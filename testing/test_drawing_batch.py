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


class TestIdCachesStayFresh(Sketch2dTestCase):
    """The id caches are now updated incrementally instead of dropped.

    A stale cache resolves a curve_id to the wrong curve, silently. After every
    kind of change the caches must equal a derivation from scratch.
    """

    def _fresh(self, field):
        from ..utilities.curve_data import get_uuid

        cd = self.sketch.target_object.data
        return [get_uuid(cd, field, i) for i in range(len(cd.curves))]

    def assert_caches_fresh(self):
        from ..utilities.curve_data import (
            UUID_FIELDS,
            get_curve_index,
            read_uuid_list,
            read_uuid_raw_list,
        )

        cd = self.sketch.target_object.data
        for field in UUID_FIELDS:
            if cd.attributes.get(f".{field}_lo") is None:
                continue
            fresh = self._fresh(field)
            self.assertEqual(read_uuid_list(cd, field), fresh, f"{field} hex ids")
            raw = [
                (
                    *cd.attributes[f".{field}_lo"].data[i].value,
                    *cd.attributes[f".{field}_hi"].data[i].value,
                )
                for i in range(len(cd.curves))
            ]
            self.assertEqual(read_uuid_raw_list(cd, field), raw, f"{field} raw ids")
        for i, cid in enumerate(self._fresh("curve_id")):
            if cid:
                self.assertEqual(get_curve_index(self.sketch, cid), i, cid)

    def test_wrapper_identity_the_caches_key_on(self):
        """Caches are keyed by id() of the datablock wrapper; that must be stable."""
        obj = self.sketch.target_object
        self.assertIs(obj.data, obj.data.attributes.id_data)

    def test_creation_with_lookups_in_between(self):
        from ..utilities.curve_data import get_curve_index

        pts = []
        for i in range(6):
            pts.append(self.add_point((i, 0)))
            get_curve_index(self.sketch, pts[-1].curve_id)  # populate mid-way
            if i:
                self.add_line(pts[i - 1], pts[i])
            self.assert_caches_fresh()
        centre = self.add_point((0, 5))
        self.add_circle(centre, 1.0)
        self.add_arc(centre, self.add_point((1, 5)), self.add_point((0, 6)))
        self.assert_caches_fresh()

    def test_in_place_id_writes(self):
        from ..utilities.curve_data import (
            get_curve_index,
            new_uuid,
            set_attribute,
            set_uuid,
        )

        p0, p1 = self.add_point((0, 0)), self.add_point((1, 0))
        line = self.add_line(p0, p1)
        self.assert_caches_fresh()
        cd = self.sketch.target_object.data

        idx = get_curve_index(self.sketch, p0.curve_id)
        set_uuid(cd, "curve_id", idx, new_uuid())  # validate-style re-mint
        self.assert_caches_fresh()

        idx = get_curve_index(self.sketch, line.curve_id)
        set_attribute(cd.attributes, "start_point_id", new_uuid(), idx)
        self.assert_caches_fresh()

    def test_removal_then_creation(self):
        pts = [self.add_point((i, 0)) for i in range(4)]
        line = self.add_line(pts[0], pts[1])
        self.assert_caches_fresh()
        pts[2].remove()
        self.assert_caches_fresh()
        line.remove()
        self.add_line(pts[1], pts[3])
        self.assert_caches_fresh()

    def test_snapshot_restore_reinstates_exact_caches(self):
        """The per-mouse-move undo installs caches captured with the snapshot."""
        probe = Operator2d.__new__(Operator2d)
        probe._active_sketch = self.sketch
        for i in range(3):
            self.add_line(self.add_point((i, 0)), self.add_point((i, 1)))
        snapshot = probe.create_snapshot(self.context)

        for step in range(3):  # three "mouse moves" of a preview
            with self.subTest(step=step):
                probe.restore_snapshot(self.context, snapshot)
                self.assert_caches_fresh()
                with probe.batched_changes(self.context):
                    self.add_line(self.add_point((9, step)), self.add_point((9, 5)))
                self.assert_caches_fresh()


class TestTrackedBatch(Sketch2dTestCase):
    """A draw update rebuilds only the segments of points it wrote."""

    def test_moved_point_rebuilds_its_segments_only(self):
        a, b, c = self.add_point((0, 0)), self.add_point((2, 0)), self.add_point((4, 0))
        moved_line = self.add_line(a, b)
        self.add_line(b, c)
        probe = Operator2d.__new__(Operator2d)
        probe._active_sketch = self.sketch

        real = curve_data.rebuild_segments
        calls = []

        def spy(sketch, point_ids=None):
            calls.append(point_ids)
            return real(sketch, point_ids=point_ids)

        with mock.patch.object(curve_data, "rebuild_segments", spy):
            with probe.batched_changes(self.context):
                a.co = (0.0, 3.0)
        self.assertEqual(calls, [{a.curve_id}], "expected one scoped rebuild")

        cd, idx, curve_slice = curve_data.get_curve_data(
            self.sketch, moved_line.curve_id
        )
        start = cd.points[curve_slice.points[0].index].position
        self.assertAlmostEqual(start[1], 3.0, places=5)

        before = np.empty(len(cd.points) * 3, dtype=np.float32)
        cd.points.foreach_get("position", before)
        rebuild_segments(self.sketch)
        after = np.empty(len(cd.points) * 3, dtype=np.float32)
        cd.points.foreach_get("position", after)
        np.testing.assert_allclose(after, before, atol=1e-5)

    def test_plain_batches_keep_the_full_rebuild(self):
        """Only the draw hook opts in; other batch_update callers are unchanged."""
        a, b = self.add_point((0, 0)), self.add_point((2, 0))
        self.add_line(a, b)
        real = curve_data.rebuild_segments
        calls = []

        def spy(sketch, point_ids=None):
            calls.append(point_ids)
            return real(sketch, point_ids=point_ids)

        with mock.patch.object(curve_data, "rebuild_segments", spy):
            with batch_update(self.sketch):
                a.co = (1.0, 1.0)
        self.assertEqual(calls, [None])


class TestFrameCache(Sketch2dTestCase):
    def test_memo_matches_direct_lookup_and_resets_per_frame(self):
        from ..drawing import frame_cache

        a, b = self.add_point((0, 0)), self.add_point((2, 0))
        line = self.add_line(a, b)
        frame_cache.begin_frame()
        first = frame_cache.curve_placement(self.sketch, line.curve_id)
        self.assertEqual(
            tuple(first),
            tuple(curve_data.get_curve_placement(self.sketch, line.curve_id)),
        )

        b.co = (4.0, 0.0)  # geometry changes between frames
        self.assertEqual(
            tuple(frame_cache.curve_placement(self.sketch, line.curve_id)),
            tuple(first),
            "within one frame the memo must hold",
        )
        frame_cache.begin_frame()
        self.assertEqual(
            tuple(frame_cache.curve_placement(self.sketch, line.curve_id)),
            tuple(curve_data.get_curve_placement(self.sketch, line.curve_id)),
        )

    def test_memo_expires_without_a_new_frame(self):
        from ..drawing import frame_cache

        a, b = self.add_point((0, 0)), self.add_point((2, 0))
        line = self.add_line(a, b)
        frame_cache.begin_frame()
        frame_cache.curve_placement(self.sketch, line.curve_id)
        b.co = (6.0, 0.0)
        with mock.patch.object(
            frame_cache.time,
            "perf_counter",
            return_value=frame_cache._frame_start + frame_cache._MAX_AGE + 1,
        ):
            got = frame_cache.curve_placement(self.sketch, line.curve_id)
        self.assertEqual(
            tuple(got),
            tuple(curve_data.get_curve_placement(self.sketch, line.curve_id)),
        )
