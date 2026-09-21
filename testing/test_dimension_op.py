"""The unified Dimension tool infers the constraint type from the selection.

Driven through the interaction harness (select entities, prefill, run main) so
each selection combo is asserted to produce the right dimensional constraint.
``run_fini=False`` skips the label-placement modal handoff (not headless-safe).
"""

from ..drawing import selection
from .utils import OpHarness, Sketch2dTestCase


class TestDimensionOp(Sketch2dTestCase):
    def _harness(self):
        from ..operators.add_dimension import VIEW3D_OT_slvs_add_dimension

        return OpHarness(VIEW3D_OT_slvs_add_dimension, self.sketch, self.context)

    def _line(self, p1, p2):
        return self.add_line(self.add_point(p1), self.add_point(p2))

    def _select(self, *refs):
        selection.selected.clear()
        for r in refs:
            selection.selected.append(r.curve_id)

    def _dispatch(self, *refs):
        self._select(*refs)
        h = self._harness()
        h.prefill()
        h.finish(run_fini=False)
        return h.op.target

    def test_single_line_infers_distance(self):
        from ..model.distance import SlvsDistance

        line = self._line((0.0, 0.0), (4.0, 0.0))
        self.assertIsInstance(self._dispatch(line), SlvsDistance)

    def test_line_second_line_switches_to_angle(self):
        # A line drops into placement as a length; adopting a second line during
        # placement (a click, simulated here via _second_ref) switches to angle.
        from ..model.angle import SlvsAngle
        from ..model.curve_ref import curve_ref

        l1 = self._line((0.0, 0.0), (4.0, 0.0))
        l2 = self._line((0.0, 0.0), (3.0, 3.0))
        self._select(l1)
        h = self._harness()
        h.prefill()
        h.op._second_ref = curve_ref(self.sketch, l2.curve_id)
        h.op._create_constraint(self.context)
        self.assertIsInstance(h.op.target, SlvsAngle)

    def test_two_points_infer_distance(self):
        from ..model.distance import SlvsDistance

        p1 = self.add_point((0.0, 0.0))
        p2 = self.add_point((3.0, 0.0))
        self.assertIsInstance(self._dispatch(p1, p2), SlvsDistance)

    def test_circle_infers_diameter(self):
        from ..model.diameter import SlvsDiameter

        c = self.add_circle(self.add_point((0.0, 0.0)), 2.0)
        self.assertIsInstance(self._dispatch(c), SlvsDiameter)

    def _switch(self, first, second):
        """Pick ``first``, adopt ``second`` mid-placement, return the target."""
        from ..model.curve_ref import curve_ref

        self._select(first)
        h = self._harness()
        h.prefill()
        h.op._second_ref = curve_ref(self.sketch, second.curve_id)
        h.op._create_constraint(self.context)
        return h.op.target

    def test_circle_plus_point_is_distance(self):
        from ..model.distance import SlvsDistance

        c = self.add_circle(self.add_point((0.0, 0.0)), 2.0)
        p = self.add_point((5.0, 0.0))
        self.assertIsInstance(self._switch(c, p), SlvsDistance)

    def test_circle_plus_line_is_distance(self):
        from ..model.distance import SlvsDistance

        c = self.add_circle(self.add_point((0.0, 0.0)), 2.0)
        line = self._line((5.0, -3.0), (5.0, 3.0))
        self.assertIsInstance(self._switch(c, line), SlvsDistance)

    def test_line_plus_circle_orders_curve_first(self):
        from ..model.distance import SlvsDistance

        c = self.add_circle(self.add_point((6.0, 0.0)), 2.0)
        line = self._line((0.0, 0.0), (0.0, 4.0))
        target = self._switch(line, c)
        self.assertIsInstance(target, SlvsDistance)
        # The curve must be entity1 for the native distance solver.
        self.assertEqual(target.curve_id_1, c.curve_id)

    def test_curve_to_curve_is_edge_distance(self):
        # Two curves measure edge-to-edge along the line of centres: centres are
        # 6 apart with radii 2 and 1, so the gap is 3.
        from ..model.distance import SlvsDistance

        c1 = self.add_circle(self.add_point((0.0, 0.0)), 2.0)
        c2 = self.add_circle(self.add_point((6.0, 0.0)), 1.0)
        target = self._switch(c1, c2)
        self.assertIsInstance(target, SlvsDistance)
        # The constraint references the curves themselves (so the solver adds
        # both radii), not their centres.
        self.assertEqual(set(target.curve_id_placements()), {c1.curve_id, c2.curve_id})
        self.assertAlmostEqual(target.value, 3.0, places=3)

    def test_circle_line_keeps_side(self):
        # A circle above a line must stay above it after solving (no jump across).
        c = self.add_circle(self.add_point((0.0, 3.0)), 1.0)
        line = self._line((-5.0, 0.0), (5.0, 0.0))
        self._switch(c, line)
        self.assertTrue(self.sketch.solve(self.context))
        self.assertGreater(c.ct.co.y, 0.0)

    def test_two_circles_prefill_distance(self):
        # Pre-selecting two circles and pressing D must dimension the distance
        # between them (not just diameter the first).
        from ..model.distance import SlvsDistance

        c1 = self.add_circle(self.add_point((0.0, 0.0)), 2.0)
        c2 = self.add_circle(self.add_point((6.0, 0.0)), 1.0)
        self.assertIsInstance(self._dispatch(c1, c2), SlvsDistance)

    def test_curve_to_curve_edge_distance_solves(self):
        # Enforcing an edge gap of 5 with radii 2 and 1 must place the centres 8
        # apart (the solver constrains centre-to-centre = value + r1 + r2).
        c1 = self.add_circle(self.add_point((0.0, 0.0), fixed=True), 2.0)
        c2 = self.add_circle(self.add_point((6.0, 0.0)), 1.0)
        target = self._switch(c1, c2)
        target.value = 5.0
        self.assertTrue(self.sketch.solve(self.context))
        self.assertAlmostEqual((c2.ct.co - c1.ct.co).length, 8.0, places=2)

    def test_line_length_spans_endpoints(self):
        # The native solver needs two point ids, so a lone line is measured as
        # the distance between its own endpoints.
        p1 = self.add_point((0.0, 0.0))
        p2 = self.add_point((4.0, 0.0))
        line = self.add_line(p1, p2)
        target = self._dispatch(line)
        self.assertEqual(set(target.curve_id_placements()), {p1.curve_id, p2.curve_id})

    def test_parallel_second_line_uses_distance(self):
        # Two parallel lines have no angle vertex -> the tool measures the
        # perpendicular gap as a point-to-line distance, not an angle.
        from ..model.curve_ref import curve_ref
        from ..model.distance import SlvsDistance

        l1 = self._line((0.0, 0.0), (4.0, 0.0))
        l2 = self._line((0.0, 2.0), (4.0, 2.0))
        self._select(l1)
        h = self._harness()
        h.prefill()
        h.op._second_ref = curve_ref(self.sketch, l2.curve_id)
        h.op._create_constraint(self.context)
        self.assertIsInstance(h.op.target, SlvsDistance)

    def test_duplicate_discarded_at_fini(self):
        # The tentative constraint is always created (so it previews and can still
        # change type); a duplicate is only discarded at commit (fini).
        from ..model.distance import SlvsDistance

        line = self._line((0.0, 0.0), (4.0, 0.0))
        self.assertIsInstance(self._dispatch(line), SlvsDistance)
        n1 = len(list(self.sketch.constraints.all))

        self._select(line)
        h = self._harness()
        h.prefill()
        h.finish(run_fini=False)
        # Tentative duplicate exists before commit ...
        self.assertIsInstance(h.op.target, SlvsDistance)
        self.assertEqual(len(list(self.sketch.constraints.all)), n1 + 1)
        # ... and is discarded at fini.
        h.op.fini(self.context, True)
        self.assertIsNone(h.op.target)
        self.assertEqual(len(list(self.sketch.constraints.all)), n1)

    def test_duplicate_angle_via_switch_discarded_at_fini(self):
        # The switch path stores the partner in _second_ref (not entity2); dedup
        # must compare curve ids explicitly -- the case the base ``exists`` missed.
        from ..model.angle import SlvsAngle
        from ..model.curve_ref import curve_ref

        l1 = self._line((0.0, 0.0), (4.0, 0.0))
        l2 = self._line((0.0, 0.0), (3.0, 3.0))

        self._select(l1)
        h = self._harness()
        h.prefill()
        h.op._second_ref = curve_ref(self.sketch, l2.curve_id)
        h.op._create_constraint(self.context)
        self.assertIsInstance(h.op.target, SlvsAngle)
        n1 = len(list(self.sketch.constraints.all))

        self._select(l1)
        h2 = self._harness()
        h2.prefill()
        h2.op._second_ref = curve_ref(self.sketch, l2.curve_id)
        h2.op._create_constraint(self.context)
        self.assertIsInstance(h2.op.target, SlvsAngle)  # tentative created
        h2.op.fini(self.context, True)
        self.assertIsNone(h2.op.target)  # discarded at commit
        self.assertEqual(len(list(self.sketch.constraints.all)), n1)

    def test_conflicting_value_rejected_at_fini(self):
        # Two fixed points are 3 apart; a length dimension typed to 5 can't solve,
        # so it must be rejected (and removed) at commit.
        p0 = self.add_point((0.0, 0.0), fixed=True)
        p1 = self.add_point((3.0, 0.0), fixed=True)
        n0 = len(list(self.sketch.constraints.all))

        self._select(p0, p1)
        h = self._harness()
        h.prefill()
        h.finish(run_fini=False)
        self.assertIsNotNone(h.op.target)
        self.assertEqual(len(list(self.sketch.constraints.all)), n0 + 1)

        h.op._value_input().current = "5"
        h.op._apply_value(self.context)  # forces distance 5 -> inconsistent

        h.op.fini(self.context, True)
        self.assertIsNone(h.op.target)
        self.assertEqual(len(list(self.sketch.constraints.all)), n0)

    def test_placement_value_entry_sets_value(self):
        # Typing a value during placement sets the constraint's value (routed
        # through the constraint's own subtype-aware ``value`` property).
        line = self._line((0.0, 0.0), (4.0, 0.0))
        self._select(line)
        h = self._harness()
        h.prefill()
        h.finish(run_fini=False)
        target = h.op.target
        self.assertIsNotNone(target)
        h.op._value_input().current = "10"
        h.op._apply_value(self.context)
        self.assertAlmostEqual(target.value, 10.0, places=3)

    def test_states_end_with_placement(self):
        from ..operators.add_dimension import VIEW3D_OT_slvs_add_dimension

        states = VIEW3D_OT_slvs_add_dimension.states()
        self.assertEqual(states[-1].name, "Placement")
        self.assertTrue(states[-1].optional)
        self.assertIsNone(states[-1].property)

    def tearDown(self):
        selection.selected.clear()
        return super().tearDown()


