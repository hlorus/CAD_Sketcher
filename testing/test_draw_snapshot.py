"""Interactive-undo snapshot for 2D draw operators.

Draw operators snapshot state each mouse-move so an interactive step can be
undone before the next preview. The base snapshot re-serialized the whole scene
plus every sketch's curves; ``Operator2d`` scopes it to the active sketch's curve
data + constraints (issue #342). These guard that the scoped snapshot restores
the active sketch exactly and never touches other sketches.
"""

from ..model.curve_ref import LineRef, PointRef
from ..model.sketch_ref import set_active_sketch
from ..operators.add_rectangle import View3D_OT_slvs_add_rectangle
from .utils import Sketch2dTestCase, make_operator_double


class TestDrawSnapshot(Sketch2dTestCase):
    def _op(self):
        op = make_operator_double(View3D_OT_slvs_add_rectangle)()
        op._state_data = {}
        return op

    def _curve_count(self):
        return len(self.sketch.target_object.data.curves)

    def test_restore_returns_active_sketch_to_snapshot(self):
        set_active_sketch(self.context, self.sketch.target_object)
        p0 = self.add_point((0, 0), fixed=True)
        p1 = self.add_point((2, 0))
        line = self.add_line(p0, p1)
        before = self._curve_count()
        ncon_before = len(list(self.sketch.constraints.all))

        op = self._op()
        snap = op.create_snapshot(self.context)

        # Simulate an interactive preview: add geometry + a constraint.
        a = PointRef.create(self.sketch, (5, 5))
        b = PointRef.create(self.sketch, (6, 6))
        ln = LineRef.create(self.sketch, a, b)
        self.sketch.constraints.add_horizontal(curve_id_1=ln.curve_id)
        self.assertGreater(self._curve_count(), before)

        op.restore_snapshot(self.context, snap)

        self.assertEqual(self._curve_count(), before)
        self.assertEqual(len(list(self.sketch.constraints.all)), ncon_before)
        # The original line still resolves to its real endpoints.
        self.assertEqual(tuple(round(v, 1) for v in line.p2.co), (2.0, 0.0))

    def test_snapshot_leaves_other_sketches_untouched(self):
        # A second sketch that must be ignored by the active sketch's snapshot.
        other = self.new_sketch()
        op_other = PointRef.create(other, (1, 1))
        LineRef.create(other, op_other, PointRef.create(other, (2, 2)))
        other_count = len(other.target_object.data.curves)

        set_active_sketch(self.context, self.sketch.target_object)
        PointRef.create(self.sketch, (0, 0))
        op = self._op()
        snap = op.create_snapshot(self.context)
        # The snapshot only names the active sketch.
        self.assertEqual(snap["active_name"], self.sketch.target_object.name)

        # Mutating the other sketch then restoring must not revert it.
        LineRef.create(
            other, PointRef.create(other, (3, 3)), PointRef.create(other, (4, 4))
        )
        grown = len(other.target_object.data.curves)
        op.restore_snapshot(self.context, snap)
        self.assertEqual(len(other.target_object.data.curves), grown)
        self.assertGreater(grown, other_count)
