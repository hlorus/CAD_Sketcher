"""The merge-id gate must never give a different answer than recomputing.

``compute_merge_ids`` (and the source seeds it writes) is skipped when the
sketch's connectivity signature is unchanged, because weld ids derive from which
point curves a segment references and from coincidence constraints, never from
positions. That is a silent-failure risk: stale weld ids do not raise, they stop
a corner welding, and the sketch quietly fails to fill (issue #342 territory).

Every test here does the same thing: perform an edit, let the gate decide, then
force a full recompute and assert nothing moved. If the signature ever misses an
input, the forced pass repairs it and the comparison fails.
"""

import math

import numpy as np

from ..utilities.curve_data import (
    SOURCE_CURVE_ID_ATTR,
    SOURCE_ENDPOINT_ID_ATTR,
    _connectivity_signature,
    compute_merge_ids,
    refresh_curve_geometry,
)
from .utils import Sketch2dTestCase

_GATED_ATTRS = ("merge_id", SOURCE_CURVE_ID_ATTR, SOURCE_ENDPOINT_ID_ATTR)


class MergeGateEquivalence(Sketch2dTestCase):
    def _snapshot(self):
        cd = self.sketch.target_object.data
        snap = {}
        for name in _GATED_ATTRS:
            attr = cd.attributes.get(name)
            if attr is None:
                continue
            length = len(cd.points) if attr.domain == "POINT" else len(cd.curves)
            buf = np.empty(length, dtype=np.int32)
            attr.data.foreach_get("value", buf)
            snap[name] = buf
        return snap

    def assert_gate_matches_recompute(self):
        """Whatever the gate decided, a forced recompute must change nothing."""
        compute_merge_ids(self.sketch)  # gated: may skip
        gated = self._snapshot()
        compute_merge_ids(self.sketch, force=True)
        forced = self._snapshot()

        self.assertEqual(set(gated), set(forced))
        self.assertTrue(gated, "no gated attributes were written at all")
        for name in forced:
            np.testing.assert_array_equal(
                gated[name],
                forced[name],
                err_msg=f"{name!r} was stale: the gate skipped a real change",
            )


class TestGateCoversConnectivityChanges(MergeGateEquivalence):
    def test_position_only_change(self):
        p0 = self.add_point((0, 0), fixed=True)
        p1 = self.add_point((2, 0))
        self.add_line(p0, p1)
        self.solve()

        p1.co = (3.0, 1.0)
        self.solve()
        self.assert_gate_matches_recompute()

    def test_adding_a_segment(self):
        p0 = self.add_point((0, 0), fixed=True)
        p1 = self.add_point((2, 0))
        self.add_line(p0, p1)
        self.solve()
        compute_merge_ids(self.sketch)

        p2 = self.add_point((2, 2))
        self.add_line(p1, p2)
        self.solve()
        self.assert_gate_matches_recompute()

    def test_adding_a_coincidence_constraint(self):
        """A constraint can change weld ids with no geometry change at all.

        Two endpoints at the same spot belong to distinct point curves until a
        coincidence constraint unions them, so this moves the answer while every
        position, id and count stays put. The signature has to include it.
        """
        a0 = self.add_point((0, 0), fixed=True)
        a1 = self.add_point((2, 0))
        b0 = self.add_point((2, 0))
        b1 = self.add_point((2, 2))
        self.add_line(a0, a1)
        self.add_line(b0, b1)
        self.solve()
        compute_merge_ids(self.sketch)
        before = self._snapshot()

        self.sketch.constraints.add_coincident(
            curve_id_1=a1.curve_id, curve_id_2=b0.curve_id
        )
        self.solve()
        self.assert_gate_matches_recompute()

        after = self._snapshot()
        self.assertFalse(
            np.array_equal(before["merge_id"], after["merge_id"]),
            "the coincidence constraint should have changed the weld ids",
        )

    def test_arc_resegmentation_shifts_point_indices(self):
        """Growing an arc changes its point count, moving every later index."""
        centre = self.add_point((0, 0), fixed=True)
        start = self.add_point((2.0, 0), fixed=True)
        end = self.add_point((0.0, 2.0))
        self.add_arc(centre, start, end)
        p0 = self.add_point((5, 0))
        p1 = self.add_point((7, 0))
        self.add_line(p0, p1)
        self.solve()
        compute_merge_ids(self.sketch)

        for degrees in (300, 45, 200):
            with self.subTest(degrees=degrees):
                a = math.radians(degrees)
                end.co = (2.0 * math.cos(a), 2.0 * math.sin(a))
                self.solve()
                self.assert_gate_matches_recompute()

    def test_after_a_geometry_refresh(self):
        """refresh_curve_geometry rebuilds topology and restores attributes."""
        p0 = self.add_point((0, 0), fixed=True)
        p1 = self.add_point((2, 0))
        self.add_line(p0, p1)
        self.add_circle(self.add_point((5, 0)), 1.0)
        self.solve()
        refresh_curve_geometry(self.sketch)
        self.assert_gate_matches_recompute()

    def test_fresh_sketch_never_skips(self):
        """A signature match must not skip when the outputs were never written."""
        p0 = self.add_point((0, 0), fixed=True)
        p1 = self.add_point((2, 0))
        self.add_line(p0, p1)
        self.solve()
        compute_merge_ids(self.sketch)

        # Drop the outputs but leave connectivity untouched, exactly the state a
        # datablock is in before its first merge pass.
        cd = self.sketch.target_object.data
        for name in _GATED_ATTRS:
            if cd.attributes.get(name) is not None:
                cd.attributes.remove(cd.attributes[name])

        self.assertTrue(
            compute_merge_ids(self.sketch),
            "gate skipped a sketch whose merge attributes do not exist",
        )
        self.assertIsNotNone(cd.attributes.get("merge_id"))


