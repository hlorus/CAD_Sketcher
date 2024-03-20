from unittest import skip

from testing.utils import BgsTestCase, Sketch2dTestCase


class TestSolver(BgsTestCase):

    # Run official demos as tests from:
    # https://github.com/solvespace/solvespace/blob/master/exposed/CDemo.c

    def test_example_3d(self):
        entities = self.entities
        constraints = self.constraints

        p1 = entities.add_point_3d((10, 10, 10))
        p2 = entities.add_point_3d((20, 20, 20))
        p2.fixed = True
        e1 = entities.add_line_3d(p1, p2)

        c = constraints.add_distance(p1, p2)
        c.value = 30

        self.assertTrue(self.sketcher.solve(self.context))
        self.assertEqual(tuple(p2.location), (20, 20, 20))
        self.assertAlmostEqual((p2.location - p1.location).length, 30, places=5)


class TestSolver2d(Sketch2dTestCase):
    def test_example_2d(self):
        context = self.context
        entities = self.entities
        constraints = self.constraints

        # wp = entities.origin_plane_XY
        # sketch2 = entities.add_sketch(wp)
        # sketch2.name = "Sketch2"
        sketch2 = self.sketch

        # Line
        origin = entities.add_point_2d((0, 0), sketch2, index_reference=True)

        p1 = entities.add_point_2d((10, 20), sketch2, index_reference=True)
        p2 = entities.add_point_2d((20, 10), sketch2, index_reference=True)
        line = entities.add_line_2d(p1, p2, sketch2, index_reference=True)
        constraints.add_distance(p1, p2, sketch2).value = 30
        constraints.add_distance(origin, line).value = 10

        # TODO: remove normal argument for add_arc and add_circle
        nm = entities.add_normal_2d(sketch2)


        # Arc
        p3 = entities.add_point_2d((100, 120), sketch2, index_reference=True)
        p4 = entities.add_point_2d((120, 110), sketch2, index_reference=True)
        p5 = entities.add_point_2d((150, 150), sketch2, index_reference=True)


        arc = entities.add_arc(nm, p3, p4, p5, sketch2, index_reference=True)

        # Circle
        # p6 = entities.add_point_2d((200, 200), sketch2)
        # circle = entities.add_circle(nm, p6, 30, sketch2)

        self.assertTrue(sketch2.solve(context))
