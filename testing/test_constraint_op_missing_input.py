"""Constraint operators run without their entities cancel instead of raising."""

import bpy

from ..model.sketch_ref import set_active_sketch
from .utils import Sketch2dTestCase


class TestConstraintOpMissingInput(Sketch2dTestCase):
    def setUp(self):
        super().setUp()
        set_active_sketch(self.context, self.sketch.target_object)
        self.circle = self.add_circle(self.add_point((2, 2)), 1.0)

    def test_no_entities_cancels(self):
        ops = bpy.ops.view3d
        for op in (
            ops.slvs_add_tangent,
            ops.slvs_add_parallel,
            ops.slvs_add_coincident,
            ops.slvs_add_diameter,
        ):
            self.assertEqual(op("EXEC_DEFAULT"), {"CANCELLED"}, op)
        self.assertEqual(len(list(self.sketch.constraints.all)), 0)

    def test_second_entity_missing_cancels(self):
        result = bpy.ops.view3d.slvs_add_tangent(
            "EXEC_DEFAULT",
            ptr0_kind="CircleRef",
            ptr0_existing=True,
            ptr0_name=self.circle.curve_id,
        )
        self.assertEqual(result, {"CANCELLED"})
