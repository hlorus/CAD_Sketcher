"""Origin workplane self-heal (#571): flattened/hidden/missing planes."""

import bpy
from mathutils import Matrix

from .utils import Sketch2dTestCase
from ..utilities.workplane import (
    ensure_origin_workplane_empties,
    repair_origin_workplanes,
    iter_wp_empties,
    _target_matrix,
    _ORIGIN_WP_CONFIGS,
)


class TestOriginWorkplanes(Sketch2dTestCase):
    def _sk(self):
        return self.context.scene.sketcher

    def test_repair_restores_flattened_planes(self):
        """Undo can flatten XZ/YZ to identity; repair must restore normals."""
        ensure_origin_workplane_empties(self.context)
        sk = self._sk()

        sk.wp_xz.matrix_world = Matrix.Identity(4)
        sk.wp_yz.matrix_world = Matrix.Identity(4)

        repair_origin_workplanes(self.context)

        for prop, _name, euler, _id in _ORIGIN_WP_CONFIGS:
            emp = getattr(sk, prop)
            target = _target_matrix(euler)
            for j in range(3):
                self.assertAlmostEqual(
                    emp.matrix_world.col[2][j], target.col[2][j], places=5,
                    msg=f"{prop} normal not restored",
                )

    def test_repair_rehides_origin_empty(self):
        ensure_origin_workplane_empties(self.context)
        sk = self._sk()
        sk.wp_xy.hide_viewport = False
        repair_origin_workplanes(self.context)
        self.assertTrue(sk.wp_xy.hide_viewport)

    def test_ensure_recreates_missing_plane(self):
        ensure_origin_workplane_empties(self.context)
        sk = self._sk()
        bpy.data.objects.remove(sk.wp_yz)
        self.assertFalse(sk.wp_yz)

        ensure_origin_workplane_empties(self.context)
        self.assertTrue(sk.wp_yz)
        self.assertEqual(len(list(iter_wp_empties(self.context))), 3)
