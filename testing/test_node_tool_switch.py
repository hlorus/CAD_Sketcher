"""One-off tools return to a select tool after finishing.

The switch itself (framework ``_end`` on success) needs a real modal run to
observe, so this guards the intent: each one-off tool declares which select tool
it returns to, and operators that should stay active declare none.
"""

from unittest import TestCase

from ..declarations import BLENDER_SELECT_TOOL, WorkSpaceTools
from ..operators.add_sketch import View3D_OT_slvs_add_sketch
from ..operators.modifiers import (
    View3D_OT_node_array_linear,
    View3D_OT_node_extrude,
    View3D_OT_node_fill,
    View3D_OT_node_revolve,
)


class TestReturnToTool(TestCase):
    def test_object_node_tools_return_to_blender_select(self):
        for op in (
            View3D_OT_node_extrude,
            View3D_OT_node_revolve,
            View3D_OT_node_array_linear,
        ):
            self.assertEqual(op.return_to_tool, BLENDER_SELECT_TOOL, op.__name__)

    def test_add_sketch_returns_to_sketch_select(self):
        # Add Sketch enters sketch mode, so it returns to the sketch select tool.
        self.assertEqual(
            View3D_OT_slvs_add_sketch.return_to_tool, WorkSpaceTools.Select
        )

    def test_fill_stays_active(self):
        # Fill has no workspacetool, so it must not steal the active tool.
        self.assertIsNone(View3D_OT_node_fill.return_to_tool)
