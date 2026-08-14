"""Regression tests for inferred-constraint validation and rollback."""

from unittest.mock import patch

from .utils import Sketch2dTestCase, make_operator_double
from ..operators.base_2d import Operator2d


class TestAutoConstraints(Sketch2dTestCase):
    def test_rejected_constraint_is_removed_and_failure_flags_are_cleared(self):
        sc = self.sketch.constraints
        p0 = self.add_point((0.0, 0.0), fixed=True)
        p1 = self.add_point((3.0, 0.0))
        line = self.add_line(p0, p1)
        existing = sc.add_distance(
            init=True,
            value=3.0,
            curve_id_1=p0.curve_id,
            curve_id_2=p1.curve_id,
        )
        self.assertTrue(self.sketch.solve(self.context))

        op = Operator2d.__new__(Operator2d)
        op._active_sketch = self.sketch
        op._state_data = {0: {}}
        op.state_index = 0
        self.context.scene.sketcher.auto_axis_constraints = True

        rejected = op.add_auto_constraint(
            self.context,
            sc.add_vertical,
            curve_id_1=line.curve_id,
        )

        self.assertIsNone(rejected)
        self.assertEqual(len(list(sc.vertical)), 0)
        self.assertEqual(self.sketch.solver_state, "OKAY")
        self.assertFalse(existing.failed)
        self.assertFalse(any(c.failed for c in sc.all))

    def _rectangle_op(self):
        from ..operators.add_rectangle import View3D_OT_slvs_add_rectangle

        op = make_operator_double(View3D_OT_slvs_add_rectangle)()
        op._active_sketch = self.sketch
        op._state_data = {1: {}}
        op.state_index = 1
        op.lines = [type("Line", (), {"curve_id": str(i)})() for i in range(4)]
        return op

    def test_cancelled_rectangle_does_not_add_auto_constraints(self):
        op = self._rectangle_op()
        with patch.object(op, "add_auto_constraint") as add:
            op.fini(self.context, False)
        add.assert_not_called()

    def test_rectangle_validates_auto_constraints_sequentially(self):
        op = self._rectangle_op()
        sc = self.sketch.constraints
        calls = []

        def validate(context, add, **kwargs):
            calls.append((add.__name__, kwargs["curve_id_1"]))

        with patch.object(op, "add_auto_constraint", side_effect=validate):
            op.fini(self.context, True)

        self.assertEqual(
            calls,
            [
                ("add_horizontal", "0"),
                ("add_vertical", "1"),
                ("add_horizontal", "2"),
                ("add_vertical", "3"),
            ],
        )
