"""The live state value is formatted in scene units and published to the viewport."""

from types import SimpleNamespace

from mathutils import Vector

from .. import global_data
from ..stateful_operator.logic import StatefulOperatorLogic
from .utils import OpHarness, Sketch2dTestCase

_NO_REGION = object()


class _Region:
    """A stand-in 3D view region, identified the way the draw handler checks it."""

    def __init__(self, ident=1):
        self.width = 800
        self.height = 600
        self._ident = ident

    def as_pointer(self):
        return self._ident


class _Formatter:
    """The formatter alone, over a state whose property subtype is given here.

    The real thing reads ``get_property()`` and ``rna_type``, which only a
    registered operator has, so they are supplied rather than mocked around.
    """

    _format_number = StatefulOperatorLogic._format_number
    _format_values = StatefulOperatorLogic._format_values

    def __init__(self, *subtypes):
        self._names = ["p%d" % i for i in range(len(subtypes))]
        self.rna_type = SimpleNamespace(
            properties={
                name: SimpleNamespace(subtype=subtype)
                for name, subtype in zip(self._names, subtypes)
            }
        )

    def get_property(self):
        return self._names


class TestStateValueFormat(Sketch2dTestCase):
    def test_a_distance_is_shown_in_scene_units(self):
        # 0.05 m reads as a length with its unit, not as raw Blender units.
        text = _Formatter("DISTANCE")._format_values([0.05])
        self.assertNotEqual(text, "0.050")
        self.assertTrue(any(c.isalpha() for c in text), text)

    def test_an_angle_is_shown_in_scene_units(self):
        import math

        text = _Formatter("ANGLE")._format_values([math.radians(45)])
        self.assertIn("45", text)
        self.assertNotIn("0.785", text)

    def test_a_plain_number_keeps_three_decimals(self):
        self.assertEqual(_Formatter(None)._format_values([1.5]), "1.500")
        self.assertEqual(_Formatter(None)._format_values([2]), "2")

    def test_a_coordinate_formats_each_component_as_a_length(self):
        text = _Formatter("XYZ")._format_values([Vector((0.05, 0.1))])
        self.assertTrue(text.startswith("(") and text.endswith(")"), text)
        self.assertEqual(text.count(","), 1, text)
        # Each component carries its unit, rather than being a bare number.
        self.assertTrue(any(c.isalpha() for c in text), text)

    def test_a_subtype_free_vector_stays_plain(self):
        text = _Formatter(None)._format_values([Vector((1.0, 2.0))])
        self.assertEqual(text, "(1.000, 2.000)")


class TestStateValuePublish(Sketch2dTestCase):
    def setUp(self):
        super().setUp()
        global_data.state_value = None
        self.addCleanup(setattr, global_data, "state_value", None)

    def _op(self):
        from ..operators.add_circle import View3D_OT_slvs_add_circle2d

        op = OpHarness(View3D_OT_slvs_add_circle2d, self.sketch, self.context).op
        op._numeric = SimpleNamespace(is_active=False, current="")
        op._last_coords = Vector((120, 90))
        op._status_value = "50 mm"
        return op

    def _publish(self, op, region=_NO_REGION):
        ctx = SimpleNamespace(region=_Region() if region is _NO_REGION else region)
        StatefulOperatorLogic._publish_state_value(op, ctx)
        return global_data.state_value

    def test_the_value_is_published_with_its_region_and_anchor(self):
        published = self._publish(self._op())
        self.assertEqual(published[0], "50 mm")
        self.assertEqual(tuple(published[1]), (120.0, 90.0))
        self.assertEqual(published[2], 1)

    def test_numeric_entry_wins_over_the_resolved_value(self):
        op = self._op()
        op._numeric = SimpleNamespace(is_active=True, current="12")
        self.assertEqual(self._publish(op)[0], "12")

    def test_nothing_is_published_without_a_value(self):
        op = self._op()
        op._status_value = None
        self.assertIsNone(self._publish(op))

    def test_nothing_is_published_outside_a_region(self):
        self.assertIsNone(self._publish(self._op(), region=None))

    def test_a_stale_value_is_dropped(self):
        global_data.state_value = ("old", Vector((0, 0)), 1)
        op = self._op()
        op._status_value = ""
        self.assertIsNone(self._publish(op))

    def test_the_preference_turns_it_off(self):
        from ..utilities.preferences import get_prefs

        prefs = get_prefs()
        prefs.show_state_value = False
        self.addCleanup(setattr, prefs, "show_state_value", True)
        self.assertIsNone(self._publish(self._op()))
