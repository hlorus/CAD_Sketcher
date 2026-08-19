"""One-off node tools return to Blender's select tool after finishing.

The interactive tool switch itself (via ``fini`` on success) needs a real modal
run to observe, so this guards the intent: the tool-backed one-off operators opt
in, and operators without their own workspacetool do not.
"""

from unittest import TestCase

from ..operators.modifiers import (
    View3D_OT_node_array_linear,
    View3D_OT_node_extrude,
    View3D_OT_node_fill,
    View3D_OT_node_revolve,
)


class TestNodeToolReturnToSelect(TestCase):
    def test_one_off_tools_opt_in(self):
        self.assertTrue(View3D_OT_node_extrude.return_to_select_tool)
        self.assertTrue(View3D_OT_node_revolve.return_to_select_tool)
        self.assertTrue(View3D_OT_node_array_linear.return_to_select_tool)

    def test_fill_does_not_switch(self):
        # Fill has no workspacetool, so it must not steal the active tool.
        self.assertFalse(View3D_OT_node_fill.return_to_select_tool)
