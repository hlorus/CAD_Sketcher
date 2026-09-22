"""Bringing files written before parts existed into the part model.

Applies the rules new sketches follow, from what the file already records: a
sketch drawn on a body joins that body's part, one that has been made solid roots
its own, and a plain sketch is left alone until it becomes solid.
"""

import bmesh
import bpy
from mathutils import Matrix, Vector

from ..utilities.face_anchor import KEY_SOURCE
from ..utilities.part import (
    is_part_root,
    migrate_parts,
    part_root_of,
    world_matrix_of,
)
from .utils import Sketch2dTestCase


class TestPartMigration(Sketch2dTestCase):
    def setUp(self):
        super().setUp()
        # The scene is shared across the class, so settle anything an earlier
        # test left behind; each test then speaks only about what it creates.
        migrate_parts(self.scene)
        # Pretend the file was written before parts existed; otherwise there is
        # nothing to migrate and the prompt stays away (which is the point).
        self.scene.sketcher.version = (0, 31, 0)

    def _legacy_plane(self, name="WP", matrix=None):
        """A workplane empty placing a sketch, as older files store it."""
        empty = bpy.data.objects.new(name, None)
        self.scene.collection.objects.link(empty)
        if matrix is not None:
            empty.matrix_world = matrix
        return empty

    def _place_on(self, obj, plane):
        obj.parent = plane
        obj.slvs_workplane = plane
        obj.lock_location = (True, True, True)

    def _cube(self, name="body"):
        me = bpy.data.meshes.new(name)
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=2.0)
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(name, me)
        self.scene.collection.objects.link(ob)
        return ob

    def _add_extrude(self, obj):
        from ..utilities.extrude_nodes import (
            EXTRUDE_NODE_GROUP,
            build_extrude_node_group,
        )

        group = bpy.data.node_groups.get(EXTRUDE_NODE_GROUP)
        if group is None:
            group = build_extrude_node_group()
        mod = obj.modifiers.new("CAD_Sketcher Extrude", "NODES")
        mod.node_group = group
        return mod

    def test_a_plain_sketch_is_left_alone(self):
        obj = self.sketch.target_object
        plane = self._legacy_plane()
        self._place_on(obj, plane)

        self.assertFalse(migrate_parts(self.scene))
        self.assertIsNone(part_root_of(obj))
        self.assertEqual(obj.parent, plane)
        self.assertEqual(tuple(obj.lock_location), (True, True, True))

    def test_a_solid_sketch_becomes_a_part_root_and_keeps_its_place(self):
        obj = self.sketch.target_object
        plane = self._legacy_plane(matrix=Matrix.Translation(Vector((0.0, 0.0, 3.0))))
        self._place_on(obj, plane)
        self.context.view_layer.update()
        self._add_extrude(obj)

        self.assertTrue(migrate_parts(self.scene))
        self.assertTrue(is_part_root(obj))
        # It owns its transform now: no parent, its own plane, and it did not move.
        self.assertIsNone(obj.parent)
        self.assertIsNone(obj.slvs_workplane)
        self.assertEqual(world_matrix_of(obj).translation, Vector((0.0, 0.0, 3.0)))
        self.assertEqual(tuple(obj.lock_location), (False, False, False))

    def test_a_sketch_drawn_on_a_body_joins_its_part(self):
        obj = self.sketch.target_object
        body = self._cube()
        plane = self._legacy_plane()
        plane[KEY_SOURCE] = body
        self._place_on(obj, plane)

        self.assertTrue(migrate_parts(self.scene))
        self.assertTrue(is_part_root(body))
        self.assertEqual(part_root_of(obj), body)
        # The plane is what joined, so the sketch still follows it.
        self.assertEqual(obj.parent, plane)
        self.assertEqual(part_root_of(plane), body)

    def test_migration_is_idempotent(self):
        obj = self.sketch.target_object
        plane = self._legacy_plane()
        self._place_on(obj, plane)
        self._add_extrude(obj)

        self.assertTrue(migrate_parts(self.scene))
        self.assertFalse(migrate_parts(self.scene))

    def test_a_migrated_part_moves_with_its_geometry(self):
        obj = self.sketch.target_object
        plane = self._legacy_plane(matrix=Matrix.Translation(Vector((1.0, 0.0, 0.0))))
        self._place_on(obj, plane)
        self.context.view_layer.update()
        self._add_extrude(obj)
        migrate_parts(self.scene)

        from ..model.sketch_ref import Sketch

        migrated = Sketch(obj)
        obj.matrix_basis = Matrix.Translation(Vector((5.0, 0.0, 0.0)))
        self.context.view_layer.update()
        # The plane it used to hang from must not hold the geometry back.
        self.assertEqual(migrated.plane_matrix.translation, Vector((5.0, 0.0, 0.0)))

    def test_detection_and_the_one_migrate_operator(self):
        from ..utilities.part import needs_part_migration

        obj = self.sketch.target_object
        plane = self._legacy_plane()
        self._place_on(obj, plane)
        self.assertFalse(needs_part_migration(self.scene))  # a plain sketch: nothing

        self._add_extrude(obj)
        self.assertTrue(needs_part_migration(self.scene))

        bpy.ops.view3d.slvs_migrate_legacy()
        self.assertTrue(is_part_root(obj))
        self.assertFalse(needs_part_migration(self.scene))

    def test_nothing_happens_on_file_load(self):
        # Migration restructures the hierarchy, so opening a file must not do it:
        # the load handler leaves everything alone (see the panel prompt).
        from ..handlers import on_load_post

        obj = self.sketch.target_object
        plane = self._legacy_plane()
        self._place_on(obj, plane)
        self._add_extrude(obj)

        on_load_post(None)
        self.assertFalse(is_part_root(obj))
        self.assertEqual(obj.parent, plane)

    def test_a_new_file_is_never_asked_to_migrate(self):
        # The reported annoyance: sketching in a fresh file offered migration,
        # because a sketch is global until it is made solid.
        from ..utilities.part import needs_part_migration

        self.scene.sketcher.version = (0, 0, 0)  # never saved
        obj = self.sketch.target_object
        self._place_on(obj, self._legacy_plane())
        self._add_extrude(obj)

        self.assertFalse(needs_part_migration(self.scene))

    def test_a_file_saved_by_this_build_is_not_asked_either(self):
        from ..utilities.part import PARTS_VERSION, needs_part_migration

        self.scene.sketcher.version = PARTS_VERSION
        obj = self.sketch.target_object
        self._place_on(obj, self._legacy_plane())
        self._add_extrude(obj)

        self.assertFalse(needs_part_migration(self.scene))

    def test_an_older_file_still_is(self):
        from ..utilities.part import needs_part_migration

        self.scene.sketcher.version = (0, 31, 0)
        obj = self.sketch.target_object
        self._place_on(obj, self._legacy_plane())
        self._add_extrude(obj)

        self.assertTrue(needs_part_migration(self.scene))

    def test_a_file_from_the_latest_channel_is_not_prompted(self):
        # Pre-parts builds on the "latest" channel wrote 0.32.0, the version
        # parts ship in, so those files look current and are not prompted. They
        # are updated by running the operator by hand instead.
        from ..utilities.part import needs_part_migration

        self.scene.sketcher.version = (0, 32, 0)
        obj = self.sketch.target_object
        self._place_on(obj, self._legacy_plane())
        self._add_extrude(obj)

        self.assertFalse(needs_part_migration(self.scene))

    def test_running_it_by_hand_still_updates_such_a_file(self):
        from ..utilities.part import is_part_root

        self.scene.sketcher.version = (0, 32, 0)
        obj = self.sketch.target_object
        self._place_on(obj, self._legacy_plane())
        self._add_extrude(obj)

        bpy.ops.view3d.slvs_migrate_legacy()
        self.assertTrue(is_part_root(obj))
