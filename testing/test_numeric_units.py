"""Unit letters in numeric entry only apply to a typed number, so they don't
swallow tool shortcuts."""

from types import SimpleNamespace
from unittest import TestCase

import bpy

from ..stateful_operator.utilities.keymap import is_unit_input
from ..stateful_operator.utilities.numeric import NumericInput

LENGTH_PROP = bpy.types.Object.bl_rna.properties["location"]
UNITLESS_PROP = bpy.types.Object.bl_rna.properties["pass_index"]


def _key(event_type, **mods):
    base = dict(ctrl=False, alt=False, shift=False, oskey=False)
    base.update(mods)
    return SimpleNamespace(type=event_type, value="PRESS", **base)


class TestUnitInputScope(TestCase):
    def test_unit_letter_after_digit(self):
        self.assertTrue(is_unit_input(_key("M"), "5", LENGTH_PROP))

    def test_no_unit_before_a_digit(self):
        self.assertFalse(is_unit_input(_key("M"), "", LENGTH_PROP))
        self.assertFalse(is_unit_input(_key("M"), "-", LENGTH_PROP))

    def test_modifiers_are_never_units(self):
        for mod in ("ctrl", "alt", "shift", "oskey"):
            with self.subTest(mod=mod):
                self.assertFalse(
                    is_unit_input(_key("M", **{mod: True}), "5", LENGTH_PROP)
                )

    def test_unitless_property_takes_no_units(self):
        self.assertFalse(is_unit_input(_key("M"), "5", UNITLESS_PROP))

    def test_unknown_property_allows_units(self):
        self.assertTrue(is_unit_input(_key("C"), "5"))

    def test_non_unit_key(self):
        self.assertFalse(is_unit_input(_key("Q"), "5", LENGTH_PROP))


class TestNumericInputUnits(TestCase):
    def _input(self, prop):
        numeric = NumericInput()
        numeric.init_substate(prop)
        return numeric

    def _type(self, numeric, *events):
        for event in events:
            numeric.evaluate_event(event)
        return numeric.current

    def test_number_with_unit(self):
        numeric = self._input(LENGTH_PROP)
        self.assertEqual(self._type(numeric, _key("FIVE"), _key("C"), _key("M")), "5cm")

    def test_shortcut_is_not_appended(self):
        numeric = self._input(LENGTH_PROP)
        self.assertEqual(self._type(numeric, _key("FIVE"), _key("M", ctrl=True)), "5")

    def test_letter_after_clearing_is_ignored(self):
        numeric = self._input(LENGTH_PROP)
        back = SimpleNamespace(type="BACK_SPACE", value="PRESS")
        self.assertEqual(self._type(numeric, _key("FIVE"), back, _key("M")), "")

    def test_unitless_number_ignores_letters(self):
        numeric = self._input(UNITLESS_PROP)
        self.assertEqual(self._type(numeric, _key("THREE"), _key("M")), "3")
