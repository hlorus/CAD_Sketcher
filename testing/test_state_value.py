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
    _value_texts = StatefulOperatorLogic._value_texts
    _status_origin = None

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
        return _stub_rna(op)

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

    def test_a_box_is_published_while_dragging(self):
        region, rv3d = _view3d()
        if region is None:
            self.skipTest("no 3D viewport in this Blender")
        boxes, region_ptr = self._publish(self._op())
        self.assertEqual(region_ptr, region.as_pointer())
        # The circle's centre state is a coordinate, so it reads one per axis.
        self.assertEqual(len(boxes), 2)
        text, start, end, focused = boxes[0]
        self.assertTrue(text)
        self.assertFalse(focused, "nothing has focus until it is typed into")
        # Both ends of the stretch are the geometry's world points projected
        # into the region; the first point has no stretch, so they coincide.
        from bpy_extras.view3d_utils import location_3d_to_region_2d

        expected = location_3d_to_region_2d(
            region, rv3d, self.sketch.world_matrix @ Vector((0.0, 0.0, 0.0))
        )
        self.assertEqual(tuple(start), tuple(expected))
        self.assertEqual(tuple(end), tuple(expected))

    def test_nothing_is_published_without_an_anchor(self):
        op = self._op()
        op._active_sketch = None
        from ..model.sketch_ref import set_active_sketch

        set_active_sketch(self.context, None)
        self.assertIsNone(self._publish(op))

    def test_numeric_entry_wins_over_the_resolved_value(self):
        op = self._op()
        op._numeric = _Numeric(typed={0: "12"})
        _stub_rna(op)
        boxes, _ = self._publish(op)
        self.assertEqual(boxes[0][0], "12")
        self.assertTrue(boxes[0][3])

    def test_nothing_is_published_without_a_value(self):
        op = self._op()
        op._status_value = None
        op._status_values = ()
        self.assertIsNone(self._publish(op))

    def test_nothing_is_published_outside_a_region(self):
        self.assertIsNone(self._publish(self._op(), region=None))

    def test_a_stale_value_is_dropped(self):
        global_data.state_value = ((("old", Vector((0, 0)), Vector((0, 0)), False),), 1)
        op = self._op()
        op._status_value = ""
        op._status_values = ()
        self.assertIsNone(self._publish(op))

    def test_the_preference_turns_it_off(self):
        from ..utilities.preferences import get_prefs

        prefs = get_prefs()
        prefs.show_state_value = False
        self.addCleanup(setattr, prefs, "show_state_value", True)
        self.assertIsNone(self._publish(self._op()))


class TestStateValueSpan(Sketch2dTestCase):
    """What a 2D tool says each value measures: a stretch of what it is drawing."""

    def _line_op(self):
        from ..operators.add_line_2d import View3D_OT_slvs_add_line2d

        harness = OpHarness(View3D_OT_slvs_add_line2d, self.sketch, self.context)
        harness.op._numeric = SimpleNamespace(is_active=False, current="")
        return harness

    def _only_span(self, op, values):
        spans = op.state_value_spans(self.context, values, 1)
        self.assertEqual(len(spans), 1)
        return spans[0]

    def _world(self, local):
        return self.sketch.world_matrix @ Vector(local).to_3d()

    def _assert_at(self, point, local):
        self.assertAlmostEqual((point - self._world(local)).length, 0.0, places=5)

    def test_the_first_point_has_no_stretch(self):
        op = self._line_op().op
        start, end = self._only_span(op, [Vector((2.0, 1.0))])
        self._assert_at(start, (2.0, 1.0))
        self.assertEqual(tuple(start), tuple(end))

    def test_a_segment_spans_from_its_last_point(self):
        harness = self._line_op()
        harness.place_point((0.0, 0.0))
        harness.op.redo_states(self.context)
        start, end = self._only_span(harness.op, [Vector((4.0, 0.0))])
        self._assert_at(start, (0.0, 0.0))
        self._assert_at(end, (4.0, 0.0))

    def test_a_number_state_sits_on_the_point_before_it(self):
        from ..operators.add_circle import View3D_OT_slvs_add_circle2d

        harness = OpHarness(View3D_OT_slvs_add_circle2d, self.sketch, self.context)
        harness.place_point((1.0, 2.0))
        harness.op.redo_states(self.context)
        # The radius state carries a float, so there is no stretch to show.
        start, end = self._only_span(harness.op, [0.5])
        self._assert_at(start, (1.0, 2.0))
        self.assertEqual(tuple(start), tuple(end))

    def test_no_sketch_means_no_span(self):
        op = self._line_op().op
        op._active_sketch = None
        from ..model.sketch_ref import set_active_sketch

        set_active_sketch(self.context, None)
        self.assertEqual(
            op.state_value_spans(self.context, [Vector((1.0, 1.0))], 1), []
        )


