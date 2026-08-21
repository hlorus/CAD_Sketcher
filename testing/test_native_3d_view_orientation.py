"""Viewport-orientation regression for native free-3D placement."""

import math
from types import SimpleNamespace

from mathutils import Quaternion, Vector

from .utils import BgsTestCase


class TestNative3DViewOrientation(BgsTestCase):
    def test_view_plane_normal_comes_from_region_view_rotation(self):
        """An angled orbit must produce an angled plane, never global XY."""
        from ..operators.base_sketch_3d import OperatorSketch3d

        rotation = Quaternion(Vector((1.0, 0.0, 0.0)), math.radians(45.0))
        context = SimpleNamespace(
            region_data=SimpleNamespace(view_rotation=rotation),
            region=SimpleNamespace(width=1920, height=1080),
        )

        normal = OperatorSketch3d._view_plane_normal(None, context)
        expected = (rotation @ Vector((0.0, 0.0, 1.0))).normalized()

        self.assertAlmostEqual(normal.dot(expected), 1.0, places=6)
        self.assertGreater(abs(normal.y), 1e-6)
        self.assertGreater(abs(normal.z), 1e-6)
        self.assertLess(abs(normal.x), 1e-6)
