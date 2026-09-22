"""Copying a whole part.

Blender's duplicate copies only what is selected, so a body copied on its own
arrives without the cutters that shape it. This takes the part as a unit and
rewrites the copy's references to point inside itself.
"""

import bmesh
import bpy
from mathutils import Matrix, Vector

from ..operators.modifiers import apply_boolean, boolean_cutters
from ..utilities.part import (
    duplicate_part,
    is_part_root,
    join_part,
    mark_part_root,
    part_root_of,
    world_matrix_of,
)
from .utils import BgsTestCase


class TestDuplicatePart(BgsTestCase):
    def _cube(self, name, location=(0.0, 0.0, 0.0)):
        name = f"dup_{name}"
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
        body = self._cube("body")
        mark_part_root(body)
        cutter = self._cube("cutter", location=(0.9, 0.0, 0.0))
        join_part(body, cutter)
        apply_boolean(body, cutter, "Difference")
        return body, cutter

    def test_the_whole_part_is_copied(self):
        body, cutter = self._part_with_cutter()

        copy = duplicate_part(self.context, body)

        self.assertTrue(is_part_root(copy))
        self.assertNotEqual(copy, body)
        members = copy.children_recursive
        self.assertEqual(len(members), 1, "the cutter must come along")
        self.assertEqual(part_root_of(members[0]), copy)

    def test_the_copy_is_cut_by_its_own_cutter(self):
        body, cutter = self._part_with_cutter()

        copy = duplicate_part(self.context, body)
        copied_cutter = copy.children_recursive[0]

        self.assertEqual(boolean_cutters(copy), [copied_cutter])
        self.assertNotIn(cutter, boolean_cutters(copy))
        # And the original is untouched.
        self.assertEqual(boolean_cutters(body), [cutter])

    def test_the_copy_owns_its_data(self):
        body, _cutter = self._part_with_cutter()
        copy = duplicate_part(self.context, body)
        self.assertNotEqual(copy.data, body.data)

    def test_members_keep_their_place_within_the_copy(self):
        body, cutter = self._part_with_cutter()
        self.context.view_layer.update()
        offset = world_matrix_of(cutter).translation - world_matrix_of(body).translation

        copy = duplicate_part(self.context, body)
        copy.matrix_basis = Matrix.Translation(Vector((10.0, 0.0, 0.0)))
        self.context.view_layer.update()
        copied_cutter = copy.children_recursive[0]

        moved = (
            world_matrix_of(copied_cutter).translation
            - world_matrix_of(copy).translation
        )
        self.assertAlmostEqual((moved - offset).length, 0.0, places=4)

    def test_a_sketch_in_the_copy_points_at_the_copied_workplane(self):
        body = self._cube("body")
        mark_part_root(body)
        plane = bpy.data.objects.new("dup_plane", None)
        self.scene.collection.objects.link(plane)
        join_part(body, plane)

        curve = bpy.data.hair_curves.new("dup_sketch")
        sketch = bpy.data.objects.new("dup_sketch", curve)
        self.scene.collection.objects.link(sketch)
        sketch.parent = plane
        sketch.slvs_workplane = plane

        copy = duplicate_part(self.context, body)
        copied = {obj.name: obj for obj in copy.children_recursive}
        copied_sketch = next(o for o in copied.values() if o.type == "CURVES")

        self.assertNotEqual(copied_sketch.slvs_workplane, plane)
        self.assertEqual(copied_sketch.slvs_workplane, copied_sketch.parent)

    def test_the_operator_copies_the_selected_part(self):
        body, _cutter = self._part_with_cutter()
        bpy.ops.object.select_all(action="DESELECT")
        body.select_set(True)
        self.context.view_layer.objects.active = body

        before = {o.name for o in self.scene.objects}
        bpy.ops.view3d.slvs_duplicate_part()
        new_objects = [o for o in self.scene.objects if o.name not in before]

        self.assertEqual(len(new_objects), 2, "body and cutter")

    def test_the_shortcut_passes_the_key_on_when_no_part_is_selected(self):
        # A failing poll leaves Shift+D to Blender's own duplicate.
        plain = self._cube("plain")
        bpy.ops.object.select_all(action="DESELECT")
        plain.select_set(True)
        self.context.view_layer.objects.active = plain

        self.assertFalse(bpy.ops.view3d.slvs_duplicate_part.poll())

    def test_the_button_still_works_when_the_shortcut_is_off(self):
        # The preference belongs to the key, not to the operator: gating the poll
        # on it would grey the panel button out too.
        from ..utilities.preferences import get_prefs

        body, _cutter = self._part_with_cutter()
        bpy.ops.object.select_all(action="DESELECT")
        body.select_set(True)
        self.context.view_layer.objects.active = body

        prefs = get_prefs()
        prefs.part_duplicate_shortcuts = False
        try:
            self.assertTrue(bpy.ops.view3d.slvs_duplicate_part.poll())
            before = {o.name for o in self.scene.objects}
            bpy.ops.view3d.slvs_duplicate_part()
            self.assertTrue({o.name for o in self.scene.objects} - before)
        finally:
            prefs.part_duplicate_shortcuts = True

    def test_the_copies_end_up_selected(self):
        body, _cutter = self._part_with_cutter()
        bpy.ops.object.select_all(action="DESELECT")
        body.select_set(True)
        self.context.view_layer.objects.active = body

        bpy.ops.view3d.slvs_duplicate_part()
        self.assertFalse(body.select_get())
        self.assertTrue(self.context.view_layer.objects.active.select_get())
        self.assertNotEqual(self.context.view_layer.objects.active, body)
