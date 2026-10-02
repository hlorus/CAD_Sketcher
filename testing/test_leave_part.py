"""Leaving a part: taking one thing out, or taking the whole part apart.

Make Part had no inverse, and unparenting by hand leaves the object pinned: a
body is fixed within its part when it joins and nothing frees it again.
"""

import bmesh
import bpy

from ..operators.add_sketch import build_sketch_on_workplane, create_face_workplane
from ..operators.leave_part import detachable
from ..utilities.body import body_of
from ..utilities.collections import sync_part_collections
from ..utilities.part import (
    assembly_root_of,
    create_assembly,
    is_part_root,
    join_assembly,
    join_part,
    mark_part_root,
    part_root_of,
    reconcile_groups,
    settle_membership,
    world_matrix_of,
)
from .utils import BgsTestCase


def _cube(scene, name, location=(0.0, 0.0, 0.0)):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=2.0)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    scene.collection.objects.link(ob)
    ob.location = location
    return ob


class TestRemoveFromPart(BgsTestCase):
    def _part_with_feature(self):
        """A part whose base body is cut by a sketched feature on its own plane."""
        from ..operators.modifiers import apply_boolean

        root = _cube(self.scene, "rm_root")
        mark_part_root(root)
        plane = create_face_workplane(self.context, root, 0)
        sketch = build_sketch_on_workplane(self.context, plane)
        body = body_of(sketch.target_object)
        settle_membership(sketch.target_object, [root], self.context)
        apply_boolean(root, body, "Difference")
        reconcile_groups(self.scene)
        sync_part_collections(self.scene)
        return root, plane, sketch.target_object, body

    def test_the_whole_feature_leaves_together(self):
        """The plane is what hangs off the root, so it is what detaches."""
        root, plane, sketch, body = self._part_with_feature()

        self.assertEqual(detachable(body, root), plane)
        self.assertEqual(detachable(sketch, root), plane)

        self.context.view_layer.objects.active = body
        self.assertEqual(bpy.ops.view3d.slvs_remove_from_part(), {"FINISHED"})

        self.assertIsNone(part_root_of(body))
        self.assertIsNone(part_root_of(sketch))
        self.assertTrue(is_part_root(root), "the part itself stays")

    def test_what_leaves_can_be_moved_again(self):
        """The bug this fixes: a body keeps the lock it got on joining."""
        _root, _plane, _sketch, body = self._part_with_feature()
        self.assertEqual(tuple(body.lock_location), (True, True, True))

        self.context.view_layer.objects.active = body
        bpy.ops.view3d.slvs_remove_from_part()
        reconcile_groups(self.scene)

        self.assertEqual(tuple(body.lock_location), (False, False, False))
        self.assertEqual(tuple(body.lock_rotation), (False, False, False))
        # Scale stays locked: the solver reads a plane as a rigid frame.
        self.assertEqual(tuple(body.lock_scale), (True, True, True))

    def test_it_stays_where_it_stood(self):
        root, _plane, _sketch, body = self._part_with_feature()
        root.matrix_basis = root.matrix_basis.Translation((3.0, 1.0, 0.0))
        self.context.view_layer.update()
        before = world_matrix_of(body)

        self.context.view_layer.objects.active = body
        bpy.ops.view3d.slvs_remove_from_part()

        after = world_matrix_of(body)
        self.assertAlmostEqual(
            (after.translation - before.translation).length, 0.0, places=5
        )

    def test_the_cutter_shows_itself_again(self):
        """A cutter in a part is hidden; out of one it has to be findable."""
        _root, _plane, _sketch, body = self._part_with_feature()
        self.assertTrue(body.hide_viewport, "a cutter in a part hides")

        self.context.view_layer.objects.active = body
        bpy.ops.view3d.slvs_remove_from_part()
        reconcile_groups(self.scene)

        self.assertFalse(body.hide_viewport)

    def test_a_part_leaves_its_assembly(self):
        assembly = create_assembly(self.context, "rm_asm")
        part = _cube(self.scene, "rm_part")
        mark_part_root(part)
        join_assembly(assembly, part)
        sync_part_collections(self.scene)

        self.context.view_layer.objects.active = part
        self.assertEqual(bpy.ops.view3d.slvs_remove_from_part(), {"FINISHED"})

        self.assertIsNone(assembly_root_of(part))
        self.assertTrue(is_part_root(part), "it is still a part of its own")

    def test_it_needs_something_in_a_group(self):
        loose = _cube(self.scene, "rm_loose")
        self.context.view_layer.objects.active = loose
        self.assertFalse(bpy.ops.view3d.slvs_remove_from_part.poll())

        lone = _cube(self.scene, "rm_lone")
        mark_part_root(lone)
        self.context.view_layer.objects.active = lone
        self.assertFalse(
            bpy.ops.view3d.slvs_remove_from_part.poll(),
            "a part in no assembly has nothing to leave",
        )


