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
    return np.column_stack([world[:, 0] * 10, world[:, 1] * 10]), np.ones(len(world), bool)


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
        super().tearDown()

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
        # First pick populates the cache; a second pick (mouse just moved, no
        # geometry change) must reuse the same extracted data, not rebuild.
        picking._pick_cache.clear()
        picking.pick(self.ctx, (40, 0))
        cached = picking._pick_cache[self.sketch.target_object.name][1]
        picking.pick(self.ctx, (20, 0))
        self.assertIs(
            picking._pick_cache[self.sketch.target_object.name][1],
            cached,
            "hover rebuilt pick data despite unchanged geometry",
        )
        # Adding a segment changes the geometry signature -> cache refreshes and
        # the new element is pickable.
        c = self.add_point((4, 4))
        line2 = self.add_line(self.b, c)
        self.solve()
        self.assertEqual(picking.pick(self.ctx, (40, 40)), c.curve_id)
        self.assertIsNot(
            picking._pick_cache[self.sketch.target_object.name][1], cached
        )
        self.assertTrue(line2.valid)
