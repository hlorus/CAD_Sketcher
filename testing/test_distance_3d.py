"""Regression coverage for 3D distance constraints (#55)."""

from mathutils import Vector

from .utils import BgsTestCase
from ..solver_3d import solve_system_3d


class TestDistance3D(BgsTestCase):
    def test_point_distance_solves_and_has_world_space_matrix(self):
        p1 = self.entities.add_point_3d((0.0, 0.0, 0.0), fixed=True)
        p2 = self.entities.add_point_3d((3.0, 4.0, 0.0))

        c = self.constraints.distance.add()
        c.entity1 = p1
        c.entity2 = p2
        self.constraints._init_constraint(c)
        c.assign_init_props()

        self.assertAlmostEqual(c.value, 5.0, places=5)

        matrix = c.matrix_basis()
        self.assertLess((matrix.translation - Vector((1.5, 2.0, 0.0))).length, 1e-5)

        world_x = (matrix.to_3x3() @ Vector((1.0, 0.0, 0.0))).normalized()
        expected_x = Vector((3.0, 4.0, 0.0)).normalized()
        self.assertGreater(world_x.dot(expected_x), 0.9999)

        c.value = 10.0
        self.assertTrue(solve_system_3d(self.context))
        self.assertAlmostEqual((p2.location - p1.location).length, 10.0, places=4)
