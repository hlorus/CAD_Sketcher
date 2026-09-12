"""Tests for the drawing extraction layer (drawing.render_data).

The extraction is pure data (no GPU), so it can be verified headless. It feeds
the cached overlay and, later, CPU picking. These guard that geometry is
extracted into the right buckets and that the change-signature both stays stable
and detects the changes that must invalidate cached batches.
"""

import math

from mathutils import Vector

from ..drawing import render_data, selection
from ..utilities.curve_data import read_uuid_list, refresh_curve_geometry
from ..utilities.preferences import get_prefs
from .utils import Sketch2dTestCase


class TestRenderData(Sketch2dTestCase):
    def _ts(self):
        return get_prefs().theme_settings.entity

    def _build_point_line_circle(self):
        p0 = self.add_point((0, 0), fixed=True)
        p1 = self.add_point((3, 0))
        self.add_line(p0, p1)
        self.add_circle(self.add_point((6, 0)), 1.0)
        self.solve()
        refresh_curve_geometry(self.sketch)

    def test_extraction_buckets(self):
        self._build_point_line_circle()
        data = render_data.build(self.sketch, self._ts(), is_active=True)

        n_points = sum(len(centres) for centres, _sizes in data.point_buckets.values())
        n_segments = sum(
            sum(len(chunk) for chunk in chunks) for chunks in data.line_buckets.values()
        )

        self.assertEqual(n_points, 3)  # the three point curves
        geo = render_data.geometry(self.sketch)
        self.assertEqual(len(geo.point_cids), 3)
        self.assertGreater(n_segments, 1)  # line + tessellated circle
        # Every bucket chunk is (M, 2, 3): a segment carries both its endpoints.
        for chunks in data.line_buckets.values():
            for chunk in chunks:
                self.assertEqual(chunk.shape[1:], (2, 3))
        self.assertEqual(n_segments, len(geo.seg_co))

    def test_signature_stable_and_invalidates(self):
        self._build_point_line_circle()
        base = render_data.overlay_signature(self.sketch, True, ())
        self.assertEqual(base, render_data.overlay_signature(self.sketch, True, ()))

        cd = self.sketch.target_object.data

        # Moving a point must change the signature.
        original = tuple(cd.points[0].position)
        cd.points[0].position = (9, 9, 0)
        self.assertNotEqual(base, render_data.overlay_signature(self.sketch, True, ()))
        cd.points[0].position = original

        # Selecting a curve must change the signature. Selection is transient
        # runtime state (the selection module), not a persisted attribute.
        self.assertEqual(base, render_data.overlay_signature(self.sketch, True, ()))
        cid = read_uuid_list(cd, "curve_id")[0]
        selection.clear()
        selection.selected.append(cid)
        try:
            self.assertNotEqual(
                base, render_data.overlay_signature(self.sketch, True, ())
            )
        finally:
            selection.clear()

        # Active/inactive must change the signature (colors differ).
        self.assertNotEqual(base, render_data.overlay_signature(self.sketch, False, ()))

    def test_signature_tracks_world_transform(self):
        """build() bakes matrix_world into every pick/overlay position, so the
        signature must change when the sketch's world transform moves. Omitting
        it let the pick cache serve stale world coordinates for a sketch on a
        moved/settling workplane -- selection went dead on non-origin-plane
        sketches (the whole cache keys on this fingerprint)."""
        from mathutils import Matrix

        self._build_point_line_circle()
        obj = self.sketch.target_object
        before_geo = render_data.geometry_signature(self.sketch)
        before_overlay = render_data.overlay_signature(self.sketch, True, ())

        original = obj.matrix_world.copy()
        try:
            obj.matrix_world = Matrix.Translation((5, 3, 0)) @ original
            self.assertNotEqual(
                before_geo,
                render_data.geometry_signature(self.sketch),
                "world transform move did not change geometry_signature",
            )
            self.assertNotEqual(
                before_overlay,
                render_data.overlay_signature(self.sketch, True, ()),
            )
        finally:
            obj.matrix_world = original

    def test_inactive_signature_ignores_hover(self):
        """Hover is active-only, so it must not invalidate an inactive sketch's
        signature (which would rebuild its batches on every mouse-move)."""
        self._build_point_line_circle()
        selection.clear()
        try:
            inactive = render_data.overlay_signature(self.sketch, False, ())
            selection.hover = "abc123"
            self.assertEqual(
                inactive,
                render_data.overlay_signature(self.sketch, False, ()),
                "hover changed an inactive sketch's signature",
            )
            # The active sketch, by contrast, must react to hover.
            active = render_data.overlay_signature(self.sketch, True, ())
            selection.hover = "def456"
            self.assertNotEqual(
                active, render_data.overlay_signature(self.sketch, True, ())
            )
        finally:
            selection.clear()


