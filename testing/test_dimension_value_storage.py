"""A dimension keeps its number when its scene property is lost.

The value is written to ``scene["slvs:c:{uid}"]`` so it can be driven, and
mirrored onto the constraint. Sketches that arrive from another file, or whose
uid changes, lose that scene property: without the mirror the dimension
silently starts measuring the geometry instead of holding it, and a zeroed one
collapses the sketch on the next solve.
"""

from unittest import mock

from ..utilities import validate
from .utils import Sketch2dTestCase


class TestDimensionValueStorage(Sketch2dTestCase):
    def _distance(self, value=5.0):
        a = self.add_point((0, 0), fixed=True)
        b = self.add_point((value, 0))
        self.add_line(a, b)
        c = self.sketch.constraints.add_distance(
            init=True, curve_id_1=a.curve_id, curve_id_2=b.curve_id
        )
        c.value = value
        return a, b, c

    def test_value_mirrored_onto_constraint(self):
        _, _, c = self._distance(5.0)
        self.assertAlmostEqual(c.value_store, 5.0, places=5)

    def test_value_survives_losing_the_scene_property(self):
        """Linking a sketch into another file leaves the scene property behind."""
        _, _, c = self._distance(7.5)
        del self.scene[c.value_key()]

        self.assertAlmostEqual(c.value, 7.5, places=5)

    def test_repair_restores_a_lost_value(self):
        _, _, c = self._distance(7.5)
        del self.scene[c.value_key()]

        self.assertEqual(validate.repair_constraint_values(self.scene), 1)
        self.assertAlmostEqual(self.scene[c.value_key()], 7.5, places=5)

    def test_repair_measures_when_nothing_was_stored(self):
        """Files written before the mirror can be left with a zeroed value."""
        a, b, c = self._distance(4.0)
        key = c.value_key()
        self.scene[key] = 0.0
        c.value_store = 0.0

        self.assertEqual(validate.repair_constraint_values(self.scene), 1)
        self.assertAlmostEqual(self.scene[key], 4.0, places=5)

        self.solve()
        self.assertAlmostEqual((b.co - a.co).length, 4.0, places=3)

    def test_repair_leaves_a_healthy_value_alone(self):
        _, _, c = self._distance(5.0)
        self.assertEqual(validate.repair_constraint_values(self.scene), 0)
        self.assertAlmostEqual(self.scene[c.value_key()], 5.0, places=5)


class TestSharedSketchData(Sketch2dTestCase):
    """Several objects sharing one sketch datablock must not churn uids.

    A linked asset used more than once, a library override and a linked
    duplicate all put the same sketch data on several objects. Treating each
    object as its own sketch made the same constraint look like a duplicate of
    itself, so its uid (and with it its value) was re-minted on every update.
    """

    def _share_data_with_second_object(self):
        obj = self.sketch.target_object
        copy = obj.copy()  # shares obj.data
        self.scene.collection.objects.link(copy)
        self.addCleanup(lambda: self.data.objects.remove(copy))
        return copy

    def test_dedup_does_not_rename_uids_of_shared_data(self):
        a = self.add_point((0, 0), fixed=True)
        b = self.add_point((5, 0))
        c = self.sketch.constraints.add_distance(
            init=True, curve_id_1=a.curve_id, curve_id_2=b.curve_id
        )
        c.value = 5.0
        uid = c.constraint_uid
        self._share_data_with_second_object()

        for _ in range(3):
            self.assertFalse(
                validate._dedup_constraint_uids(self.scene),
                "shared sketch data must not look like a duplicate constraint",
            )
        self.assertEqual(c.constraint_uid, uid)
        self.assertAlmostEqual(c.value, 5.0, places=5)

    def test_linked_data_is_not_written_to(self):
        a = self.add_point((0, 0), fixed=True)
        b = self.add_point((5, 0))
        self.sketch.constraints.add_distance(
            init=True, curve_id_1=a.curve_id, curve_id_2=b.curve_id
        )
        with mock.patch.object(validate, "is_editable", return_value=False):
            self.assertFalse(validate.validate_all_sketches(self.scene))
            self.assertEqual(validate.repair_constraint_values(self.scene), 0)
