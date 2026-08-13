from mathutils import Vector

from .utils import Sketch2dTestCase
from ..utilities.projection_anchor import (
    VERTEX_ID_ATTR,
    project_mesh_object,
    refresh_projection_for_sketch,
)


class TestProjectionAnchor(Sketch2dTestCase):
    def _mesh_object(self):
        mesh = self.data.meshes.new("ProjectionSourceMesh")
        mesh.from_pydata(
            [(0.0, 0.0, 1.0), (2.0, 0.0, 1.0), (2.0, 1.0, 1.0)],
            [(0, 1), (1, 2)],
            [],
        )
        mesh.update()
        obj = self.data.objects.new("ProjectionSource", mesh)
        self.scene.collection.objects.link(obj)
        return obj

    def test_projection_keeps_live_vertex_reference(self):
        source = self._mesh_object()
        points, lines = project_mesh_object(self.sketch, source, construction=True)

        self.assertEqual(len(points), 3)
        self.assertEqual(len(lines), 2)
        self.assertTrue(all(point.fixed for point in points))
        self.assertTrue(all(point.construction for point in points))
        self.assertTrue(all(line.construction for line in lines))
        self.assertIsNotNone(source.data.attributes.get(VERTEX_ID_ATTR))

        self.assertLess((points[0].co - Vector((0.0, 0.0))).length, 1e-6)
        self.assertLess((points[1].co - Vector((2.0, 0.0))).length, 1e-6)

        source.data.vertices[1].co = (3.5, 0.5, 1.0)
        source.data.update()
        self.context.view_layer.update()
        depsgraph = self.context.evaluated_depsgraph_get()
        moved = refresh_projection_for_sketch(
            self.sketch,
            depsgraph,
            force=True,
        )

        self.assertGreaterEqual(moved, 1)
        self.assertLess((points[1].co - Vector((3.5, 0.5))).length, 1e-5)

        source.location.y = 2.0
        self.context.view_layer.update()
        depsgraph = self.context.evaluated_depsgraph_get()
        moved = refresh_projection_for_sketch(
            self.sketch,
            depsgraph,
            force=True,
        )

        self.assertGreaterEqual(moved, 1)
        self.assertLess((points[1].co - Vector((3.5, 2.5))).length, 1e-5)
