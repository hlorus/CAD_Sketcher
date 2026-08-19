"""Regression coverage for native 3D operator placement routing."""

from mathutils import Vector

from .utils import BgsTestCase


class TestNative3DOperatorRouting(BgsTestCase):
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
