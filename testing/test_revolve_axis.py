"""Revolving around a base plane's own axis.

An axis is not an object: it is a direction of one of the XY/XZ/YZ empties. The
plane is parented into its part, so an axis read off it stays that part's axis
and moves with it (see utilities.workplane).
"""

import math

import bmesh
import bpy
from mathutils import Matrix, Vector

from ..utilities.part import ensure_part_planes, mark_part_root
from ..utilities.workplane import (
    AXIS_ID_X,
    AXIS_ID_Y,
    AXIS_ID_Z,
    axis_by_pick_id,
    axis_endpoints,
    axis_label,
    axis_plane,
    ensure_origin_workplane_empties,
    iter_axis_candidates,
)
from .utils import BgsTestCase


class TestRevolveAxis(BgsTestCase):
    def setUp(self):
        super().setUp()
        self.entities.ensure_origin_elements(self.context)
        ensure_origin_workplane_empties(self.context)

    def _cube(self, name="body"):
        me = bpy.data.meshes.new(name)
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=2.0)
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(name, me)
        self.scene.collection.objects.link(ob)
        return ob

    def _focus(self, obj):
        for other in self.scene.objects:
            other.select_set(False)
        self.context.view_layer.update()
        obj.select_set(True)
        self.context.view_layer.objects.active = obj

    def test_the_scenes_axes_are_offered_by_default(self):
        for other in self.scene.objects:
            other.select_set(False)
        self.context.view_layer.update()

        offered = list(iter_axis_candidates(self.context))
        self.assertEqual(
            [pick_id for _p, _i, pick_id in offered], [AXIS_ID_X, AXIS_ID_Y, AXIS_ID_Z]
        )
        self.assertEqual(axis_plane(self.context), self.context.scene.sketcher.wp_xy)
        self.assertEqual(
            axis_label(*axis_by_pick_id(self.context, AXIS_ID_Z)), "Origin Z"
        )

        # They point along the world axes, from the world origin.
        for index, expected in enumerate(
            (Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1)))
        ):
            plane, _index = axis_by_pick_id(
                self.context, (AXIS_ID_X, AXIS_ID_Y, AXIS_ID_Z)[index]
            )
            start, end = axis_endpoints(plane, index)
            self.assertEqual(start, Vector((0, 0, 0)))
            self.assertAlmostEqual(
                (end - start).normalized().dot(expected), 1.0, places=5
            )

    def test_a_part_in_focus_offers_its_own_axes(self):
        body = self._cube("bracket")
        mark_part_root(body)
        ensure_part_planes(self.context, body)
        body.matrix_basis = Matrix.Translation(
            Vector((3.0, 0.0, 0.0))
        ) @ Matrix.Rotation(math.pi / 2, 4, "Z")
        self.context.view_layer.update()
        self._focus(body)

        plane, index = axis_by_pick_id(self.context, AXIS_ID_X)
        self.assertEqual(plane.get("slvs:part_plane"), "XY")
        self.assertEqual(axis_label(plane, index), f"{body.name} X")

        start, end = axis_endpoints(plane, index)
        # Its own frame: rooted at the part, turned with it.
        self.assertAlmostEqual((start - Vector((3.0, 0.0, 0.0))).length, 0.0, places=5)
        self.assertAlmostEqual(
            (end - start).normalized().dot(Vector((0, 1, 0))), 1.0, places=5
        )

    def test_moving_the_part_moves_its_axis(self):
        body = self._cube("bracket")
        mark_part_root(body)
        ensure_part_planes(self.context, body)
        self._focus(body)
        plane, index = axis_by_pick_id(self.context, AXIS_ID_Z)

        body.matrix_basis = Matrix.Translation(Vector((0.0, 5.0, 0.0)))
        self.context.view_layer.update()

        start, _end = axis_endpoints(plane, index)
        self.assertAlmostEqual((start - Vector((0.0, 5.0, 0.0))).length, 0.0, places=5)

    def test_the_operator_resolves_a_plane_pointer_to_that_axis(self):
        # What a pick stores is the plane empty plus which direction it is; the
        # revolve reads its endpoints back from that, live.
        from ..operators.modifiers import View3D_OT_node_revolve
        from .utils import make_operator_double

        body = self._cube("bracket")
        mark_part_root(body)
        planes = ensure_part_planes(self.context, body)
        self._focus(body)

        op = make_operator_double(View3D_OT_node_revolve)()
        op.get_state_pointer = lambda index=1, implicit=True: (planes[0].name, 2)

        ends = op._axis_endpoints()
        self.assertIsNotNone(ends)
        start, end = ends
        self.assertAlmostEqual(
            (end - start).normalized().dot(Vector((0, 0, 1))), 1.0, places=5
        )

    def test_the_axes_are_only_drawn_while_one_is_being_picked(self):
        from .. import global_data
        from ..operators.modifiers import View3D_OT_node_revolve
        from .utils import make_operator_double

        op = make_operator_double(View3D_OT_node_revolve)()
        states = op.get_states()
        axis_index = next(i for i, state in enumerate(states) if state.name == "Axis")

        op.set_state(self.context, 0)
        self.assertFalse(global_data.axis_picker)
        op.set_state(self.context, axis_index)
        self.assertTrue(global_data.axis_picker)

        op.fini(self.context, False)
        self.assertFalse(global_data.axis_picker)
        self.assertIsNone(global_data.hover_axis)
