import math
from unittest import skip

from testing.utils import Sketch2dTestCase


class TestConstraintAdd(Sketch2dTestCase):
    def test_horizontal(self):
        context = self.context
        entities = self.entities
        constraints = self.constraints
        sketch = self.sketch

        p0 = entities.add_point_2d((0, 0), sketch)
        p0.fixed = True

        # Test constraint between two points
        p1 = entities.add_point_2d((3, 1), sketch)
        c1 = constraints.add_horizontal(p0, entity2=p1, sketch=sketch)
        self.solve()
        self.assertAlmostEqual(p1.co.y, 0.0)

        # Test constraint with one line
        p2 = entities.add_point_2d((-3, -1), sketch)
        line = entities.add_line_2d(p0, p2, sketch)
        c2 = constraints.add_horizontal(line, sketch=sketch)
        self.solve()
        self.assertAlmostEqual(p2.co.y, 0.0)

    def test_vertical(self):
        context = self.context
        entities = self.entities
        constraints = self.constraints
        sketch = self.sketch

        p0 = entities.add_point_2d((0, 0), sketch, fixed=True, index_reference=True)

        # Test constraint between two points
        p1 = entities.add_point_2d((3, 1), sketch, index_reference=True)
        c1 = constraints.add_vertical(p0, entity2=p1, sketch=sketch)
        self.solve()
        self.assertAlmostEqual(c1.entity2.co.x, 0.0)

        # Test constraint with one line
        p2 = entities.add_point_2d((-3, -1), sketch, index_reference=True)
        line = entities.add_line_2d(p0, p2, sketch, index_reference=True)
        c2 = constraints.add_vertical(line, sketch=sketch)
        self.solve()
        self.assertAlmostEqual(c2.entity1.p2.co.x, 0.0)


