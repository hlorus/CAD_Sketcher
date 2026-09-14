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
        self.assertTrue(h.finish())

        # Corner removed, arc center and two tangent points added: nothing else.
        self.assertEqual(self._point_count(), before + 2)
