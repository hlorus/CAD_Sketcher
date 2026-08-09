"""Quantify tweak/drag stability through the real solver stack.

Drives ``CurveSolver`` the same way ``operators/tweak.py`` does during an
interactive drag: for each cursor step a fresh solver is built (warm-started
from the last solved curve data), the dragged point is pulled to the cursor,
and the system is re-solved. We then measure how the *rest* of the geometry
responds along a scripted drag path.

Metrics (see issue on tweak instability):
  kick_max   -- max ||d(tracked)|| / ||d(cursor)|| between steps; ~1 is a
                faithful follow, >>1 is a discontinuous jump (branch flip).
  flips      -- number of steps whose kick exceeds FLIP_THRESH.
  hysteresis -- ||tracked_final - tracked_initial|| after a *closed* drag path
                (cursor returns to start); 0 means the drag is reversible.

``control_slider`` is a well-posed 1-DOF drag and MUST stay stable -- it guards
against regressions that would make even simple dragging jump.
``fully_defined_drag`` covers issue #584 (dragging a pinned sketch used to flip
it to 'Inconsistent') and now passes. The linkage and equal-chain cases still
exhibit deeper drag instability and are marked ``expectedFailure`` so the suite
stays green while documenting the bug; a fix turns them into unexpected
successes.
"""

import math
import unittest

from mathutils import Vector

from ..curve_solver import CurveSolver
from .utils import Sketch2dTestCase

FLIP_THRESH = 5.0


def _circle_path(cx, cy, r, n):
    return [
        (cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n))
        for i in range(n + 1)
    ]


class TweakStabilityMixin:
    """Drive a drag path and compute stability metrics."""

    def _drag(self, dragged, tracked, path):
        tracked0 = None
        prev_tracked = prev_target = None
        kick_max = 0.0
        flips = fails = 0
        for target in path:
            solver = CurveSolver(self.context, self.sketch)
            solver.tweak(dragged.curve_id, Vector((target[0], target[1], 0.0)))
            if not solver.solve():
                fails += 1
                continue
            tr = [Vector(p.co) for p in tracked]
            if tracked0 is None:
                tracked0 = tr
            if prev_tracked is not None:
                dtrack = max((a - b).length for a, b in zip(tr, prev_tracked))
                dtarget = (
                    math.hypot(target[0] - prev_target[0], target[1] - prev_target[1])
                    or 1e-9
                )
                kick = dtrack / dtarget
                kick_max = max(kick_max, kick)
                if kick > FLIP_THRESH:
                    flips += 1
            prev_tracked, prev_target = tr, target
        hyst = (
            max((a - b).length for a, b in zip(prev_tracked, tracked0))
            if tracked0
            else None
        )
        return {
            "kick_max": kick_max,
            "flips": flips,
            "hysteresis": hyst,
            "fails": fails,
        }