class TestConstraintInit(Sketch2dTestCase):
    def test_distance(self):
        context = self.context
        entities = self.entities
        constraints = self.constraints

        sketch = self.sketch
        p0 = entities.add_point_2d((0, 0), sketch)
        p0.fixed = True

        # Constrain single Line
        p1 = entities.add_point_2d((-2, 0), sketch)
        line = entities.add_line_2d(p0, p1, sketch)
        c1 = constraints.add_distance(line, None, sketch=sketch, init=True)

        self.solve()
        self.assertAlmostEqual(line.length, 2.0)
        self.assertAlmostEqual(c1.value, 2.0)

        # Constrain 2 points
        p2 = entities.add_point_2d((0.0, 2.0), sketch)
        c2 = constraints.add_distance(p0, p2, sketch=sketch, init=True)
        self.solve()
        self.assertAlmostEqual(p2.co.y, 2.0)
        self.assertAlmostEqual(c2.value, 2.0)

        # Constrain line-point
        # c3 = constraints.add_distance(p2, line, sketch=sketch, init=True)
        # self.solve()
        # self.assertAlmostEqual(c3.value, 2.0)

    def test_distance_flip(self):
        context = self.context
        entities = self.entities
        constraints = self.constraints

        sketch = self.sketch
        p0 = entities.add_point_2d((0, 0), sketch)
        p0.fixed = True

        # Line
        p1 = entities.add_point_2d((1, -1), sketch)
        p1.fixed = True
        p2 = entities.add_point_2d((1, 1), sketch)
        line = entities.add_line_2d(p1, p2, sketch)
        c1 = constraints.add_distance(p0, line, sketch=sketch, init=True)

        self.solve()
        self.assertTrue(c1.flip)
        self.assertAlmostEqual(p2.co.x, 1.0)

        # Flip distance
        c1.flip = False

        self.assertAlmostEqual(p2.co.y, -1.0)

        # Line2 (Opposite direction)
        p3 = entities.add_point_2d((-1, -1), sketch)
        p3.fixed = True
        p4 = entities.add_point_2d((-1, 1), sketch)
        line2 = entities.add_line_2d(p3, p4, sketch)
        c2 = constraints.add_distance(p0, line2, sketch=sketch, init=True)

        self.solve()
        self.assertFalse(c2.flip)
        self.assertAlmostEqual(p4.co.x, -1.0)

        # Flip distance2
        c2.flip = True
        self.assertAlmostEqual(p4.co.y, -1.0)

    def test_distance_aligned(self):
        context = self.context
        entities = self.entities
        constraints = self.constraints

        sketch = self.sketch
        p0 = entities.add_point_2d((0, 0), sketch)
        p0.fixed = True

        p1 = entities.add_point_2d((1, 2), sketch)
        c1 = constraints.add_distance(
            p0, p1, sketch=sketch, init=True, align="VERTICAL"
        )
        c2 = constraints.add_distance(
            p0, p1, sketch=sketch, init=True, align="HORIZONTAL"
        )

        self.solve()
        self.assertAlmostEqual(c1.value, 2.0)
        self.assertAlmostEqual(c2.value, 1.0)

        # Change alignment
        length = (p1.co - p0.co).length
        c1.align = "NONE"
        self.assertAlmostEqual(c1.value, length)

    def test_diameter(self):
        context = self.context
        entities = self.entities
        constraints = self.constraints

        sketch = self.sketch
        p0 = entities.add_point_2d((0, 0), sketch)
        p0.fixed = True

        nm = sketch.wp.nm

        # Constrain circle diameter
        circle1 = entities.add_circle(nm, p0, 3.0, sketch)
        c1 = constraints.add_diameter(circle1, sketch=sketch, init=True, value=4.0)

        self.solve()
        self.assertAlmostEqual(circle1.radius, 2.0)
        self.assertAlmostEqual(c1.value, 4.0)

        # Constrain circle radius
        circle2 = entities.add_circle(nm, p0, 3.0, sketch)
        c2 = constraints.add_diameter(circle2, sketch=sketch, init=True, setting=True)

        self.solve()
        self.assertAlmostEqual(circle2.radius, 3.0)
        self.assertAlmostEqual(c2.value, 3.0)

        # Submit value and setting
        circle3 = entities.add_circle(nm, p0, 1.0, sketch)
        c3 = constraints.add_diameter(
            circle3, sketch=sketch, init=True, value=0.8, setting=True
        )

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
        context = self.context
        entities = self.entities
        constraints = self.constraints

        sketch = self.sketch
        p0 = entities.add_point_2d((0, 0), sketch)
        p0.fixed = True

        nm = sketch.wp.nm

        # Constrain arc
        p1 = entities.add_point_2d((3.0, 0.0), sketch)
        p2 = entities.add_point_2d((0.0, 3.0), sketch)
        arc1 = entities.add_arc(nm, p0, p1, p2, sketch)
        c1 = constraints.add_diameter(arc1, sketch=sketch, init=True)

        self.solve()
        self.assertAlmostEqual(arc1.radius, 3.0)
        self.assertAlmostEqual(c1.value, 6.0)

        c1.setting = True
        self.assertAlmostEqual(arc1.radius, 3.0)
        self.assertAlmostEqual(c1.value, 3.0)

    def test_angle(self):
        context = self.context
        entities = self.entities
        constraints = self.constraints

        sketch = self.sketch
        p0 = entities.add_point_2d((0, 0), sketch)
        p0.fixed = True

        # Line1
        p1 = entities.add_point_2d((1, 1), sketch)
        p1.fixed = True
        line1 = entities.add_line_2d(p0, p1, sketch)

        # Line2
        p2 = entities.add_point_2d((0, 1), sketch)
        line2 = entities.add_line_2d(p0, p2, sketch)

        c = constraints.add_angle(line1, line2, sketch=sketch, init=True)

        self.solve()
        self.assertAlmostEqual(p2.co.x, 0.0)
        self.assertGreater(p2.co.y, 0.0)
        self.assertAlmostEqual(c.value, math.radians(45))
        # NOTE: Which value (45 / (180-45)) is constrained depends on the directions of the lines

        c.setting = not c.setting
        self.solve()
        self.assertAlmostEqual(p2.co.x, 0.0)
        self.assertGreater(p2.co.y, 0.0)
        self.assertAlmostEqual(c.value, math.radians(180 - 45))

    def test_distance_ref(self):
        context = self.context
        entities = self.entities
        constraints = self.constraints
        sketch = self.sketch

        p0 = entities.add_point_2d((0, 0), sketch)
        p0.fixed = True

        p1 = entities.add_point_2d((1, 1), sketch)
        c1 = constraints.add_distance(p0, p1, sketch=sketch)
        c1.is_reference = True
        p1.co = (2, 0)

        self.assertAlmostEqual(c1.value, 2)

    def test_diameter_ref(self):
        context = self.context
        entities = self.entities
        constraints = self.constraints
        sketch = self.sketch

        p0 = entities.add_point_2d((0, 0), sketch)
        p0.fixed = True

        nm = sketch.wp.nm
        circle = entities.add_circle(nm, p0, 3, sketch)
        c1 = constraints.add_diameter(circle, sketch=sketch)
        c1.is_reference = True
        circle.radius = 2.5

        self.assertAlmostEqual(c1.value, 5.0)

    def test_ratio(self):
        p0 = self.entities.add_point_2d((0, 0), self.sketch)
        p0.fixed = True

        p1 = self.entities.add_point_2d((3, 0), self.sketch)
        line1 = self.entities.add_line_2d(p0, p1, self.sketch)

        p2 = self.entities.add_point_2d((0, 1), self.sketch)
        line2 = self.entities.add_line_2d(p0, p2, self.sketch)

        c = self.constraints.add_ratio(line1, line2, self.sketch, init=True)
        self.solve()
        self.assertAlmostEqual(c.value, 3.0)

        p2.fixed = True
        c.value = 4.0
        self.solve()
        self.assertAlmostEqual(line1.length, 4.0)
