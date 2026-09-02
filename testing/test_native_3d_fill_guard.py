"""Regression coverage for the native free-3D Fill guard (#607/#608)."""

from .utils import BgsTestCase


class TestNative3DFillGuard(BgsTestCase):
    def setUp(self):
        from ..model.native_3d import create_3d_sketch
        from ..model.sketch_ref import set_active_sketch

        self.sketch = create_3d_sketch(self.context, self._testMethodName)
        set_active_sketch(self.context, self.sketch)
        return super().setUp()

    def tearDown(self):
        from ..model.sketch_ref import set_active_sketch

        set_active_sketch(self.context, None)
        self.sketch.remove_objects()
        return super().tearDown()

    def _fill_socket(self, modifier):
        return next(
            item
            for item in modifier.node_group.interface.items_tree
            if getattr(item, "item_type", "") == "SOCKET"
            and getattr(item, "in_out", "") == "INPUT"
            and item.name == "Fill"
        )

    def test_manual_fill_toggle_is_rejected_for_native_3d_sketch(self):
        """Free-3D sketches must never enter Blender's planar Fill Curve path."""
        from ..handlers import _disable_unsupported_3d_fill
        from ..operators.modifiers import get_modifier_input, set_modifier_input
        from ..utilities.curve_data import CONVERT_MODIFIER_NAME

        modifier = self.sketch.target_object.modifiers.get(CONVERT_MODIFIER_NAME)
        self.assertIsNotNone(modifier)
        self.assertIsNotNone(modifier.node_group)

        fill_socket = self._fill_socket(modifier)
        self.assertFalse(get_modifier_input(modifier, fill_socket.identifier))

        # Reproduce the UI regression reported on PR #608: the user manually
        # enables Fill on the shared convert modifier of a free-3D sketch.
        set_modifier_input(modifier, fill_socket.identifier, True)
        self.assertTrue(get_modifier_input(modifier, fill_socket.identifier))

        _disable_unsupported_3d_fill(self.context.scene)

        self.assertFalse(get_modifier_input(modifier, fill_socket.identifier))
