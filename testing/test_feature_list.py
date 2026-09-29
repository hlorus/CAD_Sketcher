"""The list keyed on bodies, and the cutter visibility override it exposes.

Rows used to be sketches, which left a feature with no sketch unlistable and the
cutter's own solid with no control anywhere. Rows are bodies now; the sketch
hangs off the row.
"""

import bmesh
import bpy

from ..operators.modifiers import apply_boolean
from ..ui.sketches_list import (
    VIEW3D_UL_sketches,
    cutting_bodies,
    is_feature_row,
    row_parts,
)
from ..utilities.part import (
    SHOW_CUTTER_KEY,
    join_part,
    mark_part_root,
    update_cutter_display,
)
from .utils import BgsTestCase


class _Filter:
    """Stands in for the UIList while filtering (see test_sketch_list)."""

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


class TestFeatureRows(BgsTestCase):
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

    def _part_with_feature(self):
        from ..operators.add_sketch import (
            build_sketch_on_workplane,
            create_face_workplane,
        )
        from ..utilities.body import body_of
        from ..utilities.part import settle_membership

        root = self._cube("fl_root")
        mark_part_root(root)
        plane = create_face_workplane(self.context, root, 0)
        sketch = build_sketch_on_workplane(self.context, plane)
        body = body_of(sketch.target_object)
        settle_membership(sketch.target_object, [root], self.context)
        apply_boolean(root, body, "Difference")
        update_cutter_display(body, [root], True)
        return root, sketch.target_object, body

    def test_a_row_resolves_to_its_body_and_sketch(self):
        _root, sketch, body = self._part_with_feature()

        self.assertEqual(row_parts(body), (body, sketch))

    def test_a_sketch_with_no_body_is_still_its_own_row(self):
        """An old file never loses a sketch to the re-key."""
        curve = bpy.data.hair_curves.new("fl_legacy")
        obj = bpy.data.objects.new("fl_legacy", curve)
        self.scene.collection.objects.link(obj)
        from ..model.sketch_ref import stamp_sketch_props

        stamp_sketch_props(obj)

        self.assertEqual(row_parts(obj), (None, obj))

    def test_a_body_with_no_sketch_is_listed(self):
        """A mesh made a part by hand has no sketch, and used to be invisible."""
        bare = self._cube("fl_bare")
        mark_part_root(bare)
        self.assertEqual(row_parts(bare), (bare, None), "it is the row's body half")
        host_sketch = self._cube("fl_unrelated", location=(9.0, 0.0, 0.0))

        bpy.ops.object.select_all(action="DESELECT")
        bare.select_set(True)
        self.context.view_layer.objects.active = bare

        shown = _Filter().shown(self.context)
        self.assertIn(bare.name, shown)
        self.assertNotIn(host_sketch.name, shown, "another part is not listed")

    def test_the_feature_body_is_listed_with_its_part(self):
        root, _sketch, body = self._part_with_feature()

        bpy.ops.object.select_all(action="DESELECT")
        root.select_set(True)
        self.context.view_layer.objects.active = root

        shown = _Filter().shown(self.context)
        self.assertIn(root.name, shown)
        self.assertIn(body.name, shown, "the cutter is a row of its own")

    def test_a_loose_mesh_earns_no_row(self):
        """The list is the part's contents, not every mesh in the file."""
        self.assertFalse(is_feature_row(self._cube("fl_loose")))

    def test_a_cutting_body_is_recognised(self):
        root, _sketch, body = self._part_with_feature()

        cutting = cutting_bodies(self.scene)
        self.assertIn(body.name, cutting)
        self.assertNotIn(root.name, cutting)


class TestCutterVisibility(BgsTestCase):
    """The override behind the row's second icon."""

    def _part_with_cutter(self):
        def cube(name, location=(0.0, 0.0, 0.0)):
            me = bpy.data.meshes.new(name)
            bm = bmesh.new()
            bmesh.ops.create_cube(bm, size=2.0)
            bm.to_mesh(me)
            bm.free()
            ob = bpy.data.objects.new(name, me)
            self.scene.collection.objects.link(ob)
            ob.location = location
            return ob

        root = cube("cv_root")
        mark_part_root(root)
        cutter = cube("cv_cutter", location=(0.9, 0.0, 0.0))
        join_part(root, cutter)
        apply_boolean(root, cutter, "Difference")
        update_cutter_display(cutter, [root], True)
        return root, cutter

    def test_a_cutter_hides_itself_by_default(self):
        _root, cutter = self._part_with_cutter()
        self.assertTrue(cutter.hide_viewport)

    def test_the_toggle_shows_it_as_a_wireframe(self):
        _root, cutter = self._part_with_cutter()

        self.assertEqual(
            bpy.ops.view3d.slvs_set_cutter_visibility(body_name=cutter.name),
            {"FINISHED"},
        )

        self.assertFalse(cutter.hide_viewport)
        # Not a solid: it would sit over the result it just cut.
        self.assertEqual(cutter.display_type, "WIRE")

    def test_the_choice_survives_the_display_rules(self):
        """The reason it is stored: membership changes re-apply the rules."""
        root, cutter = self._part_with_cutter()
        bpy.ops.view3d.slvs_set_cutter_visibility(body_name=cutter.name)

        update_cutter_display(cutter, [root], True)

        self.assertTrue(cutter.get(SHOW_CUTTER_KEY, False))
        self.assertFalse(cutter.hide_viewport, "the rules hid it again")

    def test_toggling_back_hides_it(self):
        root, cutter = self._part_with_cutter()
        bpy.ops.view3d.slvs_set_cutter_visibility(body_name=cutter.name)
        bpy.ops.view3d.slvs_set_cutter_visibility(body_name=cutter.name)

        self.assertFalse(cutter.get(SHOW_CUTTER_KEY, False))
        self.assertTrue(cutter.hide_viewport)
        update_cutter_display(cutter, [root], True)
        self.assertTrue(cutter.hide_viewport)


class TestListIsDrawnWithoutSketches(BgsTestCase):
    """The panel's gate has to match what the list would actually show."""

    def _cube(self, name):
        me = bpy.data.meshes.new(name)
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=2.0)
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(name, me)
        self.scene.collection.objects.link(ob)
        return ob

    def _has_rows(self):
        return any(is_feature_row(obj) for obj in self.scene.objects)

    def test_a_part_of_imported_geometry_still_draws_the_list(self):
        """It has bodies and no sketch, so the old sketch gate hid its rows."""
        from ..model.sketch_ref import get_sketches

        bare = self._cube("gl_bare")
        mark_part_root(bare)

        self.assertFalse(any(True for _ in get_sketches(self.context)))
        self.assertTrue(self._has_rows())

    def test_an_empty_scene_draws_nothing(self):
        for obj in list(self.scene.objects):
            bpy.data.objects.remove(obj)
        self.assertFalse(self._has_rows())
