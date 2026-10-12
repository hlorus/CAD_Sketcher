"""Projecting geometry that only exists after the source's modifiers.

Reported: picking a face of an extruded body raised
``IndexError: bpy_prop_collection[index]: index 0 out of range, size 0``. A
CAD Sketcher body carries an empty mesh of its own and gets all its geometry
from the Convert/Extrude node groups, so the picked index addresses the
evaluated mesh while the projection read the original one.
"""

import bpy
from mathutils import Vector

from ..model.curve_ref import PointRef
from ..model.sketch_ref import Sketch, stamp_sketch_props
from ..utilities.body import body_of, ensure_body
from ..utilities.curve_data import refresh_curve_geometry
from ..utilities.projection_anchor import (
    EVALUATED_VERTEX_ID,
    iter_projected_point_bindings,
    picked_mesh,
    project_mesh_element,
    project_mesh_object,
    refresh_projection_for_sketch,
)
from .utils import Sketch2dTestCase


class TestProjectGeneratedGeometry(Sketch2dTestCase):
    def setUp(self):
        super().setUp()
        self.body = self._square_body()
        self.target = self._second_sketch()

    def _square_body(self):
        """A body whose own mesh is empty and whose face comes from a modifier."""
        corners = [(0, 0), (4, 0), (4, 4), (0, 4)]
        pts = [self.add_point(c) for c in corners]
        self._source_points = pts
        for i in range(4):
            self.add_line(pts[i], pts[(i + 1) % 4])
        self.solve()
        refresh_curve_geometry(self.sketch)
        obj = self.sketch.target_object
        body = body_of(obj) or ensure_body(self.context, obj, "Body")
        self.context.view_layer.update()
        return body

    def _second_sketch(self):
        curve = bpy.data.hair_curves.new("Target Sketch")
        obj = bpy.data.objects.new("Target Sketch", curve)
        self.scene.collection.objects.link(obj)
        stamp_sketch_props(obj)
        obj.slvs_workplane = self.sketch.target_object.slvs_workplane
        return Sketch(obj)

    def test_the_body_has_no_mesh_of_its_own(self):
        """The precondition: everything it shows comes from its modifiers."""
        self.assertEqual(len(self.body.data.polygons), 0)
        _eval_ob, mesh = picked_mesh(self.body)
        self.assertIsNotNone(mesh)
        self.assertGreater(len(mesh.polygons), 0, "nothing generated to project")

    def test_projecting_a_generated_face(self):
        n_points, n_lines = project_mesh_element(self.target, self.body, "FACE", 0)
        self.assertEqual(n_points, 4)
        self.assertEqual(n_lines, 4)

    def test_projecting_a_generated_edge(self):
        n_points, n_lines = project_mesh_element(self.target, self.body, "EDGE", 0)
        self.assertEqual(n_points, 2)
        self.assertEqual(n_lines, 1)

    def test_projecting_a_generated_vertex(self):
        n_points, n_lines = project_mesh_element(self.target, self.body, "VERTEX", 0)
        self.assertEqual(n_points, 1)
        self.assertEqual(n_lines, 0)

    def test_the_same_face_twice_reuses_its_points(self):
        project_mesh_element(self.target, self.body, "FACE", 0)
        again = project_mesh_element(self.target, self.body, "FACE", 0)
        self.assertEqual(again, (0, 0), "a second pick stacked duplicates")

    def test_a_generated_binding_is_marked_as_such(self):
        project_mesh_element(self.target, self.body, "FACE", 0)
        bindings = list(iter_projected_point_bindings(self.target))
        self.assertEqual(len(bindings), 4)
        for _cid, source, vertex_id, _fallback, _last in bindings:
            self.assertEqual(source, self.body)
            self.assertEqual(vertex_id, EVALUATED_VERTEX_ID)

    def _projected_positions(self):
        return sorted(
            tuple(round(c, 3) for c in PointRef(self.target, cid).co)
            for cid, _src, _vid, _fb, _last in iter_projected_point_bindings(
                self.target
            )
        )

    def test_a_projection_of_generated_geometry_follows_its_source(self):
        """The point of a live projection: it tracks when the source changes."""
        project_mesh_element(self.target, self.body, "FACE", 0)
        before = self._projected_positions()

        # Move the source sketch, which rebuilds the body's generated mesh.
        for point in self._source_points:
            point.co = Vector(point.co) + Vector((5.0, 0.0))
        self.solve()
        refresh_curve_geometry(self.sketch)
        self.context.view_layer.update()
        depsgraph = self.context.evaluated_depsgraph_get()
        refresh_projection_for_sketch(self.target, depsgraph, force=True)

        after = self._projected_positions()
        self.assertEqual(len(before), 4)
        # Not merely "something moved": every corner follows by exactly the
        # distance the source moved, which a stale or re-derived binding would
        # not do.
        for old_co, new_co in zip(before, after):
            self.assertAlmostEqual(new_co[0] - old_co[0], 5.0, places=4)
            self.assertAlmostEqual(new_co[1] - old_co[1], 0.0, places=4)

    def test_an_out_of_range_pick_reports_instead_of_crashing(self):
        for elem_type, index in (
            ("FACE", 99),
            ("EDGE", 99),
            ("VERTEX", 99),
            ("FACE", -1),
        ):
            with self.assertRaises(ValueError, msg=f"{elem_type} {index}"):
                project_mesh_element(self.target, self.body, elem_type, index)

    def test_an_unknown_element_type_is_rejected(self):
        with self.assertRaises(ValueError):
            project_mesh_element(self.target, self.body, "CORNER", 0)

    def test_projecting_the_whole_generated_body(self):
        points, lines = project_mesh_object(self.target, self.body)
        self.assertGreater(len(points), 0)
        self.assertGreater(len(lines), 0)


