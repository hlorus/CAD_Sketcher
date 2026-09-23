"""A typed offset distance is held by a dimension.

Dragging an offset is a placement, so it stays free; typing an exact distance is
a decision, and the tool records it the way the bevel tool records a typed
radius.
"""

from ..model.curve_ref import CircleRef, LineRef
from ..operators.offset import View3D_OT_slvs_add_offset
from .utils import OpHarness, Sketch2dTestCase


class TestOffsetDimension(Sketch2dTestCase):
    def _offset(self, source, distance, typed):
        h = OpHarness(View3D_OT_slvs_add_offset, self.sketch, self.context)
        h.pick(source).set_value(distance)
        h.op.dimension_distance = typed
        self.assertTrue(h.finish())
        return h.op

    def _constraints(self):
        return [c for c in self.sketch.constraints.all]

    def test_a_typed_offset_of_a_line_is_dimensioned(self):
        line = self.add_line(self.add_point((0.0, 0.0)), self.add_point((4.0, 0.0)))

        self._offset(line, 1.5, typed=True)

        dimensions = [c for c in self._constraints() if c.type == "DISTANCE"]
        self.assertEqual(len(dimensions), 1)
        self.assertAlmostEqual(abs(dimensions[0].value), 1.5, places=5)

    def test_a_dragged_offset_is_left_free(self):
        line = self.add_line(self.add_point((0.0, 0.0)), self.add_point((4.0, 0.0)))

        self._offset(line, 1.5, typed=False)

        self.assertEqual(self._constraints(), [])

    def test_a_typed_circle_offset_takes_a_radius(self):
        """Concentric circles are a radius apart, which no distance expresses."""
        circle = self.add_circle(self.add_point((0.0, 0.0)), 2.0)

        self._offset(circle, 1.0, typed=True)

        dimensions = [c for c in self._constraints() if c.type == "DIAMETER"]
        self.assertEqual(len(dimensions), 1)
        self.assertTrue(dimensions[0].setting)  # shown as a radius
        self.assertAlmostEqual(dimensions[0].value, 3.0, places=5)

    def test_the_dimension_lands_on_the_new_geometry(self):
        line = self.add_line(self.add_point((0.0, 0.0)), self.add_point((4.0, 0.0)))

        op = self._offset(line, 2.0, typed=True)

        new_line = op._new_path[0]
        self.assertIsInstance(new_line, LineRef)
        dimension = next(c for c in self._constraints() if c.type == "DISTANCE")
        self.assertIn(new_line.p1.curve_id, dimension.curve_id_placements())

    def test_offsetting_a_circle_keeps_the_source_untouched(self):
        circle = self.add_circle(self.add_point((0.0, 0.0)), 2.0)

        op = self._offset(circle, 1.0, typed=True)

        self.assertIsInstance(op._new_path[0], CircleRef)
        self.assertAlmostEqual(circle.radius, 2.0, places=5)
