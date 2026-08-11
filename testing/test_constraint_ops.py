"""Constraint operators driven through the interaction system (Tier 2).

Constraint tools are stateful operators too, but built dynamically from the
constraint's ``signature`` (see ``base_constraint.GenericConstraintOp``): one
pointer state per entity slot, ``use_create=False`` (entities must be picked,
never created). These tests drive them the way constraints are normally applied
-- select the entities, invoke the tool -- and assert prefill fills the entity
slots and ``main`` creates the constraint referencing them.
"""

from ..drawing import selection
from .utils import OpHarness, Sketch2dTestCase


class TestConstraintOperators(Sketch2dTestCase):
    def _harness(self, real_cls):
        return OpHarness(real_cls, self.sketch, self.context)

    def _line(self, p1, p2):
        return self.add_line(self.add_point(p1), self.add_point(p2))

    def _select(self, *refs):
        selection.selected.clear()
        for r in refs:
            selection.selected.append(r.curve_id)

    # -- two selected lines -> parallel constraint ---------------------------
    def test_parallel_from_two_selected_lines(self):
        from ..model.parallel import SlvsParallel
        from ..operators.add_geometric_constraints import VIEW3D_OT_slvs_add_parallel

        l1 = self._line((0.0, 0.0), (4.0, 1.0))
        l2 = self._line((0.0, 3.0), (4.0, 5.0))
        self._select(l1, l2)

        h = self._harness(VIEW3D_OT_slvs_add_parallel)
        h.prefill()

        # Both entity slots filled by the selection.
        self.assertEqual(h.op.entity1.curve_id, l1.curve_id)
        self.assertEqual(h.op.entity2.curve_id, l2.curve_id)
        self.assertTrue(h.op.check_props(), "both entities should satisfy the states")

        h.finish()
        target = h.op.target
        self.assertIsInstance(target, SlvsParallel)
        self.assertEqual(
            set(target.curve_id_placements()),
            {l1.curve_id, l2.curve_id},
        )

    # -- single selected line -> horizontal constraint -----------------------
    def test_horizontal_from_single_selected_line(self):
        from ..model.horizontal import SlvsHorizontal
        from ..operators.add_geometric_constraints import VIEW3D_OT_slvs_add_horizontal

        line = self._line((0.0, 0.0), (5.0, 1.0))  # not yet horizontal
        self._select(line)

        h = self._harness(VIEW3D_OT_slvs_add_horizontal)
        h.prefill()

        self.assertEqual(h.op.entity1.curve_id, line.curve_id)
        h.finish()

        target = h.op.target
        self.assertIsInstance(target, SlvsHorizontal)
        self.assertIn(line.curve_id, target.curve_id_placements())

    def test_dimensional_constraints_expose_numeric_value_state(self):
        from ..operators.add_angle import VIEW3D_OT_slvs_add_angle
        from ..operators.add_diameter import VIEW3D_OT_slvs_add_diameter
        from ..operators.add_distance import VIEW3D_OT_slvs_add_distance

        operators = (
            VIEW3D_OT_slvs_add_angle,
            VIEW3D_OT_slvs_add_diameter,
            VIEW3D_OT_slvs_add_distance,
        )

        for operator in operators:
            with self.subTest(operator=operator.__name__):
                value_state = operator.get_states_definition()[-1]

                self.assertEqual(value_state.name, "Value")
                self.assertEqual(value_state.property, "value")
                self.assertTrue(value_state.optional)
                self.assertFalse(value_state.allow_prefill)
                self.assertEqual(
                    value_state.state_func,
                    "_current_constraint_value",
                )

    # -- wrong type is rejected: a point can't be a parallel operand ---------
    def test_point_rejected_for_parallel(self):
        from ..operators.add_geometric_constraints import VIEW3D_OT_slvs_add_parallel

        pt = self.add_point((1.0, 1.0))
        self._select(pt)

        h = self._harness(VIEW3D_OT_slvs_add_parallel)
        h.prefill()

        self.assertFalse(
            h.op.get_state_data(0).get("is_existing_entity", False),
            "a point must not fill a line-only parallel slot",
        )

    def tearDown(self):
        selection.selected.clear()
        return super().tearDown()