class TestDissolvePart(BgsTestCase):
    def test_the_objects_stay_and_the_part_goes(self):
        root = _cube(self.scene, "ds_root")
        mark_part_root(root)
        member = _cube(self.scene, "ds_member", location=(1.0, 0.0, 0.0))
        join_part(root, member)
        sync_part_collections(self.scene)

        self.context.view_layer.objects.active = root
        self.assertEqual(bpy.ops.view3d.slvs_dissolve_part(), {"FINISHED"})

        self.assertIsNotNone(bpy.data.objects.get(root.name))
        self.assertIsNotNone(bpy.data.objects.get(member.name))
        self.assertFalse(is_part_root(root))
        self.assertIsNone(part_root_of(member))
        self.assertIsNone(member.parent)

    def test_members_keep_their_place(self):
        root = _cube(self.scene, "ds_place_root")
        mark_part_root(root)
        member = _cube(self.scene, "ds_place_member", location=(1.0, 0.0, 0.0))
        join_part(root, member)
        root.matrix_basis = root.matrix_basis.Translation((0.0, 4.0, 2.0))
        self.context.view_layer.update()
        before = world_matrix_of(member)

        self.context.view_layer.objects.active = root
        bpy.ops.view3d.slvs_dissolve_part()

        after = world_matrix_of(member)
        self.assertAlmostEqual(
            (after.translation - before.translation).length, 0.0, places=5
        )

    def test_the_emptied_collection_goes(self):
        from ..utilities.collections import is_part_collection

        root = _cube(self.scene, "ds_coll_root")
        mark_part_root(root)
        sync_part_collections(self.scene)
        coll = next(c for c in root.users_collection if is_part_collection(c))
        name = coll.name

        self.context.view_layer.objects.active = root
        bpy.ops.view3d.slvs_dissolve_part()

        self.assertIsNone(bpy.data.collections.get(name))

    def test_dissolving_an_assembly_keeps_its_parts(self):
        assembly = create_assembly(self.context, "ds_asm")
        parts = []
        for i in range(2):
            part = _cube(self.scene, f"ds_asm_part{i}", location=(2.0 * i, 0.0, 0.0))
            mark_part_root(part)
            join_assembly(assembly, part)
            parts.append(part)
        sync_part_collections(self.scene)
        assembly_name = assembly.name

        self.context.view_layer.objects.active = assembly
        self.assertEqual(bpy.ops.view3d.slvs_dissolve_part(), {"FINISHED"})

        for part in parts:
            self.assertIsNotNone(bpy.data.objects.get(part.name))
            self.assertTrue(is_part_root(part))
            self.assertIsNone(assembly_root_of(part))
        # The root Empty stood for the group and holds nothing of its own.
        self.assertIsNone(bpy.data.objects.get(assembly_name))

    def test_it_needs_a_group(self):
        loose = _cube(self.scene, "ds_loose")
        self.context.view_layer.objects.active = loose
        self.assertFalse(bpy.ops.view3d.slvs_dissolve_part.poll())
