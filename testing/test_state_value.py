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


def _view3d():
    """The real region and its view data, so world points project for real."""
    import bpy

    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type != "VIEW_3D":
                continue
            for region in area.regions:
                if region.type == "WINDOW":
                    return region, area.spaces.active.region_3d
    return None, None


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
        op._status_value = "50 mm"
        op._status_values = (Vector((0.0, 0.0)),)
        return op

    def _publish(self, op, region=_NO_REGION):
        stub = _Region()
        ctx = SimpleNamespace(
            region=stub if region is _NO_REGION else region,
            region_data=SimpleNamespace(),
        )
        # Projection needs a real view; borrow the one the test window has.
        real_region, real_rv3d = _view3d()
        if region is _NO_REGION and real_region is not None:
            ctx.region, ctx.region_data = real_region, real_rv3d
        StatefulOperatorLogic._publish_state_value(op, ctx)
        return global_data.state_value

    def test_one_box_is_published_while_dragging(self):
        region, rv3d = _view3d()
        if region is None:
            self.skipTest("no 3D viewport in this Blender")
        boxes, region_ptr = self._publish(self._op())
        self.assertEqual(region_ptr, region.as_pointer())
        self.assertEqual(len(boxes), 1)
        text, coords, focused = boxes[0]
        self.assertEqual(text, "50 mm")
        self.assertFalse(focused, "nothing has focus until it is typed into")
        # The anchor is the geometry's world point projected into the region.
        from bpy_extras.view3d_utils import location_3d_to_region_2d

        expected = location_3d_to_region_2d(
            region, rv3d, self.sketch.world_matrix @ Vector((0.0, 0.0, 0.0))
        )
        self.assertEqual(tuple(coords), tuple(expected))

    def test_nothing_is_published_without_an_anchor(self):
        op = self._op()
        op._active_sketch = None
        from ..model.sketch_ref import set_active_sketch

        set_active_sketch(self.context, None)
        self.assertIsNone(self._publish(op))

    def test_numeric_entry_wins_over_the_resolved_value(self):
        op = self._op()
        op._numeric = _Numeric(typed={0: "12"})
        boxes, _ = self._publish(op)
        self.assertEqual(boxes[0][0], "12")
        self.assertTrue(boxes[0][2])

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


class TestStateValueAnchor(Sketch2dTestCase):
    """Where a 2D tool puts a single box: on the thing it is drawing."""

    def _line_op(self):
        from ..operators.add_line_2d import View3D_OT_slvs_add_line2d

        harness = OpHarness(View3D_OT_slvs_add_line2d, self.sketch, self.context)
        harness.op._numeric = SimpleNamespace(is_active=False, current="")
        return harness

    def _only_anchor(self, op, values):
        anchors = op.state_value_anchors(self.context, values, 1)
        self.assertEqual(len(anchors), 1)
        return anchors[0]

    def _world(self, local):
        return self.sketch.world_matrix @ Vector(local).to_3d()

    def test_the_first_point_anchors_on_itself(self):
        op = self._line_op().op
        anchor = self._only_anchor(op, [Vector((2.0, 1.0))])
        self.assertAlmostEqual((anchor - self._world((2.0, 1.0))).length, 0.0, places=5)

    def test_a_segment_anchors_halfway_along_it(self):
        harness = self._line_op()
        harness.place_point((0.0, 0.0))
        harness.op.redo_states(self.context)
        anchor = self._only_anchor(harness.op, [Vector((4.0, 0.0))])
        self.assertAlmostEqual((anchor - self._world((2.0, 0.0))).length, 0.0, places=5)

    def test_a_number_state_anchors_on_the_point_before_it(self):
        from ..operators.add_circle import View3D_OT_slvs_add_circle2d

        harness = OpHarness(View3D_OT_slvs_add_circle2d, self.sketch, self.context)
        harness.place_point((1.0, 2.0))
        harness.op.redo_states(self.context)
        # The radius state carries a float, so there is no live point to average.
        anchor = self._only_anchor(harness.op, [0.5])
        self.assertAlmostEqual((anchor - self._world((1.0, 2.0))).length, 0.0, places=5)

    def test_no_sketch_means_no_anchor(self):
        op = self._line_op().op
        op._active_sketch = None
        from ..model.sketch_ref import set_active_sketch

        set_active_sketch(self.context, None)
        self.assertEqual(
            op.state_value_anchors(self.context, [Vector((1.0, 1.0))], 1), []
        )


