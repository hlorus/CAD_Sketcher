"""Giving an older file's sketches the bodies their geometry belongs on.

Before the split the sketch object *was* the body: its modifiers turned a Curves
object into a mesh, which is what stops the stack being applied (issue #723).
Migration moves the stack to a real mesh and repoints everything that meant the
sketch's geometry.
"""

import bmesh
import bpy
from mathutils import Matrix, Vector

from ..operators.modifiers import apply_boolean, boolean_cutters
from ..utilities.body import body_of, is_body, migrate_bodies, sketch_of
from ..utilities.curve_data import CONVERT_MODIFIER_NAME
from ..utilities.face_anchor import KEY_SOURCE
from ..utilities.part import is_part_root, mark_part_root, part_root_of
from .utils import Sketch2dTestCase


class TestBodyMigration(Sketch2dTestCase):
    def _cube(self, name):
        me = bpy.data.meshes.new(name)
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=2.0)
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(name, me)
        self.scene.collection.objects.link(ob)
        return ob

    def _legacy_sketch(self):
        """A sketch shaped the way older files stored one: it carries the stack."""
        obj = self.sketch.target_object
        for modifier in list(obj.modifiers):
            obj.modifiers.remove(modifier)
        from ..utilities.curve_data import _ensure_convert_modifier

        _ensure_convert_modifier(obj)
        obj.slvs_body = None
        obj.slvs_workplane = None
        obj.parent = None
        return obj

    def test_the_stack_moves_to_a_body(self):
        obj = self._legacy_sketch()
        self.assertIn(CONVERT_MODIFIER_NAME, [m.name for m in obj.modifiers])

        self.assertTrue(migrate_bodies(self.context, self.scene))

        body = body_of(obj)
        self.assertIsNotNone(body)
        self.assertTrue(is_body(body))
        self.assertEqual(sketch_of(body), obj)
        # The sketch keeps nothing that changes its type.
        self.assertEqual(list(obj.modifiers), [])
        self.assertIn(CONVERT_MODIFIER_NAME, [m.name for m in body.modifiers])

    def test_the_body_stands_where_the_sketch_did(self):
        obj = self._legacy_sketch()
        obj.matrix_world = Matrix.Translation(Vector((3.0, 0.0, 1.0)))
        self.context.view_layer.update()

        migrate_bodies(self.context, self.scene)
        self.context.view_layer.update()

        body = body_of(obj)
        self.assertEqual(body.matrix_world.translation, Vector((3.0, 0.0, 1.0)))
        # And the sketch now sits on a plane of its own, in the same place.
        self.assertIsNotNone(obj.slvs_workplane)
        self.assertEqual(obj.matrix_world.translation, Vector((3.0, 0.0, 1.0)))

    def test_a_part_root_hands_over_to_its_body(self):
        obj = self._legacy_sketch()
        mark_part_root(obj)

        migrate_bodies(self.context, self.scene)

        body = body_of(obj)
        self.assertTrue(is_part_root(body))
        self.assertFalse(is_part_root(obj))
        self.assertEqual(part_root_of(obj), body)

    def test_another_parts_boolean_follows_the_body(self):
        obj = self._legacy_sketch()
        target = self._cube("target")
        apply_boolean(target, obj, "Difference")
        self.assertEqual(boolean_cutters(target), [obj])

        migrate_bodies(self.context, self.scene)

        self.assertEqual(boolean_cutters(target), [body_of(obj)])

    def test_a_face_anchor_follows_the_body(self):
        obj = self._legacy_sketch()
        plane = bpy.data.objects.new("anchored", None)
        self.scene.collection.objects.link(plane)
        plane[KEY_SOURCE] = obj

        migrate_bodies(self.context, self.scene)

        self.assertEqual(plane[KEY_SOURCE], body_of(obj))

    def test_migration_is_idempotent(self):
        self._legacy_sketch()
        self.assertTrue(migrate_bodies(self.context, self.scene))
        self.assertFalse(migrate_bodies(self.context, self.scene))

    def test_the_body_takes_over_the_name(self):
        # Whatever the part was called in the old file is what the user grabs
        # now, so the name goes with the geometry rather than the source.
        obj = self._legacy_sketch()
        obj.name = "Bracket"

        migrate_bodies(self.context, self.scene)

        body = body_of(obj)
        self.assertEqual(body.name, "Bracket")
        self.assertEqual(body.data.name, "Bracket")
        self.assertEqual(obj.name, "Bracket Sketch")
        self.assertEqual(obj.slvs_workplane.name, "Bracket Workplane")

    def test_a_linked_boolean_group_does_not_stop_the_update(self):
        # From a real file: a boolean group linked from a library keeps whatever
        # interface it was built with, so its Cutter socket may not be there at
        # all. Reading it raised and took the whole update down with it.
        obj = self._legacy_sketch()
        cube = self._cube("target")
        for existing in list(bpy.data.node_groups):
            if existing.name == "CAD Sketcher Boolean":
                existing.name = "CAD Sketcher Boolean.real"
        stale = bpy.data.node_groups.new("CAD Sketcher Boolean", "GeometryNodeTree")
        stale.interface.new_socket(
            "Geometry", in_out="INPUT", socket_type="NodeSocketGeometry"
        )
        modifier = cube.modifiers.new("CAD_Sketcher Boolean", "NODES")
        modifier.node_group = stale

        self.assertTrue(migrate_bodies(self.context, self.scene))
        self.assertIsNotNone(body_of(obj))
