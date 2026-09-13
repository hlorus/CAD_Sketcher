"""Tests for face-anchored workplanes (utilities.face_anchor).

A workplane empty created from a mesh face is anchored via a persistent FACE
attribute id; the recompute derives its transform from the evaluated mesh so it
follows edits and deformation. These tests drive ``recompute_anchor_matrix``
directly on the evaluated object (deterministic — independent of the depsgraph
handler's timing).
"""

import bmesh
import bpy
from mathutils import Matrix

from ..utilities import face_anchor as fa
from .utils import BgsTestCase


class TestFaceAnchor(BgsTestCase):
    def setUp(self):
        # Fresh cube + empty anchored to face 0 (the -X face, center (-1,0,0)).
        me = bpy.data.meshes.new("anchor_cube")
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=2.0)
        bm.to_mesh(me)
        bm.free()
        self.ob = bpy.data.objects.new("anchor_cube", me)
        self.scene.collection.objects.link(self.ob)

        self.empty = bpy.data.objects.new("WP", None)
        self.scene.collection.objects.link(self.empty)
        # Give the empty a valid frame for the -X face before stamping:
        # Z = -X (face normal), X = +Z (a genuine in-plane axis). stamp_face_anchor
        # records the frame's X as the in-plane reference, so an identity frame
        # would store an axis parallel to the normal — degenerate, and the
        # recomputed frame could never stay rigid with the mesh.
        self.empty.matrix_world = Matrix(
            (
                (0.0, 0.0, -1.0, -1.0),
                (0.0, 1.0, 0.0, 0.0),
                (1.0, 0.0, 0.0, 0.0),
                (0.0, 0.0, 0.0, 1.0),
            )
        )
        fa.stamp_face_anchor(self.empty, self.ob, 0)
        self.face_id = self.empty[fa.KEY_FACE_ID]

    def tearDown(self):
        me = self.ob.data
        bpy.data.objects.remove(self.empty, do_unlink=True)
        bpy.data.objects.remove(self.ob, do_unlink=True)
        bpy.data.meshes.remove(me)

    # -- helpers ----------------------------------------------------------

    def _recompute(self):
        """Run the real recompute against the evaluated cube; update last_co."""
        dg = self.context.evaluated_depsgraph_get()
        dg.update()
        eval_ob = self.ob.evaluated_get(dg)
        res = fa.recompute_anchor_matrix(
            eval_ob,
            self.face_id,
            self.empty.get(fa.KEY_LAST_CO),
            self.empty.get(fa.KEY_REF),
        )
        if res is None:
            return None
        matrix, last_co = res
        self.empty[fa.KEY_LAST_CO] = last_co
        return matrix

    def _count_id_faces(self):
        # clear_face_id removes the attribute once no face carries the id, so a
        # missing attribute legitimately means zero.
        attr = self.ob.data.attributes.get(fa.FACE_ID_ATTR)
        if attr is None:
            return 0
        return sum(
            1 for p in self.ob.data.polygons if attr.data[p.index].value == self.face_id
        )

    def _select_id_faces(self, bm):
        layer = bm.faces.layers.int.get(fa.FACE_ID_ATTR)
        return [f for f in bm.faces if f[layer] == self.face_id]

    # -- creation ---------------------------------------------------------

    def test_stamp_creates_face_attribute(self):
        attr = self.ob.data.attributes.get(fa.FACE_ID_ATTR)
        self.assertIsNotNone(attr)
        self.assertEqual(attr.domain, "FACE")
        self.assertEqual(self._count_id_faces(), 1)

    def test_face_id_unique_per_mesh(self):
        e2 = bpy.data.objects.new("WP2", None)
        self.scene.collection.objects.link(e2)
        fa.stamp_face_anchor(e2, self.ob, 1)
        self.assertNotEqual(e2[fa.KEY_FACE_ID], self.empty[fa.KEY_FACE_ID])
        bpy.data.objects.remove(e2, do_unlink=True)

    # -- tracking ---------------------------------------------------------

    def test_baseline_on_face_center(self):
        m = self._recompute()
        self.assertIsNotNone(m)
        self.assertAlmostEqual(m.translation.x, -1.0, places=4)

    def test_follows_object_translation(self):
        self.ob.location = (5, 0, 0)
        m = self._recompute()
        self.assertIsNotNone(m)
        self.assertAlmostEqual(m.translation.x, 4.0, places=3)

    def test_follows_vertex_deform(self):
        for vi in self.ob.data.polygons[0].vertices:
            self.ob.data.vertices[vi].co.x -= 2.0
        self.ob.data.update()
        m = self._recompute()
        self.assertIsNotNone(m)
        self.assertLess(m.translation.x, -2.0)

    def test_normal_orientation_follows_face(self):
        m = self._recompute()
        # Z of the workplane frame is the face normal (-X face -> -X normal).
        normal = m.to_3x3().col[2]
        self.assertAlmostEqual(normal.x, -1.0, places=3)

    def test_frame_rigid_under_object_rotation(self):
        # The in-plane axes must rotate rigidly with the mesh: the frame's X
        # axis expressed in the object's local space stays constant across an
        # object rotation. (The world-up heuristic fails this — it re-solves the
        # in-plane direction from world Z, so a drawn line swings.)
        import math

        from mathutils import Euler

        m0 = self._recompute()
        x0_local = self.ob.matrix_world.to_3x3().inverted() @ m0.to_3x3().col[0]

        self.ob.rotation_euler = Euler((math.radians(45), 0.0, math.radians(90)))
        self.context.view_layer.update()

        m1 = self._recompute()
        x1_local = self.ob.matrix_world.to_3x3().inverted() @ m1.to_3x3().col[0]

        for a, b in zip(x0_local, x1_local):
            self.assertAlmostEqual(a, b, places=4)

    # -- topology edits ---------------------------------------------------

    def test_survives_subdivide(self):
        bm = bmesh.new()
        bm.from_mesh(self.ob.data)
        bm.faces.ensure_lookup_table()
        edges = {ed for f in self._select_id_faces(bm) for ed in f.edges}
        bmesh.ops.subdivide_edges(bm, edges=list(edges), cuts=2, use_grid_fill=True)
        bm.to_mesh(self.ob.data)
        bm.free()
        self.ob.data.update()

        self.assertEqual(self._count_id_faces(), 9)
        m = self._recompute()
        self.assertIsNotNone(m)
        # Plane stays put over the subdivided face set.
        self.assertAlmostEqual(m.translation.x, -1.0, places=2)

    def test_mirror_picks_cluster_without_canceling_normal(self):
        # Mirror creates a disjoint twin face with the same id and opposite
        # normal; naive area-weighting would cancel the normal to zero.
        self.ob.modifiers.new("mirror", "MIRROR")
        m = self._recompute()
        self.assertIsNotNone(m, "normal canceled — cluster selection failed")
        # Stays on the originally picked (-X) cluster.
        self.assertLess(m.translation.x, 0.0)

    # -- cleanup ----------------------------------------------------------

    def test_clear_face_id_resets_and_removes_attribute(self):
        # Single anchor -> clearing its id removes the whole attribute.
        fa.clear_face_id(self.ob.data, self.face_id)
        self.assertEqual(self._count_id_faces(), 0)
        self.assertIsNone(self.ob.data.attributes.get(fa.FACE_ID_ATTR))

    def test_clear_face_id_keeps_other_anchors(self):
        e2 = bpy.data.objects.new("WP2", None)
        self.scene.collection.objects.link(e2)
        fa.stamp_face_anchor(e2, self.ob, 1)
        id2 = e2[fa.KEY_FACE_ID]

        fa.clear_face_id(self.ob.data, self.face_id)
        attr = self.ob.data.attributes.get(fa.FACE_ID_ATTR)
        self.assertIsNotNone(attr)  # id2 still present -> attribute stays
        self.assertEqual(attr.data[1].value, id2)
        bpy.data.objects.remove(e2, do_unlink=True)

    def test_clear_anchor_makes_workplane_free(self):
        # "Make Free": props stripped, mesh attribute gone, empty stays put.
        pos = self.empty.matrix_world.translation.copy()
        fa.clear_anchor(self.empty)
        self.assertNotIn(fa.KEY_FACE_ID, self.empty)
        self.assertNotIn(fa.KEY_SOURCE, self.empty)
        self.assertNotIn(fa.KEY_DETACHED, self.empty)
        self.assertIsNone(self.ob.data.attributes.get(fa.FACE_ID_ATTR))
        self.assertAlmostEqual((self.empty.matrix_world.translation - pos).length, 0.0)

    def test_reconcile_clears_deleted_anchor(self):
        # Prime the live set, then delete the empty and reconcile.
        fa.reconcile_orphan_anchors(self.scene)
        self.assertEqual(self._count_id_faces(), 1)

        bpy.data.objects.remove(self.empty, do_unlink=True)
        fa.reconcile_orphan_anchors(self.scene)
        self.assertIsNone(self.ob.data.attributes.get(fa.FACE_ID_ATTR))

        # Re-link an empty so tearDown's removal stays valid.
        self.empty = bpy.data.objects.new("WP", None)
        self.scene.collection.objects.link(self.empty)

    def test_detached_when_face_deleted(self):
        bm = bmesh.new()
        bm.from_mesh(self.ob.data)
        bm.faces.ensure_lookup_table()
        bmesh.ops.delete(bm, geom=self._select_id_faces(bm), context="FACES")
        bm.to_mesh(self.ob.data)
        bm.free()
        self.ob.data.update()

        self.assertIsNone(self._recompute())

    # -- duplicated anchors -----------------------------------------------

    def _duplicate_empty(self):
        # Object.copy() carries custom properties, exactly like Shift+D.
        dup = self.empty.copy()
        self.scene.collection.objects.link(dup)
        return dup

    def _place_on_face(self, empty):
        empty[fa.KEY_LAST_CO] = [-1.0, 0.0, 0.0]
        empty.matrix_world.translation = (-1.0, 0.0, 0.0)

    def test_duplicate_right_after_copy_frees_the_copy(self):
        self._place_on_face(self.empty)
        dup = self._duplicate_empty()
        self.context.view_layer.update()

        # The depsgraph handler may already have run on the update; either way
        # the end state must be the same.
        fa.free_duplicate_anchors(self.scene)

        self.assertIn(fa.KEY_FACE_ID, self.empty)
        self.assertNotIn(fa.KEY_FACE_ID, dup)
        self.assertNotIn(fa.KEY_SOURCE, dup)
        # The kept empty still uses the face, so the mesh id must survive.
        fa.reconcile_orphan_anchors(self.scene)
        self.assertEqual(self._count_id_faces(), 1)
        bpy.data.objects.remove(dup, do_unlink=True)

    def test_duplicate_keeps_the_empty_on_the_face(self):
        self._place_on_face(self.empty)
        dup = self._duplicate_empty()
        # The original was moved away; the copy still sits on the face.
        self.empty.matrix_world.translation = (5.0, 5.0, 5.0)
        dup.matrix_world.translation = (-1.0, 0.0, 0.0)
        self.context.view_layer.update()

        fa.free_duplicate_anchors(self.scene)

        self.assertNotIn(fa.KEY_FACE_ID, self.empty)
        self.assertIn(fa.KEY_FACE_ID, dup)
        # Freed empties stay where the user put them.
        self.assertAlmostEqual(self.empty.matrix_world.translation.x, 5.0)
        bpy.data.objects.remove(dup, do_unlink=True)

    def test_single_anchor_untouched(self):
        self.assertEqual(fa.free_duplicate_anchors(self.scene), [])
        self.assertIn(fa.KEY_FACE_ID, self.empty)

    # -- changing the anchor ----------------------------------------------

    def test_change_face_replaces_old_anchor(self):
        # What the Anchor/Change Face operator does on a click.
        old_id = self.face_id
        fa.clear_anchor(self.empty)
        fa.stamp_face_anchor(self.empty, self.ob, 1)

        attr = self.ob.data.attributes.get(fa.FACE_ID_ATTR)
        ids = [attr.data[i].value for i in range(len(self.ob.data.polygons))]
        self.assertNotIn(old_id, ids[:1])
        self.assertEqual(ids[1], self.empty[fa.KEY_FACE_ID])
        self.assertEqual(sum(1 for v in ids if v), 1)

    def test_can_anchor_face_rejects_topology_modifiers(self):
        dg = self.context.evaluated_depsgraph_get()
        self.assertTrue(fa.can_anchor_face(self.ob, self.ob.evaluated_get(dg)))
        mod = self.ob.modifiers.new("solid", "SOLIDIFY")
        dg = self.context.evaluated_depsgraph_get()
        dg.update()
        self.assertFalse(fa.can_anchor_face(self.ob, self.ob.evaluated_get(dg)))
        self.ob.modifiers.remove(mod)

    def test_origin_workplanes_detected(self):
        from ..utilities.workplane import ensure_origin_workplane_empties

        ensure_origin_workplane_empties(self.context)
        self.assertTrue(fa.is_origin_workplane(self.scene, self.scene.sketcher.wp_xy))
        self.assertFalse(fa.is_origin_workplane(self.scene, self.empty))

    def test_panel_shows_anchor_on_shared_workplane(self):
        from ..model.sketch_ref import Sketch, stamp_sketch_props
        from ..ui.panels.sketch_select import _draw_workplane

        sketches = []
        for i in range(2):
            ob = bpy.data.objects.new(f"anchor_sk{i}", bpy.data.hair_curves.new("c"))
            self.scene.collection.objects.link(ob)
            stamp_sketch_props(ob)
            ob.parent = self.empty
            sketches.append(ob)

        class _Layout:
            def __init__(self):
                self.labels, self.ops = [], []

            def label(self, text="", icon=""):
                self.labels.append(text)

            def operator(self, idname, text="", icon=""):
                self.ops.append(text)
                return type("Props", (), {})()

            def row(self, align=False):
                return self

            box = row

        try:
            layout = _Layout()
            _draw_workplane(self.context, layout, Sketch(sketches[0]))
            self.assertEqual(
                layout.labels,
                ["Workplane anchored to anchor_cube (shared by 2 sketches)"],
            )
            self.assertEqual(layout.ops, ["Change Workplane", "Make Free"])

            fa.clear_anchor(self.empty)
            layout = _Layout()
            _draw_workplane(self.context, layout, Sketch(sketches[0]))
            self.assertEqual(layout.labels, [])
            self.assertEqual(layout.ops, ["Change Workplane"])
        finally:
            for ob in sketches:
                data = ob.data
                bpy.data.objects.remove(ob, do_unlink=True)
                bpy.data.hair_curves.remove(data)

    # -- changing a sketch's workplane --------------------------------------

    def _sketch_on(self, parent, name="wp_sketch"):
        from ..model.sketch_ref import stamp_sketch_props

        ob = bpy.data.objects.new(name, bpy.data.hair_curves.new(name))
        self.scene.collection.objects.link(ob)
        stamp_sketch_props(ob)
        ob.parent = parent
        return ob

    def _remove(self, ob):
        data = ob.data
        bpy.data.objects.remove(ob, do_unlink=True)
        bpy.data.hair_curves.remove(data)

    def test_set_sketch_workplane_moves_sketch_onto_plane(self):
        from ..operators.add_sketch import set_sketch_workplane

        target = bpy.data.objects.new("target_wp", None)
        self.scene.collection.objects.link(target)
        target.matrix_world = Matrix.Translation((3.0, 4.0, 5.0))
        sk = self._sketch_on(self.empty)
        other = self._sketch_on(self.empty, "other_sketch")
        try:
            self.assertTrue(set_sketch_workplane(self.context, sk, target))
            self.context.view_layer.update()
            self.assertIs(sk.parent, target)
            self.assertAlmostEqual(
                (sk.matrix_world.translation - target.matrix_world.translation).length,
                0.0,
            )
            # The old workplane is still used by another sketch: keep its anchor.
            self.assertIn(self.empty.name, bpy.data.objects)
            self.assertIn(fa.KEY_FACE_ID, self.empty)
            # Picking the current workplane again is a no-op.
            self.assertFalse(set_sketch_workplane(self.context, sk, target))
        finally:
            self._remove(sk)
            self._remove(other)
            bpy.data.objects.remove(target, do_unlink=True)

    def test_set_sketch_workplane_removes_unused_face_workplane(self):
        from ..operators.add_sketch import set_sketch_workplane
        from ..utilities.workplane import ensure_origin_workplane_empties

        ensure_origin_workplane_empties(self.context)
        wp_xy = self.scene.sketcher.wp_xy
        old = self.empty
        sk = self._sketch_on(old)
        try:
            self.assertTrue(set_sketch_workplane(self.context, sk, wp_xy))
            # The face workplane was only used by this sketch: gone, with its id.
            self.assertNotIn("WP", bpy.data.objects)
            self.assertIsNone(self.ob.data.attributes.get(fa.FACE_ID_ATTR))
            # Moving off an origin plane must never delete it.
            back = bpy.data.objects.new("WP", None)
            self.scene.collection.objects.link(back)
            self.empty = back  # tearDown removes it
            self.assertTrue(set_sketch_workplane(self.context, sk, back))
            self.assertIs(self.scene.sketcher.wp_xy, wp_xy)
            self.assertIn(wp_xy.name, bpy.data.objects)
        finally:
            self._remove(sk)
