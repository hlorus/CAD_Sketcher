"""Origin workplane self-heal (#571) and eval-preserving hide (#670)."""

import os
import tempfile
import unittest

import bpy
from mathutils import Matrix

from ..utilities.workplane import (
    _ORIGIN_WP_CONFIGS,
    _target_matrix,
    ensure_origin_workplane_empties,
    iter_wp_empties,
    repair_origin_workplanes,
)
from .utils import Sketch2dTestCase


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
                    emp.matrix_world.col[2][j],
                    target.col[2][j],
                    places=5,
                    msg=f"{prop} normal not restored",
                )

    def test_planes_hidden_without_dropping_from_eval(self):
        """Origin empties must be hidden (#571) but stay in the depsgraph so their
        matrix_world tracks their rotation across reload/drivers (#670) -- i.e.
        eye-hidden, never hide_viewport (which excludes them from evaluation)."""
        ensure_origin_workplane_empties(self.context)
        sk = self._sk()
        for prop, _name, _euler, _id in _ORIGIN_WP_CONFIGS:
            emp = getattr(sk, prop)
            self.assertFalse(emp.hide_viewport, f"{prop} must not use hide_viewport")
            self.assertTrue(emp.hide_get(), f"{prop} should be eye-hidden")
            self.assertTrue(emp.hide_select, f"{prop} should be unselectable")

    def test_repair_rehides_origin_empty(self):
        """A drifted (unhidden) origin empty is re-hidden without hide_viewport."""
        ensure_origin_workplane_empties(self.context)
        sk = self._sk()
        sk.wp_xy.hide_set(False)
        sk.wp_xy.hide_viewport = True  # legacy state repair must also clear
        repair_origin_workplanes(self.context)
        self.assertTrue(sk.wp_xy.hide_get())
        self.assertFalse(sk.wp_xy.hide_viewport)

    def test_ensure_recreates_missing_plane(self):
        ensure_origin_workplane_empties(self.context)
        sk = self._sk()
        bpy.data.objects.remove(sk.wp_yz)
        self.assertFalse(sk.wp_yz)

        ensure_origin_workplane_empties(self.context)
        self.assertTrue(sk.wp_yz)
        self.assertEqual(len(list(iter_wp_empties(self.context))), 3)


class TestOriginWorkplaneReload(unittest.TestCase):
    """Regression for #670: orthogonal planes collapsed onto XY after reload.

    A hide_viewport'd empty is dropped from depsgraph evaluation, so after a
    file load its matrix_world is never recomputed from its rotation and reads
    identity (normal +Z) -- collapsing XZ/YZ onto XY. Saving and reopening must
    leave every origin plane's world normal intact.
    """

    def tearDown(self):
        # Don't leak the reloaded scene into later test modules in this process.
        bpy.ops.wm.read_homefile(use_empty=True)

    def test_normals_survive_save_reload(self):
        ensure_origin_workplane_empties(bpy.context)
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "origin_reload.blend")
            bpy.ops.wm.save_as_mainfile(filepath=path)
            bpy.ops.wm.open_mainfile(filepath=path)

            sk = bpy.context.scene.sketcher
            for prop, _name, euler, _id in _ORIGIN_WP_CONFIGS:
                emp = getattr(sk, prop)
                self.assertTrue(emp, f"{prop} missing after reload")
                target = _target_matrix(euler)
                for j in range(3):
                    self.assertAlmostEqual(
                        emp.matrix_world.col[2][j],
                        target.col[2][j],
                        places=5,
                        msg=f"{prop} collapsed after reload (#670)",
                    )
