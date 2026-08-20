from mathutils import Vector

from ..utilities.curve_data import get_curve_data
from ..utilities.projection_anchor import (
    PROJECT_LAST_CO_ATTR,
    PROJECT_SRC_SLOT_ATTR,
    PROJECT_VERTEX_ID_ATTR,
    PROJECT_VERTEX_INDEX_ATTR,
    VERTEX_ID_ATTR,
    find_projected_point,
    project_curves_object,
    project_mesh_element,
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

    def _quad_object(self):
        mesh = self.data.meshes.new("ProjectionQuadMesh")
        mesh.from_pydata(
            [(0.0, 0.0, 1.0), (2.0, 0.0, 1.0), (2.0, 2.0, 1.0), (0.0, 2.0, 1.0)],
            [],
            [(0, 1, 2, 3)],
        )
        mesh.update()
        obj = self.data.objects.new("ProjectionQuad", mesh)
        self.scene.collection.objects.link(obj)
        return obj

    def _count_curves(self):
        return len(self.sketch.data.curves)

    def test_project_single_edge_element(self):
        source = self._mesh_object()
        n_points, n_lines = project_mesh_element(self.sketch, source, "EDGE", 0)

        # Edge 0 links verts 0 and 1: two new points plus one connecting line.
        self.assertEqual((n_points, n_lines), (2, 1))
        # Both endpoints are live-bound and their line rides on them.
        self.assertIsNotNone(find_projected_point(self.sketch, source, 0))
        self.assertIsNotNone(find_projected_point(self.sketch, source, 1))
        self.assertIsNone(find_projected_point(self.sketch, source, 2))

        # A second, adjacent edge reuses the shared vertex 1: only one new point.
        n_points, n_lines = project_mesh_element(self.sketch, source, "EDGE", 1)
        self.assertEqual((n_points, n_lines), (1, 1))
        self.assertIsNotNone(find_projected_point(self.sketch, source, 2))

    def test_reprojecting_same_edge_adds_no_duplicate_line(self):
        source = self._mesh_object()
        first = project_mesh_element(self.sketch, source, "EDGE", 0)
        curves = len(self.sketch.data.curves)

        # Re-picking the exact same edge reuses both points and the line, so
        # nothing new is created (the points already deduped, now the line too).
        again = project_mesh_element(self.sketch, source, "EDGE", 0)
        self.assertEqual(first, (2, 1))
        self.assertEqual(again, (0, 0))
        self.assertEqual(len(self.sketch.data.curves), curves)

    def test_perpendicular_edge_creates_no_zero_length_line(self):
        # An edge going straight through the sketch plane (e.g. a cube side face
        # projected edge-on) collapses both endpoints to one 2D spot. No line.
        mesh = self.data.meshes.new("PerpSource")
        mesh.from_pydata([(1.0, 1.0, 0.0), (1.0, 1.0, 2.0)], [(0, 1)], [])
        mesh.update()
        source = self.data.objects.new("PerpSource", mesh)
        self.scene.collection.objects.link(source)

        n_points, n_lines = project_mesh_element(self.sketch, source, "EDGE", 0)
        self.assertEqual(n_lines, 0)

    def test_project_single_vertex_element(self):
        source = self._mesh_object()
        n_points, n_lines = project_mesh_element(self.sketch, source, "VERTEX", 2)
        self.assertEqual((n_points, n_lines), (1, 0))
        point = find_projected_point(self.sketch, source, 2)
        self.assertIsNotNone(point)
        self.assertTrue(point.fixed)
        # Re-picking the same vertex must not stack a duplicate point.
        again = project_mesh_element(self.sketch, source, "VERTEX", 2)
        self.assertEqual(again, (0, 0))

    def test_project_face_outline_shares_corners(self):
        source = self._quad_object()
        n_points, n_lines = project_mesh_element(self.sketch, source, "FACE", 0)
        # A quad face: four shared corner points and four boundary lines.
        self.assertEqual((n_points, n_lines), (4, 4))
        for v in range(4):
            self.assertIsNotNone(find_projected_point(self.sketch, source, v))
        # Face outline is a closed loop of eight curves (4 points + 4 lines).
        self.assertEqual(self._count_curves(), 8)

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

        points, lines, _ = project_curves_object(
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

        points, lines, _ = project_curves_object(self.sketch, src.target_object)
        self.assertEqual(len(lines), 2)
        self.assertEqual(len(points), 3, "shared endpoint must not duplicate")

    def test_project_sketch_source_standalone_points_and_skips_curves(self):
        # A standalone point projects (a point is a point at any angle); an arc
        # is skipped and counted so the caller can report it.
        from ..model.curve_ref import PointRef

        src = self.new_sketch()
        PointRef.create(src, (3.0, 4.0))  # standalone point, no line
        center = PointRef.create(src, (0.0, 0.0))
        start = PointRef.create(src, (1.0, 0.0))
        end = PointRef.create(src, (0.0, 1.0))
        from ..model.curve_ref import ArcRef

        ArcRef.create(src, center, start, end)  # an arc -> skipped

        points, lines, skipped = project_curves_object(self.sketch, src.target_object)
        self.assertEqual(len(lines), 0)
        self.assertGreaterEqual(len(points), 1)
        # The standalone point landed at its position.
        self.assertTrue(any((p.co - Vector((3.0, 4.0))).length < 1e-6 for p in points))
        self.assertEqual(skipped, 1, "the arc must be counted as skipped")
