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
