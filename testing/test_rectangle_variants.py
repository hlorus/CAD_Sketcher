"""The center and 3-point rectangle tools.

Both build the same four lines as the corner-to-corner tool; what differs is
where the corners come from and what keeps the shape a rectangle when the sketch
solves.
"""

import math

from mathutils import Vector

from ..model.curve_ref import LineRef, curve_ref
from ..operators.add_rectangle import (
    View3D_OT_slvs_add_rectangle_3point,
    View3D_OT_slvs_add_rectangle_center,
    centered_corners,
    edge_corners,
    signed_offset,
)
from ..utilities.curve_data import read_uuid_list
from .utils import OpHarness, Sketch2dTestCase


class TestRectangleCorners(Sketch2dTestCase):
    def test_centered_corners_mirror_the_picked_one(self):
        corners = centered_corners((1.0, 1.0), (3.0, 2.0))
        self.assertEqual(corners, ((3.0, 2.0), (-1.0, 2.0), (-1.0, 0.0), (3.0, 0.0)))

    def test_edge_corners_stand_off_the_edge(self):
        corners = edge_corners((0.0, 0.0), (2.0, 0.0), 1.0)
        self.assertEqual(corners[:2], ((0.0, 0.0), (2.0, 0.0)))
        self.assertAlmostEqual(corners[2][1], 1.0)
        self.assertAlmostEqual(corners[3][1], 1.0)

    def test_edge_corners_follow_the_edge_angle(self):
        corners = edge_corners((0.0, 0.0), (0.0, 2.0), 1.0)
        self.assertAlmostEqual(corners[2][0], -1.0)
        self.assertAlmostEqual(corners[2][1], 2.0)

    def test_a_width_on_the_other_side_is_negative(self):
        self.assertGreater(signed_offset((0, 0), (2, 0), Vector((1.0, 1.0))), 0)
        self.assertLess(signed_offset((0, 0), (2, 0), Vector((1.0, -1.0))), 0)

    def test_no_edge_no_rectangle(self):
        self.assertIsNone(edge_corners((1.0, 1.0), (1.0, 1.0), 2.0))


class TestRectangleVariants(Sketch2dTestCase):
    def _lines(self):
        cd = self.sketch.target_object.data
        refs = (curve_ref(self.sketch, cid) for cid in read_uuid_list(cd, "curve_id"))
        return [r for r in refs if isinstance(r, LineRef) and r.valid]

    def _constraint_types(self):
        return sorted(c.type for c in self.sketch.constraints.all)

    def test_center_rectangle_is_centred_on_its_first_point(self):
        self.context.scene.sketcher.auto_axis_constraints = False
        h = OpHarness(View3D_OT_slvs_add_rectangle_center, self.sketch, self.context)
        h.place_point((1.0, 1.0)).place_point((3.0, 2.0))
        self.assertTrue(h.finish())

        corners = [line.p1.co for line in self._lines()]
        self.assertEqual(len(corners), 4)
        middle = sum(corners, Vector((0.0, 0.0))) / 4
        self.assertAlmostEqual(middle.x, 1.0, places=5)
        self.assertAlmostEqual(middle.y, 1.0, places=5)

    def test_center_rectangle_holds_its_center(self):
        """A diagonal plus a midpoint constraint, or the center would drift."""
        self.context.scene.sketcher.auto_axis_constraints = True
        h = OpHarness(View3D_OT_slvs_add_rectangle_center, self.sketch, self.context)
        h.place_point((0.0, 0.0)).place_point((2.0, 1.0))
        h.finish()

        self.assertIn("MIDPOINT", self._constraint_types())
        # The diagonal is construction geometry, not part of the outline.
        diagonals = [line for line in self._lines() if line.construction]
        self.assertEqual(len(diagonals), 1)

    def test_three_point_rectangle_is_rotated_and_stays_square(self):
        self.context.scene.sketcher.auto_axis_constraints = True
        h = OpHarness(View3D_OT_slvs_add_rectangle_3point, self.sketch, self.context)
        h.place_point((0.0, 0.0)).place_point((2.0, 2.0)).set_value(1.0)
        self.assertTrue(h.finish())

        lines = self._lines()
        self.assertEqual(len(lines), 4)
        edge = lines[0].p2.co - lines[0].p1.co
        self.assertAlmostEqual(math.degrees(edge.angle(Vector((1.0, 0.0)))), 45.0, 3)
        # Perpendicular and parallel hold a rotated rectangle; horizontal and
        # vertical would say nothing about it.
        types = self._constraint_types()
        self.assertIn("PERPENDICULAR", types)
        self.assertEqual(types.count("PARALLEL"), 2)
        self.assertNotIn("HORIZONTAL", types)

    def test_three_point_rectangle_assumes_a_width_until_it_is_set(self):
        """The edge is drawn against a rectangle, not against two loose points,
        and the stand-in width is a share of the edge rather than a square."""
        h = OpHarness(View3D_OT_slvs_add_rectangle_3point, self.sketch, self.context)
        h.place_point((0.0, 0.0)).place_point((3.0, 0.0))
        h.op.state_index = 1
        h.op.redo_states(self.context)
        self.assertTrue(h.op.main(self.context))

        corners = [line.p1.co for line in self._lines()]
        self.assertEqual(len(corners), 4)
        self.assertAlmostEqual(max(c.y for c in corners), 1.5, places=5)
