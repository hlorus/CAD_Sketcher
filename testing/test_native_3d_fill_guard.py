"""Regression coverage for the native free-3D Fill guard (#607/#608)."""

from types import SimpleNamespace
from unittest.mock import Mock

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

    def test_native_3d_converter_hardwires_wire_branch(self):
        """A 3D sketch must never evaluate the planar Fill Curve branch."""
        from ..model.native_3d import CONVERT_3D_WIRE_LOCK_VERSION
        from ..utilities.curve_data import CONVERT_MODIFIER_NAME

        modifier = self.sketch.target_object.modifiers.get(CONVERT_MODIFIER_NAME)
        self.assertIsNotNone(modifier)
        node_group = modifier.node_group
        self.assertIsNotNone(node_group)
        self.assertEqual(
            node_group.get("cad_sketcher_3d_wire_lock_version"),
            CONVERT_3D_WIRE_LOCK_VERSION,
        )

        fill_socket = self._fill_socket(modifier)
        self.assertFalse(fill_socket.default_value)
        if hasattr(fill_socket, "hide_in_modifier"):
            self.assertTrue(fill_socket.hide_in_modifier)

        geometry_switch = next(
            node
            for node in node_group.nodes
            if node.bl_idname == "GeometryNodeSwitch"
            and getattr(node, "input_type", "") == "GEOMETRY"
        )
        switch_input = geometry_switch.inputs.get("Switch")
        self.assertIsNotNone(switch_input)
        self.assertFalse(switch_input.is_linked)
        self.assertFalse(switch_input.default_value)

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

        # Reproduce the UI regression reported on PR #608. Even if an old file or
        # script writes the hidden Fill input back to true, the geometry switch is
        # already hard-wired to wire mode and the compatibility guard restores the
        # stored value to false.
        set_modifier_input(modifier, fill_socket.identifier, True)
        self.assertTrue(get_modifier_input(modifier, fill_socket.identifier))

        _disable_unsupported_3d_fill(self.context.scene)

        self.assertFalse(get_modifier_input(modifier, fill_socket.identifier))

    def test_rejected_fill_dirties_modifier_owner_for_gn_re_evaluation(self):
        """Resetting Fill from the depsgraph guard must invalidate the GN result."""
        from ..model.native_3d import _set_convert_fill

        fill_socket = SimpleNamespace(
            item_type="SOCKET", in_out="INPUT", name="Fill", identifier="fill"
        )

        class FakeOwner:
            def __init__(self):
                self.update_tag = Mock()

            def get(self, _name, default=None):
                return default

        owner = FakeOwner()

        class FakeModifier(dict):
            pass

        modifier = FakeModifier()
        modifier.node_group = SimpleNamespace(
            interface=SimpleNamespace(items_tree=[fill_socket])
        )
        modifier.properties = None
        modifier.id_data = owner

        self.assertTrue(_set_convert_fill(modifier, False))
        self.assertFalse(modifier["fill"])
        owner.update_tag.assert_called_once_with()