class TestProjectThroughModifiers(Sketch2dTestCase):
    """A plain mesh whose modifiers change the indices the pick refers to.

    The old code read the object's own mesh, so an index from the evaluated
    geometry addressed the wrong vertex (or nothing). These guard the half of
    the fix that is not about generated bodies.
    """

    def _mirrored_quad(self):
        mesh = bpy.data.meshes.new("Quad")
        mesh.from_pydata(
            [(1.0, 0.0, 0.0), (3.0, 0.0, 0.0), (3.0, 2.0, 0.0), (1.0, 2.0, 0.0)],
            [],
            [(0, 1, 2, 3)],
        )
        mesh.update()
        obj = bpy.data.objects.new("Quad", mesh)
        self.scene.collection.objects.link(obj)
        obj.modifiers.new("Mirror", "MIRROR")
        self.context.view_layer.update()
        return obj

    def test_the_modifier_doubles_the_geometry(self):
        obj = self._mirrored_quad()
        _eval_ob, mesh = picked_mesh(obj, self.context.evaluated_depsgraph_get())
        self.assertEqual(len(obj.data.polygons), 1)
        self.assertEqual(len(mesh.polygons), 2, "the mirror did not apply")

    def test_projecting_the_mirrored_face(self):
        """Face 1 exists only after the mirror: the old code raised IndexError."""
        obj = self._mirrored_quad()
        depsgraph = self.context.evaluated_depsgraph_get()
        n_points, n_lines = project_mesh_element(
            self.sketch, obj, "FACE", 1, depsgraph=depsgraph
        )
        self.assertEqual((n_points, n_lines), (4, 4))

        # It lands on the mirrored side, not on the original face.
        xs = [
            PointRef(self.sketch, cid).co.x
            for cid, _s, _v, _f, _l in iter_projected_point_bindings(self.sketch)
        ]
        self.assertTrue(all(x < 0 for x in xs), f"projected the wrong face: {xs}")

    def test_a_source_with_added_geometry_binds_to_the_evaluated_vertex(self):
        """No trustworthy mapping back, so it binds to what was actually picked.

        The mirror leaves 8 evaluated vertices against 4 original ones, so an
        evaluated index cannot be assumed to name the original it came from.
        Binding to the evaluated element is honest about that; the reproject
        resolves it by index and last position.
        """
        obj = self._mirrored_quad()
        depsgraph = self.context.evaluated_depsgraph_get()
        project_mesh_element(self.sketch, obj, "FACE", 0, depsgraph=depsgraph)
        ids = [
            vid for _cid, _s, vid, _f, _l in iter_projected_point_bindings(self.sketch)
        ]
        self.assertEqual(ids, [EVALUATED_VERTEX_ID] * 4)

    def test_a_plain_source_keeps_its_persistent_ids(self):
        """Nothing changes for the ordinary case: durable ids, as before."""
        mesh = bpy.data.meshes.new("Plain")
        mesh.from_pydata(
            [(1.0, 0.0, 0.0), (3.0, 0.0, 0.0), (3.0, 2.0, 0.0), (1.0, 2.0, 0.0)],
            [],
            [(0, 1, 2, 3)],
        )
        mesh.update()
        obj = bpy.data.objects.new("Plain", mesh)
        self.scene.collection.objects.link(obj)
        depsgraph = self.context.evaluated_depsgraph_get()

        project_mesh_element(self.sketch, obj, "FACE", 0, depsgraph=depsgraph)

        ids = [
            vid for _cid, _s, vid, _f, _l in iter_projected_point_bindings(self.sketch)
        ]
        self.assertEqual(len(ids), 4)
        self.assertTrue(all(vid > 0 for vid in ids), f"lost the durable ids: {ids}")

    def test_a_projection_through_a_modifier_follows_its_source(self):
        """The binding has to stay live, whichever kind it is."""
        obj = self._mirrored_quad()
        depsgraph = self.context.evaluated_depsgraph_get()
        project_mesh_element(self.sketch, obj, "FACE", 1, depsgraph=depsgraph)
        before = sorted(
            tuple(round(c, 3) for c in PointRef(self.sketch, cid).co)
            for cid, _s, _v, _f, _l in iter_projected_point_bindings(self.sketch)
        )

        obj.location = Vector((0.0, 3.0, 0.0))
        self.context.view_layer.update()
        refresh_projection_for_sketch(
            self.sketch, self.context.evaluated_depsgraph_get(), force=True
        )

        after = sorted(
            tuple(round(c, 3) for c in PointRef(self.sketch, cid).co)
            for cid, _s, _v, _f, _l in iter_projected_point_bindings(self.sketch)
        )
        self.assertEqual(len(before), 4)
        for old_co, new_co in zip(before, after):
            self.assertAlmostEqual(new_co[0] - old_co[0], 0.0, places=4)
            self.assertAlmostEqual(new_co[1] - old_co[1], 3.0, places=4)


