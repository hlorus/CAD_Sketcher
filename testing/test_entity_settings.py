import math

import bpy
from mathutils import Vector

from .utils import BgsTestCase, Sketch2dTestCase


class TestEntitySettings(Sketch2dTestCase):
    """Per-entity settings restored to the context menu after the 0.30 refactor.

    Points expose editable coordinates (Set Coordinates) and arcs expose an
    Invert Direction toggle, each backed by an operator.
    """

    RADIUS = 2.0

    def _end_at(self, degrees):
        a = math.radians(degrees)
        return Vector((self.RADIUS * math.cos(a), self.RADIUS * math.sin(a)))

    def _point_count(self, arc):
        from ..utilities.curve_data import get_curve_data

        cd, idx, _ = get_curve_data(self.sketch, arc.curve_id)
        return cd.curves[idx].points_length

    def test_set_point_coords_moves_point(self):
        pt = self.add_point((0.0, 0.0))
        result = bpy.ops.view3d.slvs_set_point_coords(
            "EXEC_DEFAULT", curve_id=pt.curve_id, x=1.5, y=-2.5
        )
        self.assertEqual(result, {"FINISHED"})
        self.assertAlmostEqual(pt.co.x, 1.5, places=5)
        self.assertAlmostEqual(pt.co.y, -2.5, places=5)

    def test_set_point_coords_y_only(self):
        """Editing just Y (X left at its current value) must move only Y."""
        pt = self.add_point((7.0, 0.0))
        result = bpy.ops.view3d.slvs_set_point_coords(
            "EXEC_DEFAULT", curve_id=pt.curve_id, x=7.0, y=9.0
        )
        self.assertEqual(result, {"FINISHED"})
        self.assertAlmostEqual(pt.co.x, 7.0, places=5)
        self.assertAlmostEqual(pt.co.y, 9.0, places=5)

    def test_flip_arc_gives_complementary_sweep(self):
        ct = self.add_point((0.0, 0.0))
        start = self.add_point((self.RADIUS, 0.0))
        end = self.add_point(self._end_at(30))
        arc = self.add_arc(ct, start, end)

        # 30 degree sweep -> single segment (2 points).
        self.assertAlmostEqual(math.degrees(arc.angle), 30, places=3)
        self.assertEqual(self._point_count(arc), 2)

        result = bpy.ops.view3d.slvs_flip_arc("EXEC_DEFAULT", curve_id=arc.curve_id)
        self.assertEqual(result, {"FINISHED"})

        # Endpoints swapped, so the arc now takes the long way round (330 deg),
        # and the control-point count grows to match the wider sweep.
        self.assertEqual(arc.start.curve_id, end.curve_id)
        self.assertEqual(arc.end.curve_id, start.curve_id)
        self.assertAlmostEqual(math.degrees(arc.angle), 330, places=3)
        self.assertEqual(self._point_count(arc), 5)

    def test_flip_arc_is_reversible(self):
        ct = self.add_point((0.0, 0.0))
        start = self.add_point((self.RADIUS, 0.0))
        end = self.add_point(self._end_at(90))
        arc = self.add_arc(ct, start, end)
        start_id, end_id = arc.start.curve_id, arc.end.curve_id

        bpy.ops.view3d.slvs_flip_arc("EXEC_DEFAULT", curve_id=arc.curve_id)
        bpy.ops.view3d.slvs_flip_arc("EXEC_DEFAULT", curve_id=arc.curve_id)

        self.assertEqual(arc.start.curve_id, start_id)
        self.assertEqual(arc.end.curve_id, end_id)
        self.assertAlmostEqual(math.degrees(arc.angle), 90, places=3)


class TestPointCoords3D(BgsTestCase):
    """Set Coordinates edits a full local X/Y/Z on a free-3D sketch point."""

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

    def test_set_point_coords_writes_z(self):
        from ..model.native_3d import create_point_3d

        pt = create_point_3d(self.sketch, (1.0, 2.0, 3.0))
        result = bpy.ops.view3d.slvs_set_point_coords(
            "EXEC_DEFAULT", curve_id=pt.curve_id, x=4.0, y=5.0, z=6.0
        )
        self.assertEqual(result, {"FINISHED"})
        pos = pt._first_point_3d()
        self.assertAlmostEqual(pos.x, 4.0, places=5)
        self.assertAlmostEqual(pos.y, 5.0, places=5)
        self.assertAlmostEqual(pos.z, 6.0, places=5)