class _Numeric:
    """A numeric input with given buffers, standing in for a live one."""

    def __init__(self, typed=None, count=1, focused=0):
        self._typed = typed or {}
        self.substate_count = count
        self.substate_index = focused
        self.is_active = True
        self.prop = None

    def get(self, index):
        return self._typed.get(index, "")

    @property
    def current(self):
        return self.get(self.substate_index)


class TestValueBoxes(Sketch2dTestCase):
    """Typing splits the one value into a box per axis, on its own edge."""

    def _rect_op(self, start=(-0.3, -0.2), live=(0.3, 0.2)):
        from ..operators.add_rectangle import View3D_OT_slvs_add_rectangle

        harness = OpHarness(View3D_OT_slvs_add_rectangle, self.sketch, self.context)
        harness.place_point(start)
        harness.op.redo_states(self.context)
        harness.op._status_value = "(0.6 m, 0.4 m)"
        harness.op._status_values = (Vector(live),)
        return harness.op

    def test_dragging_shows_one_text_and_no_focus(self):
        op = self._rect_op()
        op._numeric = SimpleNamespace(is_active=False)
        texts, focused = op._state_value_texts()
        self.assertEqual(texts, ["(0.6 m, 0.4 m)"])
        self.assertEqual(focused, -1)

    def test_typing_splits_the_value_per_axis(self):
        op = self._rect_op()
        op._numeric = _Numeric(typed={0: "600"}, count=2, focused=0)
        texts, focused = op._state_value_texts()
        # The typed component shows what was typed; the other keeps dragging.
        self.assertEqual(texts, ["600", "0.4 m"])
        self.assertEqual(focused, 0)

    def test_focus_follows_the_substate(self):
        op = self._rect_op()
        op._numeric = _Numeric(typed={0: "600"}, count=2, focused=1)
        self.assertEqual(op._state_value_texts()[1], 1)

    def test_each_axis_box_sits_on_the_leg_it_measures(self):
        op = self._rect_op()
        anchors = op.state_value_anchors(self.context, (Vector((0.3, 0.2)),), 2)
        self.assertEqual(len(anchors), 2)
        matrix = self.sketch.world_matrix
        # Width against the horizontal edge, height against the vertical one.
        expected_x = matrix @ Vector((0.0, -0.2, 0.0))
        expected_y = matrix @ Vector((0.3, 0.0, 0.0))
        self.assertAlmostEqual((anchors[0] - expected_x).length, 0.0, places=5)
        self.assertAlmostEqual((anchors[1] - expected_y).length, 0.0, places=5)

    def test_one_box_still_sits_in_the_middle(self):
        op = self._rect_op()
        anchors = op.state_value_anchors(self.context, (Vector((0.3, 0.2)),), 1)
        expected = self.sketch.world_matrix @ Vector((0.0, 0.0, 0.0))
        self.assertAlmostEqual((anchors[0] - expected).length, 0.0, places=5)

    def test_boxes_stack_on_one_point_when_there_is_no_leg(self):
        from ..operators.add_rectangle import View3D_OT_slvs_add_rectangle

        op = OpHarness(View3D_OT_slvs_add_rectangle, self.sketch, self.context).op
        # The very first point has nothing to span, so both boxes share it.
        anchors = op.state_value_anchors(self.context, (Vector((1.0, 2.0)),), 2)
        self.assertEqual(len(anchors), 2)
        self.assertEqual(tuple(anchors[0]), tuple(anchors[1]))