class TestGateActuallySkips(Sketch2dTestCase):
    """Guard the optimization: a position-only solve must not redo the work."""

    def test_settled_and_dragged_solves_skip(self):
        p0 = self.add_point((0, 0), fixed=True)
        p1 = self.add_point((2, 0))
        self.add_line(p0, p1)
        self.add_circle(self.add_point((5, 0)), 1.0)
        self.solve()
        compute_merge_ids(self.sketch)  # warm the signature

        self.assertFalse(
            compute_merge_ids(self.sketch), "recomputed with nothing changed"
        )
        p1.co = (4.0, 2.0)
        self.solve()
        self.assertFalse(
            compute_merge_ids(self.sketch),
            "a position-only change recomputed the weld ids",
        )


class TestConnectivitySignature(Sketch2dTestCase):
    """What the gate keys on, tested directly.

    Asserting on ``compute_merge_ids``' return value cannot show this: creating a
    curve recomputes the ids on the way through, so by the time a test looks the
    signature is current again. The signature itself is the unit that has to
    discriminate.
    """

    def _signature(self):
        return _connectivity_signature(self.sketch.target_object.data)

    def test_position_change_keeps_the_signature(self):
        p0 = self.add_point((0, 0), fixed=True)
        p1 = self.add_point((2, 0))
        self.add_line(p0, p1)
        self.add_circle(self.add_point((5, 0)), 1.0)
        self.solve()

        before = self._signature()
        p1.co = (4.0, 3.0)
        self.solve()
        self.assertEqual(
            before, self._signature(), "a position-only change moved the signature"
        )

    def test_new_segment_changes_the_signature(self):
        p0 = self.add_point((0, 0), fixed=True)
        p1 = self.add_point((2, 0))
        self.add_line(p0, p1)
        self.solve()

        before = self._signature()
        self.add_line(p1, self.add_point((2, 2)))
        self.solve()
        self.assertNotEqual(before, self._signature())

    def test_coincidence_constraint_changes_the_signature(self):
        """The input that no amount of geometry inspection would reveal."""
        a0 = self.add_point((0, 0), fixed=True)
        a1 = self.add_point((2, 0))
        b0 = self.add_point((2, 0))
        b1 = self.add_point((2, 2))
        self.add_line(a0, a1)
        self.add_line(b0, b1)
        self.solve()

        before = self._signature()
        self.sketch.constraints.add_coincident(
            curve_id_1=a1.curve_id, curve_id_2=b0.curve_id
        )
        self.assertNotEqual(
            before,
            self._signature(),
            "a coincidence constraint left the signature unchanged, so the gate "
            "would serve stale weld ids and the corner would stop welding",
        )

    def test_arc_resegmentation_changes_the_signature(self):
        centre = self.add_point((0, 0), fixed=True)
        start = self.add_point((2.0, 0), fixed=True)
        end = self.add_point((0.0, 2.0))
        self.add_arc(centre, start, end)
        self.solve()

        before = self._signature()
        end.co = (2.0 * math.cos(math.radians(300)), 2.0 * math.sin(math.radians(300)))
        self.solve()
        self.assertNotEqual(
            before,
            self._signature(),
            "the arc grew to more control points without moving the signature",
        )
