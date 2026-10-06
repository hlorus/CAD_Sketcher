"""Which sketches can be picked as a reference, and why.

A sketch's curves are a hidden object: the add-on draws them itself so they do
not double up on the body's mesh. Asking Blender whether they are visible said
no to every sketch, so a plainly visible, greyed sketch could not be snapped to
or projected from.
"""

import bpy

from ..drawing.reference_pick import is_reference_source
from ..operators.add_sketch import build_sketch_on_workplane
from ..utilities.workplane import ensure_origin_workplane_empties
from .utils import BgsTestCase


class TestReferenceSource(BgsTestCase):
    def setUp(self):
        super().setUp()
        ensure_origin_workplane_empties(self.context)
        self.sk = self.context.scene.sketcher

    def test_a_drawn_coplanar_sketch_is_offered(self):
        """The reported bug: visible on screen, but not pickable."""
        active = build_sketch_on_workplane(self.context, self.sk.wp_xy)
        other = build_sketch_on_workplane(self.context, self.sk.wp_xy)
        ob = other.target_object

        # As created: hidden to Blender, drawn by the overlay.
        self.assertTrue(ob.hide_viewport)
        self.assertNotIn(ob, list(self.context.visible_objects))
        self.assertTrue(other.is_visible(self.context))

        self.assertTrue(is_reference_source(ob, self.context, active))

    def test_a_sketch_the_user_hid_is_not_offered(self):
        active = build_sketch_on_workplane(self.context, self.sk.wp_xy)
        other = build_sketch_on_workplane(self.context, self.sk.wp_xy)
        ob = other.target_object
        ob.hide_set(True)

        self.assertFalse(other.is_visible(self.context), "the eye hides it")
        self.assertFalse(is_reference_source(ob, self.context, active))
        ob.hide_set(False)

    def test_another_plane_is_not_offered_until_it_is_shown(self):
        """Referencing means coplanar; showing a sketch's curves widens it."""
        active = build_sketch_on_workplane(self.context, self.sk.wp_xy)
        other = build_sketch_on_workplane(self.context, self.sk.wp_xz)
        ob = other.target_object
        self.assertFalse(is_reference_source(ob, self.context, active))

        bpy.ops.view3d.slvs_set_sketch_visibility(sketch_name=ob.name)
        self.assertFalse(ob.hide_viewport)
        self.assertTrue(
            is_reference_source(ob, self.context, active),
            "an explicitly shown sketch is offered from any plane",
        )

    def test_a_raw_curves_object_still_follows_blender(self):
        """Only sketches are hidden by us; everything else keeps Blender's rule."""
        active = build_sketch_on_workplane(self.context, self.sk.wp_xy)
        raw = bpy.data.objects.new("rs_raw", bpy.data.hair_curves.new("rs_raw"))
        self.scene.collection.objects.link(raw)
        self.context.view_layer.update()
        self.assertTrue(is_reference_source(raw, self.context, active))
        raw.hide_set(True)
        self.assertFalse(is_reference_source(raw, self.context, active))
