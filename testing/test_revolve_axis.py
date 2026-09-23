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

        # They run along the world axes, through the world origin, reaching the
        # same distance either side of it.
        for index, expected in enumerate(
            (Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1)))
        ):
            plane, _index = axis_by_pick_id(
                self.context, (AXIS_ID_X, AXIS_ID_Y, AXIS_ID_Z)[index]
            )
            start, end = axis_endpoints(plane, index)
            self.assertAlmostEqual(((start + end) / 2.0).length, 0.0, places=5)
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
        # Its own frame: centred on the part, turned with it.
        middle = (start + end) / 2.0
        self.assertAlmostEqual((middle - Vector((3.0, 0.0, 0.0))).length, 0.0, places=5)
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

        start, end = axis_endpoints(plane, index)
        middle = (start + end) / 2.0
        self.assertAlmostEqual((middle - Vector((0.0, 5.0, 0.0))).length, 0.0, places=5)

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

    def test_the_hovered_axis_is_published_for_the_highlight(self):
        # The hover gizmo is what runs on mouse-move; pick_element only runs on
        # a click, which is why nothing lit up before.
        from .. import global_data
        from ..gizmos.object_hover import detect_axis_hover

        global_data.hover_axis = None
        try:
            # Nothing when no state is picking an axis.
            global_data.axis_picker = False
            self.assertIsNone(detect_axis_hover(self.context, Vector((0.0, 0.0))))
        finally:
            global_data.axis_picker = False
            global_data.hover_axis = None

    def test_an_axis_is_picked_before_the_geometry_behind_it(self):
        # The axes are drawn on top and run through the part, so a mesh pick
        # would otherwise always win and the axis could never be clicked.
        import inspect

        from ..operators.modifiers import View3D_OT_node_revolve

        source = inspect.getsource(View3D_OT_node_revolve.pick_element)
        axis_at = source.index("hit_test_axis(context, coords, radius)")
        mesh_at = source.index("super().pick_element(context, coords)")
        self.assertLess(axis_at, mesh_at, "the axis hit test must come first")

    def test_the_axes_come_back_for_a_re_pick(self):
        # The eyedropper re-pick starts in one state without running the tool
        # from the top, and the redo-panel re-run calls fini() behind it, which
        # put the axes away mid-pick.
        from .. import global_data
        from ..operators.modifiers import View3D_OT_node_revolve
        from .utils import make_operator_double

        op = make_operator_double(View3D_OT_node_revolve)()
        states = op.get_states()
        op.edit_state = next(
            i for i, state in enumerate(states) if state.name == "Axis"
        )
        op._hidden_modifier = None

        global_data.axis_picker = False
        try:
            op._maintain_pick_ui(self.context)
            self.assertTrue(global_data.axis_picker, "a re-pick must show them")

            op.fini(self.context, False)  # what the redo-panel re-run triggers
            op._maintain_pick_ui(self.context)
            self.assertTrue(global_data.axis_picker, "and keep showing them")

            op._finish_pick_ui(self.context)
            self.assertFalse(global_data.axis_picker)
        finally:
            global_data.axis_picker = False
            global_data.hover_axis = None

    def test_the_negative_half_picks_too(self):
        # Reported: the axes draw both ways from the frame but only highlighted
        # and picked on the positive side, because the hit test ran on a ray.
        from ..utilities.workplane import _distance_to_segment

        plane, index = axis_by_pick_id(self.context, AXIS_ID_X)
        start, end = axis_endpoints(plane, index, self.context)
        middle = (start + end) / 2.0

        # A point a little way along each half lies on the tested segment.
        for point in (middle + (end - middle) * 0.5, middle + (start - middle) * 0.5):
            self.assertAlmostEqual(
                _distance_to_segment(point.xy, start.xy, end.xy), 0.0, places=4
            )