class TestDimensionPresets(Sketch2dTestCase):
    """The Dimension tool preset like the former Distance/Angle/Diameter tools."""

    def _op(self, **flags):
        from ..operators.add_dimension import VIEW3D_OT_slvs_add_dimension

        h = OpHarness(VIEW3D_OT_slvs_add_dimension, self.sketch, self.context)
        for name, value in flags.items():
            setattr(h.op, name, value)
        return h

    def _line(self, p1, p2):
        return self.add_line(self.add_point(p1), self.add_point(p2))

    def _run(self, refs, **flags):
        selection.selected.clear()
        selection.selected.extend(r.curve_id for r in refs)
        h = self._op(**flags)
        h.prefill()
        h.finish(run_fini=False)
        return h

    def _state_names(self, h):
        return [(s.name, s.optional) for s in h.op.get_states()]

    def test_radius(self):
        from ..model.diameter import SlvsDiameter

        c = self.add_circle(self.add_point((0.0, 0.0)), 2.0)
        target = self._run([c], kind="DIAMETER", radius=True).op.target
        self.assertIsInstance(target, SlvsDiameter)
        self.assertTrue(target.setting)
        self.assertAlmostEqual(target.value, 2.0, places=4)

    def test_horizontal_line_length(self):
        from ..model.distance import SlvsDistance

        line = self._line((0.0, 0.0), (3.0, 1.0))
        target = self._run([line], kind="DISTANCE", align="HORIZONTAL").op.target
        self.assertIsInstance(target, SlvsDistance)
        self.assertEqual(target.align, "HORIZONTAL")
        self.assertAlmostEqual(target.value, 3.0, places=4)

    def test_angle_between_parallel_lines(self):
        from ..model.angle import SlvsAngle

        l1 = self._line((0.0, 0.0), (3.0, 1.0))
        l2 = self._line((0.0, 2.0), (3.0, 3.0))
        target = self._run([l1, l2], kind="ANGLE").op.target
        self.assertIsInstance(target, SlvsAngle)
        self.assertAlmostEqual(target.value, 0.0, places=4)

    def test_supplementary_angle(self):
        l1 = self._line((0.0, 0.0), (4.0, 0.0))
        l2 = self._line((0.0, 0.0), (3.0, 3.0))
        target = self._run([l1, l2], kind="ANGLE", supplementary=True).op.target
        self.assertTrue(target.setting)
        self.assertAlmostEqual(target.value, 3 * 3.14159265 / 4, places=4)

    def test_horizontal_and_vertical_distance_are_not_duplicates(self):
        p1 = self.add_point((0.0, 0.0))
        p2 = self.add_point((3.0, 1.0))
        first = self._run([p1, p2], kind="DISTANCE", align="VERTICAL")
        first.op.fini(self.context, True)
        second = self._run([p1, p2], kind="DISTANCE", align="HORIZONTAL")
        self.assertFalse(second.op._is_duplicate(self.context, second.op.target))
        again = self._run([p1, p2], kind="DISTANCE", align="VERTICAL")
        self.assertTrue(again.op._is_duplicate(self.context, again.op.target))

    def test_preset_value(self):
        line = self._line((0.0, 0.0), (3.0, 0.0))
        h = self._op(kind="DISTANCE")
        h.op._preset_value = 5.0
        selection.selected[:] = [line.curve_id]
        h.prefill()
        h.finish(run_fini=False)
        self.assertAlmostEqual(h.op.target.value, 5.0, places=4)

    def test_states_per_kind(self):
        line = self._line((0.0, 0.0), (3.0, 0.0))
        c = self.add_circle(self.add_point((6.0, 0.0)), 1.0)
        cases = (
            ("ANGLE", line, [("Entity 1", False), ("Entity 2", False)]),
            ("DIAMETER", c, [("Entity 1", False)]),
            ("DISTANCE", c, [("Entity 1", False), ("Entity 2", False)]),
            ("AUTO", c, [("Entity 1", False)]),
        )
        for kind, first, expected in cases:
            with self.subTest(kind=kind):
                h = self._run([first], kind=kind)
                self.assertEqual(self._state_names(h)[:-1], expected)
                self.assertEqual(self._state_names(h)[-1][0], "Placement")

    def test_partner_rules(self):
        from ..model.curve_ref import curve_ref

        l1 = self._line((0.0, 0.0), (4.0, 0.0))
        tilted = curve_ref(self.sketch, self._line((0.0, 1.0), (3.0, 4.0)).curve_id)
        parallel = curve_ref(self.sketch, self._line((0.0, 2.0), (4.0, 2.0)).curve_id)
        point = curve_ref(self.sketch, self.add_point((1.0, 3.0)).curve_id)

        auto = self._run([l1]).op
        self.assertTrue(auto._accepts_partner(tilted))
        distance = self._run([l1], kind="DISTANCE").op
        self.assertFalse(distance._accepts_partner(tilted))
        self.assertTrue(distance._accepts_partner(parallel))
        self.assertTrue(distance._accepts_partner(point))
        aligned = self._run([l1], kind="DISTANCE", align="HORIZONTAL").op
        self.assertFalse(aligned._accepts_partner(point))

    def test_same_invocation_compares_presets(self):
        from types import SimpleNamespace

        op = self._op(kind="DISTANCE", align="HORIZONTAL").op
        same = SimpleNamespace(
            properties=SimpleNamespace(kind="DISTANCE", align="HORIZONTAL")
        )
        other = SimpleNamespace(
            properties=SimpleNamespace(kind="DISTANCE", align="VERTICAL")
        )
        plain = SimpleNamespace(properties=SimpleNamespace())
        self.assertTrue(op.is_same_invocation(same))
        self.assertFalse(op.is_same_invocation(other))
        self.assertFalse(op.is_same_invocation(plain))

    def _redo(self, refs, **props):
        """Run the redo path: the constraint is rebuilt from the given props."""
        selection.selected.clear()
        selection.selected.extend(r.curve_id for r in refs)
        h = self._op(**props)
        h.op._redoing = True
        h.prefill()
        h.finish(run_fini=False)
        return h.op.target

    def test_redo_applies_distance_value_and_flip(self):
        p = self.add_point((0.0, 2.0))
        line = self._line((-5.0, 0.0), (5.0, 0.0))
        props = dict(kind="AUTO", align="NONE", last_align="NONE", length=4.0)
        target = self._redo([p, line], flip=True, **props)
        self.assertAlmostEqual(target.value, 4.0, places=4)
        self.assertTrue(target.flip)

    def test_redo_alignment_change_remeasures(self):
        p1 = self.add_point((0.0, 0.0))
        p2 = self.add_point((3.0, 1.0))
        target = self._redo(
            [p1, p2], align="VERTICAL", last_align="NONE", length=9.0, flip=False
        )
        self.assertEqual(target.align, "VERTICAL")
        self.assertAlmostEqual(target.value, 1.0, places=4)

    def test_redo_radius_toggle_keeps_the_circle(self):
        c = self.add_circle(self.add_point((0.0, 0.0)), 2.0)
        # Measured as a diameter (4), then switched to radius in the redo panel.
        target = self._redo(
            [c], kind="DIAMETER", radius=True, last_radius=False, length=4.0
        )
        self.assertTrue(target.setting)
        self.assertAlmostEqual(target.value, 2.0, places=4)

    def test_redo_supplementary_toggle_keeps_the_lines(self):
        import math

        l1 = self._line((0.0, 0.0), (4.0, 0.0))
        l2 = self._line((0.0, 0.0), (3.0, 3.0))
        target = self._redo(
            [l1, l2],
            kind="ANGLE",
            supplementary=True,
            last_supplementary=False,
            angle=math.pi / 4,
        )
        self.assertTrue(target.setting)
        self.assertAlmostEqual(target.value, 3 * math.pi / 4, places=4)
