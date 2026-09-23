"""The sketch list: what it shows now that sketches belong to parts.

It is the only way to reach a cutter, which is hidden from the viewport while it
is cutting, so it stays. What changed is scope: with a part in focus it lists
that part's sketches rather than every sketch in the file.
"""

import bmesh
import bpy

from ..operators.modifiers import apply_boolean
from ..ui.sketches_list import VIEW3D_UL_sketches, _cutting_sketches
from ..utilities.part import join_part, mark_part_root
from .utils import Sketch2dTestCase


class _Filter:
    """Stands in for the UIList while filtering.

    Blender only builds a real UIList to draw one, and refuses to construct a
    bpy_struct subclass from Python, so the method is called unbound against a
    plain object carrying the two attributes it reads.
    """

    filter_name = ""
    bitflag_filter_item = 1 << 30

    def shown(self, context):
        flags, _order = VIEW3D_UL_sketches.filter_items(
            self, context, context.scene, "objects"
        )
        return {
            obj.name
            for obj, flag in zip(context.scene.objects, flags)
            if flag & self.bitflag_filter_item
        }


class TestSketchList(Sketch2dTestCase):
    def _cube(self, name):
        me = bpy.data.meshes.new(name)
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=2.0)
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(name, me)
        self.scene.collection.objects.link(ob)
        return ob

    def test_every_sketch_is_listed_when_no_part_is_in_focus(self):
        bpy.ops.object.select_all(action="DESELECT")
        self.context.view_layer.objects.active = None

        shown = _Filter().shown(self.context)
        self.assertIn(self.sketch.target_object.name, shown)

    def test_the_list_narrows_to_the_part_in_focus(self):
        mine = self.sketch.target_object
        other = self.new_sketch().target_object

        body = self._cube("host")
        mark_part_root(body)
        join_part(body, mine)

        bpy.ops.object.select_all(action="DESELECT")
        body.select_set(True)
        self.context.view_layer.objects.active = body

        shown = _Filter().shown(self.context)
        self.assertIn(mine.name, shown)
        self.assertNotIn(other.name, shown, "a sketch of another part is not listed")

    def test_a_cutting_sketch_is_recognised(self):
        # Its row shows that it is cutting rather than an eye toggle: the hide is
        # the display rule's, not the user's to hand back.
        body = self._cube("body")
        cutter = self.sketch.target_object
        apply_boolean(body, cutter, "Difference")

        self.assertIn(cutter.name, _cutting_sketches(self.scene))

    def test_a_plain_sketch_is_not_marked_as_cutting(self):
        self.assertNotIn(self.sketch.target_object.name, _cutting_sketches(self.scene))


class TestPartSketchesMenu(Sketch2dTestCase):
    """What "Edit Sketch" reaches when a part holds more than one sketch."""

    def _cube(self, name):
        me = bpy.data.meshes.new(name)
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=2.0)
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(name, me)
        self.scene.collection.objects.link(ob)
        return ob

    def test_a_parts_sketches_are_listed_body_first(self):
        from ..ui.panels.sketch_select import part_sketches

        body = self.sketch.target_object
        mark_part_root(body)
        cutter = self.new_sketch().target_object
        cutter.name = "aaa_cutter"  # sorts before the body by name
        join_part(body, cutter)

        listed = part_sketches(self.context, body)
        self.assertEqual([o.name for o in listed], [body.name, cutter.name])

    def test_a_hidden_cutter_is_still_reachable(self):
        # It cannot be clicked in the viewport while it cuts, so the menu is the
        # only way in.
        from ..ui.panels.sketch_select import part_sketches
        from ..utilities.part import update_cutter_display

        body = self.sketch.target_object
        mark_part_root(body)
        cutter = self.new_sketch().target_object
        join_part(body, cutter)
        apply_boolean(body, cutter, "Difference")
        update_cutter_display(cutter, [body], True)

        self.assertFalse(cutter.visible_get())
        self.assertIn(cutter, part_sketches(self.context, body))

    def test_sketches_of_other_parts_are_not_listed(self):
        from ..ui.panels.sketch_select import part_sketches

        body = self.sketch.target_object
        mark_part_root(body)
        other_body = self._cube("other")
        mark_part_root(other_body)
        other_sketch = self.new_sketch().target_object
        join_part(other_body, other_sketch)

        listed = part_sketches(self.context, body)
        self.assertNotIn(other_sketch, listed)


class TestListAfterTheSplit(Sketch2dTestCase):
    """What the list and the Edit Sketch menu say now that a body is the root."""

    def setUp(self):
        super().setUp()
        from ..utilities.workplane import ensure_origin_workplane_empties

        ensure_origin_workplane_empties(self.context)
        self.datum = self.context.scene.sketcher.wp_xy

    def test_the_roots_own_sketch_leads_the_menu(self):
        # It used to lead by being the root; a mesh root never is one.
        from ..operators.add_sketch import build_sketch_on_workplane
        from ..ui.panels.sketch_select import part_sketches
        from ..utilities.body import body_of
        from ..utilities.part import mark_part_root, settle_membership

        first = build_sketch_on_workplane(self.context, self.datum)
        root = body_of(first.target_object)
        mark_part_root(root)
        second = build_sketch_on_workplane(self.context, self.datum)
        settle_membership(second.target_object, [root], self.context)
        # Name it so plain name order would not put it first.
        first.target_object.name = "zzz last by name"

        listed = part_sketches(self.context, root)
        self.assertEqual(listed[0], first.target_object)
        self.assertIn(second.target_object, listed)

    def test_the_eye_toggles_the_body_not_the_source(self):
        # The curves are always out of the viewport now; what stands for the
        # sketch on screen is its body.
        from ..operators.add_sketch import build_sketch_on_workplane
        from ..operators.set_sketch import visibility_target
        from ..utilities.body import body_of

        sketch = build_sketch_on_workplane(self.context, self.datum)
        obj = sketch.target_object
        body = body_of(obj)

        self.assertEqual(visibility_target(obj), body)
        self.assertTrue(obj.hide_viewport, "the source stays hidden")

        bpy.ops.view3d.slvs_set_sketch_visibility(sketch_name=obj.name)
        self.assertTrue(body.hide_viewport)
        bpy.ops.view3d.slvs_set_sketch_visibility(sketch_name=obj.name)
        self.assertFalse(body.hide_viewport)
        self.assertTrue(obj.hide_viewport)

    def test_a_sketch_with_no_body_still_answers_for_itself(self):
        from ..operators.set_sketch import visibility_target

        obj = self.sketch.target_object  # created through the model, no body
        obj.slvs_body = None

        self.assertEqual(visibility_target(obj), obj)
