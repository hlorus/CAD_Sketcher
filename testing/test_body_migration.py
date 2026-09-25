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
from .utils import BgsTestCase, Sketch2dTestCase


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


class TestBodyMigrationVisibility(Sketch2dTestCase):
    """A sketch the user had hidden must not come back as a visible body."""

    def _legacy_hidden_sketch(self):
        obj = self.sketch.target_object
        for modifier in list(obj.modifiers):
            obj.modifiers.remove(modifier)
        from ..utilities.curve_data import _ensure_convert_modifier

        _ensure_convert_modifier(obj)
        obj.slvs_body = None
        obj.slvs_workplane = None
        obj.parent = None
        return obj

    def test_a_hidden_sketch_migrates_to_a_hidden_body(self):
        obj = self._legacy_hidden_sketch()
        obj.hide_set(True)
        obj.hide_render = True

        migrate_bodies(self.context, self.scene)

        body = body_of(obj)
        self.assertTrue(body.hide_get())
        self.assertTrue(body.hide_render)

    def test_a_visible_sketch_migrates_to_a_visible_body(self):
        obj = self._legacy_hidden_sketch()

        migrate_bodies(self.context, self.scene)

        body = body_of(obj)
        self.assertFalse(body.hide_get())
        self.assertFalse(body.hide_viewport)
        self.assertFalse(body.hide_render)


class TestUpdateLeavesACurrentFileAlone(BgsTestCase):
    """Running the file update on a file that needs nothing must change nothing.

    The button is meant to be safe to press at any time, so a sketch built by
    this version has to be recognised as already split. It used not to be: only
    the update itself stamped the "body is in place" flag, so every run redid
    the whole rehome and renamed the body after the sketch, which then grew a
    "Sketch Sketch" on the next press.
    """

    def _current_sketch(self):
        """A sketch built the way this version builds one, on a face."""
        from ..operators.add_sketch import (
            build_sketch_on_workplane,
            create_face_workplane,
        )

        me = bpy.data.meshes.new("plate")
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=2.0)
        bm.to_mesh(me)
        bm.free()
        source = bpy.data.objects.new("plate", me)
        self.scene.collection.objects.link(source)
        self.addCleanup(bpy.data.objects.remove, source)
        top = next(p.index for p in me.polygons if p.normal.z > 0.9)

        wp = create_face_workplane(self.context, source, top)
        self.addCleanup(bpy.data.objects.remove, wp)
        sketch = build_sketch_on_workplane(self.context, wp)
        obj = sketch.target_object
        self.addCleanup(bpy.data.objects.remove, body_of(obj))
        self.addCleanup(bpy.data.objects.remove, obj)
        return obj

    def test_a_freshly_built_sketch_needs_no_migration(self):
        self._current_sketch()
        self.assertFalse(migrate_bodies(self.context, self.scene))

    def test_names_survive_repeated_updates(self):
        obj = self._current_sketch()
        body = body_of(obj)
        names = (body.name, obj.name, obj.slvs_workplane.name)

        for _ in range(3):
            migrate_bodies(self.context, self.scene)

        self.assertEqual((body.name, obj.name, obj.slvs_workplane.name), names)

    def test_a_body_saved_before_the_flag_is_left_alone(self):
        """Files written by this version before the flag existed heal in place.

        Nothing is there to move -- the sketch carries no stack -- so the pass
        recognises the split and marks it rather than redoing it.
        """
        from ..utilities.body import BODY_PLACED_KEY

        obj = self._current_sketch()
        body = body_of(obj)
        del body[BODY_PLACED_KEY]
        plane = obj.slvs_workplane

        self.assertFalse(migrate_bodies(self.context, self.scene))
        self.assertTrue(body[BODY_PLACED_KEY])
        self.assertEqual(obj.slvs_workplane, plane)
