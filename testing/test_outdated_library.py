"""A library saved before the body link was flagged is reported, and repairable.

Reported where it is linked, repaired only in the file that owns the bodies.
"""

import os
import tempfile
from unittest import mock

import bmesh
import bpy

from ..model.curve_ref import LineRef, PointRef
from ..operators import repair_library
from ..operators.add_sketch import build_sketch_on_workplane, create_face_workplane
from ..ui.panels import sketch_select
from ..utilities import library_refs
from ..utilities.body import BODY_SKETCH_PATH, body_of, ensure_body
from ..utilities.curve_data import refresh_curve_geometry
from ..utilities.face_anchor import WP_SOURCE_PATH
from ..utilities.workplane import ensure_origin_workplane_empties
from .test_override_reference_persistence import _run
from .utils import BgsTestCase


def flagged(body):
    return body.is_property_overridable_library(BODY_SKETCH_PATH)


def unflag(obj, path=BODY_SKETCH_PATH):
    obj.property_overridable_library_set(path, False)


class OutdatedLibraryCase(BgsTestCase):
    def setUp(self):
        super().setUp()
        existing = set(bpy.data.objects)
        self.addCleanup(
            lambda: bpy.data.batch_remove(
                [o for o in bpy.data.objects if o not in existing]
            )
        )
        self.entities.ensure_origin_elements(self.context)
        ensure_origin_workplane_empties(self.context)
        sketch = build_sketch_on_workplane(
            self.context, self.context.scene.sketcher.wp_xy
        )
        points = [PointRef.create(sketch, c) for c in ((0, 0), (4, 0), (4, 4))]
        LineRef.create(sketch, points[0], points[1])
        LineRef.create(sketch, points[1], points[2])
        refresh_curve_geometry(sketch)
        obj = sketch.target_object
        self.body = body_of(obj) or ensure_body(self.context, obj, "Body")
        self.addCleanup(library_refs.clear_state)

    def as_library(self):
        """Make this file one that is linked from: mark the body as an asset."""
        self.body.asset_mark()
        self.addCleanup(self.body.asset_clear)
        return library_refs.refresh_state()

    def face_workplane(self):
        mesh = bpy.data.meshes.new("plate")
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=2.0)
        bm.to_mesh(mesh)
        bm.free()
        plate = bpy.data.objects.new("plate", mesh)
        self.context.scene.collection.objects.link(plate)
        top = next(p.index for p in mesh.polygons if p.normal.z > 0.9)
        return create_face_workplane(self.context, plate, top)

    def linked_part(self, outdated, override=True):
        """The body of a part linked from a library file, and its override."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = os.path.join(tmp.name, "library.blend")
        _run("library", path, *(["old"] if outdated else []))
        before = set(bpy.data.objects)
        with bpy.data.libraries.load(path, link=True) as (src, dst):
            dst.objects = list(src.objects)
        scene = self.context.scene
        for obj in dst.objects:
            scene.collection.objects.link(obj)
        linked = next(obj for obj in dst.objects if "slvs:body_of" in obj)
        if override:
            linked.override_hierarchy_create(scene, self.context.view_layer)
        added = [obj for obj in bpy.data.objects if obj not in before]
        self.addCleanup(
            lambda: bpy.data.batch_remove(
                [obj for obj in added if obj.name in bpy.data.objects]
                + [linked.library]
            )
        )
        overrides = [o for o in added if o.override_library and "slvs:body_of" in o]
        return linked, (overrides[0] if overrides else None)


class TestDetection(OutdatedLibraryCase):
    def test_a_body_made_now_is_flagged(self):
        self.assertTrue(flagged(self.body))
        self.assertEqual(library_refs.outdated_body_objects(), [])

    def test_a_body_without_the_flag_is_outdated(self):
        self.body.property_overridable_library_set(BODY_SKETCH_PATH, False)
        self.assertEqual(library_refs.outdated_body_objects(), [self.body])

    def test_a_face_workplane_made_now_is_flagged(self):
        plane = self.face_workplane()
        self.assertTrue(plane.is_property_overridable_library(WP_SOURCE_PATH))
        self.assertEqual(library_refs.outdated_body_objects(), [])

    def test_a_face_workplane_without_the_flag_is_outdated(self):
        plane = self.face_workplane()
        plane.property_overridable_library_set(WP_SOURCE_PATH, False)
        self.assertEqual(library_refs.outdated_body_objects(), [plane])

    def test_an_overridden_old_library_is_outdated(self):
        linked, _ = self.linked_part(outdated=True)
        self.assertEqual(library_refs.outdated_libraries(), [linked.library])

    def test_a_library_saved_now_is_not_outdated(self):
        self.linked_part(outdated=False)
        self.assertEqual(library_refs.outdated_libraries(), [])

    def test_an_old_library_nobody_overrides_is_not_reported(self):
        self.linked_part(outdated=True, override=False)
        self.assertEqual(library_refs.outdated_libraries(), [])

    def test_linked_and_overridden_bodies_are_not_this_files_to_repair(self):
        self.linked_part(outdated=True)
        self.assertEqual(library_refs.outdated_body_objects(), [])


class TestRepairLibrary(OutdatedLibraryCase):
    def test_repair_flags_the_files_own_bodies(self):
        self.body.property_overridable_library_set(BODY_SKETCH_PATH, False)
        self.as_library()
        self.assertTrue(bpy.ops.view3d.slvs_repair_library.poll())
        bpy.ops.view3d.slvs_repair_library()
        self.assertTrue(flagged(self.body))
        self.assertFalse(bpy.ops.view3d.slvs_repair_library.poll())

    def test_repair_flags_the_files_own_face_workplanes(self):
        plane = self.face_workplane()
        plane.property_overridable_library_set(WP_SOURCE_PATH, False)
        self.as_library()
        bpy.ops.view3d.slvs_repair_library()
        self.assertTrue(plane.is_property_overridable_library(WP_SOURCE_PATH))

    def test_the_report_counts_what_was_repaired(self):
        self.assertEqual(
            repair_library.repaired_message(1), "Repaired 1 link. Save this file now."
        )
        self.assertEqual(
            repair_library.repaired_message(3),
            "Repaired 3 links. Save this file now.",
        )

    def test_nothing_to_repair_is_not_offered(self):
        self.as_library()
        self.assertFalse(bpy.ops.view3d.slvs_repair_library.poll())

    def test_a_file_that_only_links_the_library_is_not_offered_the_repair(self):
        self.linked_part(outdated=True)
        library_refs.refresh_state()
        self.assertFalse(bpy.ops.view3d.slvs_repair_library.poll())

    def test_repair_leaves_linked_and_overridden_bodies_alone(self):
        linked, override = self.linked_part(outdated=True)
        self.body.property_overridable_library_set(BODY_SKETCH_PATH, False)
        library_refs.refresh_state()
        bpy.ops.view3d.slvs_repair_library()
        self.assertTrue(flagged(self.body))
        self.assertFalse(flagged(linked))
        self.assertFalse(flagged(override))
        self.assertEqual(library_refs.outdated_libraries(), [linked.library])

    def test_a_read_only_file_is_refused(self):
        self.body.property_overridable_library_set(BODY_SKETCH_PATH, False)
        self.as_library()
        with mock.patch.object(
            repair_library, "repair_blocker", return_value="This file is read-only."
        ):
            result = bpy.ops.view3d.slvs_repair_library()
        self.assertEqual(result, {"CANCELLED"})
        self.assertFalse(flagged(self.body))

    def test_the_blocker_looks_at_the_file_on_disk(self):
        with tempfile.NamedTemporaryFile(suffix=".blend") as f:
            fake_data = mock.Mock(filepath=f.name)
            with mock.patch.object(library_refs.bpy, "data", fake_data):
                with mock.patch.object(library_refs.os, "access", return_value=False):
                    self.assertTrue(library_refs.repair_blocker())
                with mock.patch.object(library_refs.os, "access", return_value=True):
                    self.assertEqual(library_refs.repair_blocker(), "")


class TestPartialRepair(OutdatedLibraryCase):
    def test_only_links_that_took_are_counted(self):
        plane = self.face_workplane()
        unflag(self.body)
        unflag(plane, WP_SOURCE_PATH)
        self.as_library()
        with mock.patch.object(
            library_refs, "_set_overridable", side_effect=[True, False]
        ):
            self.assertEqual(library_refs.repair_bodies(), 1)

    def test_a_set_blender_refuses_is_not_counted(self):
        obj = mock.Mock()
        obj.property_overridable_library_set.return_value = False
        self.assertFalse(library_refs._set_overridable(obj, BODY_SKETCH_PATH))

    def test_a_set_that_did_not_stick_is_not_counted(self):
        obj = mock.Mock()
        obj.property_overridable_library_set.return_value = True
        obj.is_property_overridable_library.return_value = False
        self.assertFalse(library_refs._set_overridable(obj, BODY_SKETCH_PATH))

    def test_a_set_that_raises_is_not_counted(self):
        obj = mock.Mock()
        obj.property_overridable_library_set.side_effect = TypeError
        self.assertFalse(library_refs._set_overridable(obj, BODY_SKETCH_PATH))

    def test_the_operator_warns_about_what_is_left(self):
        unflag(self.body)
        self.as_library()
        with mock.patch.object(library_refs, "_set_overridable", return_value=False):
            result = bpy.ops.view3d.slvs_repair_library()
        self.assertEqual(result, {"CANCELLED"})
        self.assertEqual(library_refs.cached_state().repairable, 1)
        self.assertTrue(bpy.ops.view3d.slvs_repair_library.poll())

    def test_a_full_repair_clears_the_prompt(self):
        unflag(self.body)
        self.as_library()
        self.assertEqual(library_refs.repair_bodies(), 1)
        self.assertEqual(library_refs.cached_state().repairable, 0)

    def test_the_failure_message(self):
        self.assertEqual(
            repair_library.failed_message(2), "2 objects could not be repaired."
        )


class TestCache(OutdatedLibraryCase):
    def test_redraw_reads_the_cache_and_never_scans(self):
        unflag(self.body)
        self.as_library()
        with (
            mock.patch.object(
                library_refs, "outdated_libraries", side_effect=AssertionError
            ),
            mock.patch.object(
                library_refs, "outdated_body_objects", side_effect=AssertionError
            ),
            mock.patch.object(
                library_refs, "refresh_state", side_effect=AssertionError
            ),
        ):
            for _ in range(50):
                layout = mock.MagicMock()
                sketch_select._draw_outdated_library_prompt(self.context, layout)
                layout.box.assert_called_once()
            self.assertTrue(bpy.ops.view3d.slvs_repair_library.poll())

    def test_nothing_is_shown_before_the_first_scan(self):
        unflag(self.body)
        self.body.asset_mark()
        self.addCleanup(self.body.asset_clear)
        library_refs.clear_state()
        layout = mock.MagicMock()
        sketch_select._draw_outdated_library_prompt(self.context, layout)
        layout.box.assert_not_called()

    def test_loading_a_file_scans_it(self):
        from .. import handlers

        unflag(self.body)
        self.body.asset_mark()
        self.addCleanup(self.body.asset_clear)
        library_refs.clear_state()
        with mock.patch.object(
            library_refs, "refresh_state", wraps=library_refs.refresh_state
        ) as scan:
            handlers.on_load_post()
        scan.assert_called_once_with()
        self.assertEqual(library_refs.cached_state().repairable, 1)

    def test_an_unchanged_file_is_not_rescanned(self):
        self.as_library()
        with mock.patch.object(library_refs, "refresh_state") as scan:
            library_refs.refresh_state_if_changed()
        scan.assert_not_called()

    def test_a_new_link_is_picked_up(self):
        library_refs.refresh_state()
        linked, _ = self.linked_part(outdated=True)
        library_refs.refresh_state_if_changed()
        self.assertEqual(library_refs.cached_state().libraries, ("library.blend",))


class TestWarning(OutdatedLibraryCase):
    def test_the_warning_names_the_library_and_the_steps(self):
        linked, _ = self.linked_part(outdated=True)
        text = "\n".join(
            library_refs.warning_lines([library_refs.library_label(linked.library)])
        )
        self.assertIn("library.blend", text)
        self.assertIn("open the library file", text)
        self.assertIn("Repair Library File", text)
        self.assertIn("reload this file", text)

    def test_many_libraries_are_summarised(self):
        names = [f"lib{i}.blend" for i in range(5)]
        text = "\n".join(library_refs.warning_lines(names))
        self.assertIn("lib0.blend, lib1.blend, lib2.blend and 2 more", text)

    def _panel(self):
        layout = mock.MagicMock()
        sketch_select._draw_outdated_library_prompt(self.context, layout)
        return layout

    def test_the_panel_warns_without_a_repair_button_in_the_linking_file(self):
        self.linked_part(outdated=True)
        library_refs.refresh_state()
        box = self._panel().box.return_value
        self.assertTrue(box.alert)
        box.operator.assert_not_called()

    def test_the_panel_offers_the_repair_in_the_library_file(self):
        unflag(self.body)
        self.as_library()
        box = self._panel().box.return_value
        self.assertEqual(box.operator.call_args.args[0], "view3d.slvs_repair_library")

    def test_a_plain_local_file_with_old_bodies_shows_nothing(self):
        unflag(self.body)
        state = library_refs.refresh_state()
        self.assertFalse(state.is_library_file)
        self._panel().box.assert_not_called()
        self.assertFalse(bpy.ops.view3d.slvs_repair_library.poll())

    def test_the_panel_is_quiet_when_nothing_is_outdated(self):
        self.as_library()
        self._panel().box.assert_not_called()