class TestProjectOperatorPath(Sketch2dTestCase):
    """Through the operator, which is where the reported traceback came from.

    ``main`` is called unbound on a stand-in self, the way
    ``test_reference_pick`` does: a bpy Operator cannot be instantiated.
    """

    def _op(self, source, elem_index, blender_type):
        import types

        return types.SimpleNamespace(
            state_index=0,
            _state_data={0: {"type": blender_type}},
            construction=True,
            target=None,
            get_state_pointer=lambda index=None, implicit=False: (
                source.name,
                elem_index,
            ),
            report=lambda *a, **k: None,
        )

    def test_projecting_a_generated_face_through_the_operator(self):
        from ..operators.project_geometry import VIEW3D_OT_slvs_project_geometry

        corners = [(0, 0), (4, 0), (4, 4), (0, 4)]
        pts = [self.add_point(c) for c in corners]
        for i in range(4):
            self.add_line(pts[i], pts[(i + 1) % 4])
        self.solve()
        refresh_curve_geometry(self.sketch)
        body = body_of(self.sketch.target_object) or ensure_body(
            self.context, self.sketch.target_object, "Body"
        )
        self.context.view_layer.update()

        target = Sketch(
            self._linked_sketch_object(self.sketch.target_object.slvs_workplane)
        )
        self.scene.sketcher.active_sketch_object = target.target_object

        op = self._op(body, 0, bpy.types.MeshPolygon)
        # Settle first: the new sketch gets its origin on the next evaluation.
        self.context.evaluated_depsgraph_get()
        before = len(target.data.curves)
        self.assertTrue(VIEW3D_OT_slvs_project_geometry.main(op, self.context))
        self.assertEqual(len(target.data.curves) - before, 8)

    def _linked_sketch_object(self, workplane):
        curve = bpy.data.hair_curves.new("Op Target")
        obj = bpy.data.objects.new("Op Target", curve)
        self.scene.collection.objects.link(obj)
        stamp_sketch_props(obj)
        obj.slvs_workplane = workplane
        return obj
