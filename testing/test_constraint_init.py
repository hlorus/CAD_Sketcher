import math
from unittest import skip

from .utils import Sketch2dTestCase


class TestConstraintAdd(Sketch2dTestCase):
    def test_horizontal(self):
        ssc = self.constraints
        sketch = self.sketch

        p0 = self.add_point((0, 0), fixed=True)

        # Test constraint between two points
        p1 = self.add_point((3, 1))
        ssc.add_horizontal(sketch=sketch, curve_id_1=p0.curve_id, curve_id_2=p1.curve_id)
        self.solve()
        self.assertAlmostEqual(p1.co.y, 0.0)

        # Test constraint with one line
        p2 = self.add_point((-3, -1))
        line = self.add_line(p0, p2)
        ssc.add_horizontal(sketch=sketch, curve_id_1=line.curve_id)
        self.solve()
        self.assertAlmostEqual(p2.co.y, 0.0)

    def test_vertical(self):
        ssc = self.constraints
        sketch = self.sketch

        p0 = self.add_point((0, 0), fixed=True)

        # Test constraint between two points
        p1 = self.add_point((3, 1))
        ssc.add_vertical(sketch=sketch, curve_id_1=p0.curve_id, curve_id_2=p1.curve_id)
        self.solve()
        self.assertAlmostEqual(p1.co.x, 0.0)

        # Test constraint with one line
        p2 = self.add_point((-3, -1))
        line = self.add_line(p0, p2)
        ssc.add_vertical(sketch=sketch, curve_id_1=line.curve_id)
        self.solve()
        self.assertAlmostEqual(p2.co.x, 0.0)

    def test_tangent(self):
        ssc = self.constraints
        sketch = self.sketch

        p0 = self.add_point((0, 0), fixed=True)

        # Add line
        p1 = self.add_point((3, -1))
        p2 = self.add_point((3, 1))
        line1 = self.add_line(p1, p2)
        ssc.add_vertical(sketch=sketch, curve_id_1=line1.curve_id)

        # Add circle
        circle1 = self.add_circle(p0, 3.0)
        ssc.add_diameter(sketch=sketch, curve_id_1=circle1.curve_id, init=True, value=3.0)

        # Add tangent
        ssc.add_tangent(sketch=sketch, curve_id_1=circle1.curve_id, curve_id_2=line1.curve_id)

        self.solve()
        self.assertAlmostEqual(p1.co.x, 1.5)


