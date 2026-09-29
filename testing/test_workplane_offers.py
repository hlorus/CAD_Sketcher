"""Which workplanes the Add Sketch tool offers, and which it keeps out of the way.

Every sketch drawn on a face makes a workplane of its own, so a part used to
offer one more rectangle per feature on top of its three base planes. A part is
sketched on through those base planes and its faces; its features' planes are
its own business.
"""

import bmesh
import bpy

from ..operators.add_sketch import build_sketch_on_workplane, create_face_workplane
from ..utilities.part import (
    PART_PLANE_KEY,
    ensure_part_planes,
    mark_part_root,
    settle_membership,
)
from ..utilities.workplane import (
    ensure_origin_workplane_empties,
    is_managed_workplane,
    iter_wp_empties,
)
from .utils import BgsTestCase


class TestWorkplaneOffers(BgsTestCase):
    def setUp(self):
        super().setUp()
        ensure_origin_workplane_empties(self.context)
        self.scene.sketcher.show_origin = True

    def _cube(self, name):
        me = bpy.data.meshes.new(name)
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=2.0)
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(name, me)
        self.scene.collection.objects.link(ob)
        self.context.view_layer.update()
        return ob

    def _offered(self):
        return [obj for obj, _pick in iter_wp_empties(self.context)]

    def _part_with_face_sketches(self, name, count=3):
        root = self._cube(name)
        mark_part_root(root)
        ensure_part_planes(self.context, root)
        planes = []
        for face in range(count):
            plane = create_face_workplane(self.context, root, face)
            sketch = build_sketch_on_workplane(self.context, plane)
            settle_membership(sketch.target_object, [root], self.context)
            planes.append(plane)
        return root, planes

    def _focus(self, obj):
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        self.context.view_layer.objects.active = obj

    def test_a_part_offers_its_base_planes_and_nothing_else(self):
        root, planes = self._part_with_face_sketches("wo_part")
        self._focus(root)

        offered = self._offered()
        self.assertEqual(len(offered), 3, [o.name for o in offered])
        self.assertTrue(all(PART_PLANE_KEY in o for o in offered))
        for plane in planes:
            self.assertNotIn(plane, offered, "a feature's plane is not a sketch target")

    def test_the_count_does_not_grow_with_the_features(self):
        """The complaint: six rectangles for three sketches, and climbing."""
        root, _planes = self._part_with_face_sketches("wo_grow", count=1)
        self._focus(root)
        before = len(self._offered())

        for face in (1, 2, 3):
            plane = create_face_workplane(self.context, root, face)
            sketch = build_sketch_on_workplane(self.context, plane)
            settle_membership(sketch.target_object, [root], self.context)

        self.assertEqual(len(self._offered()), before)

    def test_a_plane_outside_any_part_is_still_offered(self):
        """A workplane belonging to no part stays available, wherever it is."""
        from mathutils import Matrix

        from ..operators.add_sketch import new_workplane_empty

        plane = new_workplane_empty(self.context, Matrix.Translation((0.0, 0.0, 3.0)))

        bpy.ops.object.select_all(action="DESELECT")
        self.context.view_layer.objects.active = None

        offered = self._offered()
        self.assertIn(plane, offered)
        self.assertTrue(is_managed_workplane(plane))

    def test_sketching_on_a_face_puts_the_body_in_a_part(self):
        """Why "not in a part" is rarer than it sounds: drawing on one creates it."""
        from ..utilities.part import part_root_of

        body = self._cube("wo_becomes")
        plane = create_face_workplane(self.context, body, 0)
        self.assertIsNone(part_root_of(plane), "not yet: nothing has been drawn")
        self.assertIn(plane, self._offered())

        build_sketch_on_workplane(self.context, plane)

        self.assertEqual(part_root_of(plane), body)
        self.assertNotIn(plane, self._offered())

    def test_another_parts_planes_stay_out_of_the_way(self):
        first, _ = self._part_with_face_sketches("wo_first", count=1)
        second, second_planes = self._part_with_face_sketches("wo_second", count=1)
        self._focus(first)

        # Asked relatively: this class shares one scene, so earlier tests leave
        # their own (part-less, and rightly offered) planes behind.
        offered = self._offered()
        for plane in second_planes:
            self.assertNotIn(plane, offered)
        base = [o for o in offered if o.get(PART_PLANE_KEY)]
        self.assertEqual(len(base), 3, [o.name for o in base])
        self.assertTrue(all(o.parent == first for o in base))
