"""Tests for how a sketch resolves the frame its coordinates live in.

A sketch's plane used to be read off ``target_object.parent``, which tied the
plane to whatever placed the sketch, and left drawing and solving reading two
different matrices. It is now an explicit pointer behind one accessor, so a
sketch that owns its transform still has a well-defined plane: its own frame.
"""

import bpy
from mathutils import Matrix, Vector

from ..model.sketch_ref import set_active_sketch
from ..operators.add_sketch import set_sketch_workplane
from ..utilities.validate import _backfill_workplane_pointer
from ..utilities.workplane import get_workplane_origin_normal
from .utils import BgsTestCase, Sketch2dTestCase


class TestSketchPlane(Sketch2dTestCase):
    def setUp(self):
        super().setUp()
        set_active_sketch(self.context, self.sketch.target_object)

    def _empty(self, name, matrix=None):
        empty = bpy.data.objects.new(name, None)
        self.scene.collection.objects.link(empty)
        if matrix is not None:
            empty.matrix_world = matrix
        return empty

    def test_setting_a_workplane_stamps_the_pointer(self):
        wp = self._empty("WP", Matrix.Translation(Vector((1.0, 2.0, 3.0))))
        self.assertTrue(
            set_sketch_workplane(self.context, self.sketch.target_object, wp)
        )
        self.assertEqual(self.sketch.target_object.slvs_workplane, wp)
        self.assertEqual(self.sketch.workplane_object, wp)
        self.assertEqual(self.sketch.plane_matrix.translation, Vector((1.0, 2.0, 3.0)))

    def test_plane_matrix_follows_the_workplane(self):
        wp = self._empty("WP")
        set_sketch_workplane(self.context, self.sketch.target_object, wp)
        wp.matrix_world = Matrix.Translation(Vector((0.0, 0.0, 7.0)))
        self.assertEqual(self.sketch.plane_matrix.translation, Vector((0.0, 0.0, 7.0)))

    def test_plane_falls_back_to_the_sketch_frame(self):
        # A sketch with no workplane object is its own plane: the frame comes
        # from the sketch object, not an identity matrix at the world origin.
        obj = self.sketch.target_object
        obj.slvs_workplane = None
        obj.parent = None
        obj.matrix_world = Matrix.Translation(Vector((0.0, 5.0, 0.0)))
        self.assertIsNone(self.sketch.workplane_object)
        self.assertEqual(self.sketch.plane_matrix.translation, Vector((0.0, 5.0, 0.0)))

        origin, normal = get_workplane_origin_normal(self.sketch)
        self.assertEqual(origin, Vector((0.0, 5.0, 0.0)))
        self.assertEqual(normal, Vector((0.0, 0.0, 1.0)))

    def test_plane_is_independent_of_the_parent(self):
        # The point of the pointer: being placed by something else does not
        # change which frame the stored coordinates are read in.
        obj = self.sketch.target_object
        wp = self._empty("WP", Matrix.Translation(Vector((0.0, 0.0, 2.0))))
        set_sketch_workplane(self.context, obj, wp)

        holder = self._empty("holder", Matrix.Translation(Vector((10.0, 0.0, 0.0))))
        obj.parent = holder
        self.assertEqual(self.sketch.plane_matrix, wp.matrix_world)

    def test_world_matrix_is_the_plane(self):
        # Drawing and solving must read the same frame; world_matrix is what the
        # overlay and picking use.
        wp = self._empty("WP", Matrix.Translation(Vector((3.0, 0.0, 0.0))))
        set_sketch_workplane(self.context, self.sketch.target_object, wp)
        self.assertEqual(self.sketch.world_matrix, self.sketch.plane_matrix)

    def test_point_location_reads_the_plane(self):
        wp = self._empty("WP", Matrix.Translation(Vector((0.0, 0.0, 4.0))))
        set_sketch_workplane(self.context, self.sketch.target_object, wp)
        point = self.add_point((1.0, 0.0))
        self.assertEqual(point.location, Vector((1.0, 0.0, 4.0)))

    def test_backfill_adopts_the_parent(self):
        # Files written before the pointer existed carry only the parent.
        obj = self.sketch.target_object
        parent = self._empty("old_parent")
        obj.parent = parent
        obj.slvs_workplane = None
        _backfill_workplane_pointer(self.sketch)
        self.assertEqual(obj.slvs_workplane, parent)

    def test_backfill_keeps_an_explicit_pointer(self):
        # A sketch that owns its transform must not re-adopt a parent as plane.
        obj = self.sketch.target_object
        other = self._empty("other_plane")
        obj.parent = self._empty("holder")
        obj.slvs_workplane = other
        _backfill_workplane_pointer(self.sketch)
        self.assertEqual(obj.slvs_workplane, other)


