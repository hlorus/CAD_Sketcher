"""Add Sketch on a curve-object face.

A CAD Sketcher sketch (and its extrude/fill result) is a Curves object whose
geometry-nodes modifier outputs a mesh. That mesh surfaces only as a depsgraph
instance, not on ``obj_eval.data``, so the face-picking path used to bail on it
(curve-object faces became unpickable). These lock in that the shared
``evaluated_surface_mesh`` helper and ``face_workplane_matrix`` read that mesh
for a Curves object, and still work for a plain mesh object.
"""

import unittest

import bpy

from ..stateful_operator.utilities.geometry import evaluated_surface_mesh
from ..utilities.geometry import face_bounds_in_plane, face_workplane_matrix


def _curves_object_with_mesh_grid(z=1.0):
    """A Curves object whose GN modifier outputs a 2x2 grid at height ``z``."""
    cu = bpy.data.hair_curves.new("C")
    ob = bpy.data.objects.new("CurveObj", cu)
    bpy.context.scene.collection.objects.link(ob)

    ng = bpy.data.node_groups.new("GN", "GeometryNodeTree")
    ng.interface.new_socket(
        "Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry"
    )
    out = ng.nodes.new("NodeGroupOutput")
    grid = ng.nodes.new("GeometryNodeMeshGrid")
    grid.inputs["Size X"].default_value = 2.0
    grid.inputs["Size Y"].default_value = 2.0
    tr = ng.nodes.new("GeometryNodeTransform")
    tr.inputs["Translation"].default_value = (0.0, 0.0, z)
    ng.links.new(grid.outputs["Mesh"], tr.inputs["Geometry"])
    ng.links.new(tr.outputs["Geometry"], out.inputs[0])
    ob.modifiers.new("GN", "NODES").node_group = ng
    return ob


class TestCurveFacePick(unittest.TestCase):
    def tearDown(self):
        bpy.ops.wm.read_homefile(use_empty=True)

    def test_evaluated_surface_mesh_reads_curves_instance_mesh(self):
        ob = _curves_object_with_mesh_grid()
        with evaluated_surface_mesh(bpy.context, ob) as (mesh, mw):
            self.assertIsNotNone(mesh, "no evaluated mesh for the Curves object")
            self.assertEqual(len(mesh.polygons), 4)

    def test_face_workplane_matrix_on_curve_face(self):
        ob = _curves_object_with_mesh_grid(z=1.0)
        mat = face_workplane_matrix(bpy.context, ob, 0)
        # Grid lies in a plane at z=1 with a +Z normal.
        normal = mat.col[2].to_3d()
        self.assertAlmostEqual(abs(normal.z), 1.0, places=4)
        self.assertAlmostEqual(mat.translation.z, 1.0, places=4)
        # Bounds are finite (the face has real extent).
        bounds = face_bounds_in_plane(bpy.context, ob, 0, mat)
        self.assertLess(bounds[0], bounds[2])
        self.assertLess(bounds[1], bounds[3])

    def test_mesh_object_still_works(self):
        bpy.ops.mesh.primitive_plane_add(location=(5.0, 0.0, 0.0))
        plane = bpy.context.active_object
        with evaluated_surface_mesh(bpy.context, plane) as (mesh, mw):
            self.assertEqual(len(mesh.polygons), 1)
        mat = face_workplane_matrix(bpy.context, plane, 0)
        self.assertAlmostEqual(abs(mat.col[2].to_3d().z), 1.0, places=4)
        self.assertAlmostEqual(mat.translation.x, 5.0, places=4)