def _stub_rna(op, subtype="XYZ"):
    """Give a twin the property RNA the real operator carries."""
    names = op.get_property() or []
    op.rna_type = SimpleNamespace(
        properties={name: SimpleNamespace(subtype=subtype) for name in names}
    )
    return op


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
        harness.op._status_values = (Vector(live),)
        _stub_rna(harness.op)
        harness.op._status_origin = Vector(start).to_3d()
        harness.op._status_value = harness.op._format_values(harness.op._status_values)
        return harness.op

    def test_dragging_reads_one_value_per_axis_with_no_focus(self):
        op = self._rect_op()
        op._numeric = SimpleNamespace(is_active=False)
        texts, focused = op._state_value_texts()
        # Measured from the first corner: the rectangle is 0.6 by 0.4, not a
        # corner at (0.3, 0.2). Each axis is dimensioned on its own edge, so
        # each gets its own text even before anything is typed.
        self.assertEqual(len(texts), 2)
        self.assertIn("0.6", texts[0])
        self.assertIn("0.4", texts[1])
        self.assertEqual(focused, -1)

    def test_typing_splits_the_value_per_axis(self):
        op = self._rect_op()
        op._numeric = _Numeric(typed={0: "600"}, count=2, focused=0)
        texts, focused = op._state_value_texts()
        # The typed component shows what was typed; the other keeps dragging,
        # and shows the height rather than the corner's coordinate.
        self.assertEqual(len(texts), 2)
        self.assertEqual(texts[0], "600")
        self.assertIn("0.4", texts[1])
        self.assertEqual(focused, 0)

    def test_focus_follows_the_substate(self):
        op = self._rect_op()
        op._numeric = _Numeric(typed={0: "600"}, count=2, focused=1)
        self.assertEqual(op._state_value_texts()[1], 1)

    def test_each_axis_spans_the_leg_it_measures(self):
        op = self._rect_op()
        spans = op.state_value_spans(self.context, (Vector((0.3, 0.2)),), 2)
        self.assertEqual(len(spans), 2)
        matrix = self.sketch.world_matrix

        def corners(span):
            return [tuple(round(v, 5) for v in point) for point in span]

        # Width along the horizontal edge, height along the vertical one, the
        # two legs meeting at the corner between them.
        expected_x = [
            matrix @ Vector((-0.3, -0.2, 0.0)),
            matrix @ Vector((0.3, -0.2, 0.0)),
        ]
        expected_y = [
            matrix @ Vector((0.3, -0.2, 0.0)),
            matrix @ Vector((0.3, 0.2, 0.0)),
        ]
        self.assertEqual(corners(spans[0]), corners(expected_x))
        self.assertEqual(corners(spans[1]), corners(expected_y))

    def test_a_single_value_spans_the_whole_segment(self):
        op = self._rect_op()
        ((start, end),) = op.state_value_spans(self.context, (Vector((0.3, 0.2)),), 1)
        matrix = self.sketch.world_matrix
        self.assertAlmostEqual(
            (start - matrix @ Vector((-0.3, -0.2, 0.0))).length, 0.0, places=5
        )
        self.assertAlmostEqual(
            (end - matrix @ Vector((0.3, 0.2, 0.0))).length, 0.0, places=5
        )

    def test_values_share_one_point_when_there_is_no_leg(self):
        from ..operators.add_rectangle import View3D_OT_slvs_add_rectangle

        op = OpHarness(View3D_OT_slvs_add_rectangle, self.sketch, self.context).op
        # The very first point has nothing to span, so both sit on it.
        spans = op.state_value_spans(self.context, (Vector((1.0, 2.0)),), 2)
        self.assertEqual(len(spans), 2)
        self.assertEqual(tuple(spans[0][0]), tuple(spans[0][1]))
        self.assertEqual(tuple(spans[0]), tuple(spans[1]))


