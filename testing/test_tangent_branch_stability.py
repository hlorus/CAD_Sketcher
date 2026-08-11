"""Regression for #291: circular tangency must preserve its solution branch.

The original issue reproduction can solve on the internal tangent branch when
the constraint is created, then jump to the external branch as soon as one
circle is dragged.  Each interactive drag step rebuilds CurveSolver, so the
tangent construction must seed the branch represented by the current geometry.
"""

import math
import os
import unittest

import bpy
from mathutils import Vector

from ..curve_solver import CurveSolver
from ..model.curve_ref import curve_ref
from ..model.sketch_ref import get_sketches
from ..utilities.curve_data import get_uuid

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _open(name):
    bpy.ops.wm.open_mainfile(filepath=os.path.join(FIXTURES, name))


class TestTangentBranchStability(unittest.TestCase):
    def test_issue_291_preserves_tangent_branch_while_dragging(self):
        _open("issue_291_circle_tangents.blend")

        sketch = list(get_sketches(bpy.context))[0]

        circle_ids = []
        for index in range(len(sketch.data.curves)):
            curve_id = get_uuid(sketch.data, "curve_id", index)
            ref = curve_ref(sketch, curve_id)

            if type(ref).__name__ == "CircleRef":
                circle_ids.append(curve_id)

        self.assertEqual(len(circle_ids), 2)

        circle1 = curve_ref(sketch, circle_ids[0])
        circle2 = curve_ref(sketch, circle_ids[1])

        sketch.constraints.add_tangent(
            curve_id_1=circle1.curve_id,
            curve_id_2=circle2.curve_id,
        )

        self.assertTrue(sketch.solve(bpy.context))
        self.assertEqual(sketch.solver_state, "OKAY")

        def branch():
            c1 = curve_ref(sketch, circle_ids[0])
            c2 = curve_ref(sketch, circle_ids[1])

            center_distance = (Vector(c2.ct.co) - Vector(c1.ct.co)).length

            external_error = abs(center_distance - (c1.radius + c2.radius))
            internal_error = abs(center_distance - abs(c1.radius - c2.radius))

            return "EXTERNAL" if external_error < internal_error else "INTERNAL"

        initial_branch = branch()

        circle1 = curve_ref(sketch, circle_ids[0])
        circle2 = curve_ref(sketch, circle_ids[1])

        origin = Vector(circle1.ct.co)
        offset = Vector(circle2.ct.co) - origin
        drag_radius = offset.length
        start_angle = math.atan2(offset.y, offset.x)

        dragged_center_id = circle2.ct.curve_id

        # The old implementation changes branch almost immediately on this
        # path. A modest number of steps keeps the regression inexpensive
        # while exercising repeated solver rebuilds like interactive tweaking.
        for step in range(13):
            angle = start_angle + math.tau * step / 72

            target = Vector(
                (
                    origin.x + drag_radius * math.cos(angle),
                    origin.y + drag_radius * math.sin(angle),
                    0.0,
                )
            )

            solver = CurveSolver(bpy.context, sketch)
            solver.tweak(dragged_center_id, target)

            self.assertTrue(
                solver.solve(),
                f"solver failed at drag step {step}",
            )
            self.assertEqual(
                branch(),
                initial_branch,
                f"tangent branch changed at drag step {step}",
            )
