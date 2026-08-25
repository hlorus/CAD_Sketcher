"""Copy/paste carries the constraints among the copied geometry.

These drive the copy-buffer helpers directly (``snapshot_constraints`` /
``paste_constraints``) rather than the operators, since paste ends by invoking a
modal move that has no meaning in the background test harness.
"""

from ..operators.copy_paste import paste_constraints, snapshot_constraints
from .utils import Sketch2dTestCase


class TestCopyPasteConstraints(Sketch2dTestCase):
    def test_geometric_constraint_is_carried_to_the_copy(self):
        p1 = self.add_point((0.0, 0.0))
        p2 = self.add_point((3.0, 0.0))
        self.sketch.constraints.add_coincident(
            curve_id_1=p1.curve_id, curve_id_2=p2.curve_id
        )

        snaps = snapshot_constraints(self.sketch, {p1.curve_id, p2.curve_id})
        self.assertEqual([s["type"] for s in snaps], ["coincident"])

        # Simulate the paste: fresh points + the old->new id map.
        q1 = self.add_point((0.0, 5.0))
        q2 = self.add_point((3.0, 5.0))
        id_map = {p1.curve_id: q1.curve_id, p2.curve_id: q2.curve_id}

        before = len(list(self.sketch.constraints.coincident))
        paste_constraints(self.sketch, snaps, id_map)
        coincident = list(self.sketch.constraints.coincident)

        self.assertEqual(len(coincident) - before, 1, "the coincidence must be pasted")
        new = coincident[-1]
        self.assertEqual(
            {new.curve_id_1, new.curve_id_2},
            {q1.curve_id, q2.curve_id},
            "the pasted constraint must reference the pasted points, not the source",
        )

    def test_constraint_skipped_when_a_referenced_curve_is_not_copied(self):
        # Only constraints fully internal to the copied set are carried; a
        # constraint reaching outside would dangle on paste.
        p1 = self.add_point((0.0, 0.0))
        p2 = self.add_point((3.0, 0.0))
        self.sketch.constraints.add_coincident(
            curve_id_1=p1.curve_id, curve_id_2=p2.curve_id
        )

        self.assertEqual(snapshot_constraints(self.sketch, {p1.curve_id}), [])
        self.assertEqual(
            len(snapshot_constraints(self.sketch, {p1.curve_id, p2.curve_id})), 1
        )

    def test_dimensional_value_survives_with_a_fresh_uid(self):
        p1 = self.add_point((0.0, 0.0))
        p2 = self.add_point((3.0, 0.0))
        dist = self.sketch.constraints.add_distance(
            curve_id_1=p1.curve_id, curve_id_2=p2.curve_id, value=3.0
        )

        snaps = snapshot_constraints(self.sketch, {p1.curve_id, p2.curve_id})

        q1 = self.add_point((0.0, 5.0))
        q2 = self.add_point((3.0, 5.0))
        id_map = {p1.curve_id: q1.curve_id, p2.curve_id: q2.curve_id}
        paste_constraints(self.sketch, snaps, id_map)

        new = [
            c
            for c in self.sketch.constraints.distance
            if {c.curve_id_1, c.curve_id_2} == {q1.curve_id, q2.curve_id}
        ]
        self.assertEqual(len(new), 1, "the distance constraint must be pasted")
        # Independent identity so the copy's value is its own scene slot.
        self.assertTrue(new[0].constraint_uid)
        self.assertNotEqual(new[0].constraint_uid, dist.constraint_uid)
        self.assertAlmostEqual(new[0].value, 3.0, places=4)
