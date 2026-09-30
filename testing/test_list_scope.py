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

    def test_a_part_lists_what_it_is_made_of(self):
        self._select(self.a)

        self.assertEqual(list_scope(self.context), (PART, self.a))
        shown = _Filter().shown(self.context)
        self.assertEqual(shown, {self.a.name, self.a_cut.name})

    def test_the_base_feature_leads_the_list(self):
        """Its name would otherwise file it wherever the alphabet puts it."""
        from ..ui.sketches_list import base_first

        self.a.name = "zzz_base"  # sorts last by name
        self._select(self.a)

        objects = list(self.scene.objects)
        order = base_first(objects, self.a)
        self.assertEqual(order[objects.index(self.a)], 0)
        self.assertEqual(sorted(order), list(range(len(objects))), "not a permutation")

    def test_a_feature_keeps_the_part_in_scope(self):
        """Clicking a cutter must not empty the list it was listed in."""
        self._select(self.a_cut)

        self.assertEqual(list_scope(self.context), (PART, self.a))
        self.assertEqual(_Filter().shown(self.context), {self.a.name, self.a_cut.name})

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

    def test_the_base_feature_has_a_row_of_its_own(self):
        """Its body is the part's root, and it is the first thing listed."""
        from ..utilities.body import sketch_of

        root, base, _feature, cutter = self._part_with_cut()

        bpy.ops.object.select_all(action="DESELECT")
        root.select_set(True)
        self.context.view_layer.objects.active = root

        shown = _Filter().shown(self.context)
        self.assertEqual(shown, {root.name, cutter.name})
        self.assertEqual(sketch_of(root), base.target_object, "the row's way in")


class TestHiddenPartStaysReachable(BgsTestCase):
    """Hiding a part must not hide the only control that brings it back."""

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

    def _part(self, name):
        root = self._cube(name)
        mark_part_root(root)
        member = self._cube(f"{name}_member", (1.0, 0.0, 0.0))
        join_part(root, member)
        sync_part_collections(self.scene)
        bpy.ops.object.select_all(action="DESELECT")
        root.select_set(True)
        self.context.view_layer.objects.active = root
        return root, member

    def test_hiding_a_part_keeps_it_in_scope(self):
        """Hiding deselects, so a selection-based scope would lose it here."""
        root, _member = self._part("hp")
        self.assertEqual(list_scope(self.context), (PART, root))

        bpy.ops.view3d.slvs_set_part_visibility(part_name=root.name)

        self.assertTrue(root.hide_get())
        self.assertEqual(list(self.context.selected_objects), [])
        self.assertEqual(
            list_scope(self.context), (PART, root), "the part fell out of the panel"
        )

    def test_it_can_be_shown_again(self):
        root, member = self._part("hp_back")
        bpy.ops.view3d.slvs_set_part_visibility(part_name=root.name)

        bpy.ops.view3d.slvs_set_part_visibility(part_name=root.name)

        self.assertFalse(root.hide_get())
        self.assertFalse(member.hide_get())

    def test_deselecting_does_not_empty_the_list(self):
        """The active object outlives a click beside the work."""
        root, member = self._part("hp_keep")
        bpy.ops.object.select_all(action="DESELECT")

        self.assertEqual(list_scope(self.context), (PART, root))
        self.assertEqual(_Filter().shown(self.context), {root.name, member.name})


class TestScopeSurvivesHiding(BgsTestCase):
    """Where the scope reads the active object from.

    ``context.active_object`` is context state and goes to None the moment the
    object is hidden; the view layer keeps the pointer. Reading the former left a
    hidden part showing as "All Parts", with the toggle that unhides it gone. A
    background run cannot reproduce that (there the two agree), so the rule is
    pinned against a stub instead.
    """

    class _Objects:
        def __init__(self, active):
            self.active = active

    class _ViewLayer:
        def __init__(self, active):
            self.objects = TestScopeSurvivesHiding._Objects(active)

    class _Context:
        """A context whose active object is hidden: visible to the view layer only."""

        def __init__(self, active):
            self.active_object = None
            self.view_layer = TestScopeSurvivesHiding._ViewLayer(active)

    def _cube(self, name):
        me = bpy.data.meshes.new(name)
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=2.0)
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(name, me)
        self.scene.collection.objects.link(ob)
        return ob

    def test_the_scope_is_read_from_the_view_layer(self):
        root = self._cube("sv_root")
        mark_part_root(root)

        self.assertEqual(list_scope(self._Context(root)), (PART, root))

    def test_an_assembly_survives_it_too(self):
        from ..utilities.part import create_assembly, join_assembly

        assembly = create_assembly(self.context, "sv_asm")
        part = self._cube("sv_part")
        mark_part_root(part)
        join_assembly(assembly, part)

        self.assertEqual(list_scope(self._Context(assembly)), (ASSEMBLY, assembly))

    def test_nothing_active_is_still_the_whole_file(self):
        self.assertEqual(list_scope(self._Context(None)), (GLOBAL, None))


class TestHeaderWithoutAList(BgsTestCase):
    """The part row carries the menu, so it outlives the list under it.

    Gating the row on the parts that exist left a file with none no way to make
    one: Make Part and Add Assembly live in that menu.
    """

    def test_an_empty_scene_has_no_rows_but_a_scope_to_draw(self):
        from ..ui.sketches_list import is_feature_row

        for obj in list(self.scene.objects):
            bpy.data.objects.remove(obj)

        self.assertFalse(any(is_feature_row(obj) for obj in self.scene.objects))
        # What the row renders from is still well defined, which is what lets it
        # draw with nothing under it.
        self.assertEqual(list_scope(self.context), (GLOBAL, None))

    def test_a_plain_mesh_has_no_rows_either(self):
        """Nothing here is ours yet, and the menu is how that changes."""
        from ..ui.sketches_list import is_feature_row

        me = bpy.data.meshes.new("hdr_plain")
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=2.0)
        bm.to_mesh(me)
        bm.free()
        plain = bpy.data.objects.new("hdr_plain", me)
        self.scene.collection.objects.link(plain)
        self.context.view_layer.objects.active = plain

        self.assertFalse(is_feature_row(plain))
        self.assertEqual(list_scope(self.context), (GLOBAL, None))
        self.assertTrue(bpy.types.VIEW3D_MT_slvs_part.poll(self.context))
