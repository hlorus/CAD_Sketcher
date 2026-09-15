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
from unittest import TestCase

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
    """The gizmo group rebuilds exactly when its layout signature changes.

    Geometric constraints share one icon gizmo, so only dimensions shape it.
    """

    def _signature(self):
        from ..gizmos.constraint import VIEW3D_GGT_slvs_constraint

        _dimensional, signature = VIEW3D_GGT_slvs_constraint._layout(
            None, self.context, self.sketch
        )
        return signature

    def _line(self):
        p0 = self.add_point((0, 0))
        p1 = self.add_point((2, 0))
        return p0, p1, self.add_line(p0, p1)

    def test_geometric_constraints_keep_the_layout(self):
        p0, p1, line = self._line()
        before = self._signature()
        self.sketch.constraints.add_horizontal(curve_id_1=line.curve_id)
        self.sketch.constraints.add_coincident(
            curve_id_1=p0.curve_id, curve_id_2=p1.curve_id
        )
        p1.co = (3.0, 1.0)
        self.assertEqual(before, self._signature())

    def test_adding_or_removing_a_dimension_changes_the_layout(self):
        p0, p1, _line = self._line()
        empty = self._signature()
        c = self.sketch.constraints.add_distance(
            init=True, curve_id_1=p0.curve_id, curve_id_2=p1.curve_id
        )
        with_one = self._signature()
        self.assertNotEqual(empty, with_one)

        self.sketch.constraints.remove(c)
        self.assertEqual(empty, self._signature())


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


class TestVectorizedSourceSeeds(Sketch2dTestCase):
    """The numpy seed computation must reproduce the scalar FNV fold exactly."""

    def test_matches_scalar_hash(self):
        from ..utilities.curve_data import _stable_source_id, _stable_source_ids

        rng = np.random.default_rng(7)
        words = rng.integers(-(2**31), 2**31 - 1, size=(2000, 4), dtype=np.int64)
        words[:50] = 0  # unset ids
        words[50:60, :3] = 0  # partially set
        words = words.astype(np.int32)
        want = [_stable_source_id(tuple(int(x) for x in row)) for row in words]
        np.testing.assert_array_equal(_stable_source_ids(words), want)

    def _scalar_seeds(self):
        """The previous per-curve implementation, as the reference."""
        from ..model.constants import SketchCurveType
        from ..utilities.curve_data import _stable_source_id, read_uuid_raw_list

        cd = self.sketch.target_object.data
        curve_ids = read_uuid_raw_list(cd, "curve_id")
        start_ids = read_uuid_raw_list(cd, "start_point_id")
        end_ids = read_uuid_raw_list(cd, "end_point_id")
        curve_seeds = [_stable_source_id(v) for v in curve_ids]
        endpoint = [0] * len(cd.points)
        type_attr = cd.attributes["sketch_type"]
        for i, curve in enumerate(cd.curves):
            if (
                type_attr.data[i].value
                not in (SketchCurveType.LINE, SketchCurveType.ARC)
                or curve.points_length < 2
            ):
                continue
            if any(start_ids[i]):
                endpoint[curve.points[0].index] = _stable_source_id(start_ids[i])
            if any(end_ids[i]):
                endpoint[curve.points[curve.points_length - 1].index] = (
                    _stable_source_id(end_ids[i])
                )
        return curve_seeds, endpoint

    def test_sketch_seeds_match_the_previous_implementation(self):
        from ..utilities.curve_data import (
            SOURCE_CURVE_ID_ATTR,
            SOURCE_ENDPOINT_ID_ATTR,
            compute_generated_id_seeds,
        )

        pts = [self.add_point((i, 0)) for i in range(4)]
        self.add_line(pts[0], pts[1])
        self.add_line(pts[1], pts[2])
        centre = self.add_point((0, 4))
        self.add_arc(centre, self.add_point((1, 4)), self.add_point((0, 5)))
        self.add_circle(self.add_point((5, 5)), 1.0)
        self.solve()

        compute_generated_id_seeds(self.sketch)
        cd = self.sketch.target_object.data
        got_curve = np.empty(len(cd.curves), dtype=np.int32)
        cd.attributes[SOURCE_CURVE_ID_ATTR].data.foreach_get("value", got_curve)
        got_end = np.empty(len(cd.points), dtype=np.int32)
        cd.attributes[SOURCE_ENDPOINT_ID_ATTR].data.foreach_get("value", got_end)

        want_curve, want_end = self._scalar_seeds()
        np.testing.assert_array_equal(got_curve, want_curve)
        np.testing.assert_array_equal(got_end, want_end)


