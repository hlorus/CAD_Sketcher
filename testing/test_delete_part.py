"""Deleting a whole part.

Blender's own Delete takes the clicked object only, so a body deleted on its own
leaves the part standing, re-rooted in the cutters that shaped it. Delete Part
takes the hierarchy, its placements and the collection with it.
"""

import bmesh
import bpy

from ..operators.delete_part import part_members, part_placements
from ..utilities.collections import sync_part_collections
from ..utilities.part import instance_part, join_part, mark_part_root, part_root_of
from .utils import BgsTestCase


class TestDeletePart(BgsTestCase):
    def _cube(self, name, location=(0.0, 0.0, 0.0)):
        name = f"del_{name}"
        me = bpy.data.meshes.new(name)
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=2.0)
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(name, me)
        self.scene.collection.objects.link(ob)
        ob.location = location
        return ob

    def _part_with_cutter(self):
        from ..operators.modifiers import apply_boolean

        body = self._cube("body")
        mark_part_root(body)
        cutter = self._cube("cutter", location=(0.9, 0.0, 0.0))
        join_part(body, cutter)
        apply_boolean(body, cutter, "Difference")
        sync_part_collections(self.scene)
        return body, cutter

    def _delete(self, root):
        self.context.view_layer.objects.active = root
        return bpy.ops.view3d.slvs_delete_part(part_name=root.name)

    def test_members_are_the_whole_hierarchy(self):
        body, cutter = self._part_with_cutter()
        self.assertEqual(set(part_members(body)), {body, cutter})

    def test_the_cutter_goes_with_the_body(self):
        body, cutter = self._part_with_cutter()
        names = (body.name, cutter.name)

        self.assertEqual(self._delete(body), {"FINISHED"})

        for name in names:
            self.assertIsNone(bpy.data.objects.get(name), f"{name} outlived the part")

    def test_it_deletes_the_part_of_whatever_is_clicked(self):
        """Right-clicking a member must delete its part, not just that member."""
        body, cutter = self._part_with_cutter()
        names = (body.name, cutter.name)

        self.context.view_layer.objects.active = cutter
        self.assertEqual(bpy.ops.view3d.slvs_delete_part(), {"FINISHED"})

        for name in names:
            self.assertIsNone(bpy.data.objects.get(name))

    def test_the_emptied_collection_goes_too(self):
        body, _cutter = self._part_with_cutter()
        from ..utilities.collections import is_part_collection

        coll = next(c for c in body.users_collection if is_part_collection(c))
        name = coll.name

        self._delete(body)

        self.assertIsNone(bpy.data.collections.get(name))

    def test_placements_do_not_outlive_their_part(self):
        """An instance Empty left behind would render nothing."""
        body, _cutter = self._part_with_cutter()
        instance = instance_part(self.context, body)
        name = instance.name
        self.assertEqual(part_placements(body), [instance])

        self._delete(body)

        self.assertIsNone(bpy.data.objects.get(name))

    def test_it_does_nothing_without_a_part(self):
        loose = self._cube("loose")
        self.context.view_layer.objects.active = loose

        self.assertFalse(bpy.ops.view3d.slvs_delete_part.poll())
        self.assertIsNotNone(bpy.data.objects.get(loose.name))
        self.assertIsNone(part_root_of(loose))
