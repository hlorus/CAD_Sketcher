"""Placing linked copies of a part.

A copy is a collection instance: one part, several placements, so editing the
part updates every copy. Placements render the part; they hold no geometry, so
they are not edited where they stand.
"""

import bmesh
import bpy
from mathutils import Vector

from ..utilities.collections import part_collection, sync_part_collections
from ..utilities.part import (
    assembly_root_of,
    create_assembly,
    instance_part,
    is_part_instance,
    is_part_root,
    join_assembly,
    mark_part_root,
    part_root_of,
    world_matrix_of,
)
from .utils import BgsTestCase


class TestPartInstance(BgsTestCase):
    def _part(self, name, location=(0.0, 0.0, 0.0)):
        me = bpy.data.meshes.new(name)
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=2.0)
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(name, me)
        self.scene.collection.objects.link(ob)
        ob.location = location
        mark_part_root(ob)
        sync_part_collections(self.scene)
        return ob

    def test_an_instance_points_at_the_parts_collection(self):
        root = self._part("widget")
        self.scene.cursor.location = Vector((4.0, 0.0, 0.0))

        instance = instance_part(self.context, root)

        self.assertTrue(is_part_instance(instance))
        self.assertEqual(
            instance.instance_collection, part_collection(root, self.scene)
        )
        self.assertEqual(instance.matrix_basis.translation, Vector((4.0, 0.0, 0.0)))

    def test_the_offset_puts_the_copy_where_it_is_placed(self):
        # Without the collection's instance_offset the contents would be drawn at
        # their own world position on top of the placement, doubling the offset.
        root = self._part("widget", location=(5.0, 0.0, 0.0))
        self.context.view_layer.update()

        instance_part(self.context, root)
        self.assertEqual(
            part_collection(root, self.scene).instance_offset, Vector((5.0, 0.0, 0.0))
        )

    def test_a_placement_is_not_itself_a_part(self):
        root = self._part("widget")
        instance = instance_part(self.context, root)

        self.assertFalse(is_part_root(instance))
        self.assertIsNone(part_root_of(instance))

    def test_several_placements_share_one_part(self):
        root = self._part("widget")
        first = instance_part(self.context, root)
        self.scene.cursor.location = Vector((0.0, 3.0, 0.0))
        second = instance_part(self.context, root)

        self.assertNotEqual(first, second)
        self.assertEqual(first.instance_collection, second.instance_collection)

    def test_a_placement_joins_the_parts_assembly(self):
        root = self._part("widget")
        assembly = create_assembly(self.context)
        join_assembly(assembly, root)

        instance = instance_part(self.context, root)
        self.assertEqual(assembly_root_of(instance), assembly)

    def test_the_operator_places_the_selected_part(self):
        root = self._part("widget")
        bpy.ops.object.select_all(action="DESELECT")
        root.select_set(True)
        self.context.view_layer.objects.active = root

        before = {o.name for o in self.scene.objects}
        bpy.ops.view3d.slvs_instance_part()
        new_objects = [o for o in self.scene.objects if o.name not in before]

        self.assertEqual(len(new_objects), 1)
        self.assertTrue(is_part_instance(new_objects[0]))
        self.assertEqual(
            new_objects[0].instance_collection, part_collection(root, self.scene)
        )

    def test_a_placement_does_not_show_the_parts_cutters(self):
        # The eye is view-layer state and does not reach instanced copies, so a
        # cutter hidden that way would draw over the result at every placement.
        from ..operators.modifiers import apply_boolean
        from ..utilities.part import join_part, update_cutter_display

        root = self._part("widget")
        cutter = bpy.data.objects.new("cutter", bpy.data.meshes.new("cutter"))
        self.scene.collection.objects.link(cutter)
        join_part(root, cutter)
        apply_boolean(root, cutter, "Difference")
        update_cutter_display(cutter, [root], True)
        sync_part_collections(self.scene)

        instance = instance_part(self.context, root)
        self.context.view_layer.update()

        depsgraph = self.context.evaluated_depsgraph_get()
        drawn = {
            inst.object.name
            for inst in depsgraph.object_instances
            if inst.is_instance and inst.parent and inst.parent.original == instance
        }
        self.assertIn(root.name, drawn)
        self.assertNotIn(cutter.name, drawn)

    def test_a_placement_can_land_on_the_original(self):
        # What Alt+D does: the copy appears on the original and is then moved,
        # rather than jumping to the 3D cursor.
        root = self._part("widget", location=(3.0, 0.0, 0.0))
        self.context.view_layer.update()
        self.scene.cursor.location = Vector((0.0, 0.0, 0.0))

        placement = instance_part(
            self.context, root, location=world_matrix_of(root).translation
        )
        self.assertEqual(placement.matrix_basis.translation, Vector((3.0, 0.0, 0.0)))

    def test_the_operator_places_at_the_original_when_asked(self):
        root = self._part("widget", location=(2.0, 0.0, 0.0))
        self.context.view_layer.update()
        self.scene.cursor.location = Vector((9.0, 9.0, 9.0))
        bpy.ops.object.select_all(action="DESELECT")
        root.select_set(True)
        self.context.view_layer.objects.active = root

        before = {o.name for o in self.scene.objects}
        bpy.ops.view3d.slvs_instance_part(at_cursor=False)
        placement = next(o for o in self.scene.objects if o.name not in before)

        self.assertEqual(placement.matrix_basis.translation, Vector((2.0, 0.0, 0.0)))
        self.assertTrue(placement.select_get())
