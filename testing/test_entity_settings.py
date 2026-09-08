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

    def _editor(self):
        from ..model.group_sketcher import seed_entity_editor

        return seed_entity_editor, self.context.scene.sketcher.coord_editor

    def test_editor_renames_entity(self):
        line = self.add_line(self.add_point((0.0, 0.0)), self.add_point((1.0, 0.0)))
        seed, editor = self._editor()
        seed(self.context, line)
        editor.name = "Base edge"
        self.assertEqual(line.name, "Base edge")

    def test_editor_writes_both_components(self):
        pt = self.add_point((0.0, 0.0))
        seed, editor = self._editor()
        seed(self.context, pt)
        # Editing the field fires the update callback (as a UI edit would).
        editor.co_2d = (1.5, -2.5)
        self.assertAlmostEqual(pt.co.x, 1.5, places=5)
        self.assertAlmostEqual(pt.co.y, -2.5, places=5)

    def test_editor_y_only(self):
        """Editing just Y (X left at its current value) must move only Y."""
        pt = self.add_point((7.0, 0.0))
        seed, editor = self._editor()
        seed(self.context, pt)
        editor.co_2d = (editor.co_2d[0], 9.0)
        self.assertAlmostEqual(pt.co.x, 7.0, places=5)
        self.assertAlmostEqual(pt.co.y, 9.0, places=5)

    def test_constrained_but_movable_point_keeps_position(self):
        """A point that is horizontally constrained (Y pinned) but free in X
        keeps the typed X; only the constrained axis follows the constraint,
        instead of the whole edit being snapped back by the re-solve."""
        anchor = self.add_point((0.0, 0.0), fixed=True)
        p = self.add_point((2.0, 0.0))
        self.sketch.constraints.add_horizontal(
            curve_id_1=anchor.curve_id, curve_id_2=p.curve_id
        )
        self.solve()

        seed, editor = self._editor()
        seed(self.context, p)
        editor.co_2d = (5.0, 3.0)

        self.assertAlmostEqual(p.co.x, 5.0, places=3)  # movable X preserved
        self.assertAlmostEqual(p.co.y, 0.0, places=3)  # constrained Y

    def test_seed_does_not_move_point(self):
        """Seeding the editor loads current values without triggering a write."""
        pt = self.add_point((3.0, -1.0))
        seed, editor = self._editor()
        seed(self.context, pt)
        self.assertAlmostEqual(editor.co_2d[0], 3.0, places=5)
        self.assertAlmostEqual(editor.co_2d[1], -1.0, places=5)
        self.assertAlmostEqual(pt.co.x, 3.0, places=5)
        self.assertAlmostEqual(pt.co.y, -1.0, places=5)

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

    def test_editor_writes_xyz(self):
        from ..model.group_sketcher import seed_entity_editor
        from ..model.native_3d import create_point_3d

        pt = create_point_3d(self.sketch, (1.0, 2.0, 3.0))
        seed_entity_editor(self.context, pt)
        editor = self.context.scene.sketcher.coord_editor
        editor.co_3d = (4.0, 5.0, 6.0)
        pos = pt._first_point_3d()
        self.assertAlmostEqual(pos.x, 4.0, places=5)
        self.assertAlmostEqual(pos.y, 5.0, places=5)
        self.assertAlmostEqual(pos.z, 6.0, places=5)
