"""Regression: merging two coincident-constrained points must not leave a
self-referential coincident constraint behind.

``merge_points`` remaps every constraint's curve references from the duplicate to
the target. A coincident constraint that joined the two merged points therefore
collapses to ``curve_id_1 == curve_id_2`` (a point coincident with itself). Left in
place it is redundant and the solver flags it as failed (``REDUNDANT_OK``); the
merge must drop it instead.
"""

from .utils import Sketch2dTestCase
from ..operators.add_geometric_constraints import merge_points


class TestMergeSelfReferential(Sketch2dTestCase):
    def _coincident(self):
        return list(self.sketch.constraints.coincident)

    def test_pairwise_merge_drops_joining_coincident(self):
        sk = self.sketch
        p1 = self.add_point((0, 0))
        p2 = self.add_point((0.001, 0))
        sk.constraints.add_coincident(curve_id_1=p1.curve_id, curve_id_2=p2.curve_id)

        merge_points(self.context, p1, p2)

        self.assertEqual(
            self._coincident(), [], "joining coincident should be removed by merge"
        )

    def test_chain_merge_drops_all_collapsed_coincidents(self):
        sk = self.sketch
        p1 = self.add_point((0, 0))
        p2 = self.add_point((0.001, 0))
        p3 = self.add_point((0.002, 0))
        sk.constraints.add_coincident(curve_id_1=p1.curve_id, curve_id_2=p2.curve_id)
        sk.constraints.add_coincident(curve_id_1=p2.curve_id, curve_id_2=p3.curve_id)

        for dup in (p1, p2):
            merge_points(self.context, dup, p3)

        self.assertEqual(self._coincident(), [])

    def test_unrelated_coincident_is_preserved(self):
        """A coincident that only touches one merged point is remapped, not dropped."""
        sk = self.sketch
        p1 = self.add_point((0, 0))
        p2 = self.add_point((0.001, 0))
        other = self.add_point((5, 0))
        keep = sk.constraints.add_coincident(
            curve_id_1=p1.curve_id, curve_id_2=other.curve_id
        )

        merge_points(self.context, p1, p2)

        remaining = self._coincident()
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0].curve_id_1, p2.curve_id)
        self.assertEqual(remaining[0].curve_id_2, other.curve_id)

    def test_solver_reports_no_redundancy_after_merge(self):
        """The failed/redundant state the bug produced is gone once merged."""
        sk = self.sketch
        p1 = self.add_point((0, 0))
        p2 = self.add_point((0.001, 0), fixed=True)
        sk.constraints.add_coincident(curve_id_1=p1.curve_id, curve_id_2=p2.curve_id)

        merge_points(self.context, p1, p2)
        self.solve()

        self.assertNotEqual(sk.solver_state, "REDUNDANT_OK")
        self.assertFalse(any(c.failed for c in self._coincident()))
