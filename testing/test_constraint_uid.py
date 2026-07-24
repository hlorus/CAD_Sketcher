"""Tests for constraint UID stability (issue #544).

When a constraint is deleted from a collection, indices shift. UIDs ensure
that driver paths (scene["slvs:c:{uid}"]) remain stable after deletion.
"""

from .utils import Sketch2dTestCase


class TestConstraintUIDStability(Sketch2dTestCase):

    def test_uid_assigned_on_creation(self):
        """New constraints should get a unique UID."""
        sc = self.sketch.constraints

        p0 = self.add_point((0, 0), fixed=True)
        p1 = self.add_point((1, 0))
        c1 = sc.add_distance(init=True, curve_id_1=p0.curve_id, curve_id_2=p1.curve_id)

        uid = getattr(c1, "constraint_uid", "")
        self.assertTrue(uid, "Constraint should have a UID after creation")

    def test_uids_are_unique(self):
        """Each constraint should get a distinct UID."""
        sc = self.sketch.constraints

        p0 = self.add_point((0, 0), fixed=True)
        p1 = self.add_point((1, 0))
        p2 = self.add_point((0, 2))
        p3 = self.add_point((3, 0))

        c1 = sc.add_distance(init=True, curve_id_1=p0.curve_id, curve_id_2=p1.curve_id)
        c2 = sc.add_distance(init=True, curve_id_1=p0.curve_id, curve_id_2=p2.curve_id)
        c3 = sc.add_distance(init=True, curve_id_1=p0.curve_id, curve_id_2=p3.curve_id)

        uids = {
            getattr(c1, "constraint_uid", ""),
            getattr(c2, "constraint_uid", ""),
            getattr(c3, "constraint_uid", ""),
        }
        self.assertEqual(len(uids), 3, "All UIDs should be distinct")
        self.assertNotIn("", uids, "No UID should be empty")

    def test_value_stable_after_deletion(self):
        """Deleting a constraint should not affect other constraints' driver values."""
        sc = self.sketch.constraints
        scene = self.scene

        p0 = self.add_point((0, 0), fixed=True)
        p1 = self.add_point((1, 0))
        p2 = self.add_point((0, 2))
        p3 = self.add_point((3, 0))

        c1 = sc.add_distance(init=True, curve_id_1=p0.curve_id, curve_id_2=p1.curve_id)
        c2 = sc.add_distance(init=True, curve_id_1=p0.curve_id, curve_id_2=p2.curve_id)
        c3 = sc.add_distance(init=True, curve_id_1=p0.curve_id, curve_id_2=p3.curve_id)

        c1.value = 10.0
        c2.value = 20.0
        c3.value = 30.0

        uid1 = getattr(c1, "constraint_uid", "")
        uid3 = getattr(c3, "constraint_uid", "")
        key1 = f"slvs:c:{uid1}"
        key3 = f"slvs:c:{uid3}"

        # Delete middle constraint
        sc.remove(c2)

        # Values for c1 and c3 should be unchanged
        self.assertAlmostEqual(scene.get(key1, 0.0), 10.0,
                               msg="c1 value should be stable after c2 deletion")
        self.assertAlmostEqual(scene.get(key3, 0.0), 30.0,
                               msg="c3 value should be stable after c2 deletion")