class TestConstraintInit(Sketch2dTestCase):
    def test_distance(self):
        ssc = self.constraints
        sketch = self.sketch

        p0 = self.add_point((0, 0), fixed=True)

        # Constrain single Line
        p1 = self.add_point((-2, 0))
        line = self.add_line(p0, p1)
        c1 = ssc.add_distance(sketch=sketch, init=True, curve_id_1=line.curve_id)

        self.solve()
        self.assertAlmostEqual(line.length, 2.0)
        self.assertAlmostEqual(c1.value, 2.0)

        # Constrain 2 points
        p2 = self.add_point((0.0, 2.0))
        c2 = ssc.add_distance(sketch=sketch, init=True,
                              curve_id_1=p0.curve_id, curve_id_2=p2.curve_id)
        self.solve()
        self.assertAlmostEqual(p2.co.y, 2.0)
        self.assertAlmostEqual(c2.value, 2.0)

    def test_distance_flip(self):
        ssc = self.constraints
        sketch = self.sketch

        p0 = self.add_point((0, 0), fixed=True)

        # Line
        p1 = self.add_point((1, -1), fixed=True)
        p2 = self.add_point((1, 1))
        line = self.add_line(p1, p2)
        c1 = ssc.add_distance(sketch=sketch, init=True,
                              curve_id_1=p0.curve_id, curve_id_2=line.curve_id)

        self.solve()
        self.assertTrue(c1.flip)
        self.assertAlmostEqual(p2.co.x, 1.0)

        # Flip distance
        c1.flip = False
        self.solve()
        self.assertAlmostEqual(p2.co.y, -1.0)

        # Line2 (Opposite direction)
        p3 = self.add_point((-1, -1), fixed=True)
        p4 = self.add_point((-1, 1))
        line2 = self.add_line(p3, p4)
        c2 = ssc.add_distance(sketch=sketch, init=True,
                              curve_id_1=p0.curve_id, curve_id_2=line2.curve_id)

        self.solve()
        self.assertFalse(c2.flip)
        self.assertAlmostEqual(p4.co.x, -1.0)

        # Flip distance2
        c2.flip = True
        self.solve()
        self.assertAlmostEqual(p4.co.y, -1.0)

    def test_distance_aligned(self):
        ssc = self.constraints
        sketch = self.sketch

        p0 = self.add_point((0, 0), fixed=True)
        p1 = self.add_point((1, 2))

        c1 = ssc.add_distance(sketch=sketch, init=True, align="VERTICAL",
                              curve_id_1=p0.curve_id, curve_id_2=p1.curve_id)
        c2 = ssc.add_distance(sketch=sketch, init=True, align="HORIZONTAL",
                              curve_id_1=p0.curve_id, curve_id_2=p1.curve_id)

        self.solve()
        self.assertAlmostEqual(c1.value, 2.0)
        self.assertAlmostEqual(c2.value, 1.0)

        # Change alignment
        length = (p1.co - p0.co).length
        c1.align = "NONE"
        self.assertAlmostEqual(c1.value, length)

    def test_diameter(self):
        ssc = self.constraints
        sketch = self.sketch

        p0 = self.add_point((0, 0), fixed=True)

        # Constrain circle diameter
        circle1 = self.add_circle(p0, 3.0)
        c1 = ssc.add_diameter(sketch=sketch, init=True, value=4.0,
                              curve_id_1=circle1.curve_id)

        self.solve()
        self.assertAlmostEqual(circle1.radius, 2.0)
        self.assertAlmostEqual(c1.value, 4.0)

        # Constrain circle radius
        circle2 = self.add_circle(p0, 3.0)
        c2 = ssc.add_diameter(sketch=sketch, init=True, setting=True,
                              curve_id_1=circle2.curve_id)

        self.solve()
        self.assertAlmostEqual(circle2.radius, 3.0)
        self.assertAlmostEqual(c2.value, 3.0)

        # Submit value and setting
        circle3 = self.add_circle(p0, 1.0)
        c3 = ssc.add_diameter(sketch=sketch, init=True, value=0.8, setting=True,
                              curve_id_1=circle3.curve_id)

        self.solve()
        self.assertAlmostEqual(circle3.radius, 0.8)
        self.assertAlmostEqual(c3.value, 0.8)

        # Toggle radius/diameter
        c1.setting = True
        self.assertAlmostEqual(circle1.radius, 2.0)
        self.assertAlmostEqual(c1.value, 2.0)

        c2.setting = False
        self.assertAlmostEqual(circle2.radius, 3.0)
        self.assertAlmostEqual(c2.value, 6.0)

    def test_diameter_arc(self):
        ssc = self.constraints
        sketch = self.sketch

        p0 = self.add_point((0, 0), fixed=True)
        p1 = self.add_point((3.0, 0.0))
        p2 = self.add_point((0.0, 3.0))
        arc1 = self.add_arc(p0, p1, p2)
        c1 = ssc.add_diameter(sketch=sketch, init=True,
                              curve_id_1=arc1.curve_id)

        self.solve()
        self.assertAlmostEqual(arc1.radius, 3.0)
        self.assertAlmostEqual(c1.value, 6.0)

        c1.setting = True
        self.assertAlmostEqual(arc1.radius, 3.0)
        self.assertAlmostEqual(c1.value, 3.0)

    def test_angle(self):
        ssc = self.constraints
        sketch = self.sketch

        p0 = self.add_point((0, 0), fixed=True)

        # Line1
        p1 = self.add_point((1, 1), fixed=True)
        line1 = self.add_line(p0, p1)

        # Line2
        p2 = self.add_point((0, 1))
        line2 = self.add_line(p0, p2)

        c = ssc.add_angle(sketch=sketch, init=True,
                          curve_id_1=line1.curve_id, curve_id_2=line2.curve_id)

        self.solve()
        self.assertAlmostEqual(p2.co.x, 0.0)
        self.assertGreater(p2.co.y, 0.0)
        self.assertAlmostEqual(c.value, math.radians(45))

        # TODO: supplementary angle toggle may move point to different solution
        # c.setting = not c.setting
        # self.solve()
        # self.assertAlmostEqual(p2.co.x, 0.0)
        # self.assertAlmostEqual(c.value, math.radians(180 - 45))

    def test_distance_ref(self):
        ssc = self.constraints
        sketch = self.sketch

        p0 = self.add_point((0, 0), fixed=True)
        p1 = self.add_point((1, 1))

        c1 = ssc.add_distance(sketch=sketch,
                              curve_id_1=p0.curve_id, curve_id_2=p1.curve_id)
        c1.is_reference = True
        p1.co = (2, 0)

        self.assertAlmostEqual(c1.value, 2)

    def test_diameter_ref(self):
        ssc = self.constraints
        sketch = self.sketch

        p0 = self.add_point((0, 0), fixed=True)
        circle = self.add_circle(p0, 3)

        c1 = ssc.add_diameter(sketch=sketch, curve_id_1=circle.curve_id)
        c1.is_reference = True

        # TODO: setting radius on CircleRef not supported yet
        # circle.radius = 2.5
        # self.assertAlmostEqual(c1.value, 5.0)

    def test_ratio(self):
        ssc = self.constraints
        sketch = self.sketch

        p0 = self.add_point((0, 0), fixed=True)
        p1 = self.add_point((3, 0))
        line1 = self.add_line(p0, p1)

        p2 = self.add_point((0, 1))
        line2 = self.add_line(p0, p2)

        c = ssc.add_ratio(sketch=sketch, init=True,
                          curve_id_1=line1.curve_id, curve_id_2=line2.curve_id)
        self.solve()
        self.assertAlmostEqual(c.value, 3.0)

        p2.fixed = True
        c.value = 4.0
        self.solve()
        self.assertAlmostEqual(line1.length, 4.0)
