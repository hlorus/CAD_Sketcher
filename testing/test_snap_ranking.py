"""How snapping picks between candidates of different kinds and distances."""

from ..utilities.view import _best_per_position, _snap_rank, _snap_screen_threshold
from .utils import BgsTestCase


class TestSnapRanking(BgsTestCase):
    def test_radius_is_a_pick_radius_not_the_drag_threshold(self):
        # The drag threshold (30 px by default) is how far the mouse must travel
        # before a click becomes a drag; as a snap radius it glued the cursor to
        # vertices half a centimetre away.
        drag = self.context.preferences.inputs.drag_threshold
        self.assertLess(_snap_screen_threshold(self.context), drag)

    def test_a_near_edge_beats_a_far_vertex(self):
        # Ranking by priority alone let a vertex 22 px away win over the edge
        # 10 px under the cursor, so the point stuck to the vertex while the
        # cursor moved on.
        vertex = _snap_rank(0, 22.0, self.context)
        edge = _snap_rank(2, 10.0, self.context)
        self.assertLess(edge, vertex)

    def test_a_vertex_beats_an_edge_it_sits_on(self):
        # Close to a vertex, the vertex is what you mean -- even though the edge
        # through it is always marginally nearer.
        vertex = _snap_rank(0, 6.0, self.context)
        edge = _snap_rank(2, 2.0, self.context)
        self.assertLess(vertex, edge)

    def test_best_per_position_keeps_the_better_ranked(self):
        at = (1.0, 2.0, 0.0)
        far_vertex = (0, 22.0, None, {"type": "VERTEX", "world_point": at})
        near_edge = (2, 10.0, None, {"type": "EDGE", "world_point": at})
        kept = _best_per_position([far_vertex, near_edge], self.context)
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0][3]["type"], "EDGE")
