from unittest import skip
from geometry_sketcher.testing.utils import BgsTestCase
from geometry_sketcher import class_defines

from sys import float_info

class TestEntities(BgsTestCase):

    def test_point_3d(self):
        sketcher = self.sketcher
        entities = self.entities

        # Point at origin
        p1 = entities.add_point_3d((0, 0, 0))
        self.assertIsInstance(p1, class_defines.SlvsPoint3D)
        self.assertEqual(tuple(p1.location), (0, 0, 0))
