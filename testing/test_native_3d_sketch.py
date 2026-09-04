"""Regression coverage for native free-3D sketches (#607)."""

import math

from mathutils import Matrix, Vector

from .utils import BgsTestCase


class TestNative3DSketch(BgsTestCase):
    def setUp(self):
        from ..model.native_3d import create_3d_sketch
        from ..model.sketch_ref import set_active_sketch

        self.sketch = create_3d_sketch(self.context, self._testMethodName)
        set_active_sketch(self.context, self.sketch)
        return super().setUp()

    def tearDown(self):
        from ..model.sketch_ref import set_active_sketch

        set_active_sketch(self.context, None)
        self.sketch.remove_objects()
        return super().tearDown()

    def test_sketch_uses_origin_empty_without_workplane_constraint(self):
        obj = self.sketch.target_object
        origin = obj.parent

        self.assertIsNotNone(origin)
        self.assertEqual(origin.type, "EMPTY")
        self.assertTrue(origin.get("is_3d_sketch_origin", False))
        self.assertEqual(self.sketch.workplane_object, origin)
        self.assertEqual(tuple(obj.lock_location), (True, True, True))
        self.assertEqual(tuple(obj.lock_rotation), (True, True, True))
        self.assertEqual(tuple(obj.lock_scale), (True, True, True))

    def test_3d_sketch_disables_planar_fill_by_default(self):
        from ..operators.modifiers import get_modifier_input

        obj = self.sketch.target_object
        modifier = obj.modifiers.get("CAD Sketcher Convert")
        self.assertIsNotNone(modifier)
        self.assertIsNotNone(modifier.node_group)

        fill_socket = next(
            item
            for item in modifier.node_group.interface.items_tree
            if getattr(item, "item_type", "") == "SOCKET"
            and getattr(item, "in_out", "") == "INPUT"
            and item.name == "Fill"
        )
        self.assertFalse(get_modifier_input(modifier, fill_socket.identifier))

    def test_axis_and_plane_lock_geometry(self):
        from ..operators.base_sketch_3d import resolve_locked_position

        anchor = Vector((1.0, 1.0, 1.0))
        point = Vector((2.0, 3.0, 4.0))

        x_axis = resolve_locked_position(point, anchor, axis_lock=0)
        self.assertLess((x_axis - Vector((2.0, 1.0, 1.0))).length, 1e-6)

        yz_plane = resolve_locked_position(point, anchor, plane_lock=0)
        self.assertLess((yz_plane - Vector((1.0, 3.0, 4.0))).length, 1e-6)

        xy_plane = resolve_locked_position(point, anchor, plane_lock=2)
        self.assertLess((xy_plane - Vector((2.0, 3.0, 1.0))).length, 1e-6)

    def test_origin_is_default_view_plane_depth(self):
        from ..operators.base_sketch_3d import view_plane_intersection

        origin = self.sketch.target_object.parent
        origin.location = (4.0, -3.0, 7.0)
        self.context.view_layer.update()
        anchor = origin.matrix_world.translation

        # A view ray along -Z must land on the plane through the sketch origin,
        # not on the global XY plane. The resulting Z therefore follows the
        # moved origin exactly.
        hit = view_plane_intersection(
            (10.0, 20.0, 20.0),
            (10.0, 20.0, -20.0),
            anchor,
            (0.0, 0.0, 1.0),
        )
        self.assertLess((hit - Vector((10.0, 20.0, 7.0))).length, 1e-6)

        # A ray parallel to the temporary plane has no geometric intersection;
        # the placement fallback remains the origin depth anchor, not world zero.
        parallel = view_plane_intersection(
            (10.0, 20.0, 7.0),
            (30.0, 20.0, 7.0),
            anchor,
            (0.0, 0.0, 1.0),
        )
        self.assertLess((parallel - anchor).length, 1e-6)

    def test_points_and_lines_preserve_xyz(self):
        from ..model.native_3d import create_line_3d, create_point_3d, is_3d_sketch
        from ..utilities.curve_data import get_curve_data

        p1 = create_point_3d(self.sketch, (1.0, 2.0, 3.0), fixed=True)
        p2 = create_point_3d(self.sketch, (4.0, 6.0, 8.0))
        line = create_line_3d(self.sketch, p1, p2)

        self.assertTrue(is_3d_sketch(self.sketch))
        self.assertAlmostEqual(p1.location.z, 3.0)
        self.assertAlmostEqual(p2.location.z, 8.0)
        self.assertAlmostEqual(
            (line.p2.location - line.p1.location).length, 7.0710678, places=5
        )

        # Verify the LINE curve itself stores full XYZ, not merely its PointRef
        # endpoints. This catches the interactive regression where points were
        # correctly 3D but the generated segment was flattened to XY.
        curve_data, _curve_idx, curve_slice = get_curve_data(self.sketch, line.curve_id)
        self.assertIsNotNone(curve_data)
        positions = [
            Vector(curve_data.points[point.index].position).to_3d()
            for point in curve_slice.points
        ]
        self.assertLess((positions[0] - Vector((1.0, 2.0, 3.0))).length, 1e-6)
        self.assertLess((positions[1] - Vector((4.0, 6.0, 8.0))).length, 1e-6)
        self.assertGreater(abs(positions[0].z), 1e-6)
        self.assertGreater(abs(positions[1].z), 1e-6)

    def test_late_xy_flatten_is_restored_from_native_3d_endpoints(self):
        from ..model.native_3d import create_line_3d, create_point_3d
        from ..operators.base_sketch_3d import restore_native_3d_segments
        from ..utilities.curve_data import get_curve_data

        p1 = create_point_3d(self.sketch, (1.0, 2.0, 3.0), fixed=True)
        p2 = create_point_3d(self.sketch, (4.0, 6.0, 8.0), fixed=True)
        line = create_line_3d(self.sketch, p1, p2)

        curve_data, _curve_idx, curve_slice = get_curve_data(self.sketch, line.curve_id)
        self.assertIsNotNone(curve_data)

        # Reproduce the real regression: a late legacy 2D path rewrites only the
        # segment geometry to XY while the authoritative endpoint curves stay 3D.
        for point, source in zip(curve_slice.points, (p1, p2)):
            source_local = source._first_point_3d()
            curve_data.points[point.index].position = (
                source_local.x,
                source_local.y,
                0.0,
            )

        flattened = [
            Vector(curve_data.points[point.index].position).to_3d()
            for point in curve_slice.points
        ]
        self.assertEqual(flattened[0].z, 0.0)
        self.assertEqual(flattened[1].z, 0.0)
        self.assertAlmostEqual(p1.location.z, 3.0)
        self.assertAlmostEqual(p2.location.z, 8.0)

        restore_native_3d_segments(self.sketch)

        restored = [
            Vector(curve_data.points[point.index].position).to_3d()
            for point in curve_slice.points
        ]
        self.assertLess((restored[0] - Vector((1.0, 2.0, 3.0))).length, 1e-6)
        self.assertLess((restored[1] - Vector((4.0, 6.0, 8.0))).length, 1e-6)

    def test_origin_transform_moves_rendered_3d_geometry(self):
        from ..drawing import render_data
        from ..model.native_3d import create_line_3d, create_point_3d
        from ..utilities.preferences import get_prefs

        p1 = create_point_3d(self.sketch, (1.0, 0.0, 0.0), fixed=True)
        p2 = create_point_3d(self.sketch, (0.0, 2.0, 1.0), fixed=True)
        line = create_line_3d(self.sketch, p1, p2)
        origin = self.sketch.target_object.parent

        before = render_data.geometry_signature(self.sketch)
        local_p1 = Vector((1.0, 0.0, 0.0))
        local_p2 = Vector((0.0, 2.0, 1.0))

        origin.matrix_world = Matrix.Translation((5.0, -2.0, 3.0)) @ Matrix.Rotation(
            math.radians(90.0), 4, "Z"
        )
        self.context.view_layer.update()

        after = render_data.geometry_signature(self.sketch)
        self.assertNotEqual(before, after)

        expected_p1 = origin.matrix_world @ local_p1
        expected_p2 = origin.matrix_world @ local_p2
        data = render_data.build(
            self.sketch,
            get_prefs().theme_settings.entity,
            is_active=True,
        )
        point_world = {cid: Vector(pos) for cid, pos in data.point_ids}
        self.assertLess((point_world[p1.curve_id] - expected_p1).length, 1e-5)
        self.assertLess((point_world[p2.curve_id] - expected_p2).length, 1e-5)

        segment = next(item for item in data.segment_ids if item[0] == line.curve_id)
        self.assertLess((Vector(segment[1]) - expected_p1).length, 1e-5)
        self.assertLess((Vector(segment[2]) - expected_p2).length, 1e-5)

        # A solve/depsgraph pass must not bake the origin transform back into the
        # native coordinates or visually reset the sketch to its old position.
        self.assertTrue(self.sketch.solve(self.context))
        self.context.view_layer.update()
        solved = render_data.build(
            self.sketch,
            get_prefs().theme_settings.entity,
            is_active=True,
        )
        solved_world = {cid: Vector(pos) for cid, pos in solved.point_ids}
        self.assertLess((solved_world[p1.curve_id] - expected_p1).length, 1e-5)
        self.assertLess((solved_world[p2.curve_id] - expected_p2).length, 1e-5)

    def test_distance_solves_in_free_3d_and_dimension_is_world_space(self):
        from ..model.native_3d import create_line_3d, create_point_3d

        p1 = create_point_3d(self.sketch, (0.0, 0.0, 0.0), fixed=True)
        p2 = create_point_3d(self.sketch, (0.0, 0.0, 4.0))
        create_line_3d(self.sketch, p1, p2)

        distance = self.sketch.constraints.add_distance(
            curve_id_1=p1.curve_id,
            curve_id_2=p2.curve_id,
            value=5.0,
        )

        self.assertFalse(distance.use_align())
        self.assertTrue(self.sketch.solve(self.context))
        self.assertAlmostEqual((p2.location - p1.location).length, 5.0, places=4)
        self.assertGreater(abs(p2.location.z), 1e-4)

        matrix = distance.matrix_basis()
        expected_midpoint = (p1.location + p2.location) / 2.0
        self.assertLess((matrix.translation - expected_midpoint).length, 1e-5)

        dimension_axis = Vector(matrix.col[0][:3]).normalized()
        solved_axis = (p2.location - p1.location).normalized()
        self.assertAlmostEqual(abs(dimension_axis.dot(solved_axis)), 1.0, places=5)

    def test_unsupported_3d_constraint_is_flagged_failed(self):
        # Only distance is dispatched in free-3D; any other constraint must be
        # flagged failed after a solve rather than silently ignored.
        from ..model.native_3d import create_point_3d

        p1 = create_point_3d(self.sketch, (0.0, 0.0, 0.0), fixed=True)
        p2 = create_point_3d(self.sketch, (1.0, 0.0, 0.0))
        coincident = self.sketch.constraints.add_coincident(
            curve_id_1=p1.curve_id, curve_id_2=p2.curve_id
        )
        distance = self.sketch.constraints.add_distance(
            curve_id_1=p1.curve_id, curve_id_2=p2.curve_id, value=2.0
        )

        self.sketch.solve(self.context)

        self.assertTrue(coincident.failed, "unsupported 3D constraint not flagged")
        self.assertFalse(distance.failed, "supported distance wrongly flagged")
