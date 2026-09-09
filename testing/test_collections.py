"""Project-centric managed collections for CAD Sketcher.

Each sketch/part is its own scene-level collection (its workplane nested inside);
cutters nest under the body they feed; only the shared origin planes live in a
scene-level "Origin" collection. Nothing is excluded from the view layer --
excluding would drop the fill (the curve object is both source and consumable).
"""

import bpy

from ..utilities.curve_data import refresh_curve_geometry
from .utils import Sketch2dTestCase


class TestManagedCollection(Sketch2dTestCase):
    def _origin_collection(self):
        for child in self.context.scene.collection.children:
            if child.get("cad_origin_collection"):
                return child
        return None

    def _sketch_subcollection(self, ob):
        for coll in ob.users_collection:
            if coll.get("cad_sketch_collection"):
                return coll
        return None

    def test_part_collection_is_at_the_scene_level(self):
        ob = self.sketch.target_object
        sub = self._sketch_subcollection(ob)
        self.assertIsNotNone(sub, "sketch object not in a per-sketch collection")
        self.assertIn(
            sub.name,
            self.context.scene.collection.children,
            "part collection should be at the scene level, not under a wrapper",
        )
        self.assertNotIn(
            ob.name,
            self.context.scene.collection.objects,
            "sketch object should not sit loose in the scene master collection",
        )

    def test_each_sketch_gets_a_distinct_subcollection(self):
        first = self._sketch_subcollection(self.sketch.target_object)
        second_sketch = self.new_sketch()
        second = self._sketch_subcollection(second_sketch.target_object)
        self.assertIsNotNone(second)
        self.assertIsNot(first, second, "two sketches must not share a sub-collection")

    def test_origin_planes_go_in_a_scene_level_origin_collection(self):
        from ..utilities.workplane import ensure_origin_workplane_empties

        ensure_origin_workplane_empties(self.context)
        origin = self._origin_collection()
        self.assertIsNotNone(origin, "Origin collection not created")
        self.assertIn(
            origin.name,
            self.context.scene.collection.children,
            "Origin should be a scene-level collection (no wrapper)",
        )
        self.assertGreaterEqual(
            len(origin.objects), 3, "the three origin planes should be grouped here"
        )
        for ob in origin.objects:
            self.assertNotIn(ob.name, self.context.scene.collection.objects)

    def test_dedicated_workplane_nests_with_its_sketch(self):
        from ..utilities.collections import link_loose_workplane, nest_workplane

        ob = self.sketch.target_object
        sub = self._sketch_subcollection(ob)

        wp = bpy.data.objects.new("Workplane", None)
        link_loose_workplane(wp, self.context.scene)  # starts loose at scene level
        self.assertIn(wp.name, self.context.scene.collection.objects)

        ob.parent = wp
        nest_workplane(wp, ob)
        try:
            self.assertIn(wp.name, sub.objects, "workplane should nest with its sketch")
            self.assertNotIn(
                wp.name,
                self.context.scene.collection.objects,
                "and leave the scene root",
            )
        finally:
            bpy.data.objects.remove(wp)

    def test_free_3d_origin_nests_with_its_sketch(self):
        from ..model.native_3d import create_3d_sketch

        sketch = create_3d_sketch(self.context, "Free3D")
        obj = sketch.target_object
        origin = obj.parent
        self.assertIsNotNone(origin, "free-3D sketch has no origin empty")
        sub = self._sketch_subcollection(obj)
        self.assertIsNotNone(sub)
        self.assertIn(
            origin.name, sub.objects, "free-3D origin should nest with its sketch"
        )
        self.assertNotIn(origin.name, self.context.scene.collection.objects)

    def test_origin_plane_is_not_stolen_into_a_sketch(self):
        from ..utilities.collections import nest_workplane
        from ..utilities.workplane import ensure_origin_workplane_empties

        ensure_origin_workplane_empties(self.context)
        origin = self._origin_collection()
        wp_xy = next(iter(origin.objects))
        nest_workplane(wp_xy, self.sketch.target_object)
        self.assertIn(wp_xy.name, origin.objects, "origin plane must stay in Origin")

    def test_cutter_nests_under_the_body_it_feeds(self):
        from ..operators.modifiers import apply_boolean, boolean_cutters
        from ..utilities.collections import organize_part_nesting

        body_obj = self.sketch.target_object
        cutter_obj = self.new_sketch().target_object
        body_coll = self._sketch_subcollection(body_obj)
        cutter_coll = self._sketch_subcollection(cutter_obj)
        scene_children = self.context.scene.collection.children
        self.assertIn(cutter_coll.name, scene_children)

        mod = apply_boolean(body_obj, cutter_obj)
        self.assertIsNotNone(mod, "boolean was refused (cycle?)")
        self.assertIn(cutter_obj, boolean_cutters(body_obj))

        organize_part_nesting(self.context.scene)
        self.assertIn(cutter_coll.name, body_coll.children, "cutter did not nest")
        self.assertNotIn(cutter_coll.name, scene_children)

        # Removing the boolean un-nests it back to the scene level.
        body_obj.modifiers.remove(mod)
        organize_part_nesting(self.context.scene)
        self.assertIn(cutter_coll.name, scene_children, "cutter did not un-nest")
        self.assertNotIn(cutter_coll.name, body_coll.children)

    def test_renaming_a_sketch_syncs_its_collection(self):
        from ..utilities.collections import sync_sketch_collection_names

        ob = self.sketch.target_object
        sub = self._sketch_subcollection(ob)
        ob.name = "Renamed Sketch"
        sync_sketch_collection_names(self.context.scene)
        self.assertEqual(sub.name, "Renamed Sketch", "collection did not follow rename")

        # Runs again with no change: no rename loop.
        prev = sub.name
        sync_sketch_collection_names(self.context.scene)
        self.assertEqual(sub.name, prev, "sync must be stable, not re-rename")

    def test_deleting_a_sketch_removes_its_empty_collection(self):
        from ..utilities.collections import cleanup_sketch_collections

        extra = self.new_sketch()
        sub = self._sketch_subcollection(extra.target_object)
        self.assertIsNotNone(sub)
        name = sub.name
        bpy.data.objects.remove(extra.target_object)
        cleanup_sketch_collections(self.context.scene)
        self.assertNotIn(name, {c.name for c in self.context.scene.collection.children})

    def test_origin_collection_is_linked_but_not_excluded(self):
        """The Origin collection must stay in the view layer (never excluded)."""
        from ..utilities.collections import origin_collection

        coll = origin_collection(self.context.scene)
        self.assertIn(coll.name, self.context.scene.collection.children)
        layer_coll = self.context.view_layer.layer_collection.children.get(coll.name)
        self.assertIsNotNone(layer_coll)
        self.assertFalse(layer_coll.exclude, "Origin collection must not be excluded")

    def test_fill_still_evaluates_from_the_collection(self):
        corners = [(-2, -2), (2, -2), (2, 2), (-2, 2)]
        pts = [self.add_point(c) for c in corners]
        for i in range(4):
            self.add_line(pts[i], pts[(i + 1) % 4])
        self.solve()
        refresh_curve_geometry(self.sketch)

        ob = self.sketch.target_object
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

    def test_origin_collection_is_idempotent_and_per_scene(self):
        from ..utilities.collections import origin_collection

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
