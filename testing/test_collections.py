"""Managed collections: one per part, nested in its assembly's, derived from
the object hierarchy.

Collections are a view of membership, never its authority: parenting decides what
belongs to what, and the sync moves objects to match. Only the shared origin
planes live in a scene-level "Origin" collection. Nothing is excluded from the
view layer, since excluding would drop the fill (the curve object is both source
and consumable).
"""

import bpy

from ..utilities.collections import (
    dissolve_legacy_sketch_collections,
    origin_collection,
    sync_part_collections,
)
from ..utilities.curve_data import refresh_curve_geometry
from ..utilities.part import (
    create_assembly,
    join_assembly,
    join_part,
    mark_part_root,
)
from .utils import Sketch2dTestCase


class TestManagedCollection(Sketch2dTestCase):
    def _part_collection(self, ob):
        for coll in ob.users_collection:
            if coll.get("cad_part_collection"):
                return coll
        return None

    def _assembly_collection(self, ob):
        for coll in ob.users_collection:
            if coll.get("cad_assembly_collection"):
                return coll
        return None

    def _child_names(self, coll):
        return {c.name for c in coll.children}

    def test_a_sketch_in_no_part_sits_at_the_scene_level(self):
        ob = self.sketch.target_object
        sync_part_collections(self.context.scene)

        self.assertIsNone(self._part_collection(ob))
        self.assertIn(ob.name, self.context.scene.collection.objects)

    def test_a_part_gets_its_own_scene_level_collection(self):
        ob = self.sketch.target_object
        mark_part_root(ob)
        self.assertTrue(sync_part_collections(self.context.scene))

        coll = self._part_collection(ob)
        self.assertIsNotNone(coll)
        self.assertIn(coll.name, self.context.scene.collection.children)
        self.assertNotIn(ob.name, self.context.scene.collection.objects)

    def test_members_follow_their_part_into_its_collection(self):
        root = self.sketch.target_object
        mark_part_root(root)
        member = bpy.data.objects.new("member", None)
        self.scene.collection.objects.link(member)
        join_part(root, member)

        sync_part_collections(self.context.scene)
        self.assertEqual(self._part_collection(member), self._part_collection(root))

    def test_leaving_a_part_returns_an_object_to_the_scene_level(self):
        root = self.sketch.target_object
        mark_part_root(root)
        member = bpy.data.objects.new("member", None)
        self.scene.collection.objects.link(member)
        join_part(root, member)
        sync_part_collections(self.context.scene)

        member.parent = None
        self.assertTrue(sync_part_collections(self.context.scene))
        self.assertIsNone(self._part_collection(member))
        self.assertIn(member.name, self.context.scene.collection.objects)

    def test_a_part_collection_nests_in_its_assemblys_collection(self):
        root = self.sketch.target_object
        mark_part_root(root)
        assembly = create_assembly(self.context)
        join_assembly(assembly, root)

        sync_part_collections(self.context.scene)
        part_coll = self._part_collection(root)
        assembly_coll = self._assembly_collection(assembly)
        self.assertIsNotNone(assembly_coll)
        self.assertIn(part_coll.name, self._child_names(assembly_coll))
        self.assertIn(assembly_coll.name, self._child_names(self.scene.collection))

    def test_an_emptied_part_collection_is_removed(self):
        root = self.sketch.target_object
        mark_part_root(root)
        sync_part_collections(self.context.scene)
        name = self._part_collection(root).name

        bpy.data.objects.remove(root)
        self.assertTrue(sync_part_collections(self.context.scene))
        self.assertNotIn(name, {c.name for c in bpy.data.collections})

    def test_the_sync_settles_in_one_pass(self):
        root = self.sketch.target_object
        mark_part_root(root)
        sync_part_collections(self.context.scene)
        self.assertFalse(sync_part_collections(self.context.scene))

    def _legacy_collection(self, ob):
        """What older files were saved with: a marked collection per sketch."""
        legacy = bpy.data.collections.new("legacy_sketch")
        legacy["cad_sketch_collection"] = True
        self.scene.collection.children.link(legacy)
        for coll in list(ob.users_collection):
            coll.objects.unlink(ob)
        legacy.objects.link(ob)
        return legacy

    def test_legacy_per_sketch_collections_are_dissolved(self):
        ob = self.sketch.target_object
        self._legacy_collection(ob)

        self.assertTrue(dissolve_legacy_sketch_collections(self.context.scene))
        self.assertNotIn("legacy_sketch", {c.name for c in bpy.data.collections})
        self.assertIn(ob.name, self.context.scene.collection.objects)

    def test_opening_a_file_leaves_its_old_collections_alone(self):
        # The sync runs from the depsgraph handler, so it must not rearrange the
        # outliner of a file that was merely opened; migration does that.
        ob = self.sketch.target_object
        legacy = self._legacy_collection(ob)

        sync_part_collections(self.context.scene)
        self.assertIn(legacy.name, {c.name for c in bpy.data.collections})
        self.assertIn(ob.name, legacy.objects)

    def test_origin_planes_go_in_a_scene_level_origin_collection(self):
        from ..utilities.workplane import ensure_origin_workplane_empties

        ensure_origin_workplane_empties(self.context)
        origin = origin_collection(self.context.scene)
        for prop in ("wp_xy", "wp_xz", "wp_yz"):
            empty = getattr(self.context.scene.sketcher, prop)
            self.assertIn(empty.name, origin.objects)

    def test_origin_collection_is_linked_but_not_excluded(self):
        """The Origin collection must stay in the view layer (never excluded)."""
        coll = origin_collection(self.context.scene)
        self.assertIn(coll.name, self.context.scene.collection.children)
        layer_coll = self.context.view_layer.layer_collection.children.get(coll.name)
        self.assertIsNotNone(layer_coll)
        self.assertFalse(layer_coll.exclude, "Origin collection must not be excluded")

    def test_origin_collection_is_idempotent_and_per_scene(self):
        scene = self.context.scene
        a = origin_collection(scene)
        b = origin_collection(scene)
        self.assertIs(a, b, "origin_collection must reuse the scene's collection")

        other = bpy.data.scenes.new("other_scene")
        try:
            c = origin_collection(other)
            self.assertIsNot(c, a, "each scene must own its own Origin collection")
        finally:
            bpy.data.scenes.remove(other)

    def test_fill_still_evaluates_from_the_collection(self):
        corners = [(-2, -2), (2, -2), (2, 2), (-2, 2)]
        pts = [self.add_point(c) for c in corners]
        for i in range(4):
            self.add_line(pts[i], pts[(i + 1) % 4])
        self.solve()
        refresh_curve_geometry(self.sketch)

        ob = self.sketch.target_object
        mark_part_root(ob)
        sync_part_collections(self.context.scene)

        scene = self.context.scene
        dup = ob.copy()
        dup.data = ob.data.copy()
        scene.collection.objects.link(dup)
        for o in scene.collection.all_objects:
            o.select_set(False)
        dup.select_set(True)
        self.context.view_layer.objects.active = dup
        bpy.ops.object.convert(target="MESH")
        area = sum(p.area for p in dup.data.polygons)
        bpy.data.objects.remove(dup, do_unlink=True)

        self.assertAlmostEqual(
            area, 16.0, delta=0.01, msg="fill did not evaluate -> collection excluded?"
        )

    def test_the_sync_is_skipped_when_nothing_moved(self):
        # It walks subtrees and rewrites links, so it must not run on every
        # depsgraph update: the hierarchy signature gates it.
        root = self.sketch.target_object
        mark_part_root(root)
        sync_part_collections(self.context.scene)

        self.assertFalse(sync_part_collections(self.context.scene))

        member = bpy.data.objects.new("member", None)
        self.scene.collection.objects.link(member)
        join_part(root, member)
        self.assertTrue(sync_part_collections(self.context.scene))

    def test_a_duplicated_part_gets_its_own_collection(self):
        # Blender links a duplicate into its source's collections, so without
        # this two parts would share one container and instancing it would
        # render both.
        root = self.sketch.target_object
        mark_part_root(root)
        sync_part_collections(self.context.scene)
        source_coll = self._part_collection(root)

        copy = root.copy()
        copy.data = root.data.copy()
        source_coll.objects.link(copy)

        self.assertTrue(sync_part_collections(self.context.scene))
        copy_coll = self._part_collection(copy)
        self.assertIsNotNone(copy_coll)
        self.assertNotEqual(copy_coll, source_coll)
        self.assertIn(root.name, source_coll.objects)
        self.assertNotIn(copy.name, source_coll.objects)
