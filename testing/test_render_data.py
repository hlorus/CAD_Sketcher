"""Tests for the drawing extraction layer (drawing.render_data).

The extraction is pure data (no GPU), so it can be verified headless. It feeds
the cached overlay and, later, CPU picking. These guard that geometry is
extracted into the right buckets and that the change-signature both stays stable
and detects the changes that must invalidate cached batches.
"""

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

        n_points = sum(len(v) for v in data.point_buckets.values())
        n_line_verts = sum(len(v) for v in data.line_buckets.values())

        self.assertEqual(n_points, 3)                 # the three point curves
        self.assertEqual(len(data.point_ids), 3)
        self.assertGreater(n_line_verts, 2)           # line + tessellated circle
        self.assertEqual(n_line_verts % 2, 0)         # LINES come in pairs
        self.assertEqual(len(data.segment_ids), n_line_verts // 2)

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
            self.assertNotEqual(base, render_data.overlay_signature(self.sketch, True, ()))
        finally:
            selection.clear()

        # Active/inactive must change the signature (colors differ).
        self.assertNotEqual(base, render_data.overlay_signature(self.sketch, False, ()))

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
