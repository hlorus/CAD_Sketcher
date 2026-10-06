"""A live projection must not be picked as the state's own element."""

from mathutils import Vector

from ..drawing import selection
from ..operators.add_line_2d import View3D_OT_slvs_add_line2d
from .live_harness import LiveOpHarness, new_mesh_object
from .utils import Sketch2dTestCase


class TestProjectionNotPickable(Sketch2dTestCase):
    def setUp(self):
        super().setUp()
        self.context.scene.sketcher.use_snap_project = True
        selection.ignore_list.clear()

    def _vertex_snap(self):
        ob = new_mesh_object(
            self.context, "SnapSource", [(4, 0, 0), (6, 2, 0)], edges=[(0, 1)]
        )
        return {
            "type": "VERTEX",
            "object": ob.name,
            "vertex_index": 0,
            "world_point": Vector((4, 0, 0)),
        }

    def test_the_projected_point_is_unpickable(self):
        # Left pickable, the next hover test finds the projection under the
        # cursor and the endpoint state turns into a pick of it. The per-move
        # undo then deletes it and the state points at a dead curve.
        snap = self._vertex_snap()
        h = LiveOpHarness(View3D_OT_slvs_add_line2d, self.sketch, self.context)
        h.click((0.0, 6.0), hover="")
        h.move((4.0, 0.0), hover="", snap=snap)

        projected = h.op.state_data.get("placement_hovered", "") or ""
        from ..operators.placement import placement_of

        projected = placement_of(h.op.state_data).hovered
        self.assertTrue(projected, "the snap must have projected")
        self.assertIn(projected, selection.ignore_list)
        h.cancel()

    def test_the_endpoint_survives_repeated_snapped_moves(self):
        snap = self._vertex_snap()
        h = LiveOpHarness(View3D_OT_slvs_add_line2d, self.sketch, self.context)
        h.click((0.0, 6.0), hover="")
        for _ in range(4):
            h.move((4.0, 0.0), hover="", snap=snap)
            end = h.op.get_point(self.context, 1)
            self.assertTrue(end.valid, "the endpoint was replaced by the projection")
            self.assertLess((end.co - Vector((4.0, 0.0))).length, 1e-5, end.co)
        h.cancel()
