"""Moving a circle keeps its radius.

A circle stores its radius as the distance from its center point to its first
control point, so anything that moves the center has to carry that point along
or the rebuild reads a different radius (and a center dragged past the control
point collapses the circle).
"""

from mathutils import Vector

from ..drawing import selection
from ..operators.move import View3D_OT_slvs_move
from .utils import OpHarness, Sketch2dTestCase


class TestMoveCircle(Sketch2dTestCase):
    def _move(self, offset):
        h = OpHarness(View3D_OT_slvs_move, self.sketch, self.context)
        h.op.offset = Vector(offset)
        h.op.main(self.context)

    def setUp(self):
        super().setUp()
        selection.selected.clear()
        self.addCleanup(selection.selected.clear)

    def test_a_moved_circle_keeps_its_radius(self):
        center = self.add_point((0.0, 0.0))
        circle = self.add_circle(center, 2.0)
        selection.selected.append(circle.curve_id)

        self._move((3.0, 1.0))

        self.assertAlmostEqual(circle.ct.co.x, 3.0, places=5)
        self.assertAlmostEqual(circle.ct.co.y, 1.0, places=5)
        self.assertAlmostEqual(circle.radius, 2.0, places=5)

    def test_moving_the_center_point_alone_moves_the_circle_too(self):
        """The center is the only handle a circle has."""
        center = self.add_point((0.0, 0.0))
        circle = self.add_circle(center, 1.5)
        selection.selected.append(center.curve_id)

        self._move((0.0, 4.0))

        self.assertAlmostEqual(circle.ct.co.y, 4.0, places=5)
        self.assertAlmostEqual(circle.radius, 1.5, places=5)

    def test_a_move_past_the_control_point_does_not_collapse_the_circle(self):
        center = self.add_point((0.0, 0.0))
        circle = self.add_circle(center, 1.0)
        selection.selected.append(circle.curve_id)

        self._move((1.0, 0.0))  # the center lands on the old control point

        self.assertAlmostEqual(circle.radius, 1.0, places=5)
