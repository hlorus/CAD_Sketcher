"""What the reconcile pass remembers, across undo.

The pass compares the hierarchy with what it saw last time, and repairs a part
whose root has gone since. That memory is module state, which Blender's undo
does not touch: after an undo the file is authoritative and there is nothing to
repair, so the snapshot has to be dropped rather than diffed against.
"""

import bmesh
import bpy
from mathutils import Matrix, Vector

from ..handlers import on_undo_redo
from ..operators.add_sketch import build_sketch_on_workplane
from ..utilities.body import body_of
from ..utilities.part import (
    PART_PLANE_KEY,
    is_part_root,
    join_part,
    mark_part_root,
    reconcile_groups,
    reset_cache,
)
from .utils import BgsTestCase


class TestPartUndo(BgsTestCase):
    def setUp(self):
        super().setUp()
        self.entities.ensure_origin_elements(self.context)
        from ..utilities.workplane import ensure_origin_workplane_empties

        ensure_origin_workplane_empties(self.context)
        self.datum = self.context.scene.sketcher.wp_xy
        reset_cache()

        # Drive the pass by hand: a live handler would run it at every
        # view_layer update, which is not the order these tests are about.
        from ..handlers import on_depsgraph_update

        self._live = [
            h
            for h in bpy.app.handlers.depsgraph_update_post
            if getattr(h, "__name__", "") == on_depsgraph_update.__name__
        ]
        for handler in self._live:
            bpy.app.handlers.depsgraph_update_post.remove(handler)

    def tearDown(self):
        for handler in self._live:
            bpy.app.handlers.depsgraph_update_post.append(handler)
        super().tearDown()

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

    def _part_with_a_member(self):
        """A part at z=5 holding a body that stood at y=4 before it joined."""
        root = self._cube("root", location=(0.0, 0.0, 5.0))
        mark_part_root(root)

        sketch = build_sketch_on_workplane(self.context, self.datum)
        member = body_of(sketch.target_object)
        member.matrix_basis = Matrix.Translation(Vector((0.0, 4.0, 0.0)))
        self.context.view_layer.update()

        join_part(root, member)
        self.context.view_layer.update()
        reconcile_groups(self.scene)
        return root, member

    def _undo_the_part(self, root, member, stood_at):
        """The state an undo of "make this a part" leaves behind.

        Undo restores the file wholesale: the root is gone and the member is
        back where it was, unparented, with no parent inverse left over.
        """
        bpy.data.objects.remove(root)
        member.parent = None
        member.matrix_parent_inverse = Matrix.Identity(4)
        member.matrix_basis = Matrix.Translation(stood_at)
        self.context.view_layer.update()

    def test_undo_leaves_a_members_place_alone(self):
        stood_at = Vector((0.0, 4.0, 0.0))
        root, member = self._part_with_a_member()
        self._undo_the_part(root, member, stood_at)

        on_undo_redo(self.scene)
        reconcile_groups(self.scene)
        self.context.view_layer.update()

        # Repairing it would add the vanished root's transform a second time,
        # to a member undo has already put back.
        self.assertEqual(member.matrix_basis.translation, stood_at)

    def test_undo_does_not_hand_the_part_to_a_survivor(self):
        root, member = self._part_with_a_member()
        self._undo_the_part(root, member, Vector((0.0, 4.0, 0.0)))

        on_undo_redo(self.scene)
        reconcile_groups(self.scene)

        self.assertFalse(
            is_part_root(member),
            "undoing a part's creation left one of its members rooting a part",
        )

    def test_a_deleted_root_is_still_repaired(self):
        # The same shape without the undo: here the snapshot is the only record
        # of where the part stood, and the members do have to be put back.
        root, member = self._part_with_a_member()
        root.matrix_basis = Matrix.Translation(Vector((0.0, 0.0, 9.0)))
        self.context.view_layer.update()
        reconcile_groups(self.scene)
        placed_at = member.matrix_world.translation.copy()

        # Blender's own Delete drops the parent and keeps the child's local
        # matrix, which is where it stood when it joined, not where it is now.
        bpy.data.objects.remove(root)
        self.context.view_layer.update()

        reconcile_groups(self.scene)
        self.context.view_layer.update()

        self.assertEqual(member.matrix_world.translation, placed_at)
        self.assertTrue(is_part_root(member))

    def test_the_next_pass_reads_the_restored_file(self):
        # Dropping the snapshot must not leave the pass blind: whatever the file
        # holds after the undo is pinned again on the very next pass.
        root, member = self._part_with_a_member()
        plane = bpy.data.objects.new("root XY", None)
        self.scene.collection.objects.link(plane)
        plane[PART_PLANE_KEY] = "XY"
        plane.parent = root
        plane.lock_location = (False, False, False)

        on_undo_redo(self.scene)
        reconcile_groups(self.scene)

        self.assertTrue(all(plane.lock_location))
        self.assertTrue(is_part_root(root))
