from mathutils import Vector

from ..utilities.curve_data import get_curve_data
from ..utilities.projection_anchor import (
    PROJECT_LAST_CO_ATTR,
    PROJECT_SRC_SLOT_ATTR,
    PROJECT_VERTEX_ID_ATTR,
    PROJECT_VERTEX_INDEX_ATTR,
    VERTEX_ID_ATTR,
    project_curves_object,
    project_mesh_object,
    refresh_projection_for_sketch,
)
from .utils import Sketch2dTestCase


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

        # Binding POD data belongs to the native Curves datablock. All projected
        # points from this object share one real Object pointer slot.
        owner = self.sketch.target_object
        self.assertEqual(len(owner.slvs_project_sources), 1)
        self.assertEqual(owner.slvs_project_sources[0].source, source)
        for attr_name in (
            PROJECT_SRC_SLOT_ATTR,
            PROJECT_VERTEX_ID_ATTR,
            PROJECT_VERTEX_INDEX_ATTR,
            PROJECT_LAST_CO_ATTR,
        ):
            attr = self.sketch.data.attributes.get(attr_name)
            self.assertIsNotNone(attr)
            self.assertEqual(attr.domain, "CURVE")

        for vertex_index, point in enumerate(points):
            curve_data, curve_index, _ = get_curve_data(self.sketch, point.curve_id)
            attrs = curve_data.attributes
            self.assertEqual(attrs[PROJECT_SRC_SLOT_ATTR].data[curve_index].value, 0)
            self.assertGreater(
                attrs[PROJECT_VERTEX_ID_ATTR].data[curve_index].value,
                0,
            )
            self.assertEqual(
                attrs[PROJECT_VERTEX_INDEX_ATTR].data[curve_index].value,
                vertex_index,
            )
            last_co = Vector(attrs[PROJECT_LAST_CO_ATTR].data[curve_index].vector)
            self.assertLess(
                (last_co - source.data.vertices[vertex_index].co).length,
                1e-6,
            )

        # The old implementation stored four stringly-keyed ID properties per
        # point on the Object. None should be created by the native binding.
        self.assertFalse(
            any(str(key).startswith("slvs_project_src_") for key in owner.keys())
        )

        self.assertLess((points[0].co - Vector((0.0, 0.0))).length, 1e-6)
        self.assertLess((points[1].co - Vector((2.0, 0.0))).length, 1e-6)

        source.data.vertices[1].co = (3.5, 0.5, 1.0)
        source.data.update()
        self.context.view_layer.update()
        depsgraph = self.context.evaluated_depsgraph_get()
        refresh_projection_for_sketch(
            self.sketch,
            depsgraph,
            force=True,
        )

        # The depsgraph handler can synchronize before the explicit refresh above,
        # so validate the final live position rather than requiring that call to
        # report a fresh move.
        self.assertLess((points[1].co - Vector((3.5, 0.5))).length, 1e-5)

        source.location.y = 2.0
        self.context.view_layer.update()
        depsgraph = self.context.evaluated_depsgraph_get()
        refresh_projection_for_sketch(
            self.sketch,
            depsgraph,
            force=True,
        )

        self.assertLess((points[1].co - Vector((3.5, 2.5))).length, 1e-5)

    def _source_sketch_with_line(self, p1_co, p2_co):
        """A second sketch containing one line, to project onto the active one."""
        from ..model.curve_ref import LineRef, PointRef

        src = self.new_sketch()
        p1 = PointRef.create(src, p1_co)
        p2 = PointRef.create(src, p2_co)
        LineRef.create(src, p1, p2)
        return src, p1, p2

    def test_project_sketch_source_lines(self):
        # The active sketch is self.sketch; the source is another sketch sharing
        # the same XY workplane, so its local coords map straight through.
        src, sp1, sp2 = self._source_sketch_with_line((0.0, 0.0), (2.0, 3.0))

        points, lines = project_curves_object(
            self.sketch, src.target_object, construction=True
        )
        self.assertEqual(len(lines), 1)
        self.assertEqual(len(points), 2)
        self.assertTrue(all(p.fixed for p in points))
        self.assertTrue(all(p.construction for p in points))
        self.assertTrue(all(line.construction for line in lines))
        self.assertLess((points[0].co - Vector((0.0, 0.0))).length, 1e-6)
        self.assertLess((points[1].co - Vector((2.0, 3.0))).length, 1e-6)

        # The source sketch carries the minted persistent id, and each projected
        # point stores the binding marker on the active sketch.
        self.assertIsNotNone(src.target_object.data.attributes.get(VERTEX_ID_ATTR))
        for point in points:
            cd, idx, _ = get_curve_data(self.sketch, point.curve_id)
            self.assertGreater(cd.attributes[PROJECT_VERTEX_ID_ATTR].data[idx].value, 0)

        # Live update: move a source point, the projected point follows.
        sp2.co = (5.0, 1.0)
        self.context.view_layer.update()
        depsgraph = self.context.evaluated_depsgraph_get()
        refresh_projection_for_sketch(self.sketch, depsgraph, force=True)
        self.assertLess((points[1].co - Vector((5.0, 1.0))).length, 1e-5)

    def test_project_sketch_source_dedups_shared_endpoints(self):
        # Two connected lines share a point -> one projected point at the join.
        from ..model.curve_ref import LineRef, PointRef

        src = self.new_sketch()
        a = PointRef.create(src, (0.0, 0.0))
        b = PointRef.create(src, (1.0, 0.0))
        c = PointRef.create(src, (1.0, 1.0))
        LineRef.create(src, a, b)
        LineRef.create(src, b, c)

        points, lines = project_curves_object(self.sketch, src.target_object)
        self.assertEqual(len(lines), 2)
        self.assertEqual(len(points), 3, "shared endpoint must not duplicate")