class TestTweakStability(Sketch2dTestCase, TweakStabilityMixin):
    def test_control_slider_stable(self):
        """A 1-DOF point dragged along its own constraint circle must follow
        the cursor smoothly and return exactly (baseline: dragging works)."""
        a0 = self.add_point((0, 0), fixed=True)
        p = self.add_point((4, 0))
        line = self.add_line(a0, p)
        c = self.sketch.constraints.add_distance(init=True, curve_id_1=line.curve_id)
        c.value = 4.0
        self.solve()

        m = self._drag(p, [p], _circle_path(0, 0, 4.0, 72))
        print(f"[tweak-stability] control_slider: {m}")
        self.assertEqual(m["fails"], 0)
        self.assertLess(m["kick_max"], 2.0, m)
        self.assertLess(m["hysteresis"], 1e-6, m)

    @unittest.expectedFailure
    def test_two_bar_arm_no_elbow_flip(self):
        """Dragging the end of a rigid two-bar linkage should not make the
        elbow jump discontinuously. It currently flips through the singular
        (near-straight) pose, so the elbow lurches many times the cursor step."""
        a0 = self.add_point((0, 0), fixed=True)
        p1 = self.add_point((1.5, 2.598076))  # |a0 p1| = 3
        p2 = self.add_point((3.0, 0.0))  # |p1 p2| = 3
        self.add_line(a0, p1)
        self.add_line(p1, p2)
        sc = self.sketch.constraints
        # point-point distances -> rigid bars (a line-length constraint on a
        # two-free-point segment is a separate, unrelated matter).
        sc.add_distance(
            init=True, curve_id_1=a0.curve_id, curve_id_2=p1.curve_id
        ).value = 3.0
        sc.add_distance(
            init=True, curve_id_1=p1.curve_id, curve_id_2=p2.curve_id
        ).value = 3.0
        self.solve()

        m = self._drag(p2, [p1], _circle_path(3.0, 0.0, 2.6, 72))
        print(f"[tweak-stability] two_bar_arm: {m}")
        self.assertEqual(m["fails"], 0)
        self.assertLess(m["kick_max"], 2.0, m)  # <-- currently ~6.7 (elbow flips)

    @unittest.expectedFailure
    def test_equal_chain_reversible(self):
        """An equal-length chain dragged out and back should return to its
        original shape. Currently the free joints drift (hysteresis)."""
        a0 = self.add_point((0, 0), fixed=True)
        p1 = self.add_point((2, 0))
        p2 = self.add_point((4, 0))
        p3 = self.add_point((6, 0))
        l0 = self.add_line(a0, p1)
        l1 = self.add_line(p1, p2)
        l2 = self.add_line(p2, p3)
        sc = self.sketch.constraints
        sc.add_equal(curve_id_1=l0.curve_id, curve_id_2=l1.curve_id)
        sc.add_equal(curve_id_1=l1.curve_id, curve_id_2=l2.curve_id)
        self.solve()

        out = [(6.0 - 3.0 * i / 40.0, 2.0 * i / 40.0) for i in range(41)]
        back = [(3.0 + 3.0 * i / 40.0, 2.0 - 2.0 * i / 40.0) for i in range(41)]
        m = self._drag(p3, [p1, p2], out + back)
        print(f"[tweak-stability] equal_chain: {m}")
        self.assertEqual(m["fails"], 0)
        self.assertLess(m["hysteresis"], 1e-6, m)  # <-- currently ~0.011 (drift)

    def test_fully_defined_drag_not_inconsistent(self):
        """Dragging a fully defined (0-DOF) sketch is a graceful no-op, not a
        flip to 'Inconsistent' (issue #584). The drag would over-constrain the
        already-pinned system, so the solver drops it and re-solves, keeping the
        constrained solution."""
        p0 = self.add_point((0, 0), fixed=True)
        p1 = self.add_point((5, 0))
        p2 = self.add_point((5, 5))
        p3 = self.add_point((0, 5))
        l01 = self.add_line(p0, p1)
        l12 = self.add_line(p1, p2)
        l23 = self.add_line(p2, p3)
        l30 = self.add_line(p3, p0)
        sc = self.sketch.constraints
        sc.add_horizontal(curve_id_1=l01.curve_id)
        sc.add_horizontal(curve_id_1=l23.curve_id)
        sc.add_vertical(curve_id_1=l12.curve_id)
        sc.add_vertical(curve_id_1=l30.curve_id)
        sc.add_distance(
            init=True, curve_id_1=p0.curve_id, curve_id_2=p1.curve_id
        ).value = 5.0
        sc.add_distance(
            init=True, curve_id_1=p1.curve_id, curve_id_2=p2.curve_id
        ).value = 5.0
        self.solve()
        self.assertEqual(self.sketch.dof, 0)

        solver = CurveSolver(self.context, self.sketch)
        solver.tweak(p2.curve_id, Vector((6.0, 5.0, 0.0)))
        solver.solve()
        print(f"[tweak-stability] fully_defined_drag: state={self.sketch.solver_state}")
        self.assertNotEqual(self.sketch.solver_state, "INCONSISTENT")