class TestSketchOnAnEvaluatedPlane(BgsTestCase):
    """A sketch must be built against the original plane, never the evaluated one.

    A pointer state stores its object by name but resolves it back through the
    depsgraph, so the Add Sketch tool hands the picked workplane over evaluated.
    Parenting to runtime data, or pointing at it, holds for the session and is
    silently dropped when the file is written: the sketch reopens with no parent
    and no workplane, standing at the world origin while the plane it was drawn
    on is left orphaned. A face-anchored plane then follows its mesh face with
    nothing attached to it (issue: mesh edits stopped moving the sketch).
    """

    def _cube(self):
        import bmesh

        me = bpy.data.meshes.new("block")
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=2.0)
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new("block", me)
        self.scene.collection.objects.link(ob)
        self.addCleanup(bpy.data.objects.remove, ob)
        return ob, next(p.index for p in me.polygons if p.normal.z > 0.9)

    def _sketch_on_evaluated_face_plane(self):
        from ..operators.add_sketch import (
            build_sketch_on_workplane,
            create_face_workplane,
        )
        from ..utilities.body import body_of

        source, face = self._cube()
        plane = create_face_workplane(self.context, source, face)
        self.addCleanup(bpy.data.objects.remove, plane)

        depsgraph = self.context.evaluated_depsgraph_get()
        depsgraph.update()
        evaluated = plane.evaluated_get(depsgraph)
        self.assertTrue(evaluated.is_runtime_data, "the depsgraph owns this copy")

        sketch = build_sketch_on_workplane(self.context, evaluated)
        obj = sketch.target_object
        self.addCleanup(bpy.data.objects.remove, body_of(obj))
        self.addCleanup(bpy.data.objects.remove, obj)
        return obj, plane, source

    def test_the_sketch_stands_on_the_original_plane(self):
        obj, plane, _source = self._sketch_on_evaluated_face_plane()

        # Everything that has to survive a save must name the original.
        self.assertIs(obj.slvs_workplane, plane)
        self.assertIs(obj.parent, plane)
        self.assertFalse(obj.slvs_workplane.is_runtime_data)
        self.assertFalse(obj.parent.is_runtime_data)

    def test_the_plane_joins_the_part_it_was_picked_on(self):
        _obj, plane, source = self._sketch_on_evaluated_face_plane()

        # The plane's own parenting is dropped just as silently, which is what
        # leaves the anchored plane orphaned in a reopened file.
        self.assertIs(plane.parent, source)
        self.assertFalse(plane.is_runtime_data)

    def test_the_plane_can_still_be_renamed_after_the_body(self):
        # rename_after_bodies renames a body's plane on every depsgraph update;
        # an evaluated one is read-only and raised there on every single update.
        from ..utilities.body import body_of, name_after_body

        obj, _plane, _source = self._sketch_on_evaluated_face_plane()
        body = body_of(obj)
        body.name = "Latch"

        self.assertTrue(name_after_body(body, obj, obj.slvs_workplane))
        # Read the body's name back: Blender numbers one another object holds.
        self.assertEqual(obj.slvs_workplane.name, f"{body.name} Workplane")
