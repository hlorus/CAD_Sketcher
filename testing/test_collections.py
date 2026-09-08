"""CAD Sketcher objects live in a managed, still-evaluating collection.

Guards P1: sketch curve objects and workplane empties go into a per-scene
"CAD Sketcher" collection instead of the scene master collection, and that
collection is never excluded -- excluding it would drop the fill (the curve
object is both source and consumable).
"""

import bpy

from ..utilities.collections import CAD_COLLECTION_NAME, ensure_cad_collection
from ..utilities.curve_data import refresh_curve_geometry
from .utils import Sketch2dTestCase


class TestManagedCollection(Sketch2dTestCase):
    def _cad_collection(self):
        for child in self.context.scene.collection.children:
            if child.get("is_cad_sketcher"):
                return child
        return None

    def _sketch_subcollection(self, ob):
        for coll in ob.users_collection:
            if coll.get("cad_sketch_collection"):
                return coll
        return None

    def test_sketch_object_lands_in_its_own_subcollection(self):
        ob = self.sketch.target_object
        root = self._cad_collection()
        self.assertIsNotNone(root, "CAD Sketcher collection was not created")
        self.assertEqual(root.name.split(".")[0], CAD_COLLECTION_NAME)

        sub = self._sketch_subcollection(ob)
        self.assertIsNotNone(sub, "sketch object not in a per-sketch sub-collection")
        self.assertIn(sub.name, root.children, "sub-collection not under the CAD root")
        self.assertNotIn(
            ob.name,
            self.context.scene.collection.objects,
            "sketch object should not stay in the scene master collection",
        )

    def test_each_sketch_gets_a_distinct_subcollection(self):
        first = self._sketch_subcollection(self.sketch.target_object)
        second_sketch = self.new_sketch()
        second = self._sketch_subcollection(second_sketch.target_object)
        self.assertIsNotNone(second)
        self.assertIsNot(first, second, "two sketches must not share a sub-collection")

    def test_origin_planes_go_in_the_origin_collection(self):
        from ..utilities.workplane import ensure_origin_workplane_empties

        ensure_origin_workplane_empties(self.context)
        root = self._cad_collection()
        origin = next(
            (c for c in root.children if c.get("cad_origin_collection")), None
        )
        self.assertIsNotNone(origin, "Origin sub-collection not created")
        self.assertGreaterEqual(
            len(origin.objects), 3, "the three origin planes should be grouped here"
        )
        # And not scattered in the CAD root or the scene master.
        for ob in origin.objects:
            self.assertNotIn(ob.name, root.objects)
            self.assertNotIn(ob.name, self.context.scene.collection.objects)

    def test_dedicated_workplane_nests_with_its_sketch(self):
        from ..utilities.collections import link_object, nest_workplane

        ob = self.sketch.target_object
        sub = self._sketch_subcollection(ob)
        root = self._cad_collection()

        wp = bpy.data.objects.new("Workplane", None)
        link_object(wp, self.context.scene)  # a face workplane starts at the root
        self.assertIn(wp.name, root.objects)

        ob.parent = wp
        nest_workplane(wp, ob)
        try:
            self.assertIn(wp.name, sub.objects, "workplane should nest with its sketch")
            self.assertNotIn(wp.name, root.objects, "and leave the root")
        finally:
            bpy.data.objects.remove(wp)

    def test_origin_plane_is_not_stolen_into_a_sketch(self):
        from ..utilities.collections import nest_workplane
        from ..utilities.workplane import ensure_origin_workplane_empties

        ensure_origin_workplane_empties(self.context)
        origin = next(
            c for c in self._cad_collection().children if c.get("cad_origin_collection")
        )
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
        root = self._cad_collection()
        self.assertIn(cutter_coll.name, root.children)

        mod = apply_boolean(body_obj, cutter_obj)
        self.assertIsNotNone(mod, "boolean was refused (cycle?)")
        self.assertIn(cutter_obj, boolean_cutters(body_obj))

        organize_part_nesting(self.context.scene)
        self.assertIn(cutter_coll.name, body_coll.children, "cutter did not nest")
        self.assertNotIn(cutter_coll.name, root.children)

        # Removing the boolean un-nests it back to the root.
        body_obj.modifiers.remove(mod)
        organize_part_nesting(self.context.scene)
        self.assertIn(cutter_coll.name, root.children, "cutter did not un-nest")
        self.assertNotIn(cutter_coll.name, body_coll.children)

    def test_deleting_a_sketch_removes_its_empty_collection(self):
        from ..utilities.collections import cleanup_sketch_collections

        extra = self.new_sketch()
        sub = self._sketch_subcollection(extra.target_object)
        self.assertIsNotNone(sub)
        name = sub.name
        bpy.data.objects.remove(extra.target_object)
        cleanup_sketch_collections(self.context.scene)
        self.assertNotIn(name, {c.name for c in self._cad_collection().children})

    def test_collection_is_linked_but_not_excluded(self):
        """The collection must stay in the view layer so its objects evaluate."""
        coll = self._cad_collection()
        self.assertIn(coll.name, self.context.scene.collection.children)
        layer_coll = self.context.view_layer.layer_collection.children.get(coll.name)
        self.assertIsNotNone(layer_coll)
        self.assertFalse(layer_coll.exclude, "managed collection must not be excluded")

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

    def test_ensure_collection_is_idempotent_and_per_scene(self):
        scene = self.context.scene
        a = ensure_cad_collection(scene)
        b = ensure_cad_collection(scene)
        self.assertIs(a, b, "ensure_cad_collection must reuse the scene's collection")

        other = bpy.data.scenes.new("other_scene")
        try:
            c = ensure_cad_collection(other)
            self.assertIsNot(c, a, "each scene must own its own collection")
        finally:
            bpy.data.scenes.remove(other)
