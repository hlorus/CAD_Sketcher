"""Tests for parts: which object owns a part's transform, and who follows it.

A part is rooted in its first sketch (which becomes its body once extruded), so
the user moves the geometry they see. Workplanes and the sketches on them are
members: fixed within the part, carried along by it.
"""

import bmesh
import bpy
from mathutils import Matrix, Vector

from ..operators.add_sketch import build_sketch_on_workplane, create_face_workplane
from ..utilities.part import (
    PART_ROOT_KEY,
    is_part_root,
    join_part,
    mark_part_root,
    part_root_of,
    reconcile_parts,
    rehome_children,
    settle_membership,
)
from .utils import BgsTestCase


class TestPartRoot(BgsTestCase):
    def setUp(self):
        super().setUp()
        self.entities.ensure_origin_elements(self.context)
        from ..utilities.workplane import ensure_origin_workplane_empties

        ensure_origin_workplane_empties(self.context)
        self.datum = self.context.scene.sketcher.wp_xy

    def _cube(self, name="body", location=(0.0, 0.0, 0.0)):
        me = bpy.data.meshes.new(name)
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=2.0)
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(name, me)
        self.scene.collection.objects.link(ob)
        ob.location = location
        return ob

    def test_sketch_on_a_datum_plane_is_global(self):
        # Nothing obvious to belong to: it stays global until it is made solid.
        sketch = build_sketch_on_workplane(self.context, self.datum)
        obj = sketch.target_object

        self.assertFalse(is_part_root(obj))
        self.assertIsNone(part_root_of(obj))
        self.assertIsNone(obj.parent)
        # It is its own plane, sitting where the datum plane it was drawn on is.
        self.assertIsNone(obj.slvs_workplane)
        self.assertEqual(sketch.plane_matrix, self.datum.matrix_world)

    def test_a_global_sketch_can_be_moved(self):
        sketch = build_sketch_on_workplane(self.context, self.datum)
        obj = sketch.target_object

        self.assertEqual(tuple(obj.lock_location), (False, False, False))
        self.assertEqual(tuple(obj.lock_rotation), (False, False, False))
        # Scale stays locked: the solver reads the plane as a rigid frame.
        self.assertEqual(tuple(obj.lock_scale), (True, True, True))

        obj.matrix_world = Matrix.Translation(Vector((5.0, 0.0, 0.0)))
        self.assertEqual(sketch.plane_matrix.translation, Vector((5.0, 0.0, 0.0)))

    def test_a_standalone_solid_roots_its_own_part(self):
        sketch = build_sketch_on_workplane(self.context, self.datum)
        obj = sketch.target_object

        # Extruded with nothing to boolean into.
        self.assertEqual(settle_membership(obj, []), obj)
        self.assertTrue(is_part_root(obj))
        self.assertEqual(tuple(obj.lock_location), (False, False, False))

    def test_a_solid_that_cuts_a_body_joins_its_part(self):
        body = self._cube("target", location=(1.0, 0.0, 0.0))
        mark_part_root(body)
        cutter = build_sketch_on_workplane(self.context, self.datum)
        obj = cutter.target_object

        self.assertEqual(settle_membership(obj, [body]), body)
        self.assertEqual(part_root_of(obj), body)
        self.assertFalse(is_part_root(obj))
        # A feature does not move on its own any more.
        self.assertEqual(tuple(obj.lock_location), (True, True, True))

        # And the cut travels with the body it cuts.
        before = cutter.plane_matrix.translation.copy()
        body.matrix_basis = Matrix.Translation(Vector((0.0, 0.0, 4.0)))
        self.context.view_layer.update()
        self.assertEqual(
            cutter.plane_matrix.translation, before + Vector((0.0, 0.0, 4.0))
        )

    def test_cutting_a_bare_body_makes_it_a_part(self):
        body = self._cube("bare")
        cutter = build_sketch_on_workplane(self.context, self.datum)

        self.assertEqual(settle_membership(cutter.target_object, [body]), body)
        self.assertTrue(is_part_root(body))

    def test_a_sketch_already_in_a_part_keeps_it(self):
        body = self._cube()
        wp = create_face_workplane(self.context, body, 0)
        sketch = build_sketch_on_workplane(self.context, wp)
        other = self._cube("other", location=(10.0, 0.0, 0.0))
        mark_part_root(other)

        self.assertEqual(settle_membership(sketch.target_object, [other]), body)
        self.assertEqual(part_root_of(sketch.target_object), body)

    def test_sketch_on_a_face_joins_that_object_s_part(self):
        body = self._cube()
        wp = create_face_workplane(self.context, body, 0)
        sketch = build_sketch_on_workplane(self.context, wp)
        obj = sketch.target_object

        # The mesh became the part; the sketch is a feature inside it.
        self.assertTrue(is_part_root(body))
        self.assertFalse(is_part_root(obj))
        self.assertEqual(part_root_of(obj), body)
        self.assertEqual(obj.parent, wp)
        self.assertEqual(obj.slvs_workplane, wp)
        self.assertEqual(tuple(obj.lock_location), (True, True, True))

    def test_members_follow_the_part(self):
        body = self._cube()
        wp = create_face_workplane(self.context, body, 0)
        sketch = build_sketch_on_workplane(self.context, wp)
        before = sketch.plane_matrix.translation.copy()

        body.matrix_world = Matrix.Translation(Vector((0.0, 0.0, 3.0)))
        self.context.view_layer.update()
        self.assertEqual(
            sketch.plane_matrix.translation, before + Vector((0.0, 0.0, 3.0))
        )

    def test_joining_a_part_keeps_world_position(self):
        root = self._cube("root", location=(2.0, 0.0, 0.0))
        member = bpy.data.objects.new("member", None)
        self.scene.collection.objects.link(member)
        member.matrix_world = Matrix.Translation(Vector((0.0, 4.0, 0.0)))
        self.context.view_layer.update()

        join_part(root, member)
        self.context.view_layer.update()
        self.assertEqual(member.matrix_world.translation, Vector((0.0, 4.0, 0.0)))

    def test_rehoming_keeps_members_in_place_and_promotes_a_successor(self):
        sketch = build_sketch_on_workplane(self.context, self.datum)
        root = sketch.target_object
        mark_part_root(root)
        root.matrix_world = Matrix.Translation(Vector((7.0, 0.0, 0.0)))
        self.context.view_layer.update()

        wp = bpy.data.objects.new("WP", None)
        self.scene.collection.objects.link(wp)
        wp.matrix_world = Matrix.Translation(Vector((7.0, 1.0, 0.0)))
        self.context.view_layer.update()
        join_part(root, wp)

        member = build_sketch_on_workplane(self.context, wp)
        member_obj = member.target_object
        placed_at = member.plane_matrix.translation.copy()

        successor = rehome_children(root)
        self.context.view_layer.update()

        self.assertEqual(successor, member_obj)
        self.assertTrue(is_part_root(member_obj))
        self.assertIsNone(member_obj.parent)
        # The successor owns its transform now, so it is its own plane, and the
        # part's geometry did not jump when the old root let go.
        self.assertIsNone(member_obj.slvs_workplane)
        self.assertEqual(member.plane_matrix.translation, placed_at)
        self.assertEqual(part_root_of(wp), member_obj)

    def test_demoted_linked_duplicate_stops_rooting_a_part(self):
        from ..utilities.consumable import reconcile_linked_duplicates

        sketch = build_sketch_on_workplane(self.context, self.datum)
        root = sketch.target_object
        mark_part_root(root)

        # Alt+D: a second object sharing the same curve data, props and all.
        copy = root.copy()
        self.scene.collection.objects.link(copy)
        self.assertTrue(copy[PART_ROOT_KEY])

        self.assertTrue(reconcile_linked_duplicates(self.scene))
        self.assertFalse(is_part_root(copy))
        self.assertTrue(is_part_root(root))

    def test_deleting_a_root_outside_the_operator_is_repaired(self):
        # Blender's own Delete never reaches the sketch delete operator: it drops
        # the parent and keeps the child's local transform, so the part would
        # collapse back toward where it was first assembled.
        sketch = build_sketch_on_workplane(self.context, self.datum)
        root = sketch.target_object
        mark_part_root(root)

        wp = bpy.data.objects.new("WP", None)
        self.scene.collection.objects.link(wp)
        join_part(root, wp)
        member = build_sketch_on_workplane(self.context, wp)
        member_obj = member.target_object

        # The part is assembled, then moved as a whole.
        root.matrix_basis = Matrix.Translation(Vector((0.0, 0.0, 6.0)))
        reconcile_parts(self.scene)  # remembers the part's frame
        placed_at = member.plane_matrix.translation.copy()

        bpy.data.objects.remove(root)
        self.assertTrue(reconcile_parts(self.scene))

        self.assertTrue(is_part_root(member_obj))
        self.assertIsNone(member_obj.slvs_workplane)
        self.assertEqual(member.plane_matrix.translation, placed_at)
        self.assertEqual(part_root_of(wp), member_obj)

    def test_reconcile_is_quiet_when_nothing_is_orphaned(self):
        sketch = build_sketch_on_workplane(self.context, self.datum)
        mark_part_root(sketch.target_object)
        wp = bpy.data.objects.new("WP", None)
        self.scene.collection.objects.link(wp)
        join_part(sketch.target_object, wp)

        self.assertFalse(reconcile_parts(self.scene))
        self.assertFalse(reconcile_parts(self.scene))

    def test_moving_a_part_carries_its_solved_geometry(self):
        sketch = build_sketch_on_workplane(self.context, self.datum)
        root = sketch.target_object
        mark_part_root(root)

        from ..curve_solver import solve_system
        from ..model.curve_ref import LineRef, PointRef

        origin = PointRef.create(sketch, (0.0, 0.0), fixed=True)
        p1 = PointRef.create(sketch, (10.0, 0.0))
        line = LineRef.create(sketch, origin, p1)
        sketch.constraints.add_distance(
            curve_id_1=origin.curve_id, curve_id_2=p1.curve_id
        ).value = 30.0
        self.assertTrue(solve_system(self.context, sketch=sketch))

        local_before = Vector(p1.co)
        self.assertAlmostEqual(local_before.length, 30.0, places=4)

        root.matrix_basis = Matrix.Translation(Vector((100.0, 0.0, 0.0)))
        self.context.view_layer.update()
        self.assertTrue(solve_system(self.context, sketch=sketch))

        # The part moved; the sketch is unchanged in its own frame and simply
        # rides along in world space.
        self.assertAlmostEqual((Vector(p1.co) - local_before).length, 0.0, places=4)
        self.assertEqual(p1.location, Vector((100.0, 0.0, 0.0)) + local_before.to_3d())
        self.assertEqual(line.wp_matrix, sketch.plane_matrix)

    def test_sketch_on_a_sketch_body_joins_its_part(self):
        # The reported case: a rectangle sketch, then a sketch on the rectangle.
        # A sketch body is a Curves object, so its face can never be anchored
        # (can_anchor_face needs polygons), and part membership must not depend on
        # anchoring having worked -- only on what the sketch was drawn on.
        from ..utilities.face_anchor import KEY_FACE_ID, KEY_SOURCE

        first = build_sketch_on_workplane(self.context, self.datum)
        body = first.target_object
        self.assertFalse(is_part_root(body))  # global until something joins it

        # The workplane a non-anchorable pick produces: source recorded, no anchor.
        wp = bpy.data.objects.new("WP", None)
        self.scene.collection.objects.link(wp)
        wp[KEY_SOURCE] = body
        self.assertNotIn(KEY_FACE_ID, wp)

        second = build_sketch_on_workplane(self.context, wp)
        # Drawing on a global sketch is what promotes it to a part.
        self.assertTrue(is_part_root(body))
        self.assertEqual(part_root_of(second.target_object), body)

        # And it follows when the part moves.
        before = second.plane_matrix.translation.copy()
        body.matrix_basis = Matrix.Translation(Vector((0.0, 0.0, 9.0)))
        self.context.view_layer.update()
        self.assertEqual(
            second.plane_matrix.translation, before + Vector((0.0, 0.0, 9.0))
        )

    def test_face_workplane_records_its_source(self):
        from ..utilities.face_anchor import KEY_SOURCE

        body = self._cube()
        wp = create_face_workplane(self.context, body, 0)
        self.assertEqual(wp[KEY_SOURCE], body)

    def test_part_planes_are_offered_in_the_parts_own_frame(self):
        from ..utilities.part import part_planes

        body = self._cube("moved")
        mark_part_root(body)
        body.matrix_basis = Matrix.Translation(
            Vector((3.0, 0.0, 0.0))
        ) @ Matrix.Rotation(1.0, 4, "Y")
        self.context.view_layer.update()
        bpy.ops.object.select_all(action="DESELECT")
        body.select_set(True)
        self.context.view_layer.objects.active = body

        planes = part_planes(self.context)
        self.assertEqual([p.axis for p in planes], ["XY", "XZ", "YZ"])
        # A moved, rotated part offers planes in its frame, not the world's.
        xy = planes[0]
        self.assertEqual(xy.matrix_world.translation, Vector((3.0, 0.0, 0.0)))
        self.assertEqual(
            xy.matrix_world.to_quaternion(), body.matrix_basis.to_quaternion()
        )

    def test_no_part_in_focus_offers_no_part_planes(self):
        from ..utilities.part import part_planes

        bpy.ops.object.select_all(action="DESELECT")
        self.context.view_layer.objects.active = None
        self.assertEqual(part_planes(self.context), [])

    def test_picking_a_part_plane_materializes_one_empty(self):
        from ..utilities.part import PART_PLANE_KEY, as_workplane_object, part_planes

        body = self._cube("host")
        mark_part_root(body)
        bpy.ops.object.select_all(action="DESELECT")
        body.select_set(True)
        self.context.view_layer.objects.active = body

        plane = part_planes(self.context)[1]  # XZ
        empty = as_workplane_object(self.context, plane)

        self.assertEqual(empty.type, "EMPTY")
        self.assertEqual(empty[PART_PLANE_KEY], "XZ")
        self.assertEqual(part_root_of(empty), body)
        self.assertEqual(empty.matrix_world.translation, plane.matrix_world.translation)

        # Picking it again reuses it instead of stacking coincident workplanes.
        again = as_workplane_object(self.context, part_planes(self.context)[1])
        self.assertEqual(again, empty)

    def test_a_sketch_on_a_part_plane_joins_that_part(self):
        from ..utilities.part import as_workplane_object, part_planes

        body = self._cube("host")
        mark_part_root(body)
        bpy.ops.object.select_all(action="DESELECT")
        body.select_set(True)
        self.context.view_layer.objects.active = body

        wp = as_workplane_object(self.context, part_planes(self.context)[0])
        sketch = build_sketch_on_workplane(self.context, wp)
        self.assertEqual(part_root_of(sketch.target_object), body)