class TestTypedDimensions(Sketch2dTestCase):
    """A number typed into a value box is kept as a driving dimension."""

    def _rectangle(self, typed, start=(0.0, 0.0), end=(0.6, 0.4)):
        from ..operators.add_rectangle import View3D_OT_slvs_add_rectangle

        harness = OpHarness(View3D_OT_slvs_add_rectangle, self.sketch, self.context)
        harness.place_point(start)
        harness.place_point(end)
        # What get_numeric_value records for the components that were typed.
        harness.op.get_state_data(1)["numeric_input"] = typed
        harness.finish()
        return harness.op

    def _dimensions(self):
        return list(self.sketch.constraints.distance)

    def test_both_axes_typed_give_two_aligned_dimensions(self):
        self._rectangle([0.6, 0.4])
        dims = self._dimensions()
        self.assertEqual(len(dims), 2)
        by_align = {d.align: d for d in dims}
        self.assertEqual(set(by_align), {"HORIZONTAL", "VERTICAL"})
        self.assertAlmostEqual(by_align["HORIZONTAL"].value, 0.6, places=5)
        self.assertAlmostEqual(by_align["VERTICAL"].value, 0.4, places=5)

    def test_only_the_typed_axis_is_dimensioned(self):
        self._rectangle([0.6, None])
        dims = self._dimensions()
        self.assertEqual(len(dims), 1)
        self.assertEqual(dims[0].align, "HORIZONTAL")
        self.assertAlmostEqual(dims[0].value, 0.6, places=5)

    def test_dragging_alone_leaves_the_points_free(self):
        self._rectangle([None, None])
        self.assertEqual(self._dimensions(), [])

    def _place(self, op, dims, start=(0.0, 0.0), end=(0.6, 0.4)):
        """Place the created dimensions against a real view, as a commit does."""
        region, rv3d = _view3d()
        if region is None:
            self.skipTest("no 3D viewport in this Blender")
        matrix = self.sketch.world_matrix
        legs = [
            (matrix @ a, matrix @ b)
            for a, b in op._axis_legs(Vector(start).to_3d(), Vector(end).to_3d(), 2)
        ]
        ctx = SimpleNamespace(
            region=region,
            region_data=rv3d,
            preferences=self.context.preferences,
        )
        by_align = {d.align: d for d in dims}
        for axis, align in enumerate(("HORIZONTAL", "VERTICAL")):
            op._place_dimension(ctx, by_align[align], legs, axis)
        return legs, by_align

    def test_a_dimension_is_placed_where_its_preview_was_drawn(self):
        op = self._rectangle([0.6, 0.4])
        legs, by_align = self._place(op, self._dimensions())
        matrix = self.sketch.world_matrix
        middle = matrix @ Vector((0.3, 0.2, 0.0))
        ui_scale = self.context.preferences.system.ui_scale or 1.0

        for axis, align in enumerate(("HORIZONTAL", "VERTICAL")):
            dim = by_align[align]
            basis = dim.matrix_basis()
            offset_axis = basis.col[1].to_3d().normalized()
            line = basis.translation + offset_axis * dim.draw_offset * ui_scale
            leg_middle = (legs[axis][0] + legs[axis][1]) / 2
            # Clear of the leg, on the side away from the rest of the shape,
            # which is where the preview drew it.
            self.assertGreater(
                (line - middle).length,
                (leg_middle - middle).length,
                "%s dimension sits inside the rectangle" % align,
            )

    def test_the_placement_matches_the_pixels_it_was_drawn_at(self):
        from bpy_extras.view3d_utils import location_3d_to_region_2d

        from ..draw_handler import live_dimension_placement, live_dimension_text_height

        op = self._rectangle([0.6, 0.4])
        region, rv3d = _view3d()
        legs, by_align = self._place(op, self._dimensions())
        ui_scale = self.context.preferences.system.ui_scale or 1.0
        height = live_dimension_text_height(self.context)

        def to_2d(point):
            return location_3d_to_region_2d(region, rv3d, point)

        screen = [[to_2d(point) for point in leg] for leg in legs]
        ends = [point for leg in screen for point in leg]
        away_from = sum(ends, Vector((0.0, 0.0))) / len(ends)

        for axis, align in enumerate(("HORIZONTAL", "VERTICAL")):
            dim = by_align[align]
            basis = dim.matrix_basis()
            offset_axis = basis.col[1].to_3d().normalized()
            line = basis.translation + offset_axis * dim.draw_offset * ui_scale
            normal, pixels = live_dimension_placement(*screen[axis], away_from, height)
            leg_middle = to_2d((legs[axis][0] + legs[axis][1]) / 2)
            # The committed dimension line is as far off the leg it measures as
            # the preview line was: the same line, so the same placement.
            self.assertAlmostEqual(
                (to_2d(line) - leg_middle).dot(normal), pixels, delta=0.1
            )

    def test_a_context_without_a_view_falls_back_to_the_screen(self):
        from ..operators.base_2d import _view_region

        region, _rv3d = _view3d()
        if region is None:
            self.skipTest("no 3D viewport in this Blender")
        # What a re-run from the redo panel hands it: not a 3D view.
        found, found_data = _view_region(
            SimpleNamespace(
                area=SimpleNamespace(type="PROPERTIES"),
                region=None,
                region_data=None,
                screen=self.context.screen,
            )
        )
        self.assertEqual(found.as_pointer(), region.as_pointer())
        self.assertIsNotNone(found_data)

    def test_the_dimension_holds_when_the_sketch_is_solved(self):
        from ..curve_solver import solve_system

        self._rectangle([0.6, 0.4])
        self.assertTrue(solve_system(self.context, sketch=self.sketch))
        dims = self._dimensions()
        self.assertFalse(any(d.failed for d in dims), [d.failed for d in dims])


