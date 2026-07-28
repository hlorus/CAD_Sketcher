"""Tests for the 3D-snapping feature (#547).

Most of the snapping pipeline is viewport-bound (region, rv3d, ray_cast,
space_data) and cannot run in ``--background``, so it is validated manually in a
real Blender session. What *is* covered here:

- a regression guard asserting the snapping API still exists and ``get_pos_2d``
  accepts ``respect_snapping`` -- this is what would have caught the native-curve
  refactor silently deleting the feature;
- the pure helpers ``get_wp_matrix`` (dual entity/empty-object workplane support)
  and ``_snap_elements`` (snap-element parsing).
"""

import inspect
from unittest import TestCase

from mathutils import Matrix, Vector

from ..utilities import view


class TestSnappingApiPresent(TestCase):
    """Guard: the snapping surface must not vanish in a refactor again."""

    def test_snapping_functions_exist(self):
        for name in (
            "get_blender_snap_info",
            "get_wp_matrix",
            "_snap_elements",
            "_screen_snap_candidates",
            "_curve_snap_candidates",
            "_closest_segment_point_world",
        ):
            self.assertTrue(callable(getattr(view, name, None)), f"missing view.{name}")

    def test_get_pos_2d_accepts_respect_snapping(self):
        params = inspect.signature(view.get_pos_2d).parameters
        self.assertIn("respect_snapping", params)
        self.assertFalse(
            params["respect_snapping"].default,
            "respect_snapping must default to False (opt-in, back-compatible)",
        )

    def test_snap_bypass_short_circuits(self):
        """global_data.snap_bypass (Shift held) skips snapping before any ray_cast."""
        import bpy
        from .. import global_data

        original = global_data.snap_bypass
        try:
            global_data.snap_bypass = True
            # Returns None without touching the scene/ray_cast when bypassed.
            self.assertIsNone(view.get_blender_snap_info(bpy.context, (0.0, 0.0)))
        finally:
            global_data.snap_bypass = original


class _FakeEntityWp:
    """Stand-in for a SlvsWorkplane entity (identified by the `p1` attribute)."""

    p1 = object()
    matrix_basis = Matrix.Translation((1.0, 2.0, 3.0))


class _FakeEmptyWp:
    """Stand-in for an empty-object workplane (no `p1`)."""

    matrix_world = Matrix.Translation((4.0, 5.0, 6.0))


class TestGetWpMatrix(TestCase):
    def test_entity_workplane_uses_matrix_basis(self):
        wp = _FakeEntityWp()
        self.assertEqual(view.get_wp_matrix(wp), wp.matrix_basis)

    def test_empty_object_workplane_uses_matrix_world(self):
        wp = _FakeEmptyWp()
        self.assertEqual(view.get_wp_matrix(wp), wp.matrix_world)


class TestClosestPointOnSegment(TestCase):
    """Pure geometry behind edge snapping (viewport-independent)."""

    def test_ray_crossing_segment_midpoint(self):
        # Ray along +Z through (0.5, 0, 0); segment along X from 0 to 1.
        pt = view._closest_point_on_segment_to_ray(
            Vector((0.5, 0.0, 5.0)), Vector((0.0, 0.0, -1.0)),
            Vector((0.0, 0.0, 0.0)), Vector((1.0, 0.0, 0.0)),
        )
        self.assertAlmostEqual(pt.x, 0.5)
        self.assertAlmostEqual(pt.y, 0.0)

    def test_parallel_ray_does_not_crash(self):
        # Ray parallel to the segment -> intersect_line_line returns None.
        # This is the case that crashed with the unguarded tuple unpack.
        pt = view._closest_point_on_segment_to_ray(
            Vector((0.3, 1.0, 0.0)), Vector((1.0, 0.0, 0.0)),
            Vector((0.0, 0.0, 0.0)), Vector((1.0, 0.0, 0.0)),
        )
        self.assertIsInstance(pt, Vector)
        # Result stays clamped within the segment.
        self.assertGreaterEqual(pt.x, 0.0)
        self.assertLessEqual(pt.x, 1.0)

    def test_result_clamped_to_segment_ends(self):
        # Ray crossing well past the segment end clamps to the endpoint.
        pt = view._closest_point_on_segment_to_ray(
            Vector((5.0, 0.0, 5.0)), Vector((0.0, 0.0, -1.0)),
            Vector((0.0, 0.0, 0.0)), Vector((1.0, 0.0, 0.0)),
        )
        self.assertAlmostEqual(pt.x, 1.0)

    def test_degenerate_zero_length_segment(self):
        start = Vector((2.0, 3.0, 4.0))
        pt = view._closest_point_on_segment_to_ray(
            Vector((0.0, 0.0, 0.0)), Vector((0.0, 0.0, 1.0)), start, start.copy()
        )
        self.assertEqual(pt, start)


class _FakeToolSettings:
    def __init__(self, base=None, extra=None):
        if base is not None:
            self.snap_elements_base = base
        if extra is not None:
            self.snap_elements = extra


class TestSnapElements(TestCase):
    def test_collects_from_both_attributes(self):
        ts = _FakeToolSettings(base={"VERTEX"}, extra={"EDGE"})
        self.assertEqual(view._snap_elements(ts), {"VERTEX", "EDGE"})

    def test_edge_perpendicular_implies_edge(self):
        ts = _FakeToolSettings(base={"EDGE_PERPENDICULAR"})
        self.assertIn("EDGE", view._snap_elements(ts))

    def test_empty_when_no_snap_attributes(self):
        self.assertEqual(view._snap_elements(_FakeToolSettings()), set())

    def test_accepts_single_string_value(self):
        ts = _FakeToolSettings(base="VERTEX")
        self.assertEqual(view._snap_elements(ts), {"VERTEX"})
