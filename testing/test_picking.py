"""Tests for CPU screen-space picking (drawing.picking).

Picking replaces the GPU id-buffer: it projects the active sketch's geometry and
finds what's under the cursor / inside a box. The projection itself is
viewport-bound, so it's stubbed here with a simple orthographic mapping to
exercise the pick logic (point-over-edge priority, box overlap, ignore-list).
"""

import numpy as np

from ..drawing import picking, selection
from ..model.sketch_ref import set_active_sketch
from ..utilities.curve_data import refresh_curve_geometry
from .utils import Sketch2dTestCase


class _FakeContext:
    """Enough of a context for picking; region/region_data just need to exist."""

    region = object()
    region_data = object()

    def __init__(self, scene):
        self.scene = scene


def _ortho_projection(world, region, rv3d):
    """Top-down orthographic stub: screen = (x*10, y*10), everything visible."""
    world = np.asarray(world, dtype=float).reshape(-1, 3)
    return np.column_stack([world[:, 0] * 10, world[:, 1] * 10]), np.ones(
        len(world), bool
    )


class TestPicking(Sketch2dTestCase):
    def setUp(self):
        super().setUp()
        set_active_sketch(self.context, self.sketch.target_object)
        self.a = self.add_point((0, 0), fixed=True)
        self.b = self.add_point((4, 0))
        self.line = self.add_line(self.a, self.b)
        self.solve()
        refresh_curve_geometry(self.sketch)
        self.ctx = _FakeContext(self.scene)
        self._orig = picking._project_points_to_region
        picking._project_points_to_region = _ortho_projection

    def tearDown(self):
        picking._project_points_to_region = self._orig
        selection.ignore_list = []
        selection.hover = ""
        selection.hover_candidates = []
        selection.hover_locked = False
        super().tearDown()

    def test_pick_ranked_returns_overlapping_stack(self):
        # At point b's location (40, 0) the point and the line's endpoint overlap:
        # both are candidates, point first (grabbable vertex over edge).
        ranked = picking.pick_ranked(self.ctx, (40, 0))
        self.assertEqual(ranked[0], self.b.curve_id)
        self.assertIn(self.line.curve_id, ranked)
        self.assertGreaterEqual(len(ranked), 2)

    def test_update_hover_keeps_cycled_choice(self):
        # Hover the stack (nearest = point b), cycle to the line, then re-hover the
        # same spot: the cycled choice must survive rather than snap back to nearest.
        selection.hover = ""
        picking.update_hover(self.ctx, (40, 0))
        self.assertEqual(selection.hover_candidates[0], self.b.curve_id)
        self.assertTrue(selection.cycle_hover(1))
        self.assertEqual(selection.hover, self.line.curve_id)
        self.assertEqual(picking.update_hover(self.ctx, (40, 0)), self.line.curve_id)

    def test_cycle_hover_wraps_and_noops(self):
        selection.hover_candidates = ["a", "b", "c"]
        selection.hover = "a"
        self.assertTrue(selection.cycle_hover(1))
        self.assertEqual(selection.hover, "b")
        self.assertTrue(selection.cycle_hover(1))
        self.assertEqual(selection.hover, "c")
        self.assertTrue(selection.cycle_hover(1))  # wrap forward
        self.assertEqual(selection.hover, "a")
        self.assertTrue(selection.cycle_hover(-1))  # wrap backward
        self.assertEqual(selection.hover, "c")

        selection.hover_candidates = ["only"]
        selection.hover = "only"
        self.assertFalse(selection.cycle_hover(1))  # fewer than two -> no-op

    def test_wheel_lock_stops_alt_click_overshoot(self):
        # Alt+wheel previews to "b" and locks; the following Alt+click must commit
        # "b" (consume the lock), not advance to "c".
        selection.hover_candidates = ["a", "b", "c"]
        selection.hover = "a"
        self.assertTrue(selection.cycle_hover(1, lock=True))
        self.assertEqual(selection.hover, "b")
        self.assertTrue(selection.hover_locked)

        self.assertTrue(selection.take_hover_lock())  # Alt+click commits "b"
        self.assertFalse(selection.hover_locked)
        # A further Alt+click (no lock) digs on to the next candidate.
        self.assertFalse(selection.take_hover_lock())

    def test_moving_off_element_clears_lock(self):
        # A wheel lock must not persist once the cursor leaves the stack.
        selection.hover = self.b.curve_id
        selection.hover_locked = True
        picking.update_hover(self.ctx, (1000, 1000))  # over nothing
        self.assertFalse(selection.hover_locked)

    def test_point_takes_priority_over_edge(self):
        # Cursor over point b's screen location (40, 0).
        self.assertEqual(picking.pick(self.ctx, (40, 0)), self.b.curve_id)

    def test_edge_picked_away_from_vertices(self):
        # Mid-line (20, 0): no point within radius -> the line is picked.
        self.assertEqual(picking.pick(self.ctx, (20, 0)), self.line.curve_id)

    def test_empty_returns_nothing(self):
        self.assertEqual(picking.pick(self.ctx, (1000, 1000)), "")

    def test_box_selects_overlapping(self):
        ids = set(picking.pick_box(self.ctx, (-10, -10), (60, 60)))
        self.assertIn(self.a.curve_id, ids)
        self.assertIn(self.b.curve_id, ids)
        self.assertIn(self.line.curve_id, ids)

    def test_ignore_list_respected(self):
        selection.ignore_list = [self.b.curve_id]
        self.assertNotEqual(picking.pick(self.ctx, (40, 0)), self.b.curve_id)

    def test_cache_reuses_on_hover_and_refreshes_on_geometry_change(self):
        # A second pick (mouse just moved, no geometry change) must reuse the same
        # extracted data, not rebuild it. The extraction is shared with the
        # overlay, so identity of the returned object is the thing to check.
        from ..drawing import render_data

        render_data.invalidate()
        picking.pick(self.ctx, (40, 0))
        cached = picking._active_data(self.ctx)
        picking.pick(self.ctx, (20, 0))
        self.assertIs(
            picking._active_data(self.ctx),
            cached,
            "hover rebuilt pick data despite unchanged geometry",
        )
        # Adding a segment changes the geometry signature -> cache refreshes and
        # the new element is pickable.
        c = self.add_point((4, 4))
        line2 = self.add_line(self.b, c)
        self.solve()
        self.assertEqual(picking.pick(self.ctx, (40, 40)), c.curve_id)
        self.assertIsNot(picking._active_data(self.ctx), cached)
        self.assertTrue(line2.valid)

    def test_overlay_and_picking_share_one_extraction(self):
        """A changed-geometry frame must extract once, not once per consumer.

        The overlay and the picker each used to run their own ``build``, so every
        frame of a drag paid for the extraction twice (issue #342).
        """
        from ..drawing import render_data
        from ..utilities.preferences import get_prefs

        render_data.invalidate()
        calls = []
        real = render_data._extract_geometry

        def spy(sketch):
            calls.append(sketch)
            return real(sketch)

        import unittest.mock as mock

        with mock.patch.object(render_data, "_extract_geometry", spy):
            # One "frame": the picker resolves hover, then the overlay draws.
            picking.pick(self.ctx, (40, 0))
            render_data.build(self.sketch, get_prefs().theme_settings.entity, True)
        self.assertEqual(
            len(calls), 1, "geometry was extracted more than once for one frame"
        )

    def test_hover_does_not_re_extract_geometry(self):
        """Selection/hover changes must only redo colours, not the extraction."""
        from ..drawing import render_data
        from ..utilities.preferences import get_prefs

        ts = get_prefs().theme_settings.entity
        render_data.invalidate()
        render_data.build(self.sketch, ts, True)  # warm

        calls = []
        real = render_data._extract_geometry

        def spy(sketch):
            calls.append(sketch)
            return real(sketch)

        import unittest.mock as mock

        with mock.patch.object(render_data, "_extract_geometry", spy):
            for cid in (self.a.curve_id, self.b.curve_id, ""):
                selection.hover = cid
                render_data.build(self.sketch, ts, True)
        selection.hover = ""
        self.assertEqual(calls, [], "a hover change re-extracted the geometry")


