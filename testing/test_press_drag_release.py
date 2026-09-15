"""Tools confirm states by click-move-click and by press-drag-release."""

import bpy

from .utils import OpHarness, Sketch2dTestCase


class _Event:
    def __init__(self, value, x=0, y=0, event_type="LEFTMOUSE"):
        self.type = event_type
        self.value = value
        self.shift = False
        self.mouse_region_x = x
        self.mouse_region_y = y


class TestPressDragRelease(Sketch2dTestCase):
    def _op(self):
        from ..operators.add_line_2d import View3D_OT_slvs_add_line2d
        from ..stateful_operator.utilities.numeric import NumericInput

        op = OpHarness(View3D_OT_slvs_add_line2d, self.sketch, self.context).op
        op.wait_for_input = True
        op._numeric = NumericInput()
        return op

    def _far(self):
        return bpy.context.preferences.inputs.drag_threshold_mouse + 10

    def test_click_confirms_on_press_only(self):
        op = self._op()
        self.assertTrue(op.check_event(_Event("PRESS")))
        self.assertFalse(op.check_event(_Event("RELEASE")))
        self.assertFalse(op._drag_mode)

    def test_dragged_release_confirms_and_enters_drag_mode(self):
        op = self._op()
        self.assertTrue(op.check_event(_Event("PRESS")))
        self.assertTrue(op.check_event(_Event("RELEASE", x=self._far())))
        self.assertTrue(op._drag_mode)
        # In drag mode a press only starts the next drag; its release confirms,
        # even without moving (a plain click still works).
        self.assertFalse(op.check_event(_Event("PRESS", x=50)))
        self.assertTrue(op.check_event(_Event("RELEASE", x=50)))

    def test_release_within_threshold_is_not_a_drag(self):
        op = self._op()
        op.check_event(_Event("PRESS"))
        near = max(bpy.context.preferences.inputs.drag_threshold_mouse - 1, 0)
        self.assertFalse(op.check_event(_Event("RELEASE", x=near)))

    def test_release_without_press_is_ignored(self):
        op = self._op()
        self.assertFalse(op.check_event(_Event("RELEASE", x=self._far())))
