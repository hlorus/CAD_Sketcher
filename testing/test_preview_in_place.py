"""Updating a drawing preview in place matches rebuilding it.

Tools that opt in (``preview_in_place``) move their preview elements while the
structure of the preview stays the same, instead of undoing and recreating it
on every mouse move. After each move the sketch must look exactly as a full
rebuild would leave it.
"""

import json
from unittest import mock

from mathutils import Vector

from .live_harness import LiveOpHarness, capture_sketch, new_mesh_object
from .utils import Sketch2dTestCase


class TestPreviewInPlace(Sketch2dTestCase):
    def setUp(self):
        super().setUp()
        sc = self.context.scene.sketcher
        self._saved_settings = (
            sc.auto_axis_constraints,
            sc.use_construction,
            sc.use_snap_project,
        )
        sc.auto_axis_constraints = True
        sc.use_construction = False
        sc.use_snap_project = True
        self.anchor = self.add_point((5.0, 5.0))
        a, b = self.add_point((0.0, -3.0)), self.add_point((6.0, -3.0))
        self.guide = self.add_line(a, b)

    def tearDown(self):
        sc = self.context.scene.sketcher
        (
            sc.auto_axis_constraints,
            sc.use_construction,
            sc.use_snap_project,
        ) = self._saved_settings
        super().tearDown()

    def _captures(self, real_cls, events, in_place):
        """The sketch after each event, and how many moves were done in place."""
        updated = []
        original = real_cls.update_preview

        def counting(op, context):
            ok = original(op, context)
            updated.append(ok)
            return ok

        with (
            mock.patch.object(real_cls, "preview_in_place", in_place),
            mock.patch.object(real_cls, "update_preview", counting),
        ):
            h = LiveOpHarness(real_cls, self.sketch, self.context)
            captures = []
            for kind, co, hover, *snap in events:
                getattr(h, kind)(co, hover=hover, snap=snap[0] if snap else None)
                captures.append(json.loads(json.dumps(capture_sketch(self.sketch))))
            h.cancel()
        return captures, sum(updated)

    def assert_matches_rebuild(self, real_cls, events, in_place_moves):
        rebuilt, _ = self._captures(real_cls, events, in_place=False)
        updated, count = self._captures(real_cls, events, in_place=True)
        self.assertEqual(count, in_place_moves, "moves updated in place")
        for i, (got, expected) in enumerate(zip(updated, rebuilt)):
            self.assertEqual(got, expected, f"preview differs after event {i}")
        return rebuilt

    def test_rectangle(self):
        from ..operators.add_rectangle import View3D_OT_slvs_add_rectangle

        guide, anchor = self.guide.curve_id, self.anchor.curve_id
        self.assert_matches_rebuild(
            View3D_OT_slvs_add_rectangle,
            [
                ("click", (0.0, 0.0), ""),
                ("move", (2.0, 1.0), ""),
                ("move", (3.0, 2.0), ""),
                ("move", (4.0, 2.5), ""),
                ("move", (3.0, -3.0), guide),
                ("move", (4.0, -3.0), guide),
                ("move", (5.0, 4.0), ""),
                ("move", (5.0, 5.0), anchor),
                ("move", (5.0, 5.0), anchor),
                ("move", (7.0, 6.0), ""),
                ("move", (8.0, 6.5), ""),
            ],
            # Every move that keeps the previous move's hover.
            in_place_moves=5,
        )

    def test_rectangle_from_existing_point(self):
        from ..operators.add_rectangle import View3D_OT_slvs_add_rectangle

        anchor = self.anchor.curve_id
        self.assert_matches_rebuild(
            View3D_OT_slvs_add_rectangle,
            [
                ("click", (5.0, 5.0), anchor),
                ("move", (7.0, 7.0), ""),
                ("move", (8.0, 9.0), ""),
                ("move", (2.0, 1.0), ""),
            ],
            in_place_moves=2,
        )

    def test_line(self):
        from ..operators.add_line_2d import View3D_OT_slvs_add_line2d

        guide, anchor = self.guide.curve_id, self.anchor.curve_id
        self.assert_matches_rebuild(
            View3D_OT_slvs_add_line2d,
            [
                ("click", (0.0, 0.0), ""),
                ("move", (2.0, 0.05), ""),
                ("move", (3.0, 1.0), ""),
                ("move", (0.05, 4.0), ""),
                ("move", (3.0, -3.0), guide),
                ("move", (4.0, -3.0), guide),
                ("move", (5.0, 5.0), anchor),
                ("move", (6.0, 2.0), ""),
                ("move", (7.0, 2.5), ""),
            ],
            in_place_moves=4,
        )

    def test_circle(self):
        from ..operators.add_circle import View3D_OT_slvs_add_circle2d

        self.assert_matches_rebuild(
            View3D_OT_slvs_add_circle2d,
            [
                ("click", (1.0, 1.0), ""),
                ("move", (2.0, 1.0), ""),
                ("move", (3.0, 2.0), ""),
                ("move", (1.0, 4.0), ""),
                ("move", (0.5, 0.5), ""),
            ],
            in_place_moves=3,
        )

    def test_arc(self):
        from ..operators.add_arc import View3D_OT_slvs_add_arc2d

        guide = self.guide.curve_id
        self.assert_matches_rebuild(
            View3D_OT_slvs_add_arc2d,
            [
                ("click", (0.0, 0.0), ""),
                ("click", (2.0, 0.0), ""),
                ("move", (2.0, 0.5), ""),
                ("move", (1.0, 2.0), ""),
                # Back through the start: the sweep flips to clockwise.
                ("move", (2.0, -0.5), ""),
                ("move", (1.0, -2.0), ""),
                ("move", (-1.0, -2.0), ""),
                ("move", (-2.0, 1.0), ""),
                ("move", (0.0, -3.0), guide),
                ("move", (0.5, -3.0), guide),
            ],
            in_place_moves=5,
        )

    def _snaps(self):
        """Snap targets on a mesh edge from (8, 0) to (10, 2)."""
        ob = new_mesh_object(
            self.context, "SnapSource", [(8, 0, 0), (10, 2, 0)], edges=[(0, 1)]
        )

        def on_edge(x):
            return {
                "type": "EDGE",
                "object": ob.name,
                "edge_vertices": (0, 1),
                "world_point": Vector((x, x - 8, 0)),
            }

        vertex = {
            "type": "VERTEX",
            "object": ob.name,
            "vertex_index": 0,
            "world_point": Vector((8, 0, 0)),
        }
        midpoint = {
            "type": "EDGE_MIDPOINT",
            "object": ob.name,
            "edge_vertices": (0, 1),
            "world_point": Vector((9, 1, 0)),
        }
        return vertex, on_edge, midpoint

    def test_line_with_projected_snaps(self):
        from ..operators.add_line_2d import View3D_OT_slvs_add_line2d

        vertex, on_edge, midpoint = self._snaps()
        captures = self.assert_matches_rebuild(
            View3D_OT_slvs_add_line2d,
            [
                ("click", (8.0, 0.0), "", vertex),
                ("move", (6.0, 6.0), ""),
                ("move", (6.0, 7.0), ""),
                # Sliding along a projected edge keeps its projection.
                ("move", (8.5, 0.5), "", on_edge(8.5)),
                ("move", (9.5, 1.5), "", on_edge(9.5)),
                ("move", (9.0, 1.0), "", midpoint),
                ("move", (9.0, 1.0), "", midpoint),
                ("move", (3.0, 3.0), ""),
                ("move", (3.0, 4.0), ""),
            ],
            in_place_moves=4,
        )
        # The snaps really projected: the vertex is bound, the edge became a curve.
        self.assertTrue(captures[3]["projections"])
        self.assertGreater(len(captures[3]["curves"]), len(captures[2]["curves"]))

    def test_rectangle_with_projected_snaps(self):
        from ..operators.add_rectangle import View3D_OT_slvs_add_rectangle

        vertex, on_edge, _midpoint = self._snaps()
        self.assert_matches_rebuild(
            View3D_OT_slvs_add_rectangle,
            [
                ("move", (8.0, 0.0), "", vertex),
                ("click", (8.0, 0.0), "", vertex),
                ("move", (5.0, 3.0), ""),
                ("move", (4.0, 3.5), ""),
                ("move", (8.5, 0.5), "", on_edge(8.5)),
                ("move", (9.5, 1.5), "", on_edge(9.5)),
            ],
            in_place_moves=2,
        )
