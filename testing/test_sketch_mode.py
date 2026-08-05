"""Sketch-mode / active-sketch reconciliation after undo (dead-end bug)."""

from .utils import Sketch2dTestCase


class TestSketchModeReconcile(Sketch2dTestCase):
    def test_undo_without_active_sketch_leaves_mode(self):
        """Undoing sketch creation nulls the active sketch; sketch mode must
        follow, otherwise you are stuck (can't add or leave a sketch)."""
        from ..workspacetools.manager import enter_sketch_mode, is_sketch_mode
        from ..handlers import on_undo_redo
        from ..model.sketch_ref import set_active_sketch

        # Simulate the post-undo state: in sketch mode, but the sketch is gone.
        enter_sketch_mode()
        set_active_sketch(self.context, None)
        self.assertTrue(is_sketch_mode(), "precondition: stuck in sketch mode")

        on_undo_redo(self.context.scene)
        self.assertFalse(is_sketch_mode(), "sketch mode must be left when no sketch is active")

    def test_reconcile_enters_when_sketch_active(self):
        """Redoing back into a sketch (active again) must restore sketch mode."""
        from ..workspacetools.manager import leave_sketch_mode, is_sketch_mode
        from ..handlers import on_undo_redo
        from ..model.sketch_ref import set_active_sketch

        set_active_sketch(self.context, self.sketch.target_object)
        leave_sketch_mode()
        self.assertFalse(is_sketch_mode())

        on_undo_redo(self.context.scene)
        self.assertTrue(is_sketch_mode(), "sketch mode must be entered when a sketch is active")

    def tearDown(self):
        from ..workspacetools.manager import leave_sketch_mode
        leave_sketch_mode()
        return super().tearDown()