class TestArcTessellation(Sketch2dTestCase):
    """Arcs and circles are tessellated for all curves in one vectorized pass.

    Guards the geometry that batching must not change: every vertex on the
    circle, the chain closed with no duplicate/zero-length segment, and an open
    arc still starting and ending exactly on its defining points.
    """

    RADIUS = 1.5

    def _segments(self, is_active=True):
        data = render_data.build(
            self.sketch, get_prefs().theme_settings.entity, is_active
        )
        geo = render_data.geometry(self.sketch)
        return data, [(Vector(a), Vector(b)) for a, b in geo.seg_co]

    def _local(self, co):
        """A sketch-local 2D point in the world space build() emits."""
        return self.sketch.world_matrix @ Vector((co[0], co[1], 0.0))

    def test_circle_vertices_lie_on_the_circle(self):
        circle = self.add_circle(self.add_point((2, -1)), self.RADIUS)
        self.solve()
        refresh_curve_geometry(self.sketch)

        data, segments = self._segments()
        centre = self._local((2, -1))
        for a, b in segments:
            for v in (a, b):
                self.assertAlmostEqual((v - centre).length, self.RADIUS, places=4)
        geo = render_data.geometry(self.sketch)
        self.assertEqual(set(geo.seg_cids), {circle.curve_id})

    def test_circle_closes_without_a_degenerate_segment(self):
        self.add_circle(self.add_point((0, 0)), self.RADIUS)
        self.solve()
        refresh_curve_geometry(self.sketch)

        _data, segments = self._segments()
        self.assertEqual(len(segments), render_data.ARC_SEGMENTS)
        for i, (_a, b) in enumerate(segments):
            nxt = segments[(i + 1) % len(segments)][0]
            self.assertAlmostEqual((b - nxt).length, 0.0, places=5)
        for a, b in segments:
            self.assertGreater((b - a).length, 1e-6, "zero-length segment emitted")

    def test_arc_spans_its_defining_points(self):
        for degrees in (30, 90, 200, 350):
            with self.subTest(degrees=degrees):
                self.setUp()
                angle = math.radians(degrees)
                end_co = (self.RADIUS * math.cos(angle), self.RADIUS * math.sin(angle))
                self.add_arc(
                    self.add_point((0, 0)),
                    self.add_point((self.RADIUS, 0)),
                    self.add_point(end_co),
                )
                self.solve()
                refresh_curve_geometry(self.sketch)

                _data, segments = self._segments()
                expected = max(int(angle / math.tau * render_data.ARC_SEGMENTS), 4)
                self.assertEqual(len(segments), expected)
                self.assertAlmostEqual(
                    (segments[0][0] - self._local((self.RADIUS, 0))).length,
                    0.0,
                    places=4,
                )
                self.assertAlmostEqual(
                    (segments[-1][1] - self._local(end_co)).length, 0.0, places=4
                )

    def test_construction_and_selection_split_buckets(self):
        """Batching files arcs per (construction, colour); both must still split."""
        solid = self.add_circle(self.add_point((0, 0)), 1.0)
        self.add_circle(self.add_point((4, 0)), 1.0, construction=True)
        self.solve()
        refresh_curve_geometry(self.sketch)

        data, segments = self._segments()
        self.assertEqual(sorted(k[0] for k in data.line_buckets), [False, True])
        n_segments = sum(
            sum(len(chunk) for chunk in chunks) for chunks in data.line_buckets.values()
        )
        self.assertEqual(n_segments, len(segments))

        before = set(data.line_buckets)
        selection.clear()
        selection.selected.append(solid.curve_id)
        try:
            selected, sel_segments = self._segments()
            self.assertNotEqual(before, set(selected.line_buckets))
            self.assertEqual(len(sel_segments), len(segments))
            # Selection recolours; it must not change how much is drawn.
            self.assertEqual(
                sum(
                    sum(len(chunk) for chunk in chunks)
                    for chunks in selected.line_buckets.values()
                ),
                n_segments,
            )
        finally:
            selection.clear()
