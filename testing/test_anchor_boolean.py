"""A workplane anchored to a face must not chase a boolean its own sketch cuts."""

import bmesh
import bpy

from .utils import Sketch2dTestCase


class TestAnchorBooleanFeedback(Sketch2dTestCase):
    def setUp(self):
        super().setUp()
        from ..operators.add_sketch import create_face_workplane, set_sketch_workplane
        from ..operators.modifiers import apply_boolean, set_modifier_input
        from ..utilities.extrude_nodes import _input_ids, build_extrude_node_group

        me = bpy.data.meshes.new("anchor_body")
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=2.0)
        bm.to_mesh(me)
        bm.free()
        self.body = bpy.data.objects.new("anchor_body", me)
        self.scene.collection.objects.link(self.body)
        top = next(p.index for p in me.polygons if p.normal.z > 0.9)

        self.wp = create_face_workplane(self.context, self.body, top)
        sketch_obj = self.sketch.target_object
        set_sketch_workplane(self.context, sketch_obj, self.wp)
        # Off-center, so a hole that splits the face would shift its centroid.
        self.add_circle(self.add_point((0.5, 0.3)), 0.3)

        group = build_extrude_node_group()
        extrude = sketch_obj.modifiers.new("CAD_Sketcher Extrude", "NODES")
        extrude.node_group = group
        set_modifier_input(extrude, _input_ids(group)["Size"], -0.5)
        self.boolean = apply_boolean(
            self.body, sketch_obj, "Difference", solver="Exact"
        )

    def tearDown(self):
        from ..model.sketch_ref import set_active_sketch

        sketch_obj = self.sketch.target_object
        sketch_obj.parent = None
        for mod in list(self.body.modifiers):
            self.body.modifiers.remove(mod)
        mesh = self.body.data
        bpy.data.objects.remove(self.body, do_unlink=True)
        bpy.data.meshes.remove(mesh)
        if self.wp.name in bpy.data.objects:
            bpy.data.objects.remove(self.wp, do_unlink=True)
        set_active_sketch(self.context, None)
        super().tearDown()

    def _settle(self):
        for _ in range(3):
            self.context.view_layer.update()

    def _assert_on_face_center(self):
        pos = self.wp.matrix_world.translation
        self.assertAlmostEqual(pos.x, 0.0, places=4)
        self.assertAlmostEqual(pos.y, 0.0, places=4)
        self.assertAlmostEqual(pos.z, 1.0, places=4)

    def test_detects_own_cutter(self):
        from ..utilities.face_anchor import source_depends_on_workplane

        self.assertTrue(source_depends_on_workplane(self.body, self.wp))
        other = bpy.data.objects.new("unrelated_wp", None)
        self.scene.collection.objects.link(other)
        try:
            self.assertFalse(source_depends_on_workplane(self.body, other))
        finally:
            bpy.data.objects.remove(other, do_unlink=True)

    def test_plane_stays_put_across_solvers(self):
        from ..operators.modifiers import boolean_input_ids, set_boolean_solver
        from ..utilities.boolean_nodes import SOLVER_SOCKET

        ids = boolean_input_ids(self.boolean.node_group)
        self._settle()
        self._assert_on_face_center()
        for solver in ("Manifold", "Exact", "Manifold"):
            set_boolean_solver(self.boolean, ids[SOLVER_SOCKET], solver)
            self.body.update_tag()
            self._settle()
            self._assert_on_face_center()

    def test_still_follows_mesh_edits(self):
        for v in self.body.data.vertices:
            v.co.z += 0.5
        self.body.data.update()
        self._settle()
        self.assertAlmostEqual(self.wp.matrix_world.translation.z, 1.5, places=4)
