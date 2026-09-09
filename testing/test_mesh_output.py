"""Mesh output: a companion mesh object mirrors the active sketch's fill.

The sketch is a Curves object; its filled/wire output can't be read as a mesh.
``Create Mesh Output`` spawns a mesh object with the ``CAD Sketcher To Mesh``
group (Object Info -> Realize), which surfaces the sketch's evaluated geometry as
a real, readable, world-correct mesh -- including when the sketch sits on a
non-XY workplane (the transform must be handled by Object Info's RELATIVE space).
"""

import math

import bpy
from mathutils import Matrix, Vector

from ..utilities.curve_data import refresh_curve_geometry
from .utils import Sketch2dTestCase

RING_AREA = 6 * 4 - math.pi * 1.0**2
LOCAL_CENTROID = Vector((3.0, 2.0, 0.0))  # rectangle 0..6 x 0..4 centre


class TestMeshOutput(Sketch2dTestCase):
    def _build_rectangle_with_hole(self):
        corners = [(0, 0), (6, 0), (6, 4), (0, 4)]
        pts = [self.add_point(c) for c in corners]
        for i in range(4):
            self.add_line(pts[i], pts[(i + 1) % 4])
        self.add_circle(self.add_point((3, 2)), 1.0)

    def _create_output(self):
        before = set(self.context.scene.objects)
        result = bpy.ops.view3d.slvs_create_mesh_output()
        self.assertIn("FINISHED", result)
        new = [o for o in self.context.scene.objects if o not in before]
        self.assertEqual(len(new), 1, "operator must create exactly one object")
        return new[0]

    def _eval_mesh(self, ob):
        dg = self.context.evaluated_depsgraph_get()
        ev = ob.evaluated_get(dg)
        me = ev.to_mesh()
        area = sum(p.area for p in me.polygons)
        nfaces = len(me.polygons)
        world_centroid = ob.matrix_world @ (
            sum((v.co for v in me.vertices), Vector()) / max(1, len(me.vertices))
        )
        ev.to_mesh_clear()
        return nfaces, area, world_centroid

    def test_mesh_output_is_a_readable_ring(self):
        """The companion object is a real mesh carrying the ring (to_mesh works)."""
        self._build_rectangle_with_hole()
        self.solve()
        refresh_curve_geometry(self.sketch)

        ob = self._create_output()
        self.assertEqual(ob.type, "MESH")
        nfaces, area, centroid = self._eval_mesh(ob)

        self.assertGreater(nfaces, 0, "mesh output has no faces (fill not surfaced)")
        self.assertAlmostEqual(area, RING_AREA, delta=0.2)
        # Sketch is on the XY origin plane -> world centroid at (3, 2, 0).
        self.assertLess((centroid - LOCAL_CENTROID).length, 0.2)

    def test_mesh_output_lands_in_the_sketch_collection(self):
        """The companion groups with its source sketch's collection, not the root."""
        from ..utilities.collections import sketch_collection

        self._build_rectangle_with_hole()
        self.solve()
        refresh_curve_geometry(self.sketch)

        sub = sketch_collection(self.sketch.target_object)
        self.assertIsNotNone(sub, "sketch is not in a managed collection")
        ob = self._create_output()
        self.assertIn(ob.name, sub.objects, "mesh output not grouped with its sketch")
        self.assertNotIn(
            ob.name,
            self.context.scene.collection.objects,
            "mesh output should not sit loose in the scene root",
        )

    def test_mesh_output_follows_a_transformed_sketch(self):
        """On a non-XY-placed sketch the mesh lands at the correct world position.

        Object Info RELATIVE plus matching the object transform must reproduce the
        sketch's world placement, not leave the geometry at the origin or rotated.
        """
        self._build_rectangle_with_hole()
        self.solve()
        refresh_curve_geometry(self.sketch)

        # Tilt + offset the sketch as if drawn on an arbitrary workplane.
        transform = Matrix.Translation((10, -5, 3)) @ Matrix.Rotation(
            math.radians(45), 4, "X"
        )
        self.sketch.target_object.matrix_world = transform

        ob = self._create_output()
        nfaces, area, centroid = self._eval_mesh(ob)

        self.assertGreater(nfaces, 0)
        # Rotation preserves area.
        self.assertAlmostEqual(area, RING_AREA, delta=0.2)
        # The fill centroid must map through the sketch's transform.
        expected = transform @ LOCAL_CENTROID
        self.assertLess(
            (centroid - expected).length,
            0.2,
            f"mesh output at {centroid[:]}, expected {expected[:]}",
        )
