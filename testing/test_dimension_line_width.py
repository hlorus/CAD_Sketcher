"""Dimension line width: the stroke math, how it is drawn, and picking."""

import types
import unittest.mock as mock
from unittest import TestCase

import gpu
from mathutils import Matrix

from .. import global_data
from ..drawing import frame_cache, selection
from ..gizmos import base as gizmo_base
from ..gizmos.angle import VIEW3D_GT_slvs_angle
from ..gizmos.base import (
    ConstraintGizmoGeneric,
    _draw_dimension_lines,
    _line_batch,
    _local_to_world,
)
from ..gizmos.diameter import VIEW3D_GT_slvs_diameter
from ..gizmos.distance import VIEW3D_GT_slvs_distance
from ..gizmos.utilities import _BASE_WIDTH, dimension_line_widths
from ..shaders import Shaders
from ..utilities.preferences import get_prefs
from .utils import Sketch2dTestCase


def _view_context(base):
    """A context whose interface scale is 1, even in a background session.

    ``preferences.system.ui_scale`` is 0 without a display, and the dimension
    geometry divides by it.
    """
    ctx = types.SimpleNamespace()
    ctx.scene = base.scene
    ctx.preferences = types.SimpleNamespace(system=types.SimpleNamespace(ui_scale=1.0))
    # view_scale_key memos on the region's pointer, which a real RegionView3D has.
    region_data = types.SimpleNamespace(view_perspective="ORTHO", view_distance=8.0)
    region_data.as_pointer = lambda: id(region_data)
    ctx.region_data = region_data
    ctx.region = types.SimpleNamespace(width=512, height=512)
    return ctx


class _DimProbe:
    """Enough of a gizmo to build a dimension's line list, without GPU drawing."""

    def __init__(self, gizmo_cls, offset, basis):
        self.matrix_world = basis
        self._offset = offset
        self._create_shape = gizmo_cls._create_shape.__get__(self, _DimProbe)
        # _ensure_shape goes through these; bind them so a plain probe can host them.
        self._update_matrix_basis = ConstraintGizmoGeneric._update_matrix_basis.__get__(
            self, _DimProbe
        )
        self._shape_signature = ConstraintGizmoGeneric._shape_signature.__get__(
            self, _DimProbe
        )
        if hasattr(gizmo_cls, "_get_helplines"):
            self._get_helplines = gizmo_cls._get_helplines.__get__(self, _DimProbe)

    def target_get_value(self, _name):
        return self._offset


def _shape(gizmo_cls, context, constr, offset):
    basis = constr.matrix_basis()
    return _DimProbe(gizmo_cls, offset, basis)._create_shape(context, constr)


class _RecordingShader:
    def __init__(self):
        self.uniforms = []

    def bind(self):
        return None

    def uniform_float(self, name, value):
        self.uniforms.append((name, value))


class _RecordingBatch:
    def __init__(self):
        self.draws = 0

    def draw(self, _shader):
        self.draws += 1


class TestDimensionLineWidths(TestCase):
    def setUp(self):
        self.prefs = get_prefs()
        self._scale = self.prefs.dimension_line_scale

    def tearDown(self):
        self.prefs.dimension_line_scale = self._scale

    def test_default_scale_draws_both_strokes_at_the_base_width(self):
        self.prefs.dimension_line_scale = 1.0
        leader, witness = dimension_line_widths()
        self.assertAlmostEqual(leader, _BASE_WIDTH)
        self.assertAlmostEqual(witness, _BASE_WIDTH)

    def test_scale_two_and_four_keep_the_dimension_line_heavier(self):
        for scale, witness in ((2.0, 1.5), (4.0, 2.5)):
            self.prefs.dimension_line_scale = scale
            leader, extension = dimension_line_widths()
            self.assertAlmostEqual(leader, _BASE_WIDTH * scale)
            self.assertAlmostEqual(extension, _BASE_WIDTH * witness)
            self.assertGreater(leader, extension)

    def test_a_thinner_scale_does_not_invert_the_two_widths(self):
        self.prefs.dimension_line_scale = 0.5
        leader, witness = dimension_line_widths()
        self.assertAlmostEqual(leader, _BASE_WIDTH * 0.5)
        self.assertAlmostEqual(witness, leader)


