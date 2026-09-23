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
        from ..utilities.body import body_of

        sketch = build_sketch_on_workplane(self.context, self.datum)
        obj = sketch.target_object
        body = body_of(obj)

        self.assertIsNotNone(body, "every sketch is realised on a body")
        self.assertFalse(is_part_root(body))
        self.assertIsNone(part_root_of(obj))
        # It sits on a plane of its own, where the datum it was drawn on is: the
        # scene's datums are shared, so no part may hang from one.
        self.assertIsNotNone(obj.slvs_workplane)
        self.assertNotEqual(obj.slvs_workplane, self.datum)
        self.assertEqual(obj.slvs_workplane.parent, body)
        self.assertEqual(sketch.plane_matrix, self.datum.matrix_world)

    def test_a_global_sketch_can_be_moved(self):
        # The body is the handle; the sketch is pinned to its plane.
        from ..utilities.body import body_of

        sketch = build_sketch_on_workplane(self.context, self.datum)
        body = body_of(sketch.target_object)

        self.assertEqual(tuple(body.lock_location), (False, False, False))
        self.assertEqual(tuple(body.lock_rotation), (False, False, False))
        # Scale stays locked: the solver reads the plane as a rigid frame.
        self.assertEqual(tuple(body.lock_scale), (True, True, True))
        self.assertEqual(tuple(sketch.target_object.lock_location), (True, True, True))

        body.matrix_basis = Matrix.Translation(Vector((5.0, 0.0, 0.0)))
        self.context.view_layer.update()
        self.assertEqual(sketch.plane_matrix.translation, Vector((5.0, 0.0, 0.0)))

    def test_a_standalone_solid_roots_its_own_part(self):
        from ..utilities.body import body_of

        sketch = build_sketch_on_workplane(self.context, self.datum)
        obj = sketch.target_object
        body = body_of(obj)

        # Extruded with nothing to boolean into: the body roots the part.
        self.assertEqual(settle_membership(obj, []), body)
        self.assertTrue(is_part_root(body))
        self.assertEqual(part_root_of(obj), body)
        self.assertEqual(tuple(body.lock_location), (False, False, False))

    def test_a_solid_that_cuts_a_body_joins_its_part(self):
        from ..utilities.body import body_of

        body = self._cube("target", location=(1.0, 0.0, 0.0))
        mark_part_root(body)
        cutter = build_sketch_on_workplane(self.context, self.datum)
        obj = cutter.target_object
        cutter_body = body_of(obj)

        self.assertEqual(settle_membership(obj, [body]), body)
        self.assertEqual(part_root_of(obj), body)
        self.assertFalse(is_part_root(cutter_body))
        # A feature does not move on its own any more.
        self.assertEqual(tuple(cutter_body.lock_location), (True, True, True))

        # And the cut travels with the body it cuts.
        before = cutter.plane_matrix.translation.copy()
        body.matrix_basis = Matrix.Translation(Vector((0.0, 0.0, 4.0)))
        self.context.view_layer.update()
        self.assertEqual(
            cutter.plane_matrix.translation, before + Vector((0.0, 0.0, 4.0))
        )

    def test_a_cut_across_two_parts_stays_global(self):
        # It is an assembly-level feature: it belongs to neither part, rather than
        # to whichever one detection happened to return first.
        first = self._cube("part_a")
        second = self._cube("part_b", location=(5.0, 0.0, 0.0))
        mark_part_root(first)
        mark_part_root(second)
        cutter = build_sketch_on_workplane(self.context, self.datum)
        obj = cutter.target_object

        from ..utilities.body import body_of

        body = body_of(obj)
        self.assertIsNone(settle_membership(obj, [first, second]))
        self.assertIsNone(part_root_of(obj))
        self.assertFalse(is_part_root(body))
        # Still free to move, like any global sketch's body.
        self.assertEqual(tuple(body.lock_location), (False, False, False))

    def test_a_cut_through_two_bodies_of_one_part_joins_it(self):
        root = self._cube("part_a")
        mark_part_root(root)
        second_body = self._cube("second_body", location=(1.0, 0.0, 0.0))
        join_part(root, second_body)
        cutter = build_sketch_on_workplane(self.context, self.datum)

        self.assertEqual(
            settle_membership(cutter.target_object, [root, second_body]), root
        )
        self.assertEqual(part_root_of(cutter.target_object), root)

    def test_a_cut_across_two_bare_bodies_stays_global(self):
        first = self._cube("bare_a")
        second = self._cube("bare_b", location=(5.0, 0.0, 0.0))
        cutter = build_sketch_on_workplane(self.context, self.datum)

        self.assertIsNone(settle_membership(cutter.target_object, [first, second]))
        self.assertFalse(is_part_root(first))
        self.assertFalse(is_part_root(second))

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

    def test_reconcile_settles_and_then_goes_quiet(self):
        sketch = build_sketch_on_workplane(self.context, self.datum)
        mark_part_root(sketch.target_object)
        wp = bpy.data.objects.new("WP", None)
        self.scene.collection.objects.link(wp)
        join_part(sketch.target_object, wp)

        # The first pass notices the new member; nothing changes after that.
        self.assertTrue(reconcile_parts(self.scene))
        self.assertFalse(reconcile_parts(self.scene))
        self.assertFalse(reconcile_parts(self.scene))

    def test_moving_a_part_carries_its_solved_geometry(self):
        from ..utilities.body import body_of

        sketch = build_sketch_on_workplane(self.context, self.datum)
        root = body_of(sketch.target_object)
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

    def _focus(self, obj):
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        self.context.view_layer.objects.active = obj

    def test_part_planes_sit_in_the_parts_own_frame(self):
        from ..utilities.part import PART_PLANE_KEY, ensure_part_planes

        body = self._cube("moved")
        mark_part_root(body)
        body.matrix_basis = Matrix.Translation(
            Vector((3.0, 0.0, 0.0))
        ) @ Matrix.Rotation(1.0, 4, "Y")
        self.context.view_layer.update()

        planes = ensure_part_planes(self.context, body)
        self.assertEqual([p[PART_PLANE_KEY] for p in planes], ["XY", "XZ", "YZ"])
        for plane in planes:
            self.assertEqual(plane.type, "EMPTY")
            self.assertEqual(part_root_of(plane), body)

        self.context.view_layer.update()
        xy = planes[0]
        # A moved, rotated part offers planes in its frame, not the world's.
        self.assertEqual(xy.matrix_world.translation, Vector((3.0, 0.0, 0.0)))
        self.assertEqual(
            xy.matrix_world.to_quaternion(), body.matrix_basis.to_quaternion()
        )

    def test_part_planes_are_created_once(self):
        from ..utilities.part import ensure_part_planes

        body = self._cube("host")
        mark_part_root(body)
        first = ensure_part_planes(self.context, body)
        again = ensure_part_planes(self.context, body)
        self.assertEqual(first, again)

    def test_part_planes_are_drawn_smaller_than_the_world_planes(self):
        from ..utilities.workplane import (
            WP_ID_PART_XY,
            WP_ID_XY,
            wp_plane_bounds,
        )

        def side(pick_id):
            min_x, _min_y, max_x, _max_y = wp_plane_bounds(self.context, pick_id)
            return max_x - min_x

        self.assertLess(side(WP_ID_PART_XY), side(WP_ID_XY))

    def test_only_the_focused_parts_planes_are_offered(self):
        from ..utilities.part import ensure_part_planes, part_plane_objects

        body = self._cube("host")
        mark_part_root(body)
        ensure_part_planes(self.context, body)

        self._focus(body)
        self.assertEqual(len(part_plane_objects(self.context)), 3)

        bpy.ops.object.select_all(action="DESELECT")
        self.context.view_layer.objects.active = None
        self.assertEqual(part_plane_objects(self.context), [])

    def test_a_sketch_on_a_part_plane_joins_that_part(self):
        from ..utilities.part import ensure_part_planes

        body = self._cube("host")
        mark_part_root(body)
        wp = ensure_part_planes(self.context, body)[0]

        sketch = build_sketch_on_workplane(self.context, wp)
        self.assertEqual(part_root_of(sketch.target_object), body)

    def test_a_plane_that_loses_its_part_becomes_an_ordinary_workplane(self):
        from ..utilities.body import body_of
        from ..utilities.part import PART_PLANE_KEY, ensure_part_planes

        sketch = build_sketch_on_workplane(self.context, self.datum)
        root = body_of(sketch.target_object)
        mark_part_root(root)
        plane = ensure_part_planes(self.context, root)[0]
        member = build_sketch_on_workplane(self.context, plane)

        reconcile_parts(self.scene)
        bpy.data.objects.remove(root)
        self.assertTrue(reconcile_parts(self.scene))

        # It no longer stands for a frame it is not in; it stays where it was.
        self.assertNotIn(PART_PLANE_KEY, plane)
        self.assertEqual(part_root_of(plane), member.target_object)

    def test_every_drawable_plane_has_a_colour_and_label(self):
        # The draw handler indexes both maps by pick id, so a plane that is
        # offered without an entry raises mid-draw (KeyError on the axis colour).
        from ..utilities.part import ensure_part_planes
        from ..utilities.workplane import (
            ORIGIN_AXIS_COLOR,
            ORIGIN_LABEL,
            iter_wp_empties,
            wp_plane_bounds,
        )

        body = self._cube("host")
        mark_part_root(body)
        ensure_part_planes(self.context, body)
        self._focus(body)

        ids = [pick_id for _plane, pick_id in iter_wp_empties(self.context)]
        self.assertTrue(any(pick_id in ORIGIN_LABEL for pick_id in ids))
        for pick_id in ids:
            if pick_id in ORIGIN_LABEL:
                self.assertIn(pick_id, ORIGIN_AXIS_COLOR)
            # Bounds are looked up per drawn plane too.
            self.assertEqual(len(wp_plane_bounds(self.context, pick_id)), 4)

    def test_part_planes_are_hidden_and_unselectable(self):
        from ..utilities.part import ensure_part_planes

        body = self._cube("host")
        mark_part_root(body)
        for plane in ensure_part_planes(self.context, body):
            self.assertTrue(plane.hide_select)
            self.assertFalse(plane.hide_viewport)  # must stay evaluated
            self.assertFalse(plane.visible_get())

    def test_part_planes_can_be_created_for_a_plain_mesh_part(self):
        # They must end up reachable from the scene, or hiding them raises. Where
        # exactly is the collection sync's business (the part's own collection).
        from ..utilities.part import ensure_part_planes

        body = self._cube("plain")
        mark_part_root(body)
        planes = ensure_part_planes(self.context, body)
        for plane in planes:
            self.assertIn(plane.name, self.scene.collection.all_objects)
            self.assertTrue(plane.users_collection)

    def test_parenting_into_a_part_adopts_the_sketch(self):
        body = self._cube("host")
        mark_part_root(body)
        sketch = build_sketch_on_workplane(self.context, self.datum)
        obj = sketch.target_object

        # What Ctrl+P / an outliner drag does, nothing more.
        obj.parent = body

        self.assertTrue(reconcile_parts(self.scene))
        self.assertEqual(part_root_of(obj), body)
        # It is a feature now, so it no longer moves on its own.
        self.assertEqual(tuple(obj.lock_location), (True, True, True))

        # Nothing further to do on the next pass.
        self.assertFalse(reconcile_parts(self.scene))

    def test_unparenting_releases_a_member(self):
        body = self._cube("host")
        mark_part_root(body)
        sketch = build_sketch_on_workplane(self.context, self.datum)
        obj = sketch.target_object
        join_part(body, obj)
        reconcile_parts(self.scene)

        obj.parent = None

        self.assertTrue(reconcile_parts(self.scene))
        self.assertIsNone(part_root_of(obj))
        # Free to move again, as a global sketch is.
        self.assertEqual(tuple(obj.lock_location), (False, False, False))
        self.assertFalse(reconcile_parts(self.scene))

    def test_moving_a_sketch_between_parts_follows_the_parent(self):
        first = self._cube("part_a")
        second = self._cube("part_b", location=(4.0, 0.0, 0.0))
        mark_part_root(first)
        mark_part_root(second)
        sketch = build_sketch_on_workplane(self.context, self.datum)
        obj = sketch.target_object
        join_part(first, obj)
        reconcile_parts(self.scene)

        obj.parent = second
        reconcile_parts(self.scene)
        self.assertEqual(part_root_of(obj), second)

    def test_a_users_own_object_keeps_its_transform_freedom(self):
        # Parenting a plain mesh into a part must not lock it: it is theirs.
        body = self._cube("host")
        mark_part_root(body)
        mesh = self._cube("theirs", location=(0.0, 2.0, 0.0))

        mesh.parent = body
        self.assertTrue(reconcile_parts(self.scene))
        self.assertEqual(part_root_of(mesh), body)
        self.assertEqual(tuple(mesh.lock_location), (False, False, False))

    def test_a_free_3d_sketch_roots_its_part_in_its_origin_empty(self):
        # The Empty owns the transform, so it is what the part must be rooted in;
        # rooting the sketch would leave two movable things to disagree.
        from ..model.native_3d import create_3d_sketch
        from ..utilities.part import transform_owner

        sketch = create_3d_sketch(self.context)
        obj = sketch.target_object
        origin = obj.parent
        self.assertTrue(origin.get("is_3d_sketch_origin", False))
        self.assertEqual(transform_owner(obj), origin)

        self.assertEqual(settle_membership(obj, []), origin)
        self.assertTrue(is_part_root(origin))
        self.assertFalse(is_part_root(obj))
        self.assertEqual(part_root_of(obj), origin)
        # The sketch stays pinned to its origin; the Empty is the handle.
        self.assertEqual(tuple(obj.lock_location), (True, True, True))
        self.assertEqual(tuple(origin.lock_location), (False, False, False))

    def test_a_free_3d_sketch_joins_a_part_by_its_origin(self):
        from ..model.native_3d import create_3d_sketch

        body = self._cube("host")
        mark_part_root(body)
        sketch = create_3d_sketch(self.context)
        origin = sketch.target_object.parent

        self.assertEqual(settle_membership(sketch.target_object, [body]), body)
        self.assertEqual(part_root_of(origin), body)
        self.assertEqual(origin.parent, body)

    def test_a_face_workplane_is_hidden_but_still_pickable(self):
        # Its axes would otherwise draw in every mode; the Add Sketch picker
        # draws the plane itself while you are choosing one.
        from ..utilities.workplane import is_managed_workplane, iter_wp_empties

        body = self._cube("host")
        wp = create_face_workplane(self.context, body, 0)

        self.assertTrue(is_managed_workplane(wp))
        self.assertFalse(wp.visible_get())
        self.assertTrue(wp.hide_select)
        # Never hide_viewport: the anchor recomputes from evaluated geometry.
        self.assertFalse(wp.hide_viewport)

        offered = {obj.name for obj, _pick_id in iter_wp_empties(self.context)}
        self.assertIn(wp.name, offered)

    def test_an_empty_the_user_hid_is_not_offered(self):
        from ..utilities.workplane import iter_wp_empties

        theirs = bpy.data.objects.new("their_empty", None)
        self.scene.collection.objects.link(theirs)
        self.context.view_layer.update()
        self.assertIn(theirs.name, {o.name for o, _ in iter_wp_empties(self.context)})

        theirs.hide_set(True)
        self.assertNotIn(
            theirs.name, {o.name for o, _ in iter_wp_empties(self.context)}
        )

    def test_a_focused_parts_planes_stand_in_for_the_world_ones(self):
        # Six rectangles for three choices is a crowded viewport; while a part is
        # in focus its own frame is the one being worked in.
        from ..utilities.part import ensure_part_planes
        from ..utilities.workplane import iter_wp_empties

        body = self._cube("host")
        mark_part_root(body)
        ensure_part_planes(self.context, body)

        bpy.ops.object.select_all(action="DESELECT")
        self.context.view_layer.objects.active = None
        world = {obj.name for obj, _ in iter_wp_empties(self.context)}
        self.assertIn(self.context.scene.sketcher.wp_xy.name, world)

        self._focus(body)
        focused = {obj.name for obj, _ in iter_wp_empties(self.context)}
        self.assertIn(f"{body.name} XY", focused)
        self.assertNotIn(self.context.scene.sketcher.wp_xy.name, focused)

    def test_a_part_plane_is_told_apart_from_the_scenes(self):
        # They replace each other on screen, so the axis alone would not say
        # which frame you are about to sketch in.
        from ..utilities.part import ensure_part_planes
        from ..utilities.workplane import (
            WP_ID_PART_XY,
            WP_ID_XY,
            workplane_label,
        )

        body = self._cube("bracket")
        mark_part_root(body)
        plane = ensure_part_planes(self.context, body)[0]

        self.assertEqual(workplane_label(plane, WP_ID_PART_XY), "XY")
        self.assertEqual(
            workplane_label(self.context.scene.sketcher.wp_xy, WP_ID_XY), "Origin XY"
        )

    def test_part_planes_are_still_smaller_than_the_world_ones(self):
        from ..utilities.workplane import (
            WP_ID_PART_XY,
            WP_ID_XY,
            wp_plane_bounds,
        )

        def side(pick_id):
            min_x, _min_y, max_x, _max_y = wp_plane_bounds(self.context, pick_id)
            return max_x - min_x

        self.assertLess(side(WP_ID_PART_XY), side(WP_ID_XY))

    def test_focus_follows_the_selection_not_the_lingering_active_object(self):
        # Blender keeps an object active after it is deselected, so focus read
        # from the active object alone would stick and the world planes would
        # never come back.
        from ..utilities.part import focused_part

        body = self._cube("host")
        mark_part_root(body)
        self._focus(body)
        self.assertEqual(focused_part(self.context), body)

        bpy.ops.object.select_all(action="DESELECT")
        self.assertEqual(
            self.context.view_layer.objects.active,
            body,
            "still active, as Blender does",
        )
        self.assertIsNone(focused_part(self.context))

    def test_an_unfocused_parts_planes_are_not_drawn(self):
        # They are managed workplanes, so the generic branch would offer them
        # even while hidden: three unlabelled grey rectangles per part.
        from ..utilities.part import ensure_part_planes
        from ..utilities.workplane import iter_wp_empties

        body = self._cube("host")
        mark_part_root(body)
        planes = ensure_part_planes(self.context, body)

        bpy.ops.object.select_all(action="DESELECT")
        self.context.view_layer.objects.active = None

        offered = {obj.name for obj, _ in iter_wp_empties(self.context)}
        for plane in planes:
            self.assertNotIn(plane.name, offered)
