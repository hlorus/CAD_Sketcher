"""Arc/circle tessellation follows the convert modifier's Angular Resolution."""

import math

import bpy

from .utils import Sketch2dTestCase


class TestCurveResolution(Sketch2dTestCase):
    def _modifier(self):
        return self.sketch.target_object.modifiers["CAD Sketcher Convert"]

    def _input_id(self, name):
        from ..utilities.convert_nodes import input_identifier

        return input_identifier(self._modifier().node_group, name)

    def _set_angle(self, degrees):
        from ..operators.modifiers import set_modifier_input
        from ..utilities.convert_nodes import ANGULAR_RESOLUTION_INPUT

        set_modifier_input(
            self._modifier(),
            self._input_id(ANGULAR_RESOLUTION_INPUT),
            math.radians(degrees),
        )

    def _vertex_count(self):
        # to_mesh can't read a Curves object headless; converting a copy applies
        # the same modifier stack and is readable.
        ob = self.sketch.target_object
        dup = ob.copy()
        dup.data = ob.data.copy()
        self.context.scene.collection.objects.link(dup)
        for other in self.context.scene.collection.objects:
            other.select_set(False)
        dup.select_set(True)
        self.context.view_layer.objects.active = dup
        bpy.ops.object.convert(target="MESH")
        count = len(dup.data.vertices)
        bpy.data.objects.remove(dup, do_unlink=True)
        return count

    def _circle_vertices(self):
        self.add_circle(self.add_point((0.0, 0.0)), 1.0)
        return self._vertex_count()

    def test_default_matches_bezier_resolution(self):
        # 4 quarter segments x 12 edges each: the output before the input existed.
        self.assertEqual(self._circle_vertices(), 48)

    def test_angle_controls_circle_tessellation(self):
        self.add_circle(self.add_point((0.0, 0.0)), 1.0)
        self._set_angle(30.0)
        self.assertEqual(self._vertex_count(), 12)
        self._set_angle(45.0)
        self.assertEqual(self._vertex_count(), 8)

    def test_lines_stay_single_segment(self):
        self.add_line(self.add_point((1.0, 0.0)), self.add_point((2.0, 0.0)))
        before = self._vertex_count()
        self._set_angle(1.0)
        self.assertEqual(self._vertex_count(), before)

    def test_new_sketch_uses_preference(self):
        from ..operators.modifiers import get_modifier_input
        from ..utilities.convert_nodes import ANGULAR_RESOLUTION_INPUT
        from ..utilities.preferences import get_prefs

        prefs = get_prefs()
        previous = prefs.curve_angular_resolution
        prefs.curve_angular_resolution = math.radians(15.0)
        try:
            sketch = self.new_sketch()
            mod = sketch.target_object.modifiers["CAD Sketcher Convert"]
            from ..utilities.convert_nodes import input_identifier

            value = get_modifier_input(
                mod, input_identifier(mod.node_group, ANGULAR_RESOLUTION_INPUT)
            )
            self.assertAlmostEqual(value, math.radians(15.0), places=5)
        finally:
            prefs.curve_angular_resolution = previous

    def test_rebuild_keeps_modifier_values(self):
        # A CONVERT_VERSION bump rebuilds the group's interface; existing sketches
        # must keep their Fill and Angular Resolution values.
        from ..operators.modifiers import get_modifier_input, set_modifier_input
        from ..utilities import convert_nodes as cn

        mod = self._modifier()
        set_modifier_input(mod, self._input_id("Fill"), False)
        self._set_angle(20.0)

        mod.node_group["cad_convert_version"] = -1
        cn.build_convert_node_group()

        self.assertFalse(get_modifier_input(mod, self._input_id("Fill")))
        self.assertAlmostEqual(
            get_modifier_input(mod, self._input_id(cn.ANGULAR_RESOLUTION_INPUT)),
            math.radians(20.0),
            places=5,
        )
