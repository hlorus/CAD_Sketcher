import math

from mathutils import Matrix, Vector

from ..utilities.curve_data import get_curve_data
from ..utilities.projection_anchor import (
    PROJECT_LAST_CO_ATTR,
    PROJECT_SRC_SLOT_ATTR,
    PROJECT_VERTEX_ID_ATTR,
    PROJECT_VERTEX_INDEX_ATTR,
    VERTEX_ID_ATTR,
    _planes_are_parallel,
    find_projected_point,
    project_curves_element,
    project_curves_object,
    project_mesh_edge,
    project_mesh_element,
    project_mesh_object,
    project_mesh_vertex,
    refresh_projection_for_sketch,
    resolve_source_vertex_index,
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
        # Settle the scene first: projecting reads the evaluated mesh, and the
        # evaluation runs the handler that gives a fresh sketch its origin.
        depsgraph = self.context.evaluated_depsgraph_get()
        before = self._count_curves()
        n_points, n_lines = project_mesh_element(
            self.sketch, source, "FACE", 0, depsgraph=depsgraph
        )
        # A quad face: four shared corner points and four boundary lines.
        self.assertEqual((n_points, n_lines), (4, 4))
        for v in range(4):
            self.assertIsNotNone(find_projected_point(self.sketch, source, v))
        # Face outline is a closed loop of eight curves (4 points + 4 lines).
        self.assertEqual(self._count_curves() - before, 8)

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
        # on a non-parallel plane is skipped and counted so the caller can report it.
        from ..model.curve_ref import ArcRef, PointRef

        src = self.new_sketch(wp=self.entities.origin_plane_XZ)
        PointRef.create(src, (3.0, 4.0))  # standalone point, no line
        center = PointRef.create(src, (0.0, 0.0))
        start = PointRef.create(src, (1.0, 0.0))
        end = PointRef.create(src, (0.0, 1.0))
        ArcRef.create(src, center, start, end)  # non-parallel arc -> skipped

        points, lines, skipped = project_curves_object(self.sketch, src.target_object)
        self.assertEqual(len(lines), 0)
        self.assertGreaterEqual(len(points), 1)
        self.assertEqual(skipped, 1, "the non-parallel arc must be counted as skipped")

    def test_project_sketch_source_arcs_and_circles_parallel(self):
        # Parallel sketches project arcs and circles cleanly as native curves.
        from ..model.curve_ref import ArcRef, CircleRef, PointRef

        src = self.new_sketch()
        center = PointRef.create(src, (0.0, 0.0))
        start = PointRef.create(src, (1.0, 0.0))
        end = PointRef.create(src, (0.0, 1.0))
        ArcRef.create(src, center, start, end)

        c_center = PointRef.create(src, (4.0, 2.0))
        circle_src = CircleRef.create(src, c_center, radius=2.5)

        points, curves, skipped = project_curves_object(
            self.sketch, src.target_object, construction=True
        )
        self.assertEqual(skipped, 0)
        self.assertEqual(len(curves), 2)
        # 3 points for arc (center, start, end) + 1 for circle center = 4 points
        self.assertEqual(len(points), 4)
        self.assertTrue(all(p.fixed for p in points))
        self.assertTrue(all(p.construction for p in points))
        self.assertTrue(all(c.construction for c in curves))

        # Check circle radius
        circle = next(c for c in curves if c.is_circle())
        self.assertAlmostEqual(circle.radius, 2.5, places=4)

        # Live update: move circle center on source, projected circle center updates
        # and anchor moves with it so radius is preserved (centre-only move)
        c_center.co = (6.0, 3.0)
        circle_src.radius = 2.5
        self.context.view_layer.update()
        depsgraph = self.context.evaluated_depsgraph_get()
        refresh_projection_for_sketch(self.sketch, depsgraph, force=True)
        self.assertLess((circle.ct.co - Vector((6.0, 3.0))).length, 1e-5)
        self.assertAlmostEqual(circle.radius, 2.5, places=4)

        # Live update: change source circle radius from 2.5 to 5.0
        circle_src.radius = 5.0
        self.context.view_layer.update()
        depsgraph = self.context.evaluated_depsgraph_get()
        refresh_projection_for_sketch(self.sketch, depsgraph, force=True)
        self.assertAlmostEqual(circle.radius, 5.0, places=4)
        self.assertLess((circle.ct.co - Vector((6.0, 3.0))).length, 1e-5)

        # Live update: radius change followed by centre move in separate refresh
        c_center.co = (8.0, 5.0)
        circle_src.radius = 5.0
        self.context.view_layer.update()
        depsgraph = self.context.evaluated_depsgraph_get()
        refresh_projection_for_sketch(self.sketch, depsgraph, force=True)
        self.assertAlmostEqual(circle.radius, 5.0, places=4)
        self.assertLess((circle.ct.co - Vector((8.0, 5.0))).length, 1e-5)

    def test_project_single_vertex_dedup_and_live(self):
        # The granular snap path: one vertex -> one live point, reused on repeat.
        source = self._mesh_object()

        point = project_mesh_vertex(self.sketch, source, 1, construction=True)
        self.assertIsNotNone(point)
        self.assertTrue(point.fixed)
        self.assertTrue(point.construction)
        self.assertLess((point.co - Vector((2.0, 0.0))).length, 1e-6)

        # Snapping the same vertex again must reuse the existing point, not stack
        # a second projected reference on top of it.
        again = project_mesh_vertex(self.sketch, source, 1, construction=True)
        self.assertEqual(again.curve_id, point.curve_id)

        # A different vertex gets its own point.
        other = project_mesh_vertex(self.sketch, source, 0, construction=True)
        self.assertNotEqual(other.curve_id, point.curve_id)

        # Out-of-range index is a no-op rather than a crash.
        self.assertIsNone(project_mesh_vertex(self.sketch, source, 99))

        # The live link tracks source edits, same as a full projection.
        source.data.vertices[1].co = (4.0, 1.0, 1.0)
        source.data.update()
        self.context.view_layer.update()
        depsgraph = self.context.evaluated_depsgraph_get()
        refresh_projection_for_sketch(self.sketch, depsgraph, force=True)
        self.assertLess((point.co - Vector((4.0, 1.0))).length, 1e-5)

    def test_translating_source_object_reprojects_bound_point(self):
        # The snap workflow's real payoff: moving the whole source OBJECT (its
        # matrix_world changes, its mesh data does not) must drag the bound point
        # along. This is a different depsgraph path than editing a vertex .co, and
        # it must fire without force -- only via the object being in ``changed``.
        source = self._mesh_object()
        point = project_mesh_vertex(self.sketch, source, 1, construction=True)
        self.assertLess((point.co - Vector((2.0, 0.0))).length, 1e-6)

        # Translate the object by +3 on X (no mesh edit at all).
        source.location = (3.0, 0.0, 0.0)
        self.context.view_layer.update()
        depsgraph = self.context.evaluated_depsgraph_get()

        # Mimic the depsgraph handler: object translation puts the object (not its
        # mesh) in the changed set. No force -- change-detection must catch it.
        refresh_projection_for_sketch(self.sketch, depsgraph, changed={source})

        # The bound point follows the object's new world position (2 + 3 = 5 on X).
        self.assertLess((point.co - Vector((5.0, 0.0))).length, 1e-5)

    def test_project_mesh_edge_returns_live_line(self):
        # Snapping along an edge projects it as a live LINE (bound endpoints), so a
        # placed point can coincide onto it and slide along the edge.
        from ..model.curve_ref import LineRef

        source = self._mesh_object()  # edge 0: v0 (0,0,1) -- v1 (2,0,1)
        line = project_mesh_edge(self.sketch, source, 0, 1, construction=True)
        self.assertIsInstance(line, LineRef)
        self.assertTrue(line.construction)
        # Both endpoints are live-bound to their source vertices.
        self.assertIsNotNone(find_projected_point(self.sketch, source, 0))
        self.assertIsNotNone(find_projected_point(self.sketch, source, 1))

        # Re-snapping the same edge reuses the same line (no duplicate).
        again = project_mesh_edge(self.sketch, source, 1, 0, construction=True)
        self.assertEqual(again.curve_id, line.curve_id)

        # Degenerate / out-of-range inputs are no-ops.
        self.assertIsNone(project_mesh_edge(self.sketch, source, 1, 1))
        self.assertIsNone(project_mesh_edge(self.sketch, source, 0, 99))

    def test_project_mesh_edge_skips_plane_perpendicular_edge(self):
        # An edge going straight through the sketch plane collapses to a point;
        # there is no usable line, so the projection bails (static fallback).
        mesh = self.data.meshes.new("PerpEdge")
        mesh.from_pydata([(1.0, 1.0, 0.0), (1.0, 1.0, 2.0)], [(0, 1)], [])
        mesh.update()
        source = self.data.objects.new("PerpEdge", mesh)
        self.scene.collection.objects.link(source)
        self.assertIsNone(project_mesh_edge(self.sketch, source, 0, 1))

    def test_projected_edge_line_tracks_object_translation(self):
        # The projected edge's endpoints (and thus the line) follow the object.
        source = self._mesh_object()
        line = project_mesh_edge(self.sketch, source, 0, 1, construction=True)
        p1_before = Vector(line.p1.co)

        source.location = (5.0, 0.0, 0.0)
        self.context.view_layer.update()
        depsgraph = self.context.evaluated_depsgraph_get()
        refresh_projection_for_sketch(self.sketch, depsgraph, changed={source})
        self.assertLess((line.p1.co - (p1_before + Vector((5.0, 0.0)))).length, 1e-5)

    def test_project_mesh_vertex_places_at_snapped_world_co(self):
        # A snap hands the evaluated world position; the point lands there rather
        # than at the (possibly modifier-shifted) original vertex coordinate.
        source = self._mesh_object()
        point = project_mesh_vertex(
            self.sketch, source, 1, construction=True, world_co=(5.0, 6.0, 1.0)
        )
        self.assertIsNotNone(point)
        self.assertLess((point.co - Vector((5.0, 6.0))).length, 1e-6)

    def test_resolve_source_vertex_index(self):
        source = self._mesh_object()
        self.context.view_layer.update()
        depsgraph = self.context.evaluated_depsgraph_get()
        eval_source = source.evaluated_get(depsgraph)

        # No modifier: the evaluated index maps straight through (count matches).
        self.assertEqual(resolve_source_vertex_index(source, eval_source, 1), 1)
        # An out-of-range evaluated index resolves to nothing rather than crash.
        self.assertIsNone(resolve_source_vertex_index(source, eval_source, 99))

    def test_project_single_sketch_line_element(self):
        # Project just one picked line of a source sketch (Phase 3 of the tool).
        from ..model.curve_ref import LineRef, PointRef

        src = self.new_sketch()
        p1 = PointRef.create(src, (0.0, 0.0))
        p2 = PointRef.create(src, (2.0, 3.0))
        line = LineRef.create(src, p1, p2)

        points, lines, skipped = project_curves_element(
            self.sketch, src.target_object, line.curve_id
        )
        self.assertEqual(len(points), 2)
        self.assertEqual(len(lines), 1)
        self.assertEqual(skipped, 0)
        self.assertTrue(all(p.fixed for p in points))

        # Idempotent: re-projecting the same line reuses its endpoints, adds none.
        p_again, l_again, _ = project_curves_element(
            self.sketch, src.target_object, line.curve_id
        )
        self.assertEqual(len(p_again), 0)
        self.assertEqual(len(l_again), 0)

    def test_project_single_sketch_arc_element(self):
        # Project just one picked arc of a source sketch (coplanar / parallel).
        from ..model.curve_ref import ArcRef, PointRef

        src = self.new_sketch()
        center = PointRef.create(src, (0.0, 0.0))
        start = PointRef.create(src, (1.0, 0.0))
        end = PointRef.create(src, (0.0, 1.0))
        arc = ArcRef.create(src, center, start, end)

        points, lines, skipped = project_curves_element(
            self.sketch, src.target_object, arc.curve_id
        )
        self.assertEqual(len(points), 3)
        self.assertEqual(len(lines), 1)
        self.assertEqual(skipped, 0)
        self.assertTrue(all(p.fixed for p in points))
        self.assertTrue(all(p.construction for p in points))

        # Idempotent: re-projecting the same arc reuses center/start/end points, adds none.
        p_again, l_again, _ = project_curves_element(
            self.sketch, src.target_object, arc.curve_id
        )
        self.assertEqual(len(p_again), 0)
        self.assertEqual(len(l_again), 0)

    def test_project_single_sketch_circle_element(self):
        # Project just one picked circle of a source sketch (coplanar / parallel).
        from ..model.curve_ref import CircleRef, PointRef

        src = self.new_sketch()
        center = PointRef.create(src, (2.0, 3.0))
        circle = CircleRef.create(src, center, radius=4.0)

        points, lines, skipped = project_curves_element(
            self.sketch, src.target_object, circle.curve_id
        )
        self.assertEqual(len(points), 1)
        self.assertEqual(len(lines), 1)
        self.assertEqual(skipped, 0)
        self.assertTrue(points[0].fixed)
        self.assertTrue(points[0].construction)
        self.assertTrue(lines[0].construction)
        self.assertAlmostEqual(lines[0].radius, 4.0, places=4)

        # Idempotent: re-projecting the same circle reuses center point, adds none.
        p_again, l_again, _ = project_curves_element(
            self.sketch, src.target_object, circle.curve_id
        )
        self.assertEqual(len(p_again), 0)
        self.assertEqual(len(l_again), 0)

    def test_project_single_sketch_arc_and_circle_non_parallel_skipped(self):
        # An arc or circle on a non-parallel sketch plane cannot be represented
        # as a native circular curve; it is skipped and reports skipped=1.
        from ..model.curve_ref import ArcRef, CircleRef, PointRef

        src = self.new_sketch(wp=self.entities.origin_plane_XZ)
        center = PointRef.create(src, (0.0, 0.0))
        start = PointRef.create(src, (1.0, 0.0))
        end = PointRef.create(src, (0.0, 1.0))
        arc = ArcRef.create(src, center, start, end)

        c_center = PointRef.create(src, (3.0, 3.0))
        circle = CircleRef.create(src, c_center, radius=2.0)

        points, lines, skipped = project_curves_element(
            self.sketch, src.target_object, arc.curve_id
        )
        self.assertEqual((len(points), len(lines), skipped), (0, 0, 1))

        points, lines, skipped = project_curves_element(
            self.sketch, src.target_object, circle.curve_id
        )
        self.assertEqual((len(points), len(lines), skipped), (0, 0, 1))

    def test_project_element_rejects_non_sketch_key(self):
        # A raw-Curves index key is hoverable but not projectable yet.
        src = self.new_sketch()
        self.assertEqual(
            project_curves_element(self.sketch, src.target_object, ("point", 0)),
            ([], [], 1),
        )

    def test_snap_projection_primitives_accept_a_curve_source(self):
        # The #619 draw-snap projection reuses project_mesh_vertex/edge; these must
        # now accept a Curves source so snapping onto a sketch/curve live-projects
        # its control point or segment (not just meshes).
        import bpy

        cu = bpy.data.hair_curves.new("SnapSrc")
        cu.add_curves([2])
        cu.points[0].position = (0.0, 0.0, 0.0)
        cu.points[1].position = (2.0, 0.0, 0.0)
        src = bpy.data.objects.new("SnapSrcCurve", cu)
        self.scene.collection.objects.link(src)

        # Vertex: binds a fixed, source-tracked point to control point 0, deduped.
        pv = project_mesh_vertex(self.sketch, src, 0, construction=True)
        self.assertIsNotNone(pv)
        self.assertTrue(pv.fixed)
        self.assertIsNotNone(find_projected_point(self.sketch, src, 0))
        self.assertEqual(project_mesh_vertex(self.sketch, src, 0).curve_id, pv.curve_id)

        # Edge: projects a live line bound to both control points.
        line = project_mesh_edge(self.sketch, src, 0, 1, construction=True)
        self.assertIsNotNone(line)
        self.assertIsNotNone(find_projected_point(self.sketch, src, 1))

    def test_planes_are_parallel_fails_closed(self):
        # A missing plane_matrix or degenerate normal returns (False, False)
        # rather than failing open.
        class _Dummy:
            pass

        d1 = _Dummy()
        d2 = _Dummy()
        self.assertEqual(_planes_are_parallel(d1, d2), (False, False))

        d1.plane_matrix = Matrix.Identity(4)
        self.assertEqual(_planes_are_parallel(d1, d2), (False, False))

        d2.plane_matrix = Matrix.Diagonal((0.0, 0.0, 0.0, 1.0))
        self.assertEqual(_planes_are_parallel(d1, d2), (False, False))

    def test_project_sketch_source_arc_anti_parallel_swaps_endpoints(self):
        # When sketch plane normals are anti-parallel (is_aligned=False),
        # projecting an arc swaps start and end points to maintain CCW sweep.
        from ..model.curve_ref import ArcRef, PointRef

        src = self.new_sketch()
        center = PointRef.create(src, (0.0, 0.0))
        start = PointRef.create(src, (1.0, 0.0))
        end = PointRef.create(src, (0.0, 1.0))
        ArcRef.create(src, center, start, end)

        # Invert target sketch plane normal (rotate 180 degrees around X)
        wp = self.sketch.workplane_object
        if wp is not None:
            wp.matrix_world = Matrix.Rotation(math.pi, 4, "X")
        else:
            self.sketch.target_object.matrix_world = Matrix.Rotation(math.pi, 4, "X")

        is_parallel, is_aligned = _planes_are_parallel(self.sketch, src)
        self.assertTrue(is_parallel)
        self.assertFalse(is_aligned)

        points, curves, skipped = project_curves_object(
            self.sketch, src.target_object, construction=True
        )
        self.assertEqual(skipped, 0)
        self.assertEqual(len(curves), 1)
        arc = curves[0]
        # In target frame with flipped normal:
        # source start (1, 0, 0) lands at (1, 0)
        # source end (0, 1, 0) lands at (0, -1)
        # To sweep CCW from (0, -1) to (1, 0), start and end must swap:
        self.assertLess((arc.start.co - Vector((0.0, -1.0))).length, 1e-5)
        self.assertLess((arc.end.co - Vector((1.0, 0.0))).length, 1e-5)

    def test_project_circle_centre_move_preserves_anchor_and_radius(self):
        # Moving a projected circle's centre (centre-only, or centre after radius
        # change) must carry the anchor with it so circle.radius stays equal to
        # the source radius rather than distorting into |anchor - new_centre|.
        from ..model.curve_ref import CircleRef, PointRef

        src = self.new_sketch()
        c_center = PointRef.create(src, (0.0, 0.0))
        circle_src = CircleRef.create(src, c_center, radius=2.0)

        points, curves, skipped = project_curves_object(
            self.sketch, src.target_object, construction=True
        )
        self.assertEqual(skipped, 0)
        circle = next(c for c in curves if c.is_circle())
        self.assertAlmostEqual(circle.radius, 2.0, places=4)

        # 1. Centre-only move: move (0,0) -> (1,1). Radius must stay 2.0, not sqrt(2)=1.414.
        c_center.co = (1.0, 1.0)
        circle_src.radius = 2.0
        self.context.view_layer.update()
        depsgraph = self.context.evaluated_depsgraph_get()
        refresh_projection_for_sketch(self.sketch, depsgraph, force=True)
        self.assertLess((circle.ct.co - Vector((1.0, 1.0))).length, 1e-5)
        self.assertAlmostEqual(circle.radius, 2.0, places=4)

        # 2. Radius change: 2.0 -> 5.0 in its own refresh.
        circle_src.radius = 5.0
        self.context.view_layer.update()
        depsgraph = self.context.evaluated_depsgraph_get()
        refresh_projection_for_sketch(self.sketch, depsgraph, force=True)
        self.assertAlmostEqual(circle.radius, 5.0, places=4)
        self.assertLess((circle.ct.co - Vector((1.0, 1.0))).length, 1e-5)

        # 3. Centre move after radius change: (1,1) -> (3,1). Radius must stay 5.0, not sqrt(5)=2.236.
        c_center.co = (3.0, 1.0)
        circle_src.radius = 5.0
        self.context.view_layer.update()
        depsgraph = self.context.evaluated_depsgraph_get()
        refresh_projection_for_sketch(self.sketch, depsgraph, force=True)
        self.assertLess((circle.ct.co - Vector((3.0, 1.0))).length, 1e-5)
        self.assertAlmostEqual(circle.radius, 5.0, places=4)

        # 4. Source object translation: translating source object by (+2, +1) moves center to (5, 2)
        # while source circle radius remains 5.0.
        src.target_object.location = (2.0, 1.0, 0.0)
        self.context.view_layer.update()
        depsgraph = self.context.evaluated_depsgraph_get()
        refresh_projection_for_sketch(self.sketch, depsgraph, force=True)
        self.assertLess((circle.ct.co - Vector((5.0, 2.0))).length, 1e-5)
        self.assertAlmostEqual(circle.radius, 5.0, places=4)

    def test_project_concentric_circles_keeps_both(self):
        # Two source circles can share a center (an annulus, a counterbore). The
        # projected circle is found by the source curve it came from, so the
        # second one does not take over the first one's circle.
        from ..model.curve_ref import CircleRef, PointRef

        src = self.new_sketch()
        ct = PointRef.create(src, (0.0, 0.0))
        inner_src = CircleRef.create(src, ct, radius=1.0)
        CircleRef.create(src, ct, radius=3.0)

        _points, curves, skipped = project_curves_object(
            self.sketch, src.target_object, construction=True
        )
        self.assertEqual(skipped, 0)
        circles = [c for c in curves if c.is_circle()]
        self.assertEqual(len(circles), 2, "both concentric circles project")
        self.assertEqual(sorted(round(c.radius, 4) for c in circles), [1.0, 3.0])

        # And each still follows its own source rather than the other's.
        inner_src.radius = 2.0
        self.context.view_layer.update()
        refresh_projection_for_sketch(
            self.sketch, self.context.evaluated_depsgraph_get(), force=True
        )
        self.assertEqual(sorted(round(c.radius, 4) for c in circles), [2.0, 3.0])