class TestSegmentDistance(Sketch2dTestCase):
    """``_dist_to_segments`` replaced a per-segment Python loop.

    It runs on every mouse-move over every tessellated segment, so it is
    vectorized; these pin it against the straightforward scalar formula it
    replaced, including the degenerate and clamped cases.
    """

    @staticmethod
    def _scalar(a, b, px, py):
        """Point-to-segment distance, written out directly."""
        abx, aby = b[0] - a[0], b[1] - a[1]
        seg2 = abx * abx + aby * aby
        if seg2 < 1e-9:
            return ((px - a[0]) ** 2 + (py - a[1]) ** 2) ** 0.5
        t = ((px - a[0]) * abx + (py - a[1]) * aby) / seg2
        t = min(1.0, max(0.0, t))
        cx, cy = a[0] + t * abx, a[1] + t * aby
        return ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5

    def test_matches_the_scalar_formula(self):
        rng = np.random.default_rng(20260912)
        screen = rng.random((500, 2, 2)) * 1000.0
        px, py = 500.0, 500.0
        got = picking._dist_to_segments(screen, px, py)
        want = [self._scalar(s[0], s[1], px, py) for s in screen]
        np.testing.assert_allclose(got, want, rtol=1e-9, atol=1e-9)

    def test_handles_degenerate_and_clamped_cases(self):
        screen = np.array(
            [
                [[0.0, 0.0], [0.0, 0.0]],  # zero-length: distance to the point
                [[0.0, 0.0], [10.0, 0.0]],  # perpendicular foot inside
                [[0.0, 0.0], [1.0, 0.0]],  # foot beyond the end -> clamps to b
                [[20.0, 0.0], [30.0, 0.0]],  # foot before the start -> clamps to a
            ]
        )
        got = picking._dist_to_segments(screen, 5.0, 5.0)
        want = [self._scalar(s[0], s[1], 5.0, 5.0) for s in screen]
        np.testing.assert_allclose(got, want, rtol=1e-9, atol=1e-9)
        # the specific expectations, spelled out
        self.assertAlmostEqual(float(got[0]), (50.0) ** 0.5, places=9)
        self.assertAlmostEqual(float(got[1]), 5.0, places=9)
        self.assertAlmostEqual(float(got[2]), (16.0 + 25.0) ** 0.5, places=9)
        self.assertAlmostEqual(float(got[3]), (225.0 + 25.0) ** 0.5, places=9)
