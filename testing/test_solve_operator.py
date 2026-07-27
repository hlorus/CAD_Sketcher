"""Regression: the Solve / Solve All operator runs (#564 comment).

The operator passed ``all=`` to the solver constructor, which the native
``CurveSolver`` does not accept, so clicking Solve or Solve All raised
``TypeError: CurveSolver.__init__() got an unexpected keyword argument 'all'``.
"""

import bpy

from .utils import Sketch2dTestCase


class TestSolveOperator(Sketch2dTestCase):
    def _make_geometry(self):
        a = self.add_point((0, 0), fixed=True)
        b = self.add_point((3, 0))
        self.add_line(a, b)
        self.sketch.constraints.add_distance(
            init=True, curve_id_1=a.curve_id, curve_id_2=b.curve_id
        )

    def test_solve_active(self):
        self._make_geometry()
        self.assertEqual(bpy.ops.view3d.slvs_solve(), {"FINISHED"})

    def test_solve_all(self):
        self._make_geometry()
        self.assertEqual(bpy.ops.view3d.slvs_solve(all=True), {"FINISHED"})
