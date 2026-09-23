"""Putting an array on an existing axis.

The axes a revolve can be picked around are drawn for the arrays too: the
circular array picks one, and the linear array follows the one under the cursor
so a row can be put on an edge or a part's own axis instead of eyeballed.
"""

from mathutils import Matrix, Vector

from ..operators.modifiers import (
    View3D_OT_node_array_circular,
    View3D_OT_node_array_linear,
    offset_along_axis,
)
from .utils import BgsTestCase, make_operator_double


class TestOffsetAlongAxis(BgsTestCase):
    def test_the_offset_runs_along_the_axis(self):
        # The Z axis, one unit out in X: a drag reaching (1, 0, 3) is 3 along it.
        ends = (Vector((1.0, 0.0, 0.0)), Vector((1.0, 0.0, 1.0)))

        offset = offset_along_axis(Matrix.Identity(4), ends, Vector((1.0, 0.0, 3.0)))

        self.assertAlmostEqual((offset - Vector((0.0, 0.0, 3.0))).length, 0.0, places=5)

    def test_the_perpendicular_part_of_the_drag_is_dropped(self):
        # Only how far the cursor reached along the axis counts, so wandering off
        # it does not tilt the array.
        ends = (Vector((0.0, 0.0, 0.0)), Vector((1.0, 0.0, 0.0)))

        offset = offset_along_axis(Matrix.Identity(4), ends, Vector((2.0, 5.0, -4.0)))

        self.assertAlmostEqual((offset - Vector((2.0, 0.0, 0.0))).length, 0.0, places=5)

    def test_it_comes_back_in_the_objects_own_space(self):
        # A rotated object: the world Z axis is the object's own Y.
        inverse = Matrix.Rotation(3.14159265 / 2, 4, "X").inverted()
        ends = (Vector((0.0, 0.0, 0.0)), Vector((0.0, 0.0, 1.0)))

        offset = offset_along_axis(inverse, ends, Vector((0.0, 0.0, 2.0)))

        self.assertAlmostEqual(offset.length, 2.0, places=5)
        self.assertAlmostEqual(abs(offset.y), 2.0, places=5)

    def test_a_degenerate_axis_is_no_axis(self):
        ends = (Vector((1.0, 1.0, 1.0)), Vector((1.0, 1.0, 1.0)))

        self.assertIsNone(
            offset_along_axis(Matrix.Identity(4), ends, Vector((0.0, 0.0, 1.0)))
        )


class TestAxisOverlay(BgsTestCase):
    def _state_index(self, op, name):
        return next(i for i, state in enumerate(op.get_states()) if state.name == name)

    def _assert_drawn_during(self, cls, state_name):
        from .. import global_data

        op = make_operator_double(cls)()
        self.addCleanup(setattr, global_data, "axis_picker", False)
        self.addCleanup(setattr, global_data, "hover_axis", None)

        op.set_state(self.context, 0)
        self.assertFalse(global_data.axis_picker, "not while the object is picked")
        op.set_state(self.context, self._state_index(op, state_name))
        self.assertTrue(global_data.axis_picker, f"drawn during {state_name}")

        op.fini(self.context, False)
        self.assertFalse(global_data.axis_picker, "put away when the run ends")
        self.assertIsNone(global_data.hover_axis)

    def test_the_linear_array_offers_them_while_dragging(self):
        self._assert_drawn_during(View3D_OT_node_array_linear, "Offset")

    def test_the_circular_array_offers_them_while_picking(self):
        self._assert_drawn_during(View3D_OT_node_array_circular, "Axis")
