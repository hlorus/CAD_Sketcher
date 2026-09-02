"""Regression coverage for the native free-3D Fill guard (#607/#608)."""

import bpy

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

    def test_rejected_fill_re_evaluates_to_nonplanar_wire_geometry(self):
        """Resetting Fill must invalidate the evaluated GN result immediately."""
        from ..handlers import _disable_unsupported_3d_fill
        from ..model.native_3d import create_line_3d, create_point_3d
        from ..operators.modifiers import get_modifier_input, set_modifier_input
        from ..utilities.curve_data import CONVERT_MODIFIER_NAME

        # A closed tilted loop makes the failure visible: Blender Fill Curve
        # projects it to a planar face, while the supported free-3D path is a
        # wire mesh whose vertices retain the source XYZ coordinates.
        p1 = create_point_3d(self.sketch, (0.0, 0.0, 0.0), fixed=True)
        p2 = create_point_3d(self.sketch, (2.0, 0.0, 1.0), fixed=True)
        p3 = create_point_3d(self.sketch, (0.0, 2.0, 2.0), fixed=True)
        create_line_3d(self.sketch, p1, p2)
        create_line_3d(self.sketch, p2, p3)
        create_line_3d(self.sketch, p3, p1)

        obj = self.sketch.target_object
        modifier = obj.modifiers.get(CONVERT_MODIFIER_NAME)
        self.assertIsNotNone(modifier)
        fill_socket = self._fill_socket(modifier)

        set_modifier_input(modifier, fill_socket.identifier, True)
        self.assertTrue(get_modifier_input(modifier, fill_socket.identifier))

        # The guard runs from depsgraph_update_post in real use. It must both
        # restore the supported input value and dirty the modifier owner so the
        # viewport does not keep the already-evaluated planar Fill result.
        _disable_unsupported_3d_fill(self.context.scene)
        self.assertFalse(get_modifier_input(modifier, fill_socket.identifier))

        depsgraph = self.context.evaluated_depsgraph_get()
        depsgraph.update()
        evaluated = obj.evaluated_get(depsgraph)
        mesh = bpy.data.meshes.new_from_object(evaluated, depsgraph=depsgraph)
        try:
            self.assertEqual(len(mesh.polygons), 0)
            z_values = [vertex.co.z for vertex in mesh.vertices]
            self.assertTrue(z_values)
            self.assertGreater(max(z_values) - min(z_values), 1.5)
        finally:
            bpy.data.meshes.remove(mesh)
