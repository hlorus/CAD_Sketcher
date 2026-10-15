"""Constraint operators run with pointer props of the wrong type cancel."""

import bpy

from ..model.sketch_ref import set_active_sketch
from .utils import Sketch2dTestCase


class TestRestoredPointerTypes(Sketch2dTestCase):
    def setUp(self):
        super().setUp()
        set_active_sketch(self.context, self.sketch.target_object)
        p0 = self.add_point((0, 0))
        self.p0 = p0
        self.line = self.add_line(p0, self.add_point((4, 0)))
        self.circle = self.add_circle(self.add_point((2, 2)), 1.0)

    def _ptrs(self, *refs):
        kw = {}
        for i, ref in enumerate(refs):
            kw["ptr%d_kind" % i] = type(ref).__name__
            kw["ptr%d_existing" % i] = True
            kw["ptr%d_name" % i] = ref.curve_id
        return kw

    def _run(self, op, *refs):
        return op("EXEC_DEFAULT", **self._ptrs(*refs))

    def test_wrong_types_cancel(self):
        ops = bpy.ops.view3d
        cases = [
            (ops.slvs_add_tangent, self.line, self.circle),
            (ops.slvs_add_perpendicular, self.circle, self.line),
            (ops.slvs_add_equal, self.p0, self.line),
            (ops.slvs_add_coincident, self.line, self.circle),
            (ops.slvs_add_midpoint, self.line, self.p0),
        ]
        before = len(list(self.sketch.constraints.all))
        for op, a, b in cases:
            self.assertEqual(self._run(op, a, b), {"CANCELLED"}, op)
        self.assertEqual(len(list(self.sketch.constraints.all)), before)

    def test_kind_that_lies_about_the_curve_cancels(self):
        kw = self._ptrs(self.circle, self.line)
        kw["ptr0_name"] = self.line.curve_id
        result = bpy.ops.view3d.slvs_add_tangent("EXEC_DEFAULT", **kw)
        self.assertEqual(result, {"CANCELLED"})

    def test_valid_types_still_run(self):
        result = self._run(bpy.ops.view3d.slvs_add_tangent, self.circle, self.line)
        self.assertEqual(result, {"FINISHED"})
        self.assertEqual(len(self.sketch.constraints.tangent), 1)
