"""Making a part by hand.

Parts normally appear on their own, when a sketch is made solid or drawn on
something. This covers the cases that never pass through those tools: imported
geometry, or a sketch the user wants to place and reuse as a part.
"""

import bmesh
import bpy
from mathutils import Matrix, Vector

from ..operators.make_part import _can_become_part
from ..utilities.part import (
    instance_part,
    is_part_root,
    mark_part_root,
    part_root_of,
    world_matrix_of,
)
from .utils import Sketch2dTestCase


class TestMakePart(Sketch2dTestCase):
    def _cube(self, name, location=(0.0, 0.0, 0.0)):
        me = bpy.data.meshes.new(name)
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=2.0)
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(name, me)
        self.scene.collection.objects.link(ob)
        ob.location = location
        return ob

    def _select(self, *objects, active=None):
        bpy.ops.object.select_all(action="DESELECT")
        for obj in objects:
            obj.select_set(True)
        self.context.view_layer.objects.active = active or objects[0]

    def test_an_imported_mesh_becomes_a_part(self):
        mesh = self._cube("imported")
        self._select(mesh)

        bpy.ops.view3d.slvs_make_part()
        self.assertTrue(is_part_root(mesh))
        self.assertEqual(tuple(mesh.lock_location), (False, False, False))
        # Scale stays locked, as for every part.
        self.assertEqual(tuple(mesh.lock_scale), (True, True, True))

    def test_the_active_object_roots_it_and_the_rest_join(self):
        root = self._cube("root")
        other = self._cube("other", location=(3.0, 0.0, 0.0))
        self._select(other, root, active=root)

        bpy.ops.view3d.slvs_make_part()
        self.assertTrue(is_part_root(root))
        self.assertEqual(part_root_of(other), root)
        # Joining keeps it where it was.
        self.context.view_layer.update()
        self.assertEqual(world_matrix_of(other).translation, Vector((3.0, 0.0, 0.0)))

    def test_a_sketch_takes_over_its_transform(self):
        # Placed by a workplane, it would otherwise look unmovable: the geometry
        # would keep drawing on a plane the sketch no longer follows.
        obj = self.sketch.target_object
        plane = bpy.data.objects.new("WP", None)
        self.scene.collection.objects.link(plane)
        plane.matrix_world = Matrix.Translation(Vector((0.0, 0.0, 2.0)))
        self.context.view_layer.update()
        obj.parent = plane
        obj.slvs_workplane = plane
        self.context.view_layer.update()

        self._select(obj)
        bpy.ops.view3d.slvs_make_part()

        self.assertTrue(is_part_root(obj))
        self.assertIsNone(obj.parent)
        self.assertIsNone(obj.slvs_workplane)
        self.assertEqual(world_matrix_of(obj).translation, Vector((0.0, 0.0, 2.0)))

    def test_a_member_leaves_its_old_part(self):
        first = self._cube("first")
        mark_part_root(first)
        member = self._cube("member", location=(1.0, 0.0, 0.0))
        self._select(member, first, active=first)
        bpy.ops.view3d.slvs_make_part()  # member joins first

        self._select(member)
        bpy.ops.view3d.slvs_make_part()
        self.assertTrue(is_part_root(member))
        self.assertEqual(part_root_of(member), member)

    def test_a_placement_cannot_root_a_part(self):
        root = self._cube("widget")
        mark_part_root(root)
        from ..utilities.collections import sync_part_collections

        sync_part_collections(self.scene)
        placement = instance_part(self.context, root)

        self.assertFalse(_can_become_part(placement))
        self._select(placement)
        self.assertFalse(bpy.ops.view3d.slvs_make_part.poll())

    def test_an_empty_cannot_root_a_part(self):
        empty = bpy.data.objects.new("empty", None)
        self.scene.collection.objects.link(empty)
        self.assertFalse(_can_become_part(empty))

    def test_an_existing_part_takes_the_rest_of_the_selection_in(self):
        root = self._cube("already")
        mark_part_root(root)
        newcomer = self._cube("newcomer", location=(2.0, 0.0, 0.0))

        self._select(newcomer, root, active=root)
        bpy.ops.view3d.slvs_make_part()

        self.assertTrue(is_part_root(root))
        self.assertEqual(part_root_of(newcomer), root)
