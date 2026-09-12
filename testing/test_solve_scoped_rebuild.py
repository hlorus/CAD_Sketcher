"""The solver's scoped segment rebuild must be equivalent to a full one.

``_write_results`` rebuilds only the segments whose referenced points actually
moved, instead of re-deriving every arc/circle bezier on every solve. That is a
correctness risk: a segment the solver skips keeps whatever bezier data it had,
so anything the scoping misses shows up as stale geometry rather than as an
error.

These tests pin the invariant directly. After a solve, running an *unscoped*
``rebuild_segments`` must change nothing: positions, bezier handles and weld ids
all stay byte-identical. If the scoping ever misses a case, the full rebuild
repairs it and the comparison fails.
"""

import math

import numpy as np

from ..utilities.curve_data import rebuild_segments
from .utils import Sketch2dTestCase

# Attributes that a segment rebuild is allowed to touch.
_REBUILT_ATTRS = (
    ("handle_left", "vector", 3),
    ("handle_right", "vector", 3),
    ("merge_id", "value", 1),
)


class ScopedRebuildEquivalence(Sketch2dTestCase):
    """Base: snapshot curve data, force a full rebuild, expect no change."""

    def _snapshot(self):
        cd = self.sketch.target_object.data
        n_points = len(cd.points)
        snap = {}
        positions = np.empty(n_points * 3, dtype=np.float32)
        cd.points.foreach_get("position", positions)
        snap["position"] = positions
        for name, prop, width in _REBUILT_ATTRS:
            attr = cd.attributes.get(name)
            if attr is None:
                continue
            buf = np.empty(
                n_points * width, dtype=np.float32 if width == 3 else np.int32
            )
            attr.data.foreach_get(prop, buf)
            snap[name] = buf
        return snap

    def assert_full_rebuild_is_noop(self):
        """A full, unscoped rebuild after the solve must change nothing real.

        The tolerance is float32 noise, not slack. A repeated full rebuild is
        bit-stable, but the solver writes positions computed in double while
        rebuild_segments re-derives them from the float32 values already stored,
        so the two can differ in the last bit (~1 ULP, 2.4e-07 at unit scale).
        Staleness looks nothing like that: a segment the scoping wrongly skipped
        keeps geometry built from the point's *previous* location, off by the whole
        edit, so 1e-5 still catches it with four orders of magnitude to spare.
        """
        before = self._snapshot()
        rebuild_segments(self.sketch)  # unscoped: rebuilds every segment
        after = self._snapshot()

        self.assertEqual(set(before), set(after))
        for name in before:
            if name == "merge_id":
                np.testing.assert_array_equal(
                    after[name],
                    before[name],
                    err_msg="weld ids changed on a full rebuild",
                )
                continue
            np.testing.assert_allclose(
                after[name],
                before[name],
                atol=1e-5,
                rtol=0,
                err_msg=(
                    f"{name!r} changed when the segments were fully rebuilt, so the "
                    f"solver's scoped rebuild left it stale"
                ),
            )


class TestScopedRebuildCoversPointMoves(ScopedRebuildEquivalence):
    def test_dragging_a_point_in_a_chain(self):
        pts = [self.add_point((0, 0), fixed=True)]
        for i in range(1, 8):
            pts.append(self.add_point((i * 1.0, math.sin(i) * 0.5)))
        for i in range(7):
            self.add_line(pts[i], pts[i + 1])
        self.solve()

        pts[4].co = (4.5, 2.0)
        self.solve()
        self.assert_full_rebuild_is_noop()

    def test_moving_an_arc_centre(self):
        centre = self.add_point((0, 0))
        start = self.add_point((2, 0))
        end = self.add_point((0, 2))
        self.add_arc(centre, start, end)
        self.solve()

        centre.co = (0.5, -0.5)
        self.solve()
        self.assert_full_rebuild_is_noop()

    def test_moving_a_circle_centre(self):
        centre = self.add_point((0, 0))
        self.add_circle(centre, 1.5)
        self.solve()

        centre.co = (3.0, 1.0)
        self.solve()
        self.assert_full_rebuild_is_noop()

    def test_nothing_moved(self):
        """A solve that changes no position must still leave segments consistent."""
        centre = self.add_point((1, 1))
        self.add_circle(centre, 0.8)
        self.add_line(self.add_point((0, 0)), self.add_point((2, 0)))
        self.solve()
        self.solve()  # second solve: nothing to move
        self.assert_full_rebuild_is_noop()


