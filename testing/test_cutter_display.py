"""Tests for how a cutter is displayed, which says what it is doing.

A cutter that is cutting sits over its own result, so it is hidden. One that
cuts across parts, or currently cuts nothing, stays visible as a wireframe
because the user needs to find it.
"""

import bmesh
import bpy

from ..utilities.part import join_part, mark_part_root
from ..utilities.part import update_cutter_display as _update_cutter_display
from .utils import BgsTestCase


class TestCutterDisplay(BgsTestCase):
    def _cube(self, name):
        me = bpy.data.meshes.new(name)
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=2.0)
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(name, me)
        self.scene.collection.objects.link(ob)
        return ob

    def test_a_cutter_doing_its_job_is_hidden(self):
        body = self._cube("body")
        mark_part_root(body)
        cutter = self._cube("cutter")
        join_part(body, cutter)

        _update_cutter_display(cutter, [body], True)
        self.assertFalse(cutter.visible_get())
        # Never hide_viewport: that would drop it from evaluation, and the
        # boolean reads its evaluated geometry.
        self.assertFalse(cutter.hide_viewport)

    def test_a_cutter_spanning_parts_stays_visible_as_wire(self):
        body = self._cube("body")
        mark_part_root(body)
        other = self._cube("other")
        mark_part_root(other)
        cutter = self._cube("cutter")  # global: joined to no part

        _update_cutter_display(cutter, [body, other], True)
        self.assertTrue(cutter.visible_get())
        self.assertEqual(cutter.display_type, "WIRE")

    def test_a_cutter_that_reaches_nothing_reads_as_inert(self):
        cutter = self._cube("cutter")
        _update_cutter_display(cutter, [], True)
        self.assertTrue(cutter.visible_get())
        self.assertEqual(cutter.display_type, "WIRE")

    def test_a_solid_with_no_boolean_is_just_a_body(self):
        body = self._cube("solid")
        mark_part_root(body)
        _update_cutter_display(body, [], False)
        self.assertTrue(body.visible_get())
        self.assertEqual(body.display_type, "TEXTURED")

    def test_display_is_restored_when_a_cutter_stops_cutting(self):
        body = self._cube("body")
        mark_part_root(body)
        cutter = self._cube("cutter")
        join_part(body, cutter)

        _update_cutter_display(cutter, [body], True)
        self.assertFalse(cutter.visible_get())

        # The extrude no longer reaches the body.
        _update_cutter_display(cutter, [], True)
        self.assertTrue(cutter.visible_get())
        self.assertEqual(cutter.display_type, "WIRE")

        # And the boolean is switched off entirely.
        _update_cutter_display(cutter, [], False)
        self.assertEqual(cutter.display_type, "TEXTURED")

    def test_joining_a_part_hides_a_cutter_without_the_extrude_running(self):
        from ..operators.modifiers import apply_boolean
        from ..utilities.part import reconcile_parts

        body = self._cube("body")
        mark_part_root(body)
        cutter = self._cube("cutter")
        apply_boolean(body, cutter, "Difference")
        _update_cutter_display(cutter, [body], True)
        self.assertTrue(cutter.visible_get())  # global cutter: stays visible

        # The user parents it into the part (Ctrl+P / outliner drag).
        cutter.parent = body
        self.assertTrue(reconcile_parts(self.scene))
        self.assertFalse(cutter.visible_get())

    def test_a_plain_sketch_is_not_unhidden_by_the_reconcile(self):
        from ..utilities.part import reconcile_parts

        body = self._cube("body")
        mark_part_root(body)
        other = self._cube("not_a_cutter")
        other.hide_set(True)

        other.parent = body
        reconcile_parts(self.scene)
        # It feeds no body, so its display is none of our business.
        self.assertFalse(other.visible_get())
