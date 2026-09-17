"""Picked elements show their name and type icon in the redo panel."""

from .utils import OpHarness, Sketch2dTestCase


class TestRedoPointerDisplay(Sketch2dTestCase):
    def _op(self, **pointer):
        from ..operators.add_geometric_constraints import VIEW3D_OT_slvs_add_vertical

        op = OpHarness(VIEW3D_OT_slvs_add_vertical, self.sketch, self.context).op
        for key, value in pointer.items():
            setattr(op, "ptr0_" + key, value)
        return op

    def test_curve_shows_name_and_icon(self):
        from .. import icon_manager
        from ..model.constants import SketchCurveType

        line = self.add_line(self.add_point((0, 0)), self.add_point((0, 2)))
        line.name = "Side"
        op = self._op(kind="LineRef", name=line.curve_id, index=-1)

        text, icon = op._pointer_display(0)
        self.assertEqual(text, "Side")
        expected = icon_manager.get_entity_icon(SketchCurveType.LINE, False)
        self.assertEqual(icon, {"icon_value": expected} if expected else {})

    def test_default_name_not_the_id(self):
        point = self.add_point((1, 1))
        op = self._op(kind="PointRef", name=point.curve_id, index=-1)
        text = op._pointer_display(0)[0]
        self.assertEqual(text, point.name)
        self.assertNotIn(point.curve_id, text)

    def test_missing_curve_is_flagged(self):
        op = self._op(kind="LineRef", name="0" * 32, index=-1)
        self.assertEqual(op._pointer_display(0), ("(missing)", {"icon": "ERROR"}))

    def test_mesh_element_and_object(self):
        op = self._op(kind="MeshPolygon", name="Cube", index=5)
        self.assertEqual(op._pointer_display(0), ("Cube: Face 5", {"icon": "FACESEL"}))
        op = self._op(kind="Object", name="Cube", index=-1)
        self.assertEqual(op._pointer_display(0), ("Cube", {"icon": "OBJECT_DATA"}))