class TestConstraintIconCacheKey(Sketch2dTestCase):
    """The icon batch is reused only while nothing its icons depend on changed."""

    def _key_with_fixed_atlas(self, atlas, uvs, view=None):
        import types

        from mathutils import Matrix

        from ..drawing import constraint_icons

        ctx = types.SimpleNamespace(
            region_data=types.SimpleNamespace(perspective_matrix=view or Matrix()),
            region=types.SimpleNamespace(width=800, height=600),
            preferences=self.context.preferences,
        )
        return constraint_icons._icon_key(ctx, self.sketch, atlas, uvs)

    def setUp(self):
        super().setUp()
        self.atlas, self.uvs = object(), {}
        self.p0, self.p1 = self.add_point((0, 0)), self.add_point((2, 0))
        self.line = self.add_line(self.p0, self.p1)
        self.constraint = self.sketch.constraints.add_horizontal(
            curve_id_1=self.line.curve_id
        )

    def key(self, **kw):
        return self._key_with_fixed_atlas(self.atlas, self.uvs, **kw)

    def test_stable_when_nothing_changed(self):
        self.assertEqual(self.key(), self.key())

    def test_unconstrained_preview_geometry_keeps_the_key(self):
        """The whole point: a drawing preview must not invalidate the icons."""
        before = self.key()
        self.add_line(self.add_point((5, 5)), self.add_point((6, 6)))
        self.assertEqual(before, self.key())

    def test_moving_constrained_geometry_changes_the_key(self):
        before = self.key()
        self.p1.co = (3.0, 1.0)
        self.assertNotEqual(before, self.key())

    def test_constraint_state_changes_the_key(self):
        before = self.key()
        self.constraint.failed = True
        failed = self.key()
        self.assertNotEqual(before, failed)
        self.constraint.visible = False
        self.assertNotEqual(failed, self.key())

    def test_new_constraint_and_view_change_the_key(self):
        from mathutils import Matrix

        before = self.key()
        self.sketch.constraints.add_coincident(
            curve_id_1=self.p0.curve_id, curve_id_2=self.p1.curve_id
        )
        with_new = self.key()
        self.assertNotEqual(before, with_new)
        self.assertNotEqual(with_new, self.key(view=Matrix.Translation((1, 0, 0))))

    def test_a_rebuilt_atlas_changes_the_key(self):
        before = self.key()
        self.atlas = object()
        self.assertNotEqual(before, self.key())


class TestConstraintIconProjection(Sketch2dTestCase):
    """Icons placed for all constraints at once land where the per-icon math put them."""

    def _context(self, perspective, view_perspective, view_distance=10.0):
        import types

        return types.SimpleNamespace(
            region_data=types.SimpleNamespace(
                perspective_matrix=perspective,
                view_perspective=view_perspective,
                view_distance=view_distance,
            ),
            region=types.SimpleNamespace(width=800, height=600),
            # The interface scale is 0 in a background session.
            preferences=types.SimpleNamespace(
                system=types.SimpleNamespace(ui_scale=1.25)
            ),
        )

    def _expected(self, ctx, world, stack):
        from bpy_extras.view3d_utils import location_3d_to_region_2d
        from mathutils import Vector

        from ..utilities.preferences import get_prefs
        from ..utilities.view import get_scale_from_pos

        ui_scale = ctx.preferences.system.ui_scale
        size = get_prefs().gizmo_scale * ui_scale
        pos = location_3d_to_region_2d(ctx.region, ctx.region_data, world)
        if pos is None:
            return None
        scale_3d = max(1, get_scale_from_pos(pos, ctx.region_data) / 500)
        return (
            pos
            + Vector((1.0, 1.0)) * size / scale_3d
            + Vector((size, 0.0)) * stack * ui_scale
        )

    def test_matches_per_icon_projection(self):
        from mathutils import Matrix

        from ..drawing.constraint_icons import _screen_centers

        world = [(0.0, 0.0, 0.0), (1.5, -2.0, 0.3), (10.0, 4.0, -1.0), (0.0, 0.0, 50.0)]
        stack = np.array([0, 1, 2, 0], dtype=np.float64)
        import math

        f, near, far = 1 / math.tan(0.6), 0.1, 100.0
        perspective = Matrix(
            (
                (f / (4 / 3), 0, 0, 0),
                (0, f, 0, 0),
                (0, 0, (far + near) / (near - far), 2 * far * near / (near - far)),
                (0, 0, -1, 0),
            )
        )
        view = Matrix.Translation((0.0, 0.0, -20.0)) @ Matrix.Rotation(0.4, 4, "X")
        for mode, persp in (
            ("ORTHO", Matrix.Scale(0.1, 4)),
            ("PERSP", perspective @ view),
        ):
            ctx = self._context(persp, mode)
            centers, visible, _size = _screen_centers(
                ctx, np.array(world, dtype=np.float64), stack
            )
            for i, co in enumerate(world):
                expected = self._expected(ctx, co, stack[i])
                self.assertEqual(bool(visible[i]), expected is not None, (mode, i))
                if expected is not None:
                    np.testing.assert_allclose(
                        centers[i], tuple(expected), rtol=1e-6, atol=1e-6
                    )