class TestScopedRebuildCoversRadiusChanges(ScopedRebuildEquivalence):
    """A radius can change with the centre standing still.

    Nothing in the point pass flags that, so the second pass has to add the
    circle's centre id itself. Without it the circle keeps its old bezier.
    """

    def test_diameter_constraint_resizes_the_circle(self):
        centre = self.add_point((0, 0), fixed=True)
        circle = self.add_circle(centre, 1.0)
        diameter = self.sketch.constraints.add_diameter(
            init=True, curve_id_1=circle.curve_id
        )
        self.solve()

        diameter.value = 5.0
        self.solve()
        self.assert_full_rebuild_is_noop()

    def test_radius_shrinks(self):
        centre = self.add_point((0, 0), fixed=True)
        circle = self.add_circle(centre, 4.0)
        diameter = self.sketch.constraints.add_diameter(
            init=True, curve_id_1=circle.curve_id
        )
        self.solve()

        diameter.value = 0.5
        self.solve()
        self.assert_full_rebuild_is_noop()


class TestScopedRebuildCoversResegmentation(ScopedRebuildEquivalence):
    """An arc's control-point count tracks its sweep, so a move can resize it."""

    RADIUS = 2.0

    def _end_at(self, degrees):
        a = math.radians(degrees)
        return (self.RADIUS * math.cos(a), self.RADIUS * math.sin(a))

    def test_arc_grows_past_segment_boundaries(self):
        centre = self.add_point((0, 0), fixed=True)
        start = self.add_point((self.RADIUS, 0), fixed=True)
        end = self.add_point(self._end_at(30))
        self.add_arc(centre, start, end)
        self.solve()

        for degrees in (100, 200, 350, 80, 30):
            with self.subTest(degrees=degrees):
                end.co = self._end_at(degrees)
                self.solve()
                self.assert_full_rebuild_is_noop()


class TestScopedRebuildAfterTopologyChange(ScopedRebuildEquivalence):
    """Merge ids track connectivity, which a scoped rebuild skips recomputing.

    The solver therefore has to recompute them itself, or a corner welded by a
    coincidence constraint stops welding and the sketch no longer fills.
    """

    def test_solve_after_adding_geometry(self):
        p0 = self.add_point((0, 0), fixed=True)
        p1 = self.add_point((2, 0))
        self.add_line(p0, p1)
        self.solve()

        p2 = self.add_point((2, 2))
        self.add_line(p1, p2)
        self.solve()
        self.assert_full_rebuild_is_noop()

    def test_coincident_corner_keeps_its_weld_id(self):
        a0 = self.add_point((0, 0), fixed=True)
        a1 = self.add_point((2, 0))
        b0 = self.add_point((2, 0))
        b1 = self.add_point((2, 2))
        self.add_line(a0, a1)
        self.add_line(b0, b1)
        self.sketch.constraints.add_coincident(
            curve_id_1=a1.curve_id, curve_id_2=b0.curve_id
        )
        self.solve()

        cd = self.sketch.target_object.data
        merge = cd.attributes.get("merge_id")
        self.assertIsNotNone(merge, "merge_id attribute missing after solve")
        ids = np.empty(len(cd.points), dtype=np.int32)
        merge.data.foreach_get("value", ids)
        self.assertTrue((ids > 0).any(), "no weld ids assigned after a solve")

        self.assert_full_rebuild_is_noop()


