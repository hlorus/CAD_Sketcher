"""A sketch can be both a projection source and a projection destination."""

from mathutils import Vector

from ..model.curve_ref import LineRef, PointRef
from ..utilities.projection_anchor import (
    LEGACY_VERTEX_ID_ATTR,
    PROJECT_VERTEX_ID_ATTR,
    VERTEX_ID_ATTR,
    iter_projected_point_bindings,
    project_mesh_vertex,
    refresh_projection_for_sketch,
    source_id_attr,
)
from .utils import Sketch2dTestCase


class TestSketchSourceAndDestination(Sketch2dTestCase):
    def _other(self):
        other = self.new_sketch()
        PointRef.create(other, (0.0, 0.0), fixed=True, is_origin=True)
        b = PointRef.create(other, (2.0, 3.0))
        c = PointRef.create(other, (5.0, 3.0))
        LineRef.create(other, b, c)
        return other, b, c

    def _refresh(self, sketch):
        self.context.view_layer.update()
        refresh_projection_for_sketch(
            sketch, self.context.evaluated_depsgraph_get(), force=True
        )

    def test_both_roles_keep_their_own_geometry(self):
        # The source id (POINT domain) and the binding (CURVE domain) used to
        # share one attribute name. Blender attribute names are unique per
        # datablock, so a sketch in both roles had one attribute for both: the
        # binding then read point data by curve index and invented bindings on
        # ordinary curves, which resolved to source point 0 and dragged them to
        # the origin while drawing.
        other, b, c = self._other()
        PointRef.create(self.sketch, (0.0, 0.0), fixed=True, is_origin=True)
        d = PointRef.create(self.sketch, (7.0, 7.0))

        project_mesh_vertex(
            self.sketch, other.target_object, 1, world_co=Vector((2.0, 3.0, 0.0))
        )
        project_mesh_vertex(
            other, self.sketch.target_object, 1, world_co=Vector((7.0, 7.0, 0.0))
        )

        # Only the projected point is bound; the sketch's own curves are not.
        self.assertEqual(len(list(iter_projected_point_bindings(other))), 1)

        self._refresh(other)
        self._refresh(self.sketch)
        self.assertLess((b.co - Vector((2.0, 3.0))).length, 1e-5)
        self.assertLess((c.co - Vector((5.0, 3.0))).length, 1e-5)
        self.assertLess((d.co - Vector((7.0, 7.0))).length, 1e-5)

    def test_source_id_and_binding_are_separate_attributes(self):
        other, _b, _c = self._other()
        PointRef.create(self.sketch, (0.0, 0.0), fixed=True, is_origin=True)
        PointRef.create(self.sketch, (7.0, 7.0))
        project_mesh_vertex(
            self.sketch, other.target_object, 1, world_co=Vector((2.0, 3.0, 0.0))
        )
        project_mesh_vertex(
            other, self.sketch.target_object, 1, world_co=Vector((7.0, 7.0, 0.0))
        )
        for sketch in (other, self.sketch):
            attrs = sketch.data.attributes
            self.assertEqual(attrs[VERTEX_ID_ATTR].domain, "POINT")
            self.assertEqual(attrs[PROJECT_VERTEX_ID_ATTR].domain, "CURVE")

    def test_legacy_source_id_migrates(self):
        # A file written before the rename carries source ids under the old name.
        other, b, _c = self._other()
        data = other.data
        data.attributes.new(LEGACY_VERTEX_ID_ATTR, "INT", "POINT")
        point_index = data.curves[1].points[0].index
        data.attributes[LEGACY_VERTEX_ID_ATTR].data[point_index].value = 7

        attr = source_id_attr(data)
        self.assertIsNotNone(attr)
        self.assertEqual(attr.name, VERTEX_ID_ATTR)
        self.assertEqual(attr.domain, "POINT")
        self.assertEqual(int(attr.data[point_index].value), 7)
        self.assertIsNone(data.attributes.get(LEGACY_VERTEX_ID_ATTR))

        # The old id still resolves, so the existing binding keeps working.
        projected = project_mesh_vertex(self.sketch, other.target_object, point_index)
        self.assertIsNotNone(projected)
        b.co = (4.0, 4.0)
        self._refresh(self.sketch)
        self.assertLess((projected.co - Vector((4.0, 4.0))).length, 1e-5)
