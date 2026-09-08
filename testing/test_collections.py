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

    def test_sketch_object_lands_in_managed_collection(self):
        ob = self.sketch.target_object
        coll = self._cad_collection()
        self.assertIsNotNone(coll, "CAD Sketcher collection was not created")
        self.assertEqual(coll.name.split(".")[0], CAD_COLLECTION_NAME)
        self.assertIn(ob.name, coll.objects, "sketch object not in the collection")
        self.assertNotIn(
            ob.name,
            self.context.scene.collection.objects,
            "sketch object should not stay in the scene master collection",
        )

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
