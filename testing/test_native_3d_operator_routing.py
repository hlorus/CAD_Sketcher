"""Regression coverage for native 3D operator placement routing."""

import bpy
from mathutils import Vector

from .utils import BgsTestCase


class TestNative3DOperatorRouting(BgsTestCase):
    def test_add_sketch3d_operator_is_registered(self):
        """The native 3D creation entry point must exist in an enabled build."""
        self.assertTrue(hasattr(bpy.ops.view3d, "slvs_add_sketch3d"))

    def test_3d_sketch_disables_planar_fill(self):
        """A free-3D sketch must not evaluate through planar Fill Curve by default."""
        from ..model.native_3d import create_3d_sketch
        from ..operators.modifiers import get_modifier_input

        sketch = create_3d_sketch(self.context)
        modifier = sketch.target_object.modifiers.get("CAD Sketcher Convert")
        self.assertIsNotNone(modifier)
        fill_socket = next(
            item
            for item in modifier.node_group.interface.items_tree
            if getattr(item, "item_type", "") == "SOCKET"
            and getattr(item, "in_out", "") == "INPUT"
            and item.name == "Fill"
        )
        self.assertFalse(get_modifier_input(modifier, fill_socket.identifier))

    def test_line_pointer_states_use_native_3d_callbacks(self):
        from ..operators.add_line_3d import View3D_OT_slvs_add_line3d

        for state in View3D_OT_slvs_add_line3d.states:
            self.assertEqual(state.state_func, "state_func_3d")
            self.assertEqual(state.create_element, "create_element_3d")

    def test_point_state_uses_native_3d_view_plane_callback(self):
        from ..operators.add_point_3d import View3D_OT_slvs_add_point3d

        state = View3D_OT_slvs_add_point3d.states[0]
        self.assertEqual(state.state_func, "state_func_3d")

    def test_tilted_view_plane_is_not_global_xy(self):
        from ..operators.base_sketch_3d import view_plane_intersection

        anchor = Vector((0.0, 0.0, 0.0))
        normal = Vector((0.0, 1.0, 1.0)).normalized()
        hit = view_plane_intersection(
            (2.0, 4.0, 5.0),
            (2.0, -6.0, -5.0),
            anchor,
            normal,
        )

        self.assertAlmostEqual((hit - anchor).dot(normal), 0.0, places=6)
        self.assertGreater(abs(hit.z), 1e-6)

    def test_3d_select_hotkeys_switch_and_invoke_native_tools(self):
        """P/L from Select must never route through the 2D operators."""
        from ..declarations import Operators, WorkSpaceTools
        from ..stateful_operator.constants import Operators as StatefulOps
        from ..workspacetools.manager import ToolGroup, _select_keymap_for_group

        keymap = _select_keymap_for_group(ToolGroup.SKETCH_3D)
        routes = {}
        for entry in keymap:
            if entry[0] != StatefulOps.InvokeTool:
                continue
            event = entry[1]
            options = entry[2] or {}
            props = dict(options.get("properties", ()))
            routes[event.get("type")] = (
                props.get("tool_name"),
                props.get("operator"),
            )

        self.assertEqual(
            routes.get("P"),
            (WorkSpaceTools.AddPoint3D, Operators.AddPoint3D),
        )
        self.assertEqual(
            routes.get("L"),
            (WorkSpaceTools.AddLine3D, Operators.AddLine3D),
        )
        self.assertNotIn(
            (WorkSpaceTools.AddPoint2D, Operators.AddPoint2D), routes.values()
        )
        self.assertNotIn(
            (WorkSpaceTools.AddLine2D, Operators.AddLine2D), routes.values()
        )
