"""Deleting a feature, a part, or an assembly.

Blender's own Delete takes the clicked object only, so a body deleted on its own
leaves the part standing, re-rooted in the cutters that shaped it. These take a
whole unit, with its placements, its booleans and its collection.
"""

import bmesh
import bpy

from ..operators.delete_part import group_members, part_placements
from ..utilities.collections import sync_part_collections
from ..utilities.part import instance_part, join_part, mark_part_root, part_root_of
from .utils import BgsTestCase


def _alive(obj) -> bool:
    """Whether ``obj`` still exists: a removed one invalidates its wrapper."""
    try:
        obj.name
    except ReferenceError:
        return False
    return True


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
        self.assertEqual(set(group_members(body)), {body, cutter})

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


class TestDeleteFeature(BgsTestCase):
    """A feature is one step of a part: the solid, its sketch, its boolean."""

    def _part_with_feature(self):
        """A part whose base body is cut by a real sketched feature."""
        import bmesh

        from ..operators.add_sketch import (
            build_sketch_on_workplane,
            create_face_workplane,
        )
        from ..operators.modifiers import apply_boolean
        from ..utilities.body import body_of
        from ..utilities.part import mark_part_root, settle_membership

        me = bpy.data.meshes.new("feat_root")
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=2.0)
        bm.to_mesh(me)
        bm.free()
        root = bpy.data.objects.new("feat_root", me)
        self.scene.collection.objects.link(root)
        mark_part_root(root)

        plane = create_face_workplane(self.context, root, 0)
        sketch = build_sketch_on_workplane(self.context, plane)
        body = body_of(sketch.target_object)
        settle_membership(sketch.target_object, [root], self.context)
        apply_boolean(root, body, "Difference")
        sync_part_collections(self.scene)
        return root, plane, sketch.target_object, body

    def test_a_feature_is_a_member_not_the_root(self):
        from ..operators.delete_part import feature_root

        root, plane, sketch, body = self._part_with_feature()

        self.assertEqual(feature_root(body), body)
        self.assertEqual(feature_root(sketch), body, "a sketch means its solid")
        self.assertIsNone(feature_root(root), "the base body is the part itself")
        self.assertIsNone(feature_root(plane), "a datum plane holds features")

    def test_it_takes_the_sketch_and_leaves_the_part(self):
        root, _plane, sketch, body = self._part_with_feature()
        names = (sketch.name, body.name)

        self.context.view_layer.objects.active = body
        self.assertEqual(bpy.ops.view3d.slvs_delete_feature(), {"FINISHED"})

        for name in names:
            self.assertIsNone(bpy.data.objects.get(name))
        self.assertIsNotNone(bpy.data.objects.get(root.name), "the part survives")

    def test_the_boolean_goes_with_the_feature(self):
        """A modifier outlives its cutter, and would quietly do nothing."""
        from ..operators.modifiers import boolean_modifier_name

        root, _plane, _sketch, body = self._part_with_feature()
        name = boolean_modifier_name(body)
        self.assertIsNotNone(root.modifiers.get(name))

        self.context.view_layer.objects.active = body
        bpy.ops.view3d.slvs_delete_feature()

        self.assertIsNone(root.modifiers.get(name))

    def test_the_plane_goes_only_when_nothing_is_left_on_it(self):
        from ..operators.add_sketch import build_sketch_on_workplane
        from ..utilities.body import body_of

        root, plane, _sketch, body = self._part_with_feature()
        root_name = root.name

        # A second sketch sharing the plane: it must not lose its ground. Held by
        # reference, not by name: a body's plane is renamed after whichever body
        # is left on it.
        other = build_sketch_on_workplane(self.context, plane)
        self.context.view_layer.objects.active = body
        bpy.ops.view3d.slvs_delete_feature()
        self.assertTrue(_alive(plane), "a plane still in use must stay")

        self.context.view_layer.objects.active = body_of(other.target_object)
        bpy.ops.view3d.slvs_delete_feature()
        self.assertFalse(_alive(plane), "a spent plane stays behind")
        self.assertIsNotNone(bpy.data.objects.get(root_name))

    def test_it_does_nothing_on_a_loose_object(self):
        me = bpy.data.meshes.new("feat_loose")
        loose = bpy.data.objects.new("feat_loose", me)
        self.scene.collection.objects.link(loose)
        self.context.view_layer.objects.active = loose

        self.assertFalse(bpy.ops.view3d.slvs_delete_feature.poll())


class TestDeleteAssembly(BgsTestCase):
    def _assembly(self):
        import bmesh

        from ..utilities.part import create_assembly, join_assembly, mark_part_root

        assembly = create_assembly(self.context, "asm")
        parts = []
        for i in range(2):
            me = bpy.data.meshes.new(f"asm_part{i}")
            bm = bmesh.new()
            bmesh.ops.create_cube(bm, size=2.0)
            bm.to_mesh(me)
            bm.free()
            part = bpy.data.objects.new(f"asm_part{i}", me)
            self.scene.collection.objects.link(part)
            mark_part_root(part)
            join_assembly(assembly, part)
            parts.append(part)
        sync_part_collections(self.scene)
        return assembly, parts

    def test_the_parts_inside_go_with_it(self):
        assembly, parts = self._assembly()
        names = [assembly.name, *(p.name for p in parts)]

        self.context.view_layer.objects.active = assembly
        self.assertEqual(bpy.ops.view3d.slvs_delete_assembly(), {"FINISHED"})

        for name in names:
            self.assertIsNone(bpy.data.objects.get(name), f"{name} was left behind")

    def test_it_needs_an_assembly(self):
        me = bpy.data.meshes.new("asm_loose")
        loose = bpy.data.objects.new("asm_loose", me)
        self.scene.collection.objects.link(loose)
        self.context.view_layer.objects.active = loose

        self.assertFalse(bpy.ops.view3d.slvs_delete_assembly.poll())
