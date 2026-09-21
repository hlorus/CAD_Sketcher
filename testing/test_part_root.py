"""Tests for parts: which object owns a part's transform, and who follows it.

A part is rooted in its first sketch (which becomes its body once extruded), so
the user moves the geometry they see. Workplanes and the sketches on them are
members: fixed within the part, carried along by it.
"""

import bmesh
import bpy
from mathutils import Matrix, Vector

from ..operators.add_sketch import build_sketch_on_workplane, create_face_workplane
from ..utilities.part import (
    is_part_root,
    join_part,
    part_root_of,
    rehome_children,
)
from .utils import BgsTestCase


class TestPartRoot(BgsTestCase):
    def setUp(self):
        super().setUp()
        self.entities.ensure_origin_elements(self.context)
        from ..utilities.workplane import ensure_origin_workplane_empties

        ensure_origin_workplane_empties(self.context)
        self.datum = self.context.scene.sketcher.wp_xy

    def _cube(self, name="body", location=(0.0, 0.0, 0.0)):
        me = bpy.data.meshes.new(name)
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=2.0)
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(name, me)
        self.scene.collection.objects.link(ob)
        ob.location = location
        return ob

    def test_sketch_on_a_datum_plane_starts_a_part(self):
        sketch = build_sketch_on_workplane(self.context, self.datum)
        obj = sketch.target_object

        self.assertTrue(is_part_root(obj))
        self.assertIsNone(obj.parent)
        # It is its own plane, sitting where the datum plane it was drawn on is.
        self.assertIsNone(obj.slvs_workplane)
        self.assertEqual(sketch.plane_matrix, self.datum.matrix_world)

    def test_a_part_root_can_be_moved(self):
        sketch = build_sketch_on_workplane(self.context, self.datum)
        obj = sketch.target_object

        self.assertEqual(tuple(obj.lock_location), (False, False, False))
        self.assertEqual(tuple(obj.lock_rotation), (False, False, False))
        # Scale stays locked: the solver reads the plane as a rigid frame.
        self.assertEqual(tuple(obj.lock_scale), (True, True, True))

        obj.matrix_world = Matrix.Translation(Vector((5.0, 0.0, 0.0)))
        self.assertEqual(sketch.plane_matrix.translation, Vector((5.0, 0.0, 0.0)))

    def test_sketch_on_a_face_joins_that_object_s_part(self):
        body = self._cube()
        wp = create_face_workplane(self.context, body, 0)
        sketch = build_sketch_on_workplane(self.context, wp)
        obj = sketch.target_object

        # The mesh became the part; the sketch is a feature inside it.
        self.assertTrue(is_part_root(body))
        self.assertFalse(is_part_root(obj))
        self.assertEqual(part_root_of(obj), body)
        self.assertEqual(obj.parent, wp)
        self.assertEqual(obj.slvs_workplane, wp)
        self.assertEqual(tuple(obj.lock_location), (True, True, True))

    def test_members_follow_the_part(self):
        body = self._cube()
        wp = create_face_workplane(self.context, body, 0)
        sketch = build_sketch_on_workplane(self.context, wp)
        before = sketch.plane_matrix.translation.copy()

        body.matrix_world = Matrix.Translation(Vector((0.0, 0.0, 3.0)))
        self.context.view_layer.update()
        self.assertEqual(
            sketch.plane_matrix.translation, before + Vector((0.0, 0.0, 3.0))
        )

    def test_joining_a_part_keeps_world_position(self):
        root = self._cube("root", location=(2.0, 0.0, 0.0))
        member = bpy.data.objects.new("member", None)
        self.scene.collection.objects.link(member)
        member.matrix_world = Matrix.Translation(Vector((0.0, 4.0, 0.0)))
        self.context.view_layer.update()

        join_part(root, member)
        self.context.view_layer.update()
        self.assertEqual(member.matrix_world.translation, Vector((0.0, 4.0, 0.0)))

    def test_rehoming_keeps_members_in_place_and_promotes_a_successor(self):
        sketch = build_sketch_on_workplane(self.context, self.datum)
        root = sketch.target_object
        root.matrix_world = Matrix.Translation(Vector((7.0, 0.0, 0.0)))
        self.context.view_layer.update()

        wp = bpy.data.objects.new("WP", None)
        self.scene.collection.objects.link(wp)
        wp.matrix_world = Matrix.Translation(Vector((7.0, 1.0, 0.0)))
        self.context.view_layer.update()
        join_part(root, wp)

        member = build_sketch_on_workplane(self.context, wp)
        member_obj = member.target_object
        placed_at = member.plane_matrix.translation.copy()

        successor = rehome_children(root)
        self.context.view_layer.update()

        self.assertEqual(successor, member_obj)
        self.assertTrue(is_part_root(member_obj))
        self.assertIsNone(member_obj.parent)
        # The successor owns its transform now, so it is its own plane, and the
        # part's geometry did not jump when the old root let go.
        self.assertIsNone(member_obj.slvs_workplane)
        self.assertEqual(member.plane_matrix.translation, placed_at)
        self.assertEqual(part_root_of(wp), member_obj)
