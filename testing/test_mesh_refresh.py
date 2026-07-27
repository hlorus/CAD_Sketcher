"""Regression: editing a dimension re-evaluates the generated mesh.

The solver writes point positions in place, which does not make the Geometry
Nodes modifier re-evaluate. Operators that solve call ``refresh_curve_geometry``
themselves, but changing a constraint *value* solves via the depsgraph handler,
which previously skipped the refresh -- so the overlay updated but the generated
mesh stayed stale until a manual refresh/tweak.
"""

import bpy

from .utils import Sketch2dTestCase
from .. import curve_solver
from ..utilities import curve_data as cd_mod


class TestMeshRefresh(Sketch2dTestCase):
    def test_value_change_refreshes_and_terminates(self):
        sc = self.sketch.constraints
        a = self.add_point((0, 0), fixed=True)
        b = self.add_point((5, 0))
        self.add_line(a, b)
        c = sc.add_distance(init=True, curve_id_1=a.curve_id, curve_id_2=b.curve_id)
        c.value = 5.0
        self.solve()
        cd_mod.refresh_curve_geometry(self.sketch)

        # Count the depsgraph-handler solve + refresh triggered by a value edit.
        solves = [0]
        refreshes = [0]
        orig_solve = curve_solver.solve_system
        orig_refresh = cd_mod.refresh_curve_geometry

        def counting_solve(context, sketch=None):
            solves[0] += 1
            return orig_solve(context, sketch=sketch)

        def counting_refresh(sketch):
            refreshes[0] += 1
            return orig_refresh(sketch)

        curve_solver.solve_system = counting_solve
        cd_mod.refresh_curve_geometry = counting_refresh
        try:
            c.value = 9.0
            for _ in range(5):
                bpy.context.evaluated_depsgraph_get().update()
                bpy.context.view_layer.update()
        finally:
            curve_solver.solve_system = orig_solve
            cd_mod.refresh_curve_geometry = orig_refresh

        # Geometry actually re-solved to the new value...
        self.assertAlmostEqual((b.co - a.co).length, 9.0, places=3)
        # ...the handler refreshed the mesh at least once...
        self.assertGreaterEqual(refreshes[0], 1)
        # ...and it did not runaway-recurse (refresh mutates curve data).
        self.assertLess(solves[0], 20)
