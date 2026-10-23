"""Copy/paste carries constraints and keeps copied entities selected for moving."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

from mathutils import Vector

from .. import global_data
from ..drawing import selection
from ..model.curve_ref import LineRef, PointRef, curve_ref
from ..operators import copy_paste
from ..operators.copy_paste import paste_constraints, snapshot_constraints
from ..operators.move import View3D_OT_slvs_move
from .utils import OpHarness, Sketch2dTestCase, make_operator_double


class TestCopyPasteConstraints(Sketch2dTestCase):
    def test_geometric_constraint_is_carried_to_the_copy(self):
        p1 = self.add_point((0.0, 0.0))
        p2 = self.add_point((3.0, 0.0))
        self.sketch.constraints.add_coincident(
            curve_id_1=p1.curve_id, curve_id_2=p2.curve_id
        )

        snaps = snapshot_constraints(self.sketch, {p1.curve_id, p2.curve_id})
        self.assertEqual([s["type"] for s in snaps], ["coincident"])

        # Simulate the paste: fresh points + the old->new id map.
        q1 = self.add_point((0.0, 5.0))
        q2 = self.add_point((3.0, 5.0))
        id_map = {p1.curve_id: q1.curve_id, p2.curve_id: q2.curve_id}

        before = len(list(self.sketch.constraints.coincident))
        paste_constraints(self.sketch, snaps, id_map)
        coincident = list(self.sketch.constraints.coincident)

        self.assertEqual(len(coincident) - before, 1, "the coincidence must be pasted")
        new = coincident[-1]
        self.assertEqual(
            {new.curve_id_1, new.curve_id_2},
            {q1.curve_id, q2.curve_id},
            "the pasted constraint must reference the pasted points, not the source",
        )

    def test_constraint_skipped_when_a_referenced_curve_is_not_copied(self):
        # Only constraints fully internal to the copied set are carried; a
        # constraint reaching outside would dangle on paste.
        p1 = self.add_point((0.0, 0.0))
        p2 = self.add_point((3.0, 0.0))
        self.sketch.constraints.add_coincident(
            curve_id_1=p1.curve_id, curve_id_2=p2.curve_id
        )

        self.assertEqual(snapshot_constraints(self.sketch, {p1.curve_id}), [])
        self.assertEqual(
            len(snapshot_constraints(self.sketch, {p1.curve_id, p2.curve_id})), 1
        )

    def test_dimensional_value_survives_with_a_fresh_uid(self):
        p1 = self.add_point((0.0, 0.0))
        p2 = self.add_point((3.0, 0.0))
        dist = self.sketch.constraints.add_distance(
            curve_id_1=p1.curve_id, curve_id_2=p2.curve_id, value=3.0
        )

        snaps = snapshot_constraints(self.sketch, {p1.curve_id, p2.curve_id})

        q1 = self.add_point((0.0, 5.0))
        q2 = self.add_point((3.0, 5.0))
        id_map = {p1.curve_id: q1.curve_id, p2.curve_id: q2.curve_id}
        paste_constraints(self.sketch, snaps, id_map)

        new = [
            c
            for c in self.sketch.constraints.distance
            if {c.curve_id_1, c.curve_id_2} == {q1.curve_id, q2.curve_id}
        ]
        self.assertEqual(len(new), 1, "the distance constraint must be pasted")
        # Independent identity so the copy's value is its own scene slot.
        self.assertTrue(new[0].constraint_uid)
        self.assertNotEqual(new[0].constraint_uid, dist.constraint_uid)
        self.assertAlmostEqual(new[0].value, 3.0, places=4)


class TestCopyPasteSelection(Sketch2dTestCase):
    """Run real copy/paste bodies, replacing only the modal move handoff."""

    def setUp(self):
        super().setUp()
        selection.selected.clear()
        self.addCleanup(selection.selected.clear)
        clipboard = getattr(global_data, "COPY_BUFFER", None)
        self.addCleanup(setattr, global_data, "COPY_BUFFER", clipboard)

    def _copy(self, *refs):
        selection.selected[:] = [ref.curve_id for ref in refs]
        op = make_operator_double(copy_paste.View3D_OT_slvs_copy)()
        self.assertEqual(op.execute(self.context), {"FINISHED"})

    def _paste(self):
        op = make_operator_double(copy_paste.View3D_OT_slvs_paste)()
        context = SimpleNamespace(scene=self.context.scene, area=Mock())
        # A background Blender has no modal viewport; run the real move body
        # separately so the selection handed to it is still exercised.
        with patch.object(copy_paste, "bpy", SimpleNamespace(ops=Mock())):
            self.assertEqual(op.execute(context), {"FINISHED"})
        return [curve_ref(self.sketch, cid) for cid in selection.selected]

    def _move(self):
        h = OpHarness(View3D_OT_slvs_move, self.sketch, self.context)
        h.op.offset = Vector((5.0, 7.0))
        h.op.main(self.context)

    def test_standalone_point_is_selected_and_moves_after_paste(self):
        point = self.add_point((1.0, 2.0))
        self._copy(point)
        pasted = self._paste()

        self.assertEqual(len(pasted), 1)
        self.assertIsInstance(pasted[0], PointRef)
        self.assertNotEqual(pasted[0].curve_id, point.curve_id)
        self._move()
        self.assertEqual(tuple(pasted[0].co), (6.0, 9.0))
        self.assertEqual(tuple(point.co), (1.0, 2.0))

    def test_mixed_selection_moves_the_isolated_point_and_line(self):
        a = self.add_point((0.0, 0.0))
        b = self.add_point((2.0, 0.0))
        line = self.add_line(a, b)
        point = self.add_point((3.0, 4.0))
        self._copy(line, point)
        pasted = self._paste()

        self.assertEqual(len(pasted), 2)
        copied_line = next(ref for ref in pasted if isinstance(ref, LineRef))
        copied_point = next(ref for ref in pasted if isinstance(ref, PointRef))
        self._move()
        self.assertEqual(tuple(copied_line.p1.co), (5.0, 7.0))
        self.assertEqual(tuple(copied_line.p2.co), (7.0, 7.0))
        self.assertEqual(tuple(copied_point.co), (8.0, 11.0))
        self.assertEqual(tuple(a.co), (0.0, 0.0))
        self.assertEqual(tuple(b.co), (2.0, 0.0))
        self.assertEqual(tuple(point.co), (3.0, 4.0))

    def test_line_dependencies_are_copied_without_being_selected(self):
        a = self.add_point((0.0, 0.0))
        b = self.add_point((2.0, 0.0))
        line = self.add_line(a, b)
        self._copy(line)
        pasted = self._paste()

        self.assertEqual(len(pasted), 1)
        self.assertIsInstance(pasted[0], LineRef)
        self._move()
        self.assertEqual(tuple(pasted[0].p1.co), (5.0, 7.0))
        self.assertEqual(tuple(pasted[0].p2.co), (7.0, 7.0))

    def test_explicitly_selected_endpoint_is_preserved_and_moves_once(self):
        a = self.add_point((0.0, 0.0))
        b = self.add_point((2.0, 0.0))
        line = self.add_line(a, b)
        self._copy(line, a)
        selection.selected.clear()
        pasted = self._paste()

        self.assertEqual(len(pasted), 2)
        copied_line = next(ref for ref in pasted if isinstance(ref, LineRef))
        copied_point = next(ref for ref in pasted if isinstance(ref, PointRef))
        self.assertEqual(copied_point.curve_id, copied_line.p1.curve_id)
        self._move()
        self.assertEqual(tuple(copied_point.co), (5.0, 7.0))
        self.assertEqual(tuple(copied_line.p2.co), (7.0, 7.0))
