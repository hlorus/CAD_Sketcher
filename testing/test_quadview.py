"""Overlays follow the view they are drawn in, not the space's own view.

A quad view is four 3D regions in one area, each with its own ``RegionView3D``,
all drawn in the same redraw. ``space_data.region_3d`` is only one of them, so
anything projecting through it lays its overlay out for that one view and then
repeats it in the other three (issue #438).

Projection itself needs a real region, so these tests record which
``RegionView3D`` the projection is handed rather than where it lands, and drive
the icon cache with stand-in regions.
"""

import unittest.mock as mock
from unittest import TestCase

import numpy as np

from ..utilities import view
from .test_drawing_batch import _FakeRegionContext
from .utils import Sketch2dTestCase


class _FakeSpace:
    """A 3D space whose ``region_3d`` is a *different* view to the region's."""

    def __init__(self, rv3d):
        self.region_3d = rv3d


class _FakeSystem:
    ui_scale = 1.0


class _FakePreferences:
    system = _FakeSystem()


class _FakeViewContext:
    """One 3D region being drawn, plus the space's unrelated own view."""

    preferences = _FakePreferences()

    def __init__(self, region_data, space_region_3d, region="region"):
        self.region = region
        self.region_data = region_data
        self.space_data = _FakeSpace(space_region_3d)


class TestGet2dCoords(TestCase):
    def setUp(self):
        self.seen = []

        def spy(region, rv3d, pos):
            self.seen.append((region, rv3d))
            return None

        patcher = mock.patch.object(view, "location_3d_to_region_2d", spy)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_projects_through_the_region_being_drawn(self):
        context = _FakeViewContext("quad-3", "space-view")
        view.get_2d_coords(context, (1.0, 2.0, 3.0))
        self.assertEqual(self.seen, [("region", "quad-3")])

    def test_no_3d_region_gives_no_position(self):
        """A gizmo then skips drawing instead of projecting through nothing."""
        self.assertIsNone(
            view.get_2d_coords(_FakeViewContext(None, "space-view"), (0.0, 0.0, 0.0))
        )
        self.assertEqual(self.seen, [])


class TestDimensionLabelFollowsTheRegion(Sketch2dTestCase):
    """Every dimension label projects through the region being drawn."""

    def setUp(self):
        super().setUp()
        self.seen = []

        def spy(region, rv3d, pos):
            self.seen.append(rv3d)
            return None

        patcher = mock.patch.object(view, "location_3d_to_region_2d", spy)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _placements(self, constraint):
        """The views two regions' draws hand the projection."""
        for name in ("quad-a", "quad-b"):
            constraint.value_placement(_FakeViewContext(name, "space-view"))
        return self.seen

    def test_distance(self):
        a = self.add_point((0.0, 0.0), fixed=True)
        b = self.add_point((5.0, 0.0))
        self.add_line(a, b)
        c = self.sketch.constraints.add_distance(
            init=True, curve_id_1=a.curve_id, curve_id_2=b.curve_id
        )
        self.assertEqual(self._placements(c), ["quad-a", "quad-b"])

    def test_angle(self):
        origin = self.add_point((0.0, 0.0), fixed=True)
        a = self.add_point((2.0, 0.0))
        b = self.add_point((0.0, 2.0))
        first = self.add_line(origin, a)
        second = self.add_line(origin, b)
        c = self.sketch.constraints.add_angle(
            init=True, curve_id_1=first.curve_id, curve_id_2=second.curve_id
        )
        self.assertEqual(self._placements(c), ["quad-a", "quad-b"])

    def test_diameter(self):
        center = self.add_point((0.0, 0.0), fixed=True)
        circle = self.add_circle(center, 1.5)
        c = self.sketch.constraints.add_diameter(init=True, curve_id_1=circle.curve_id)
        self.assertEqual(self._placements(c), ["quad-a", "quad-b"])


class TestIconCacheIsPerRegion(TestCase):
    """Each region keeps its own icon layout, so icons stay clickable in all four."""

    SIZE = 10.0

    def setUp(self):
        from ..drawing import constraint_icons

        self.icons = constraint_icons
        saved = dict(constraint_icons._region_cache)
        constraint_icons._region_cache.clear()

        def restore():
            constraint_icons._region_cache.clear()
            constraint_icons._region_cache.update(saved)

        self.addCleanup(restore)

        grey = (0.5, 0.5, 0.5, 1)
        # world, stack, type, color, index, anchor, priority
        self.entries = [
            ((0, 0, 0), 0, "HORIZONTAL", grey, 0, "A", 0),
            ((0, 0, 0), 1, "EQUAL", grey, 0, "A", 0),
        ]
        uvs = {e[2]: (0, 0, 1, 1) for e in self.entries}
        uvs.update({name: (0, 0, 1, 1) for name in self.icons._BADGE_CELLS})
        self.prepared = self.icons._prepare(self.entries, uvs)

    def _hits(self, centers, hover=None):
        """What a region drawing the icons at ``centers`` leaves for picking."""
        _quads, hits = self.icons._arrange(
            self.prepared,
            np.array(centers),
            np.ones(len(self.entries), dtype=bool),
            self.SIZE,
            self.SIZE,
            "ELEMENT",
            frozenset(),
            hover,
        )
        return hits

    def test_each_region_picks_from_its_own_draw(self):
        # The same sketch seen from two views puts the group in two places.
        first, second = _FakeRegionContext(1), _FakeRegionContext(2)
        self.icons._region_entry(first)["hits"] = self._hits(
            [(100.0, 100.0), (110.0, 100.0)]
        )
        self.icons._region_entry(second)["hits"] = self._hits(
            [(400.0, 300.0), (410.0, 300.0)]
        )

        # Before the fix both regions answered from whichever drew last, so the
        # group was only reachable in that one view.
        self.assertEqual(self.icons.pick(first, (100.0, 100.0))[1], True)
        self.assertEqual(self.icons._region_cache[1]["hover"], "A")
        self.assertIsNone(self.icons._region_cache[2]["hover"])

        self.assertEqual(self.icons.pick(second, (400.0, 300.0))[1], True)
        self.assertEqual(self.icons._region_cache[2]["hover"], "A")
        # Opening the group in one view leaves the other's alone.
        self.assertEqual(self.icons._region_cache[1]["hover"], "A")

    def test_an_undrawn_region_picks_nothing(self):
        self.assertEqual(
            self.icons.pick(_FakeRegionContext(9), (0.0, 0.0)), (None, False)
        )

    def test_regions_that_stop_drawing_are_retired(self):
        """A closed quad view must not leave its batch cached forever."""
        stale = _FakeRegionContext(1)
        self.icons._region_entry(stale)
        live = [_FakeRegionContext(i) for i in range(2, 7)]
        for _ in range(self.icons._STALE_AFTER + 2):
            for context in live:
                self.icons._region_entry(context)

        self.assertNotIn(1, self.icons._region_cache)
        self.assertEqual(sorted(self.icons._region_cache), [2, 3, 4, 5, 6])