class TestConstraintIconGroups(TestCase):
    """Icons on one element (or close together) share an icon until expanded."""

    SIZE = 10.0

    def setUp(self):
        from ..drawing import constraint_icons

        self.icons = constraint_icons
        saved_cache = dict(constraint_icons._icon_cache)
        saved_hover = dict(constraint_icons._hover)
        constraint_icons._hover["group"] = None

        def restore():
            constraint_icons._icon_cache.clear()
            constraint_icons._icon_cache.update(saved_cache)
            constraint_icons._hover.clear()
            constraint_icons._hover.update(saved_hover)

        self.addCleanup(restore)
        red, grey = (1, 0, 0, 1), (0.5, 0.5, 0.5, 1)
        # world, stack, type, color, index, anchor, priority
        self.entries = [
            ((0, 0, 0), 0, "HORIZONTAL", grey, 0, "A", 0),
            ((0, 0, 0), 1, "EQUAL", red, 0, "A", 2),
            ((0, 0, 0), 0, "VERTICAL", grey, 0, "B", 0),
            ((0, 0, 0), 0, "PARALLEL", grey, 0, "C", 0),
        ]
        # Screen centers as _screen_centers would stack them: A's second icon one
        # step right of its first, C in the same icon cell as A, B far away.
        self.centers = np.array(
            [(100.0, 100.0), (110.0, 100.0), (400.0, 300.0), (106.0, 104.0)]
        )

    def arrange(self, mode, expanded=frozenset()):
        uvs = {e[2]: (0, 0, 1, 1) for e in self.entries}
        uvs.update({name: (0, 0, 1, 1) for name in self.icons._BADGE_CELLS})
        self.prepared = self.icons._prepare(self.entries, uvs)
        return self.icons._arrange(
            self.prepared,
            self.centers,
            np.ones(len(self.entries), dtype=bool),
            self.SIZE,
            self.SIZE,
            mode,
            frozenset(expanded),
        )

    def cells(self, quads):
        return [self.prepared["names"][c] for c in quads["codes"]]

    def test_off_shows_every_icon(self):
        quads, hits = self.arrange("OFF")
        self.assertEqual(
            self.cells(quads), ["HORIZONTAL", "EQUAL", "VERTICAL", "PARALLEL"]
        )
        self.assertEqual(len(hits["group_centers"]), 0)

    def test_per_element_groups_an_element_with_a_badge(self):
        quads, hits = self.arrange("ELEMENT")
        cells = self.cells(quads)
        self.assertEqual(cells[:2], ["VERTICAL", "PARALLEL"])
        self.assertIn(cells[2], ("HORIZONTAL", "EQUAL"))
        self.assertEqual(cells[3:], ["BADGE"])
        self.assertEqual(hits["group_counts"].tolist(), [2])
        # The group shows the failed (red) color of its standout member.
        np.testing.assert_allclose(quads["colors"][2], (1, 0, 0, 1))
        np.testing.assert_allclose(quads["centers"][2], (100.0, 100.0))
        self.assertEqual(hits["group_keys"], ["A"])
        np.testing.assert_allclose(hits["group_centers"][0], (100.0, 100.0))

    def test_nearby_elements_merge(self):
        quads, hits = self.arrange("NEARBY")
        cells = self.cells(quads)
        self.assertEqual(cells[0], "VERTICAL")
        self.assertEqual(cells[-1], "BADGE")
        self.assertEqual(hits["group_counts"].tolist(), [3])
        self.assertEqual(hits["group_keys"], ["A"])

    def test_nearby_merges_across_grid_cells_and_chains(self):
        from ..drawing.constraint_icons import _nearby_labels

        size = 10.0
        points = np.array(
            [
                (19.0, 0.0),
                (21.0, 0.0),
                (29.0, 5.0),
                (80.0, 80.0),
                (200.0, 0.0),
                (0.0, 100.0),
                (20.0, 100.0),
                # Just under an icon size apart diagonally: overlapping icons.
                (300.0, 300.0),
                (307.0, 306.0),
            ]
        )
        labels = _nearby_labels(points, size)
        self.assertNotEqual(labels[5], labels[6])  # two icon sizes apart
        self.assertEqual(labels[7], labels[8])
        self.assertEqual(labels[0], labels[1])  # either side of a cell boundary
        self.assertEqual(labels[1], labels[2])  # chained
        self.assertNotEqual(labels[0], labels[3])
        self.assertNotEqual(labels[3], labels[4])

    def test_two_digit_count(self):
        self.entries = [
            ((0, 0, 0), i, "EQUAL", (1, 1, 1, 1), i, "A", 0) for i in range(12)
        ]
        self.centers = np.array([(100.0 + 10 * i, 100.0) for i in range(12)])
        quads, hits = self.arrange("ELEMENT")
        self.assertEqual(self.cells(quads), ["EQUAL", "BADGE"])
        self.assertEqual(hits["group_counts"].tolist(), [12])

    def test_opening_a_merged_group_lays_its_icons_in_a_row(self):
        from ..drawing import selection

        # A and C overlap and merge; opening A opens the group as one row from A.
        quads, hits = self.arrange("NEARBY", expanded={"A"})
        cells = self.cells(quads)
        self.assertNotIn("BADGE", cells)
        self.assertEqual(hits["group_keys"], [])
        row = {
            tuple(c)
            for c, code in zip(quads["centers"].tolist(), quads["codes"].tolist())
            if self.prepared["names"][code] != "VERTICAL"
        }
        self.assertEqual(row, {(100.0, 100.0), (110.0, 100.0), (120.0, 100.0)})
        # B stays where it is.
        self.assertIn([400.0, 300.0], quads["centers"].tolist())

        self.icons._icon_cache["anchors"] = frozenset({"A", "B", "C"})
        saved = (selection.hover, list(selection.selected))
        try:
            selection.hover, selection.selected[:] = "A", []
            self.assertEqual(self.icons._expanded_elements(), frozenset({"A"}))
            # Selecting geometry opens nothing, nor does hovering a curve without
            # icons of its own.
            selection.hover, selection.selected[:] = "D", ["B", "D"]
            self.assertEqual(self.icons._expanded_elements(), frozenset())
        finally:
            selection.hover, selection.selected[:] = saved[0], saved[1]

    def test_hover_expands_and_collapses(self):
        _quads, hits = self.arrange("ELEMENT")
        self.icons._icon_cache["hits"] = hits

        part, changed = self.icons.pick((96.0, 96.0))
        self.assertEqual((part, changed), (None, True))
        self.assertEqual(self.icons._hover["group"], "A")

        quads, hits = self.arrange("ELEMENT")
        self.icons._icon_cache["hits"] = hits
        self.assertNotIn("BADGE", self.cells(quads))
        # Its icons are pickable and moving onto them keeps it open.
        self.assertEqual(self.icons.pick((110.0, 100.0)), (1, False))
        self.assertEqual(self.icons._hover["group"], "A")
        # Away from it: closes.
        self.assertEqual(self.icons.pick((250.0, 250.0)), (None, True))
        self.assertIsNone(self.icons._hover["group"])

    def test_badge_cells(self):
        from ..icon_manager import badge_cells

        cells = dict(badge_cells(64))
        self.assertEqual(sorted(cells), ["BADGE"])
        disc = cells["BADGE"]
        self.assertEqual(disc[32, 32, 3], 1.0)
        self.assertEqual(disc[0, 0, 3], 0.0)
