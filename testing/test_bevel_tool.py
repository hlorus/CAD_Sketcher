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
        h.op.redo_states(self.context)
        self.assertTrue(h.op.main(self.context))
        arc = h.op._results[0]["arc"]
        # Previewed as construction until the lines are trimmed.
        self.assertTrue(arc.construction)
        h.op.fini(self.context, True)
        self.assertFalse(arc.construction)

        # Corner removed, arc center and two tangent points added: nothing else.
        self.assertEqual(self._point_count(), before + 2)

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
