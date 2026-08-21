"""End-to-end drive of the stateful creation tools (Tier 1).

Each tool is a stateful operator (see ``stateful_operator/docs.md`` and the user
docs ``interaction_system.md``): the user iterates through *pointer* states (pick
or place an element) and *property* states (enter a value) until all are valid,
then ``main`` builds the result. These tests script that iteration through
``OpHarness`` -- ``place_point`` for a pointer state's placement, ``set_value``
for a property state, ``pick`` for an existing element -- and assert the geometry
and the auto-constraints ``main``/``fini`` add.
"""


from ..model.curve_ref import ArcRef, CircleRef, LineRef, PointRef
from .utils import OpHarness, Sketch2dTestCase


class TestCreateOperators(Sketch2dTestCase):
    def _harness(self, real_cls):
        return OpHarness(real_cls, self.sketch, self.context)

    def _count_lines(self):
        from ..model.curve_ref import curve_ref
        from ..utilities.curve_data import read_uuid_list

        cd = self.sketch.target_object.data
        ids = read_uuid_list(cd, "curve_id")
        return sum(1 for cid in ids if cid and curve_ref(self.sketch, cid).is_line())

    # -- line ----------------------------------------------------------------
    def test_line_from_two_placements(self):
        from ..operators.add_line_2d import View3D_OT_slvs_add_line2d

        h = self._harness(View3D_OT_slvs_add_line2d)
        h.place_point((0.0, 0.0)).place_point((3.0, 5.0))
        h.finish()

        line = h.op.target
        self.assertIsInstance(line, LineRef)
        self.assertAlmostEqual(line.p1.co.x, 0.0)
        self.assertAlmostEqual(line.p2.co.y, 5.0)

    def test_axis_aligned_line_gets_horizontal_constraint(self):
        from ..model.horizontal import SlvsHorizontal
        from ..operators.add_line_2d import View3D_OT_slvs_add_line2d

        self.context.scene.sketcher.auto_axis_constraints = True
        h = self._harness(View3D_OT_slvs_add_line2d)
        h.place_point((0.0, 0.0)).place_point((5.0, 0.0))  # horizontal
        h.finish()

        self.assertTrue(h.op.has_alignment)
        line_cid = h.op.target.curve_id
        horiz = [
            c
            for c in self.sketch.constraints.all
            if isinstance(c, SlvsHorizontal) and line_cid in c.curve_id_placements()
        ]
        self.assertEqual(
            len(horiz), 1, "expected exactly one auto horizontal constraint"
        )

    def test_auto_constraints_toggle_off_suppresses_alignment(self):
        """With Auto Constraints disabled, an axis-aligned line gets no constraint."""
        from ..model.horizontal import SlvsHorizontal
        from ..operators.add_line_2d import View3D_OT_slvs_add_line2d

        self.context.scene.sketcher.auto_axis_constraints = False
        try:
            h = self._harness(View3D_OT_slvs_add_line2d)
            h.place_point((0.0, 0.0)).place_point((5.0, 0.0))  # horizontal
            h.finish()

            self.assertFalse(
                h.op.has_alignment, "toggle off must suppress auto alignment"
            )
            line_cid = h.op.target.curve_id
            horiz = [
                c
                for c in self.sketch.constraints.all
                if isinstance(c, SlvsHorizontal) and line_cid in c.curve_id_placements()
            ]
            self.assertEqual(
                len(horiz), 0, "no auto constraint should be added when disabled"
            )
        finally:
            self.context.scene.sketcher.auto_axis_constraints = True

    def test_shift_bypass_suppresses_alignment(self):
        """Shift on a segment (skip_auto_constraints) bypasses auto alignment
        even with the toggle enabled."""
        from ..model.horizontal import SlvsHorizontal
        from ..operators.add_line_2d import View3D_OT_slvs_add_line2d

        self.context.scene.sketcher.auto_axis_constraints = True
        h = self._harness(View3D_OT_slvs_add_line2d)
        h.place_point((0.0, 0.0)).place_point((5.0, 0.0))  # horizontal
        # Mimic Shift held during the segment (what check_event records).
        h.op.get_state_data(h.op.state_index)["skip_auto_constraints"] = True
        h.finish()

        self.assertFalse(
            h.op.has_alignment, "Shift bypass must suppress auto alignment"
        )
        line_cid = h.op.target.curve_id
        horiz = [
            c
            for c in self.sketch.constraints.all
            if isinstance(c, SlvsHorizontal) and line_cid in c.curve_id_placements()
        ]
        self.assertEqual(
            len(horiz), 0, "no auto constraint should be added under Shift bypass"
        )

    def test_shift_bypass_is_not_sticky(self):
        """A confirm with Shift sets the bypass; a later confirm without Shift
        clears it (regression: the bypass used to hang after Shift release)."""
        from ..operators.add_line_2d import View3D_OT_slvs_add_line2d

        class _Event:
            def __init__(self, shift):
                self.type = "LEFTMOUSE"
                self.value = "PRESS"
                self.shift = shift

        op = self._harness(View3D_OT_slvs_add_line2d).op
        op.check_event(_Event(shift=True))
        self.assertTrue(
            op.state_data.get("skip_auto_constraints"), "Shift confirm sets bypass"
        )
        op.check_event(_Event(shift=False))
        self.assertFalse(
            op.state_data.get("skip_auto_constraints"),
            "confirm without Shift must clear the bypass (not sticky)",
        )

    def test_diagonal_line_gets_no_alignment_constraint(self):
        from ..operators.add_line_2d import View3D_OT_slvs_add_line2d

        h = self._harness(View3D_OT_slvs_add_line2d)
        h.place_point((0.0, 0.0)).place_point((5.0, 5.0))  # 45 degrees
        h.finish()

        self.assertFalse(
            h.op.has_alignment, "diagonal line must not be auto-constrained"
        )

    def test_line_continue_draw_after_placed_endpoint(self):
        from ..operators.add_line_2d import View3D_OT_slvs_add_line2d

        h = self._harness(View3D_OT_slvs_add_line2d)
        h.place_point((0.0, 0.0)).place_point((3.0, 5.0))
        h.finish()
        # Endpoint was freshly placed (not an existing pick), so the chain continues.
        self.assertTrue(h.op.continue_draw())

    # -- circle (pointer center + property radius) ---------------------------
    def test_circle_from_center_and_radius(self):
        from ..operators.add_circle import View3D_OT_slvs_add_circle2d

        h = self._harness(View3D_OT_slvs_add_circle2d)
        h.place_point((1.0, 1.0)).set_value(2.5)  # center, then radius
        h.finish()

        circle = h.op.target
        self.assertIsInstance(circle, CircleRef)
        self.assertAlmostEqual(circle.ct.co.x, 1.0)
        self.assertAlmostEqual(circle.radius, 2.5, places=4)

    # -- arc (three pointer states) ------------------------------------------
    def test_arc_from_three_placements(self):
        from ..operators.add_arc import View3D_OT_slvs_add_arc2d

        h = self._harness(View3D_OT_slvs_add_arc2d)
        h.place_point((0.0, 0.0))  # center
        h.place_point((2.0, 0.0))  # start
        h.place_point((0.0, 2.0))  # end
        h.finish()

        arc = h.op.target
        self.assertIsInstance(arc, ArcRef)
        self.assertAlmostEqual(arc.ct.co.x, 0.0)
        self.assertAlmostEqual(arc.ct.co.y, 0.0)

    # -- rectangle (two pointer states -> four lines) ------------------------
    def test_rectangle_builds_four_lines(self):
        from ..operators.add_rectangle import View3D_OT_slvs_add_rectangle

        before = self._count_lines()
        h = self._harness(View3D_OT_slvs_add_rectangle)
        h.place_point((0.0, 0.0)).place_point((4.0, 2.0))
        h.finish()

        self.assertEqual(
            self._count_lines() - before, 4, "rectangle must add four lines"
        )

    # -- point (single property state) ---------------------------------------
    def test_point_from_coordinates(self):
        from mathutils import Vector

        from ..operators.add_point_2d import View3D_OT_slvs_add_point2d

        h = self._harness(View3D_OT_slvs_add_point2d)
        h.set_value(Vector((7.0, 8.0)))
        h.finish()

        pt = h.op.target
        self.assertIsInstance(pt, PointRef)
        self.assertAlmostEqual(pt.co.x, 7.0)
        self.assertAlmostEqual(pt.co.y, 8.0)

    def test_point_snapped_to_mesh_vertex_live_projects(self):
        # Add Point is a coordinate state (no create_element), so its main() must
        # run the snap-link itself -- otherwise snapping onto a mesh vertex would
        # only ever place a dead static point.
        from mathutils import Vector

        from ..operators.add_point_2d import View3D_OT_slvs_add_point2d
        from ..utilities.projection_anchor import iter_projected_point_bindings

        mesh = self.data.meshes.new("SnapSrc")
        mesh.from_pydata([(1.0, 1.0, 0.0)], [], [])
        mesh.update()
        source = self.data.objects.new("SnapSrc", mesh)
        self.scene.collection.objects.link(source)
        self.context.view_layer.update()

        self.context.scene.sketcher.auto_axis_constraints = True
        self.context.scene.sketcher.use_snap_project = True

        h = self._harness(View3D_OT_slvs_add_point2d)
        h.set_value(Vector((1.0, 1.0)))
        # Emulate what state_func stashes when the cursor is on a mesh vertex.
        data = h.op.get_state_data(0)
        data["snapped"] = True
        data["snap"] = {
            "type": "VERTEX",
            "object": "SnapSrc",
            "vertex_index": 0,
            "world_point": Vector((1.0, 1.0, 0.0)),
        }
        h.finish()

        bindings = list(iter_projected_point_bindings(self.sketch))
        self.assertEqual(len(bindings), 1, "the snap must create one live binding")
        self.assertEqual(bindings[0][1], source)

    # -- mixed paradigm: pick an existing point, place the other ------------
    def test_line_reuses_picked_start_point(self):
        from ..operators.add_line_2d import View3D_OT_slvs_add_line2d

        existing = self.add_point((1.0, 2.0))
        h = self._harness(View3D_OT_slvs_add_line2d)
        h.pick(existing).place_point((6.0, 2.0))
        h.finish()

        line = h.op.target
        self.assertEqual(line.p1.curve_id, existing.curve_id)
        self.assertNotEqual(line.p2.curve_id, existing.curve_id)

    def test_line_no_continue_after_picked_endpoint(self):
        from ..operators.add_line_2d import View3D_OT_slvs_add_line2d

        existing_end = self.add_point((6.0, 2.0))
        h = self._harness(View3D_OT_slvs_add_line2d)
        h.place_point((1.0, 2.0)).pick(existing_end)
        h.finish()
        # Endpoint was an existing pick, so the continuous-draw chain stops.
        self.assertFalse(h.op.continue_draw())