class TestDimensionLineBatch(TestCase):
    def test_local_vertices_are_moved_into_world(self):
        world = _local_to_world(
            Matrix.Translation((1.0, 2.0, 3.0)), ((0.0, 0.0), (1.0, 0.0, 0.0))
        )
        self.assertAlmostEqual(world[0][0], 1.0)
        self.assertAlmostEqual(world[0][1], 2.0)
        self.assertAlmostEqual(world[0][2], 3.0)
        self.assertAlmostEqual(world[1][0], 2.0)
        self.assertAlmostEqual(world[1][2], 3.0)

    def test_an_empty_stroke_is_not_batched(self):
        # Returns before a shader is created, so this holds in background mode.
        self.assertIsNone(_line_batch(Matrix.Identity(4), ()))

    def test_drawing_sets_the_linewidth_uniform_witness_then_leader(self):
        shader = _RecordingShader()
        leader = _RecordingBatch()
        witness = _RecordingBatch()
        context = types.SimpleNamespace(
            region=types.SimpleNamespace(width=800, height=600)
        )
        prefs = get_prefs()
        saved = prefs.dimension_line_scale
        prefs.dimension_line_scale = 4.0
        try:
            with (
                mock.patch.object(Shaders, "polyline_color_3d", return_value=shader),
                mock.patch.object(gpu.state, "blend_set"),
                mock.patch.object(gpu.state, "line_width_set"),
                mock.patch.object(gpu.shader, "unbind"),
            ):
                _draw_dimension_lines(context, leader, witness, (1.0, 0.2, 0.2, 1.0))
        finally:
            prefs.dimension_line_scale = saved

        widths = [value for name, value in shader.uniforms if name == "lineWidth"]
        viewports = [value for name, value in shader.uniforms if name == "viewportSize"]
        # Extension lines are drawn first, then the heavier dimension line.
        self.assertEqual(widths, [_BASE_WIDTH * 2.5, _BASE_WIDTH * 4.0])
        self.assertEqual(viewports, [(800, 600)])
        self.assertEqual(witness.draws, 1)
        self.assertEqual(leader.draws, 1)


class TestDimensionLineRedraw(Sketch2dTestCase):
    def _distance(self):
        points = (
            self.add_point((0.0, 0.0), fixed=True),
            self.add_point((2.0, 0.0), fixed=True),
        )
        constr = self.sketch.constraints.add_distance(
            init=True, curve_id_1=points[0].curve_id, curve_id_2=points[1].curve_id
        )
        constr.draw_offset = 0.4
        return constr

    def test_the_shape_cache_ignores_the_line_scale(self):
        """Changing the preference must not rebuild the geometry batch."""
        frame_cache.begin_frame()
        constr = self._distance()
        basis = constr.matrix_basis()
        before = ConstraintGizmoGeneric._shape_signature(
            None, self.context, constr, basis
        )
        get_prefs().dimension_line_scale = 4.0
        try:
            after = ConstraintGizmoGeneric._shape_signature(
                None, self.context, constr, basis
            )
        finally:
            get_prefs().dimension_line_scale = 1.0
        self.assertEqual(before, after)

    def test_a_repeat_draw_does_not_rebuild_the_batch(self):
        frame_cache.begin_frame()
        constr = self._distance()
        probe = _DimProbe(
            VIEW3D_GT_slvs_distance, constr.draw_offset, constr.matrix_basis()
        )
        probe.as_pointer = lambda: id(probe)
        probe._shape_sig = None
        built = {"n": 0}
        real_create = probe._create_shape

        def counting_create(context, constr):
            built["n"] += 1
            return real_create(context, constr)

        probe._create_shape = counting_create
        probe.new_custom_shape = lambda _typ, coords: coords
        with mock.patch.object(gizmo_base, "_line_batch", return_value="batch"):
            ConstraintGizmoGeneric._ensure_shape(
                probe, _view_context(self.context), constr
            )
            ConstraintGizmoGeneric._ensure_shape(
                probe, _view_context(self.context), constr
            )
        self.assertEqual(built["n"], 1)
        self.assertEqual(probe._leader_batch, "batch")


