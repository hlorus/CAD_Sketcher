"""Entity names are derived, not stored on the curve.

A curve carries only an integer ordinal; the displayed name is that ordinal and
the type. Only a name a user typed is stored, in a collection on the sketch, so
no geometry rebuild can lose it (Blender wipes STRING attributes on every
``remove_curves``).
"""

from ..model.curve_names import custom_name
from ..utilities.curve_data import (
    get_curve_index,
    next_name_ordinal,
    remove_native_curve_by_id,
    reusing_curve_ids,
    set_attribute,
)
from ..utilities.validate import reset_cache, validate_sketch
from .utils import Sketch2dTestCase


class TestCurveNames(Sketch2dTestCase):
    @property
    def _data(self):
        return self.sketch.target_object.data

    def test_name_is_the_type_and_an_ordinal(self):
        first = self.add_point((0.0, 0.0))
        second = self.add_point((1.0, 0.0))
        line = self.add_line(first, second)

        self.assertEqual(second.name, "Point %d" % (int(first.name.split()[1]) + 1))
        self.assertTrue(line.name.startswith("Line "))

    def test_an_ordinal_is_never_handed_out_twice(self):
        """Deleting an entity must not make the next one a duplicate."""
        a = self.add_point((0.0, 0.0))
        b = self.add_point((1.0, 0.0))
        taken = {a.name, b.name}

        remove_native_curve_by_id(self.sketch, a.curve_id)
        self.assertNotIn(self.add_point((2.0, 0.0)).name, taken)

    def test_a_rename_survives_a_rebuild(self):
        """An operator re-run removes its output and rebuilds it under the same
        ids; the name is on the sketch, not on the curve, so it is still there."""
        point = self.add_point((0.0, 0.0))
        point.name = "Anchor"
        cid = point.curve_id

        remove_native_curve_by_id(self.sketch, cid)
        with reusing_curve_ids(self.sketch, [cid]):
            rebuilt = self.add_point((0.0, 0.0))

        self.assertEqual(rebuilt.curve_id, cid)
        self.assertEqual(rebuilt.name, "Anchor")

    def test_clearing_a_rename_falls_back_to_the_derived_name(self):
        point = self.add_point((0.0, 0.0))
        derived = point.name
        point.name = "Anchor"
        self.assertEqual(custom_name(self._data, point.curve_id), "Anchor")

        point.name = ""
        self.assertEqual(point.name, derived)
        self.assertEqual(custom_name(self._data, point.curve_id), "")

    def test_the_self_heal_forgets_names_of_deleted_entities(self):
        point = self.add_point((0.0, 0.0))
        point.name = "Anchor"
        cid = point.curve_id
        remove_native_curve_by_id(self.sketch, cid)

        reset_cache()
        validate_sketch(self.sketch)

        self.assertEqual(custom_name(self._data, cid), "")

    def test_a_file_written_before_derived_names_is_carried_over(self):
        """The old STRING attribute becomes an ordinal, or a rename when the
        name is not one this add-on would have generated."""
        plain = self.add_point((0.0, 0.0))
        renamed = self.add_point((1.0, 0.0))
        cd = self._data
        legacy = cd.attributes.new("name", "STRING", "CURVE")
        legacy.data[get_curve_index(self.sketch, plain.curve_id)].value = b"Point 7"
        legacy.data[get_curve_index(self.sketch, renamed.curve_id)].value = b"Anchor"
        # Ordinals only exist since the change, so clear them like an old file.
        set_attribute(cd.attributes, "name_ordinal", 0)

        reset_cache()
        validate_sketch(self.sketch)

        self.assertIsNone(cd.attributes.get("name"))
        self.assertEqual(plain.name, "Point 7")
        self.assertEqual(renamed.name, "Anchor")
        # The carried-over ordinal is in use, so the next point goes past it.
        self.assertGreater(next_name_ordinal(cd, 0), 7)
