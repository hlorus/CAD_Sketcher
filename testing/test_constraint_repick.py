"""Re-picking a constraint's entity from the redo panel replaces the constraint."""

from ..drawing import selection
from .utils import OpHarness, Sketch2dTestCase


class TestConstraintRepick(Sketch2dTestCase):
    def tearDown(self):
        selection.selected.clear()
        return super().tearDown()

    def _line(self, p1, p2):
        return self.add_line(self.add_point(p1), self.add_point(p2))

    def _parallel_count(self):
        return len(self.sketch.constraints.parallel)

    def test_repick_replaces_the_constraint_and_keeps_its_uid(self):
        from ..operators.add_geometric_constraints import VIEW3D_OT_slvs_add_parallel

        a = self._line((0.0, 0.0), (4.0, 1.0))
        b = self._line((0.0, 3.0), (4.0, 5.0))
        c = self._line((0.0, 6.0), (4.0, 9.0))
        selection.selected.extend([a.curve_id, b.curve_id])

        first = OpHarness(VIEW3D_OT_slvs_add_parallel, self.sketch, self.context)
        first.prefill()
        first.finish(run_fini=False)
        uid = first.op.output_uid
        self.assertTrue(uid)
        self.assertEqual(self._parallel_count(), 1)

        # What the redo-panel eyedropper does: a fresh instance restored from the
        # stored picks, with the second entity re-picked, then re-applied.
        again = OpHarness(VIEW3D_OT_slvs_add_parallel, self.sketch, self.context).op
        again._state_snapshot = None
        again.output_uid = uid
        for i, ref in enumerate((a, c)):
            setattr(again, "ptr%d_kind" % i, "LineRef")
            setattr(again, "ptr%d_existing" % i, True)
            setattr(again, "ptr%d_name" % i, ref.curve_id)
            setattr(again, "ptr%d_index" % i, -1)
        again.state_index = 1
        self.assertTrue(again._reapply(self.context))

        self.assertEqual(self._parallel_count(), 1)
        constraint = self.sketch.constraints.parallel[0]
        self.assertEqual(constraint.constraint_uid, uid)
        self.assertEqual(
            set(constraint.curve_id_placements()), {a.curve_id, c.curve_id}
        )

    def test_constraint_tools_are_editable(self):
        from ..operators.add_dimension import VIEW3D_OT_slvs_add_dimension
        from ..operators.add_geometric_constraints import VIEW3D_OT_slvs_add_parallel

        self.assertTrue(VIEW3D_OT_slvs_add_parallel.editable)
        self.assertFalse(VIEW3D_OT_slvs_add_dimension.editable)


class TestPickTypesLabel(Sketch2dTestCase):
    def test_readable_type_names(self):
        import bpy

        from ..model.types import SlvsLine2D, SlvsPoint2D
        from ..stateful_operator.utilities.description import pick_types_label

        self.assertEqual(pick_types_label((SlvsLine2D, SlvsPoint2D)), "line or point")
        self.assertEqual(pick_types_label((bpy.types.MeshPolygon,)), "face")
        self.assertEqual(pick_types_label(()), "element")
