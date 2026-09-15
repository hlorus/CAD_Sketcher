"""The Bevel tool acts on selected corners and never places new points."""

from ..drawing import selection
from .utils import OpHarness, Sketch2dTestCase


class TestBevelTool(Sketch2dTestCase):
    def tearDown(self):
        selection.selected.clear()
        return super().tearDown()

    def _corner(self):
        p1 = self.add_point((0.0, 0.0))
        p2 = self.add_point((4.0, 0.0))
        p3 = self.add_point((4.0, 4.0))
        self.add_line(p1, p2)
        self.add_line(p2, p3)
        return p2

    def _point_count(self):
        from ..model.constants import SketchCurveType

        cd = self.sketch.target_object.data
        types = cd.attributes["sketch_type"]
        return sum(
            1
            for i in range(len(cd.curves))
            if types.data[i].value == SketchCurveType.POINT
        )

    def test_point_state_never_creates(self):
        from ..operators.bevel import View3D_OT_slvs_bevel

        point_state = View3D_OT_slvs_bevel.states[0]
        self.assertFalse(point_state.use_create)
        self.assertTrue(point_state.optional)

    def test_detects_selected_corners(self):
        from ..operators.bevel import View3D_OT_slvs_bevel

        corner = self._corner()
        h = OpHarness(View3D_OT_slvs_bevel, self.sketch, self.context)
        self.assertFalse(h.op._has_selected_corners())

        selection.selected.append(corner.curve_id)
        h = OpHarness(View3D_OT_slvs_bevel, self.sketch, self.context)
        self.assertTrue(h.op._has_selected_corners())

    def test_bevel_selection_without_picking(self):
        # A click on empty space skips the pick; only the selected corner bevels.
        from ..operators.bevel import View3D_OT_slvs_bevel

        corner = self._corner()
        selection.selected.append(corner.curve_id)
        before = self._point_count()

        h = OpHarness(View3D_OT_slvs_bevel, self.sketch, self.context)
        h.op.next_state(self.context)  # what the tool click on empty space does
        h.op.radius = 1.0
        h.op.dimension_radius = False  # bpy props are inert on the harness twin
        h.op.redo_states(self.context)
        self.assertTrue(h.op.main(self.context))
        arc = h.op._results[0]["arc"]
        # Previewed as construction until the lines are trimmed.
        self.assertTrue(arc.construction)
        tangent_points = h.op._results[0]["bevel_points"]
        h.op.fini(self.context, True)
        self.assertFalse(arc.construction)

        # The new tangent points are smooth joints: beveling them makes no sense.
        from ..operators.bevel import _corner_segments

        topo = self.sketch.topology
        for point in tangent_points:
            self.assertIsNone(_corner_segments(topo, point.curve_id))

        # Arc center and two tangent points added; the corner stays as a
        # construction virtual sharp. Nothing else.
        self.assertEqual(self._point_count(), before + 3)
        self.assertTrue(corner.construction)

    def test_rectangle_edge_lines_end_at_the_arcs(self):
        # Beveling a rectangle edge must move each trimmed line's own geometry to
        # its new tangent point, not only its stored endpoint reference.
        from ..model.curve_ref import LineRef, curve_ref
        from ..model.sketch_ref import set_active_sketch
        from ..operators.add_rectangle import View3D_OT_slvs_add_rectangle
        from ..operators.bevel import View3D_OT_slvs_bevel
        from ..utilities.curve_data import read_uuid_list

        for edge in range(4):
            with self.subTest(edge=edge):
                sketch = self.new_sketch()
                set_active_sketch(self.context, sketch.target_object)
                rect = OpHarness(View3D_OT_slvs_add_rectangle, sketch, self.context)
                rect.place_point((0.0, 0.0))
                rect.place_point((6.0, 3.0))
                rect.finish()

                cd = sketch.target_object.data
                lines = [
                    r
                    for r in (
                        curve_ref(sketch, c) for c in read_uuid_list(cd, "curve_id")
                    )
                    if isinstance(r, LineRef)
                ]
                selection.selected.clear()
                selection.selected.append(lines[edge].curve_id)

                bevel = OpHarness(View3D_OT_slvs_bevel, sketch, self.context)
                bevel.op.next_state(self.context)
                bevel.op.radius = 1.0
                bevel.op.dimension_radius = False
                self.assertTrue(bevel.finish())

                for i, cid in enumerate(read_uuid_list(cd, "curve_id")):
                    line = curve_ref(sketch, cid)
                    if not isinstance(line, LineRef):
                        continue
                    points = cd.curves[i].points
                    for k, end in ((0, line.p1), (1, line.p2)):
                        drawn = points[k].position
                        self.assertAlmostEqual(drawn[0], end.co.x, places=4)
                        self.assertAlmostEqual(drawn[1], end.co.y, places=4)

    def _rectangle(self):
        from ..model.curve_ref import LineRef, PointRef, curve_ref
        from ..model.sketch_ref import set_active_sketch
        from ..operators.add_rectangle import View3D_OT_slvs_add_rectangle
        from ..utilities.curve_data import read_uuid_list

        sketch = self.new_sketch()
        set_active_sketch(self.context, sketch.target_object)
        rect = OpHarness(View3D_OT_slvs_add_rectangle, sketch, self.context)
        rect.place_point((0.0, 0.0))
        rect.place_point((6.0, 3.0))
        rect.finish()
        refs = [
            curve_ref(sketch, c)
            for c in read_uuid_list(sketch.target_object.data, "curve_id")
        ]
        lines = [r for r in refs if isinstance(r, LineRef)]
        points = [r for r in refs if isinstance(r, PointRef) and not r.is_origin]
        return sketch, lines, points

    def _bevel(self, sketch, ids, radius, dimension=False):
        from ..operators.bevel import View3D_OT_slvs_bevel

        selection.selected.clear()
        selection.selected.extend(ids)
        bevel = OpHarness(View3D_OT_slvs_bevel, sketch, self.context)
        bevel.op.next_state(self.context)
        bevel.op.radius = radius
        bevel.op.dimension_radius = dimension
        self.assertTrue(bevel.finish())
        return bevel.op

    def test_dimension_to_corner_survives(self):
        sketch, lines, points = self._rectangle()
        corner = next(p for p in points if p.co.x > 5 and p.co.y < 1)
        opposite = next(p for p in points if p.co.x < 1 and p.co.y > 2)
        sketch.constraints.add_distance(
            init=True, curve_id_1=opposite.curve_id, curve_id_2=corner.curve_id
        )
        before = len(list(sketch.constraints.all))

        self._bevel(sketch, [corner.curve_id], 1.0)

        # The dimension still references the kept corner, which stays on both lines.
        self.assertTrue(corner.valid)
        self.assertGreaterEqual(len(list(sketch.constraints.all)), before)
        self.assertNotEqual(sketch.solver_state, "INCONSISTENT")
        self.assertAlmostEqual(corner.co.x, 6.0, places=3)
        self.assertAlmostEqual(corner.co.y, 0.0, places=3)

    def test_radius_dimension_only_when_requested(self):
        sketch, lines, points = self._rectangle()
        corner = points[0]
        self._bevel(sketch, [corner.curve_id], 1.0)
        self.assertEqual(len(sketch.constraints.diameter), 0)

        sketch, lines, points = self._rectangle()
        self._bevel(sketch, [points[0].curve_id], 1.0, dimension=True)
        self.assertEqual(len(sketch.constraints.diameter), 1)
        dim = sketch.constraints.diameter[0]
        self.assertTrue(dim.setting)
        self.assertAlmostEqual(dim.value, 1.0, places=4)

    def test_radius_clamped_to_fit(self):
        # Both corners of the 3-long right edge share it: at most 1.5 each.
        sketch, lines, points = self._rectangle()
        right = [p for p in points if p.co.x > 5]
        op = self._bevel(sketch, [p.curve_id for p in right], 10.0)
        self.assertLessEqual(op.radius, 1.5)
        self.assertGreater(op.radius, 1.49)
        self.assertEqual(len(op._results), 2)

    def test_smooth_joints_are_not_corners(self):
        from ..operators.bevel import _corner_segments

        # Line running tangentially into a quarter arc (center (4, 1)).
        start = self.add_point((0.0, 0.0))
        joint = self.add_point((4.0, 0.0))
        self.add_line(start, joint)
        self.add_arc(self.add_point((4.0, 1.0)), joint, self.add_point((5.0, 1.0)))
        # Two collinear lines.
        a = self.add_point((0.0, 5.0))
        b = self.add_point((2.0, 5.0))
        self.add_line(a, b)
        self.add_line(b, self.add_point((4.0, 5.0)))
        # A real corner for comparison.
        corner = self._corner()

        topo = self.sketch.topology
        self.assertIsNone(_corner_segments(topo, joint.curve_id))
        self.assertIsNone(_corner_segments(topo, b.curve_id))
        self.assertIsNotNone(_corner_segments(topo, corner.curve_id))

        selection.selected.extend([joint.curve_id, b.curve_id])
        from ..operators.bevel import View3D_OT_slvs_bevel

        h = OpHarness(View3D_OT_slvs_bevel, self.sketch, self.context)
        self.assertFalse(h.op._has_selected_corners())
