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
        # hide_viewport, not the eye: the eye is view-layer state, so an
        # instanced copy of the part would still draw the cutter over its result.
        self.assertTrue(cutter.hide_viewport)

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
        self.assertFalse(cutter.hide_viewport)
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

    def test_the_boolean_tool_settles_membership_for_a_sketch_cutter(self):
        # The standalone Boolean tool follows the same rule as extrude: only a
        # sketch cutter joins, so a mesh body with its own history stays a part.
        from ..model.sketch_ref import stamp_sketch_props
        from ..utilities.part import part_root_of, settle_membership

        body = self._cube("body")
        mark_part_root(body)

        curve = bpy.data.hair_curves.new("cutter_sketch")
        cutter = bpy.data.objects.new("cutter_sketch", curve)
        self.scene.collection.objects.link(cutter)
        stamp_sketch_props(cutter)

        settle_membership(cutter, [body])
        self.assertEqual(part_root_of(cutter), body)

        mesh_cutter = self._cube("mesh_cutter")
        mark_part_root(mesh_cutter)
        settle_membership(mesh_cutter, [body])
        # Already a part of its own: left alone.
        self.assertEqual(part_root_of(mesh_cutter), mesh_cutter)

    def test_a_solid_reaching_nothing_is_not_a_cut(self):
        # Extruding in empty space used to default to Difference, because the
        # operation was chosen before anything was detected.
        from ..operators import modifiers
        from ..utilities import boolean_targets

        class _Tool(modifiers.BooleanFromToolMixin):
            operation = "Difference"
            boolean_detected = False
            offset = 1.0

            def __init__(self, cutter):
                self._obj = cutter
                self.boolean_targets = []

            def resolved_object(self):
                return self._obj

        cutter = self._cube("lonely")
        tool = _Tool(cutter)

        detect = boolean_targets.detect_targets
        boolean_targets.detect_targets = lambda *a, **k: []
        try:
            tool.finish_booleans(self.context)
        finally:
            boolean_targets.detect_targets = detect

        self.assertEqual(tool.operation, "None")
        # Undecided, not decided-as-None: a longer extrude can still auto-boolean.
        self.assertFalse(tool.boolean_detected)
        self.assertTrue(cutter.visible_get())
        self.assertEqual(cutter.display_type, "TEXTURED")
