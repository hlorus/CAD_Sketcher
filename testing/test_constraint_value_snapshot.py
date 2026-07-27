"""Regression test for dimensional values surviving snapshot/restore (#564).

Interactive draw operators take a per-frame snapshot of sketcher state and
restore it while previewing. Dimensional constraint values live in
``scene["slvs:c:{uid}"]`` custom properties, which the property-group
serialization does not capture; restoring the constraints also fires the
``is_reference`` update callback, which re-measures the constraint with
not-yet-resolved geometry refs and writes 0. Together these zeroed the value of
existing driving dimensions as soon as the user started drawing new geometry.

``create_snapshot``/``restore_snapshot`` now preserve and re-apply those values.
"""

from .utils import Sketch2dTestCase
from ..operators.base_stateful import GenericEntityOp


class TestConstraintValueSnapshot(Sketch2dTestCase):
    def _distance(self):
        return next(
            (c for c in self.sketch.constraints.all if c.type == "DISTANCE"), None
        )

    def test_driving_value_survives_snapshot_restore(self):
        sc = self.sketch.constraints
        a = self.add_point((0, 0), fixed=True)
        b = self.add_point((3, 0))
        self.add_line(a, b)
        c = sc.add_distance(init=True, curve_id_1=a.curve_id, curve_id_2=b.curve_id)
        c.value = 5.0
        self.solve()
        self.assertAlmostEqual(c.value, 5.0)

        # The per-frame cycle an interactive draw operator performs.
        op = GenericEntityOp.__new__(GenericEntityOp)
        snapshot = op.create_snapshot(self.context)
        self.assertIn("constraint_values", snapshot)
        self.assertTrue(snapshot["constraint_values"])  # the value was captured
        op.restore_snapshot(self.context, snapshot)

        restored = self._distance()
        self.assertIsNotNone(restored)
        self.assertAlmostEqual(restored.value, 5.0)  # not clobbered to 0

    def test_reference_dimension_unaffected(self):
        # Reference ("only measure") dimensions read their value live, so they
        # were never affected -- guard that the fix doesn't change that.
        sc = self.sketch.constraints
        a = self.add_point((0, 0), fixed=True)
        b = self.add_point((4, 0))
        self.add_line(a, b)
        c = sc.add_distance(init=True, curve_id_1=a.curve_id, curve_id_2=b.curve_id)
        c.is_reference = True
        self.solve()
        measured = c.value

        op = GenericEntityOp.__new__(GenericEntityOp)
        op.restore_snapshot(self.context, op.create_snapshot(self.context))

        self.assertAlmostEqual(self._distance().value, measured)
