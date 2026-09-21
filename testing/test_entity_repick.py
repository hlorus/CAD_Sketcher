"""Drawing tools replace their own output when re-run or re-picked."""

from mathutils import Vector

from ..model.curve_ref import CircleRef, LineRef, PointRef, curve_ref
from ..utilities.curve_data import read_uuid_list
from .utils import OpHarness, Sketch2dTestCase, make_operator_double


class TestEntityRepick(Sketch2dTestCase):
    def _refs(self, cls):
        cd = self.sketch.target_object.data
        refs = (curve_ref(self.sketch, cid) for cid in read_uuid_list(cd, "curve_id"))
        return [r for r in refs if isinstance(r, cls)]

    def _commit(self, harness):
        """Finish a harness run the way the modal does: fini, then record."""
        op = harness.op
        op._capture_baseline(self.context)
        self.assertTrue(op._reapply(self.context))
        op.fini(self.context, True)
        op._record_committed_output(self.context)
        op._store_pointers()
        return op

    def _persisted(self, op):
        """The props a redo-panel run or a re-pick receives."""
        values = {
            "output_ids": getattr(op, "output_ids", ""),
            "main_output_ids": getattr(op, "main_output_ids", ""),
        }
        for i in range(len(op.get_states())):
            for suffix in ("kind", "existing", "name", "index"):
                name = "ptr%d_%s" % (i, suffix)
                values[name] = getattr(op, name, None)
            for prop in op.get_property(index=i) or []:
                values[prop] = getattr(op, prop, None)
        return values

    def _fresh(self, real_cls, values, **overrides):
        op = make_operator_double(real_cls)()
        op._state_data = {}
        op._active_sketch = self.sketch
        op._undo = False
        op._state_snapshot = None
        op.state_init_coords = None
        op.executed = False
        op.continuous_draw = False
        op.initialized = False
        for name, value in {**values, **overrides}.items():
            if value is not None:
                setattr(op, name, value)
        return op

    def _rerun(self, op, **pick):
        """Re-apply ``op`` (optionally with state ``i`` re-picked to ``ref``)."""
        if pick:
            index, ref = pick["index"], pick["ref"]
            op._restore_pointers()
            data = op.get_state_data(index)
            data["type"] = type(ref)
            data["is_existing_entity"] = True
            op.set_state_pointer([ref.curve_id], index=index, implicit=True)
            op._store_pointers()
        op._capture_baseline(self.context)
        self.assertTrue(op._reapply(self.context))
        op.fini(self.context, True)
        op._record_committed_output(self.context)
        op._store_pointers()
        return op

    def test_rerun_keeps_ids_and_does_not_duplicate(self):
        from ..operators.add_line_2d import View3D_OT_slvs_add_line2d

        h = OpHarness(View3D_OT_slvs_add_line2d, self.sketch, self.context)
        h.place_point((0.0, 0.0)).place_point((3.0, 1.0))
        first = self._commit(h)
        line_ids = [r.curve_id for r in self._refs(LineRef)]
        self.assertEqual(len(line_ids), 1)

        again = self._fresh(
            View3D_OT_slvs_add_line2d, self._persisted(first), state_index=1
        )
        self._rerun(again)

        self.assertEqual([r.curve_id for r in self._refs(LineRef)], line_ids)
        self.assertEqual(again.output_ids, first.output_ids)
        self.assertEqual(again.ptr0_name, first.ptr0_name)

    def test_rerun_keeps_names(self):
        from ..operators.add_line_2d import View3D_OT_slvs_add_line2d

        h = OpHarness(View3D_OT_slvs_add_line2d, self.sketch, self.context)
        h.place_point((0.0, 0.0)).place_point((3.0, 1.0))
        first = self._commit(h)
        line = self._refs(LineRef)[0]
        line.name = "Edge"
        line.p2.name = "Tip"

        again = self._fresh(
            View3D_OT_slvs_add_line2d, self._persisted(first), state_index=1
        )
        self._rerun(again)

        line = self._refs(LineRef)[0]
        self.assertEqual(line.name, "Edge")
        self.assertEqual(line.p2.name, "Tip")

    def test_repick_line_endpoint(self):
        from ..operators.add_line_2d import View3D_OT_slvs_add_line2d

        h = OpHarness(View3D_OT_slvs_add_line2d, self.sketch, self.context)
        h.place_point((0.0, 0.0)).place_point((3.0, 1.0))
        first = self._commit(h)
        start_id = first.ptr0_name
        placed_end = first.ptr1_name
        target = PointRef.create(self.sketch, Vector((5.0, 2.0)))

        again = self._fresh(
            View3D_OT_slvs_add_line2d, self._persisted(first), state_index=1
        )
        self._rerun(again, index=1, ref=target)

        lines = self._refs(LineRef)
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].p1.curve_id, start_id)
        self.assertEqual(lines[0].p2.curve_id, target.curve_id)
        # The point the line used to end at was the tool's own and is gone.
        ids = read_uuid_list(self.sketch.target_object.data, "curve_id")
        self.assertNotIn(placed_end, ids)
        self.assertIn(target.curve_id, ids)

    def test_repick_circle_center(self):
        from ..operators.add_circle import View3D_OT_slvs_add_circle2d

        center = self.add_point((0.0, 0.0))
        other = self.add_point((4.0, 0.0))
        h = OpHarness(View3D_OT_slvs_add_circle2d, self.sketch, self.context)
        h.pick(center).set_value(1.5)
        first = self._commit(h)
        self.assertEqual(len(self._refs(CircleRef)), 1)

        again = self._fresh(
            View3D_OT_slvs_add_circle2d, self._persisted(first), state_index=1
        )
        self._rerun(again, index=0, ref=other)

        circles = self._refs(CircleRef)
        self.assertEqual(len(circles), 1)
        self.assertEqual(circles[0].ct.curve_id, other.curve_id)
        # A picked point is never part of the tool's output.
        self.assertTrue(center.valid)

    def test_repick_rectangle_corner_keeps_one_set_of_constraints(self):
        from ..operators.add_rectangle import View3D_OT_slvs_add_rectangle

        self.context.scene.sketcher.auto_axis_constraints = True
        corner = self.add_point((-1.0, -1.0))
        h = OpHarness(View3D_OT_slvs_add_rectangle, self.sketch, self.context)
        h.pick(corner).place_point((3.0, 2.0))
        first = self._commit(h)
        constraints = len(list(self.sketch.constraints.all))
        self.assertEqual(len(self._refs(LineRef)), 4)

        moved = self.add_point((-2.0, -2.0))
        again = self._fresh(
            View3D_OT_slvs_add_rectangle, self._persisted(first), state_index=1
        )
        self._rerun(again, index=0, ref=moved)

        self.assertEqual(len(self._refs(LineRef)), 4)
        self.assertEqual(len(list(self.sketch.constraints.all)), constraints)
        self.assertTrue(corner.valid)

    def test_clearing_a_pick_falls_back_to_a_point_of_its_own(self):
        from ..operators.add_line_2d import View3D_OT_slvs_add_line2d

        target = self.add_point((5.0, 2.0))
        h = OpHarness(View3D_OT_slvs_add_line2d, self.sketch, self.context)
        h.place_point((0.0, 0.0)).pick(target)
        first = self._commit(h)
        self.assertEqual(len(self._refs(LineRef)), 1)

        again = self._fresh(
            View3D_OT_slvs_add_line2d, self._persisted(first), state_index=1
        )
        again._restore_pointers()
        # What the redo panel's clear button does for state 1.
        value = again.pick_fallback_value(self.context, 1)
        self.assertAlmostEqual((value - target.co).length, 0.0)
        for name in again.get_property(index=1):
            setattr(again, name, value)
        data = again.get_state_data(1)
        data["is_existing_entity"] = False
        data.pop("curve_id", None)
        self._rerun(again)

        lines = self._refs(LineRef)
        self.assertEqual(len(lines), 1)
        # The line ends at its own point now, where the picked one was.
        self.assertNotEqual(lines[0].p2.curve_id, target.curve_id)
        self.assertAlmostEqual((lines[0].p2.co - target.co).length, 0.0)
        self.assertTrue(target.valid)

    def test_clear_keeps_the_picked_type_to_fall_back_on(self):
        """The edit invoke blanks the state for a re-pick, but a clear needs the
        pick to read its fallback position from."""
        from ..operators.add_line_2d import View3D_OT_slvs_add_line2d

        target = self.add_point((5.0, 2.0))
        h = OpHarness(View3D_OT_slvs_add_line2d, self.sketch, self.context)
        h.place_point((0.0, 0.0)).pick(target)
        first = self._commit(h)

        again = self._fresh(
            View3D_OT_slvs_add_line2d, self._persisted(first), state_index=1
        )
        again._restore_pointers()
        again._pending_clear = True
        again._reset_edited_state(1)
        value = again.pick_fallback_value(self.context, 1)
        self.assertIsNotNone(value)
        self.assertAlmostEqual((value - target.co).length, 0.0)