class TestScopedRebuildActuallyScopes(Sketch2dTestCase):
    """Guard the optimization itself: a solve must not re-derive every arc.

    Equivalence alone would still pass if the scoping silently degraded to a full
    rebuild, which is the regression that would quietly give the performance back.
    """

    def _circles(self, count):
        centres = []
        for i in range(count):
            centre = self.add_point((i * 2.0, 0))
            centres.append(centre)
            self.add_circle(centre, 0.7)
        return centres

    def _scopes_of_one_solve(self):
        """The ``point_ids`` the solver hands to rebuild_segments during a solve."""
        import unittest.mock as mock

        from ..utilities import curve_data as cd_mod

        real = cd_mod.rebuild_segments
        calls = []

        def spy(sketch, point_ids=None):
            calls.append(point_ids)
            return real(sketch, point_ids=point_ids)

        # The solver imports rebuild_segments inside _write_results, so the name
        # resolves from this module at call time and patching it here takes effect.
        with mock.patch.object(cd_mod, "rebuild_segments", spy):
            self.solve()
        return calls

    def test_a_settled_solve_rebuilds_nothing(self):
        self._circles(12)
        self.solve()

        calls = self._scopes_of_one_solve()

        self.assertEqual(len(calls), 1, "solver did not call rebuild_segments once")
        self.assertIsNotNone(
            calls[0], "solver fell back to an unscoped rebuild of every segment"
        )
        self.assertEqual(
            calls[0], set(), f"a settled solve reported moves: {calls[0]!r}"
        )

    def test_a_caller_move_is_already_rebuilt(self):
        """Writing ``co`` rebuilds the segments itself, so the solve adds nothing.

        The solver only reports points *it* relocated. When the caller moved the
        point and the solver agrees with that position, there is nothing left to
        rebuild -- the ``co`` setter already did it (see curve_ref.rebuild path).
        """
        centres = self._circles(12)
        self.solve()

        centres[3].co = (6.0, 3.0)
        calls = self._scopes_of_one_solve()

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0], set())

    def _write_position_directly(self, point, co):
        """Move a point in curve data, bypassing the ``co`` setter's rebuild.

        This is the state the solver is meant to correct: a position changed with
        segments not yet rebuilt, so the solve has a genuine difference to write.
        """
        from ..utilities.curve_data import get_curve_data

        cd, _idx, curve_slice = get_curve_data(self.sketch, point.curve_id)
        cd.points[curve_slice.points[0].index].position = (co[0], co[1], 0.0)

    def test_solver_driven_move_leaves_bystanders_alone(self):
        """The point the solver corrects is rebuilt; unrelated circles are not."""
        centres = self._circles(12)  # bystanders that must NOT be rebuilt
        anchor = self.add_point((0, 0), fixed=True)
        free = self.add_point((3.0, 0))
        self.add_line(anchor, free)
        # Point-to-point: the line form of add_distance is not enforced by the
        # solver, so it would leave the geometry free and the solve a no-op.
        distance = self.sketch.constraints.add_distance(
            init=True, curve_id_1=anchor.curve_id, curve_id_2=free.curve_id
        )
        # Assigning value stores it in scene["slvs:c:<uid>"]. Without that the
        # getter derives the value from the current geometry, so the constraint is
        # always already satisfied and the solver never corrects anything.
        distance.value = 3.0
        self.solve()

        # Drag `free` off its constrained length; the solver has to pull it back.
        self._write_position_directly(free, (9.0, 4.0))
        calls = self._scopes_of_one_solve()

        self.assertEqual(len(calls), 1)
        moved = calls[0]
        self.assertIsNotNone(moved, "solver fell back to an unscoped rebuild")
        self.assertIn(
            free.curve_id, moved, "the point the solver relocated was not reported"
        )
        for centre in centres:
            self.assertNotIn(
                centre.curve_id,
                moved,
                "an untouched circle was flagged for rebuild, so the scoping is "
                "not actually narrowing the work",
            )
