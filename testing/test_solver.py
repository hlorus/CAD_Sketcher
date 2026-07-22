from unittest import skip

from .utils import Sketch2dTestCase


class TestSolver2d(Sketch2dTestCase):
    def test_example_2d(self):
        sketch = self.sketch
        ssc = sketch.constraints  # native per-sketch constraints (what solve reads)

        origin = self.add_point((0, 0), fixed=True)

        p1 = self.add_point((10, 20))
        p2 = self.add_point((20, 10))
        line = self.add_line(p1, p2)

        # Arc
        p3 = self.add_point((100, 120))
        p4 = self.add_point((120, 110))
        p5 = self.add_point((115, 115))
        arc = self.add_arc(p3, p4, p5)

        # Circle
        p6 = self.add_point((200, 200))
        circle = self.add_circle(p6, 30)

        # Add constraints
        ssc.add_distance(curve_id_1=p1.curve_id, curve_id_2=p2.curve_id).value = 30
        ssc.add_distance(curve_id_1=origin.curve_id, curve_id_2=line.curve_id).value = 10
        ssc.add_vertical(curve_id_1=line.curve_id)
        ssc.add_distance(curve_id_1=origin.curve_id, curve_id_2=p1.curve_id).value = 15
        ssc.add_equal(curve_id_1=arc.curve_id, curve_id_2=circle.curve_id)
        ssc.add_diameter(curve_id_1=arc.curve_id).value = 17.0/2

        self.solve()

    def test_example_2d_fail(self):
        sketch = self.sketch
        ssc = sketch.constraints  # native per-sketch constraints (what solve reads)

        origin = self.add_point((0, 0), fixed=True)

        p1 = self.add_point((10, 20))
        p2 = self.add_point((20, 10))
        line = self.add_line(p1, p2)

        # Arc
        p3 = self.add_point((100, 120))
        p4 = self.add_point((120, 110))
        p5 = self.add_point((115, 115))
        arc = self.add_arc(p3, p4, p5)

        # Circle
        p6 = self.add_point((200, 200))
        circle = self.add_circle(p6, 30)

        # Add constraints
        ssc.add_distance(curve_id_1=p1.curve_id, curve_id_2=p2.curve_id).value = 30
        ssc.add_distance(curve_id_1=origin.curve_id, curve_id_2=line.curve_id).value = 10
        ssc.add_vertical(curve_id_1=line.curve_id)
        ssc.add_distance(curve_id_1=origin.curve_id, curve_id_2=p1.curve_id).value = 15
        ssc.add_distance(curve_id_1=origin.curve_id, curve_id_2=p2.curve_id).value = 18
        ssc.add_equal(curve_id_1=arc.curve_id, curve_id_2=circle.curve_id)
        ssc.add_diameter(curve_id_1=arc.curve_id).value = 17.0/2

        self.assertFalse(sketch.solve(self.context))
        self.assertEqual(sketch.get_solver_state().identifier, "INCONSISTENT")
