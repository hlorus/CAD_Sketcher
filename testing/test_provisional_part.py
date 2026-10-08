"""A sketch is a part from the first stroke, and quiet until it is solid.

Drawing a sketch used to leave a body that was not a part: the part only
appeared later, by hand. It is one now, so Delete Part, Make Instance and the
part row apply to it without a promotion step. What waits is the machinery, not
the part: no base planes standing in for the world's, no collection of its own,
until something solid stands on it.
"""

import bmesh
import bpy

from ..operators.add_sketch import build_sketch_on_workplane
from ..utilities.body import body_of
from ..utilities.collections import part_collection, sync_part_collections
from ..utilities.extrude_nodes import EXTRUDE_NODE_GROUP
from ..utilities.part import (
    PART_PLANE_KEY,
    existing_part_plane,
    is_part_root,
    is_provisional_part,
    reconcile_groups,
    settle_membership,
)
from ..utilities.workplane import ensure_origin_workplane_empties, iter_wp_empties
from .utils import BgsTestCase


class TestProvisionalPart(BgsTestCase):
    def setUp(self):
        super().setUp()
        self.entities.ensure_origin_elements(self.context)
        ensure_origin_workplane_empties(self.context)
        self.datum = self.context.scene.sketcher.wp_xy

    def _sketch(self):
        sketch = build_sketch_on_workplane(self.context, self.datum)
        return sketch, body_of(sketch.target_object)

    def _cube(self, name="cube"):
        me = bpy.data.meshes.new(name)
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=2.0)
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(name, me)
        self.scene.collection.objects.link(ob)
        return ob

    def _make_solid(self, body):
        """What extruding leaves behind: the modifier the reconcile pass reads."""
        group = bpy.data.node_groups.get(
            EXTRUDE_NODE_GROUP
        ) or bpy.data.node_groups.new(EXTRUDE_NODE_GROUP, "GeometryNodeTree")
        mod = body.modifiers.new(name="Extrude", type="NODES")
        mod.node_group = group

    def _focus(self, obj):
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        self.context.view_layer.objects.active = obj
        self.context.view_layer.update()

    def test_a_drawn_sketch_is_a_part(self):
        _sketch, body = self._sketch()
        self.assertTrue(is_part_root(body))
        self.assertTrue(is_provisional_part(body))

    def test_it_offers_no_base_planes_while_provisional(self):
        # The one that matters: these stand in for the world's planes, so a part
        # that is still only a sketch must not take them away.
        sketch, body = self._sketch()
        self._focus(body)

        offered = [plane for plane, _id in iter_wp_empties(self.context)]
        self.assertIsNone(existing_part_plane(body, "XY"))
        self.assertIn(self.datum, offered, "the world planes are still there")
        self.assertIn(
            sketch.target_object.slvs_workplane,
            offered,
            "and so is the plane the sketch sits on",
        )

    def test_it_gets_no_collection_while_provisional(self):
        _sketch, body = self._sketch()
        sync_part_collections(self.scene)
        self.assertIn(body.name, self.scene.collection.objects)

    def test_becoming_solid_realises_it(self):
        sketch, body = self._sketch()
        plane = sketch.target_object.slvs_workplane

        self._make_solid(body)
        reconcile_groups(self.scene)

        self.assertFalse(is_provisional_part(body))
        # The plane it was drawn on becomes the part's XY, not a second plane.
        self.assertEqual(existing_part_plane(body, "XY"), plane)
        self.assertEqual(plane.get(PART_PLANE_KEY), "XY")
        sync_part_collections(self.scene)
        self.assertIn(body.name, part_collection(body, self.scene).objects)

    def test_realising_is_one_way(self):
        _sketch, body = self._sketch()
        self._make_solid(body)
        reconcile_groups(self.scene)

        body.modifiers.remove(body.modifiers[-1])
        reconcile_groups(self.scene)
        self.assertFalse(is_provisional_part(body), "a part stays a part")

    def test_make_part_realises_it_by_hand(self):
        _sketch, body = self._sketch()
        self._focus(body)

        bpy.ops.view3d.slvs_make_part()

        self.assertFalse(is_provisional_part(body))
        for axis in ("XY", "XZ", "YZ"):
            self.assertIsNotNone(existing_part_plane(body, axis), axis)

    def test_a_provisional_part_gives_way_to_what_it_cuts(self):
        # Its own part was never asked for, so the body it cuts claims it.
        cube = self._cube("target")
        sketch, body = self._sketch()

        root = settle_membership(sketch.target_object, [cube], self.context)

        self.assertEqual(root, cube)
        self.assertFalse(is_part_root(body))

    def test_a_part_the_user_asked_for_does_not_give_way(self):
        cube = self._cube("target")
        _sketch, body = self._sketch()
        self._focus(body)
        bpy.ops.view3d.slvs_make_part()

        root = settle_membership(body, [cube], self.context)

        self.assertEqual(root, body, "a part in full keeps itself")

    def test_a_cut_across_two_parts_is_no_part_at_all(self):
        first, second = self._cube("a"), self._cube("b")
        for cube in (first, second):
            self._focus(cube)
            bpy.ops.view3d.slvs_make_part()
        sketch, body = self._sketch()

        self.assertIsNone(settle_membership(sketch.target_object, [first, second]))
        self.assertFalse(is_part_root(body), "an assembly-level feature, not a part")
