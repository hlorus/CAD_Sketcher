"""What the offset tool builds.

The offset runs along one side of the path it walks. For a line that side is a
normal; for an arc it is a radius, and an arc sweeps counter-clockwise from its
start to its end, so walking it forwards keeps its center on the left: the same
side of travel is the *smaller* radius.
"""

import math

from mathutils import Vector

from ..model.curve_ref import ArcRef, LineRef, curve_ref
from ..operators.offset import View3D_OT_slvs_add_offset
from ..utilities.curve_data import read_uuid_list
from .utils import OpHarness, Sketch2dTestCase


class TestOffsetGeometry(Sketch2dTestCase):
    def _offset(self, source, distance):
        h = OpHarness(View3D_OT_slvs_add_offset, self.sketch, self.context)
        h.pick(source).set_value(distance)
        h.op.dimension_distance = False
        self.assertTrue(h.finish())
        return h.op

    def _new(self, op, cls):
        return [ref for ref in op._new_path if isinstance(ref, cls)]

    def _quarter_arc(self):
        """A quarter arc of radius 2, from (2, 0) counter-clockwise to (0, 2)."""
        return self.add_arc(
            self.add_point((0.0, 0.0)),
            self.add_point((2.0, 0.0)),
            self.add_point((0.0, 2.0)),
        )

    def test_a_lone_line_offsets_to_a_line_of_the_same_length(self):
        """Both ends move, which a path of one segment used not to do."""
        line = self.add_line(self.add_point((0.0, 0.0)), self.add_point((4.0, 0.0)))

        op = self._offset(line, 1.0)

        new = self._new(op, LineRef)[0]
        self.assertAlmostEqual(new.length, 4.0, places=5)
        self.assertAlmostEqual(abs(new.p1.co.y - line.p1.co.y), 1.0, places=5)
        self.assertAlmostEqual(new.p1.co.y, new.p2.co.y, places=5)

    def test_a_lone_arc_keeps_its_sweep(self):
        arc = self._quarter_arc()

        op = self._offset(arc, 0.5)

        new = self._new(op, ArcRef)[0]
        self.assertAlmostEqual(new.radius, 1.5, places=5)
        self.assertAlmostEqual(math.degrees(new.angle), 90.0, places=3)
        self.assertAlmostEqual((new.start.co - Vector((1.5, 0.0))).length, 0.0, 5)
        self.assertAlmostEqual((new.end.co - Vector((0.0, 1.5))).length, 0.0, 5)

    def test_an_arc_offsets_the_other_way_for_a_negative_distance(self):
        arc = self._quarter_arc()

        op = self._offset(arc, -0.5)

        self.assertAlmostEqual(self._new(op, ArcRef)[0].radius, 2.5, places=5)

    def test_a_path_offsets_line_and_arc_to_the_same_side(self):
        """Line, arc, line: the offset has to stay connected across the corners."""
        a = self.add_point((-4.0, 0.0))
        b = self.add_point((-2.0, 0.0))
        c = self.add_point((0.0, 2.0))
        d = self.add_point((0.0, 4.0))
        first = self.add_line(a, b)
        self.add_arc(self.add_point((-2.0, 2.0)), b, c)
        self.add_line(c, d)

        op = self._offset(first, 0.5)

        lines = self._new(op, LineRef)
        arcs = self._new(op, ArcRef)
        self.assertEqual((len(lines), len(arcs)), (2, 1))
        # Each segment sits half a unit inside its source, and they meet.
        self.assertAlmostEqual(lines[0].p1.co.y, 0.5, places=5)
        self.assertAlmostEqual(arcs[0].radius, 1.5, places=5)
        self.assertAlmostEqual(lines[1].p1.co.x, -0.5, places=5)
        self.assertAlmostEqual((arcs[0].start.co - lines[0].p2.co).length, 0.0, 5)
        self.assertAlmostEqual((arcs[0].end.co - lines[1].p1.co).length, 0.0, 5)

    def test_the_offset_of_a_path_is_all_new_geometry(self):
        a = self.add_point((-4.0, 0.0))
        b = self.add_point((-2.0, 0.0))
        c = self.add_point((0.0, 2.0))
        first = self.add_line(a, b)
        self.add_arc(self.add_point((-2.0, 2.0)), b, c)
        before = set(read_uuid_list(self.sketch.target_object.data, "curve_id"))

        op = self._offset(first, 0.5)

        for ref in op._new_path:
            self.assertNotIn(ref.curve_id, before)
            self.assertTrue(curve_ref(self.sketch, ref.curve_id).valid)
