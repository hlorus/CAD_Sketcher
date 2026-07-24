"""Tests for curve identity (the int-UUID codec and its survival).

Direct coverage of the encoding that the rest of the suite only exercised
incidentally, plus a regression for the INT32_2D-not-handled bug: the geometry
save/restore loops skipped the id attributes, so a refresh zeroed every id and
geometry resolved to the origin.
"""

import bpy

from .utils import BgsTestCase, Sketch2dTestCase
from ..utilities import curve_data as cd


class TestCurveIdCodec(BgsTestCase):
    """The hex <-> INT32_2D codec round-trips exactly, including edge cases."""

    def _fresh(self, n):
        cv = bpy.data.hair_curves.new("codec")
        cv.add_curves([1] * n)
        cd.ensure_standard_attributes(cv)
        return cv

    def test_roundtrip_known_and_edge_values(self):
        cases = [
            "00000000000000000000000000000001",  # low bit
            "80000000000000000000000000000000",  # high bit -> negative int32
            "ffffffffffffffffffffffffffffffff",  # all bits
            "0123456789abcdef0123456789abcdef",  # arbitrary
            "ffffffff00000000ffffffff00000000",  # word/half boundaries
        ]
        cv = self._fresh(len(cases))
        for i, u in enumerate(cases):
            cd.set_uuid(cv, "curve_id", i, u)
        # per-curve read and bulk read must both match, and agree with each other
        self.assertEqual([cd.get_uuid(cv, "curve_id", i) for i in range(len(cases))], cases)
        self.assertEqual(cd.read_uuid_list(cv, "curve_id"), cases)

    def test_empty_id_is_unset(self):
        cv = self._fresh(1)
        self.assertEqual(cd.get_uuid(cv, "curve_id", 0), "")  # zero-initialized
        cd.set_uuid(cv, "curve_id", 0, "0123456789abcdef0123456789abcdef")
        cd.set_uuid(cv, "curve_id", 0, "")
        self.assertEqual(cd.get_uuid(cv, "curve_id", 0), "")

    def test_new_uuid_unique_and_128bit(self):
        ids = {cd.new_uuid() for _ in range(1000)}
        self.assertEqual(len(ids), 1000)
        self.assertTrue(all(len(x) == 32 for x in ids))


class TestCurveIdSurvival(Sketch2dTestCase):
    """Identity survives the geometry-rebuild paths."""

    def test_ids_survive_geometry_refresh(self):
        # refresh_curve_geometry rebuilds topology (remove+add curves). The id
        # attributes must be preserved, or endpoints resolve to (0, 0).
        p1 = self.add_point((3.0, 4.0))
        p2 = self.add_point((5.0, 6.0))
        line = self.add_line(p1, p2)

        obj = self.sketch.target_object
        before = cd.read_uuid_list(obj.data, "curve_id")

        cd.refresh_curve_geometry(self.sketch)

        after = cd.read_uuid_list(obj.data, "curve_id")
        self.assertEqual(before, after)
        self.assertTrue(all(len(x) == 32 for x in after))
        # endpoints still resolve to their real positions, not the origin
        self.assertEqual(tuple(round(v, 1) for v in line.p1.co), (3.0, 4.0))
        self.assertEqual(tuple(round(v, 1) for v in line.p2.co), (5.0, 6.0))