class TestDimensionShape(Sketch2dTestCase):
    """The live value is drawn as a dimension on the stretch it measures."""

    def _normal(self, start, end, away_from):
        from ..draw_handler import _dimension_normal

        return _dimension_normal(Vector(start), Vector(end), Vector(away_from))

    def _shape(self, start, end, normal, height=10.0):
        from ..draw_handler import _dimension_shape

        return _dimension_shape(Vector(start), Vector(end), Vector(normal), height)

    def test_the_dimension_line_goes_on_the_outer_side(self):
        # The bottom edge of a rectangle whose middle is above it: the
        # dimension belongs below, clear of the face.
        normal = self._normal((0, 0), (100, 0), (50, 60))
        self.assertAlmostEqual(normal.y, -1.0, places=5)

    def test_a_lone_stretch_is_dimensioned_above_itself(self):
        normal = self._normal((0, 0), (100, 0), (50, 0))
        self.assertAlmostEqual(normal.y, 1.0, places=5)

    def test_the_dimension_line_clears_the_geometry(self):
        leader, witness = self._shape((0, 0), (100, 0), (0, 1))
        # Every drawn point sits off the stretch, on the normal's side.
        self.assertTrue(all(point.y > 0 for point in leader), leader)
        # Extension lines run from just off the ends out past the line.
        starts = [point.y for point in witness[0::2]]
        ends = [point.y for point in witness[1::2]]
        self.assertTrue(all(0 < y < 16 for y in starts), starts)
        self.assertTrue(all(y > 16 for y in ends), ends)
        self.assertEqual(
            [round(point.x, 5) for point in witness], [0.0, 0.0, 100.0, 100.0]
        )

    def test_arrowheads_turn_outwards_on_a_short_stretch(self):
        height = 10.0
        long_leader, _ = self._shape((0, 0), (100, 0), (0, 1), height)
        short_leader, _ = self._shape((0, 0), (15, 0), (0, 1), height)
        # Long enough: the arrows are inside, so nothing is drawn past the ends.
        self.assertTrue(all(0 <= point.x <= 100 for point in long_leader))
        # Too short: they are drawn beyond them instead, and the dimension
        # line is extended out to meet them.
        self.assertTrue(any(point.x < 0 for point in short_leader), short_leader)
        self.assertTrue(any(point.x > 15 for point in short_leader), short_leader)

    def test_the_shape_is_pairs_of_points(self):
        leader, witness = self._shape((0, 0), (100, 0), (0, 1))
        # Drawn as LINES, so each pair of points is one segment.
        self.assertEqual(len(leader) % 2, 0)
        self.assertEqual(len(witness), 4)
        self.assertTrue(all(len(point) == 3 for point in leader + witness))
