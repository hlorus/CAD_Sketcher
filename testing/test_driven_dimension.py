"""Regression: driven/animated dimension values re-solve the geometry (#544).

Dimensional values live in ``scene["slvs:c:{uid}"]`` custom properties expressly
so they can be driven or keyframed. A driver writes that value during depsgraph
evaluation, which does not reliably trigger ``depsgraph_update_post``; the
``frame_change_post`` handler re-solves so the geometry follows.
"""

from .utils import Sketch2dTestCase


class TestDrivenDimension(Sketch2dTestCase):
    def test_driver_on_dimension_updates_geometry(self):
        sc = self.sketch.constraints
        a = self.add_point((0, 0), fixed=True)
        b = self.add_point((5, 0))
        self.add_line(a, b)
        c = sc.add_distance(init=True, curve_id_1=a.curve_id, curve_id_2=b.curve_id)
        c.value = 5.0
        self.solve()

        uid = getattr(c, "constraint_uid", "")
        key = f"slvs:c:{uid}"
        fcurve = self.scene.driver_add(f'["{key}"]')
        fcurve.driver.type = "SCRIPTED"
        fcurve.driver.expression = "2 + frame"

        self.scene.frame_set(7)  # driver -> 9
        self.assertAlmostEqual(self.scene[key], 9.0)
        self.assertAlmostEqual((b.co - a.co).length, 9.0, places=3)

        self.scene.frame_set(3)  # driver -> 5
        self.assertAlmostEqual((b.co - a.co).length, 5.0, places=3)