class TestDimensionLineGeometry(Sketch2dTestCase):
    def setUp(self):
        super().setUp()
        frame_cache.begin_frame()
        self.view = _view_context(self.context)

    def test_distance_angle_and_diameter_each_build_a_stroke(self):
        origin = self.add_point((0.0, 0.0), fixed=True)
        end = self.add_point((2.0, 0.0), fixed=True)
        distance = self.sketch.constraints.add_distance(
            init=True, curve_id_1=origin.curve_id, curve_id_2=end.curve_id
        )
        distance.draw_offset = 0.6
        leader, witness = _shape(VIEW3D_GT_slvs_distance, self.view, distance, 0.6)
        self.assertGreaterEqual(len(leader), 2)
        self.assertEqual(len(leader) % 2, 0)
        self.assertEqual(len(witness), 4)

        corner = self.add_point((4.0, 0.0), fixed=True)
        arm = self.add_point((4.0, 2.0), fixed=True)
        angle = self.sketch.constraints.add_angle(
            init=True,
            curve_id_1=self.add_line(
                corner, self.add_point((6.0, 0.0), fixed=True)
            ).curve_id,
            curve_id_2=self.add_line(corner, arm).curve_id,
        )
        angle.draw_offset = 1.2
        angle.draw_outset = 0.0
        leader, witness = _shape(VIEW3D_GT_slvs_angle, self.view, angle, 1.2)
        self.assertGreaterEqual(len(leader), 2)
        self.assertEqual(len(witness), 4)

        circle = self.add_circle(self.add_point((9.0, 0.0), fixed=True), 0.8)
        diameter = self.sketch.constraints.add_diameter(
            init=True, curve_id_1=circle.curve_id
        )
        diameter.leader_angle = 0.0
        diameter.draw_offset = 0.2
        leader, witness = _shape(VIEW3D_GT_slvs_diameter, self.view, diameter, 0.2)
        self.assertGreaterEqual(len(leader), 2)
        self.assertEqual(witness, ())

    def test_the_pick_shape_is_the_dimension_line_only(self):
        """Extension lines stay out of the select shape, as they did before."""
        frame_cache.begin_frame()
        a = self.add_point((0.0, 0.0), fixed=True)
        b = self.add_point((2.0, 0.0), fixed=True)
        constr = self.sketch.constraints.add_distance(
            init=True, curve_id_1=a.curve_id, curve_id_2=b.curve_id
        )
        constr.draw_offset = 0.5
        probe = _DimProbe(VIEW3D_GT_slvs_distance, 0.5, constr.matrix_basis())
        probe.as_pointer = lambda: id(probe)
        probe._shape_sig = None
        probe.new_custom_shape = lambda typ, coords: (typ, coords)
        with mock.patch.object(gizmo_base, "_line_batch", return_value="batch"):
            ConstraintGizmoGeneric._ensure_shape(probe, self.view, constr)
        primitive, picked = probe.custom_shape
        _leader, witness = probe._create_shape(self.view, constr)
        self.assertEqual(primitive, "LINES")
        self.assertEqual(len(picked) % 2, 0)
        # The four extension endpoints are not part of what a click selects.
        self.assertNotIn(witness[0], picked)


class _SelectableProbe(ConstraintGizmoGeneric):
    def __init__(self, constr):
        self.constr = constr
        self.index = 0
        self.type = constr.type
        self.is_highlight = False
        self.custom_shape = "pick"
        self.picked = []
        self._leader_batch = "leader"
        self._witness_batch = "witness"

    def as_pointer(self):
        return id(self)

    def _get_constraint(self, _context):
        return self.constr

    def _ensure_shape(self, _context, _constr):
        return None

    def draw_custom_shape(self, shape, select_id=None):
        self.picked.append((shape, select_id))


class TestDimensionLinePointer(Sketch2dTestCase):
    def setUp(self):
        super().setUp()
        frame_cache.begin_frame()
        a = self.add_point((0.0, 0.0), fixed=True)
        b = self.add_point((2.0, 0.0), fixed=True)
        self.constr = self.sketch.constraints.add_distance(
            init=True, curve_id_1=a.curve_id, curve_id_2=b.curve_id
        )
        self.probe = _SelectableProbe(self.constr)
        self._highlight = selection.highlight_constraint
        self._running = global_data.stateful_op_running

    def tearDown(self):
        selection.highlight_constraint = self._highlight
        global_data.stateful_op_running = self._running
        super().tearDown()

    def test_hover_draws_the_highlight_color(self):
        selection.highlight_constraint = self.constr
        seen = {}

        def record(_context, _leader, _witness, color):
            seen["color"] = tuple(float(c) for c in color)

        with mock.patch.object(gizmo_base, "_draw_dimension_lines", record):
            self.probe.draw(self.context)
        highlight = tuple(get_prefs().theme_settings.constraint.highlight)
        self.assertEqual(seen["color"], highlight)

    def test_a_click_still_selects_the_dimension(self):
        global_data.stateful_op_running = False
        self.probe.draw_select(self.context, 17)
        self.assertEqual(self.probe.picked, [("pick", 17)])

    def test_a_running_tool_does_not_let_the_dimension_take_the_click(self):
        global_data.stateful_op_running = True
        self.probe.draw_select(self.context, 17)
        self.assertEqual(self.probe.picked, [])
