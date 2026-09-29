"""What the list shows: one part's features, an assembly's parts, or the file.

A part owns the list, so it is drawn above it rather than as a row: its delete
takes the whole part, which has no business sitting in the same column as a
feature's.
"""

import bmesh
import bpy

from ..ui.sketches_list import (
    ASSEMBLY,
    GLOBAL,
    PART,
    VIEW3D_UL_sketches,
    list_scope,
)
from ..utilities.collections import sync_part_collections
from ..utilities.part import create_assembly, join_assembly, join_part, mark_part_root
from .utils import BgsTestCase


class _Filter:
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


class TestListScope(BgsTestCase):
    def setUp(self):
        super().setUp()
        self.a = self._cube("sc_a")
        mark_part_root(self.a)
        self.a_cut = self._cube("sc_a_cut", (0.9, 0.0, 0.0))
        join_part(self.a, self.a_cut)

        self.b = self._cube("sc_b", (5.0, 0.0, 0.0))
        mark_part_root(self.b)

        self.assembly = create_assembly(self.context, "sc_asm")
        join_assembly(self.assembly, self.a)
        join_assembly(self.assembly, self.b)
        sync_part_collections(self.scene)

    def _cube(self, name, location=(0.0, 0.0, 0.0)):
        me = bpy.data.meshes.new(name)
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=2.0)
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(name, me)
        self.scene.collection.objects.link(ob)
        ob.location = location
        return ob

    def _select(self, obj):
        bpy.ops.object.select_all(action="DESELECT")
        if obj is not None:
            obj.select_set(True)
        self.context.view_layer.objects.active = obj

    def test_a_part_lists_its_features_and_not_itself(self):
        self._select(self.a)

        self.assertEqual(list_scope(self.context), (PART, self.a))
        shown = _Filter().shown(self.context)
        self.assertEqual(shown, {self.a_cut.name})

    def test_a_feature_keeps_the_part_in_scope(self):
        """Clicking a cutter must not empty the list it was listed in."""
        self._select(self.a_cut)

        self.assertEqual(list_scope(self.context), (PART, self.a))
        self.assertEqual(_Filter().shown(self.context), {self.a_cut.name})

    def test_an_assembly_lists_its_parts(self):
        self._select(self.assembly)

        self.assertEqual(list_scope(self.context), (ASSEMBLY, self.assembly))
        shown = _Filter().shown(self.context)
        self.assertEqual(shown, {self.a.name, self.b.name})
        self.assertNotIn(self.a_cut.name, shown, "a part's insides stay inside")

    def test_nothing_selected_lists_every_part(self):
        # A sketch drawn but not yet made solid belongs to no part, and has to
        # stay reachable. (A plain cube is not ours and never gets a row.)
        from ..model.sketch_ref import stamp_sketch_props

        loose = bpy.data.objects.new("sc_loose", bpy.data.hair_curves.new("sc_loose"))
        self.scene.collection.objects.link(loose)
        stamp_sketch_props(loose)
        self._select(None)

        scope, root = list_scope(self.context)
        self.assertEqual((scope, root), (GLOBAL, None))
        shown = _Filter().shown(self.context)
        self.assertIn(self.a.name, shown)
        self.assertIn(self.b.name, shown)
        self.assertNotIn(self.a_cut.name, shown, "features belong to their part")
        self.assertIn(loose.name, shown, "a sketch in no part is still reachable")


class TestPartVisibility(BgsTestCase):
    def _cube(self, name, location=(0.0, 0.0, 0.0)):
        me = bpy.data.meshes.new(name)
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=2.0)
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(name, me)
        self.scene.collection.objects.link(ob)
        ob.location = location
        return ob

    def test_hiding_a_part_hides_what_is_in_it(self):
        """Blender does not cascade visibility, so the members go one by one."""
        root = self._cube("pv_root")
        mark_part_root(root)
        member = self._cube("pv_member", (1.0, 0.0, 0.0))
        join_part(root, member)
        sync_part_collections(self.scene)

        self.assertEqual(
            bpy.ops.view3d.slvs_set_part_visibility(part_name=root.name), {"FINISHED"}
        )
        self.assertTrue(root.hide_get())
        self.assertTrue(member.hide_get(), "the feature was left floating")

        bpy.ops.view3d.slvs_set_part_visibility(part_name=root.name)
        self.assertFalse(root.hide_get())
        self.assertFalse(member.hide_get())

    def test_it_leaves_the_cutter_flag_alone(self):
        """hide_viewport belongs to the display rules; the part uses the eye."""
        root = self._cube("pv_cut_root")
        mark_part_root(root)
        cutter = self._cube("pv_cutter", (0.9, 0.0, 0.0))
        join_part(root, cutter)
        cutter.hide_viewport = True

        bpy.ops.view3d.slvs_set_part_visibility(part_name=root.name)

        self.assertTrue(cutter.hide_viewport, "the display rules were overwritten")


class TestLeavingASketch(BgsTestCase):
    """What stays selected, and so which part the sidebar then shows."""

    def setUp(self):
        super().setUp()
        from ..utilities.workplane import ensure_origin_workplane_empties

        ensure_origin_workplane_empties(self.context)
        self.datum = self.context.scene.sketcher.wp_xy

    def _part_with_cut(self):
        from ..operators.add_sketch import build_sketch_on_workplane
        from ..operators.modifiers import apply_boolean
        from ..utilities.body import body_of
        from ..utilities.part import (
            promote_to_root,
            settle_membership,
            update_cutter_display,
        )

        base = build_sketch_on_workplane(self.context, self.datum)
        root = body_of(base.target_object)
        promote_to_root(root)
        mark_part_root(root)

        feature = build_sketch_on_workplane(self.context, self.datum)
        cutter = body_of(feature.target_object)
        settle_membership(feature.target_object, [root], self.context)
        apply_boolean(root, cutter, "Difference")
        update_cutter_display(cutter, [root], True)
        return root, base, feature, cutter

    def test_a_hidden_cutter_cannot_be_selected(self):
        """The reason the part has to stand in for it."""
        _root, _base, _feature, cutter = self._part_with_cut()

        bpy.ops.object.select_all(action="DESELECT")
        cutter.select_set(True)

        self.assertTrue(cutter.hide_viewport)
        self.assertEqual(list(self.context.selected_objects), [])

    def test_leaving_a_cut_selects_its_part(self):
        from ..operators.utilities import select_result_ob

        root, _base, feature, _cutter = self._part_with_cut()

        select_result_ob(self.context, feature)

        self.assertEqual([o.name for o in self.context.selected_objects], [root.name])
        self.assertEqual(list_scope(self.context), (PART, root))

    def test_leaving_the_base_sketch_selects_the_part_itself(self):
        from ..operators.utilities import select_result_ob

        root, base, _feature, _cutter = self._part_with_cut()

        select_result_ob(self.context, base)

        self.assertEqual([o.name for o in self.context.selected_objects], [root.name])
        self.assertEqual(list_scope(self.context), (PART, root))

    def test_the_base_sketch_is_reachable_though_it_has_no_row(self):
        """It is drawn in the header instead: its body is the part."""
        from ..utilities.body import sketch_of

        root, base, _feature, cutter = self._part_with_cut()

        bpy.ops.object.select_all(action="DESELECT")
        root.select_set(True)
        self.context.view_layer.objects.active = root

        shown = _Filter().shown(self.context)
        self.assertEqual(shown, {cutter.name})
        self.assertNotIn(base.target_object.name, shown)
        self.assertEqual(sketch_of(root), base.target_object, "the header's way in")
