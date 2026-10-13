"""Tests for curve identity (the int-UUID codec and its survival).

Direct coverage of the encoding that the rest of the suite only exercised
incidentally, plus a regression for the INT32_2D-not-handled bug: the geometry
save/restore loops skipped the id attributes, so a refresh zeroed every id and
geometry resolved to the origin.
"""

import bpy

from ..utilities import curve_data as cd
from .utils import BgsTestCase, Sketch2dTestCase


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

    def test_curve_id_list_cache_tracks_add_remove(self):
        """The cached hex-id list (per-frame draw/pick fast path) must stay in
        sync as curves are added and removed, not serve a stale list."""
        data = self.sketch.target_object.data

        p0 = self.add_point((0.0, 0.0))
        p1 = self.add_point((1.0, 0.0))
        line = self.add_line(p0, p1)
        cached = cd.read_curve_id_list(data)
        self.assertEqual(cached, cd.read_uuid_list(data, "curve_id"))
        self.assertIn(line.curve_id, cached)

        # add -> cache must include the new curve
        p2 = self.add_point((2.0, 0.0))
        line2 = self.add_line(p1, p2)
        cached = cd.read_curve_id_list(data)
        self.assertEqual(cached, cd.read_uuid_list(data, "curve_id"))
        self.assertIn(line2.curve_id, cached)

        # remove -> cache must drop it
        line2.remove()
        cached = cd.read_curve_id_list(data)
        self.assertEqual(cached, cd.read_uuid_list(data, "curve_id"))
        self.assertNotIn(line2.curve_id, cached)

    def test_uuid_list_cache_invalidated_on_set_uuid(self):
        """Writing an id via set_uuid must not leave a stale cached list."""
        p0 = self.add_point((0.0, 0.0))
        p1 = self.add_point((1.0, 0.0))
        line = self.add_line(p0, p1)
        data = self.sketch.target_object.data

        idx = cd.get_curve_index(self.sketch, line.curve_id)
        cd.read_uuid_list(data, "curve_id")  # populate cache
        new = cd.new_uuid()
        cd.set_uuid(data, "curve_id", idx, new)

        refreshed = cd.read_uuid_list(data, "curve_id")
        self.assertIn(new, refreshed)
        self.assertNotIn(line.curve_id, refreshed)


class TestCurveIdCacheReuse(BgsTestCase):
    """The id caches must not outlive their datablock.

    They are kept per Curves datablock. Keyed on the Python id() of its wrapper
    alone, a datablock freed while its entries were cached left them behind, and
    a new datablock whose wrapper landed on the same address read the dead one's
    ids as its own (seen as test_weld_scale welding a rectangle wrong).
    """

    def _with_ids(self, n):
        cv = bpy.data.hair_curves.new("reuse")
        cv.add_curves([1] * n)
        cd.ensure_standard_attributes(cv)
        for i in range(n):
            cd.set_uuid(cv, "curve_id", i, cd.new_uuid())
        return cv

    def _reused(self):
        """A dead datablock's cached ids, and a new datablock at its address."""
        import gc

        dead = self._with_ids(4)
        ids = list(cd.read_uuid_list(dead, "curve_id"))
        cd.read_uuid_raw_list(dead, "curve_id")
        address = id(dead)
        bpy.data.hair_curves.remove(dead)
        del dead
        gc.collect()

        probes = []
        for _ in range(5000):
            fresh = bpy.data.hair_curves.new("probe")
            if id(fresh) == address:
                for probe in probes:
                    bpy.data.hair_curves.remove(probe)
                return ids, fresh
            probes.append(fresh)
        for probe in probes:
            bpy.data.hair_curves.remove(probe)
        self.skipTest("Python did not reuse the freed wrapper's address")

    def test_a_new_datablock_does_not_read_a_dead_ones_ids(self):
        dead_ids, fresh = self._reused()
        fresh.add_curves([1] * len(dead_ids))
        cd.ensure_standard_attributes(fresh)
        own = [cd.get_uuid(fresh, "curve_id", i) for i in range(len(dead_ids))]

        self.assertEqual(cd.read_uuid_list(fresh, "curve_id"), own)
        self.assertEqual(
            [any(raw) for raw in cd.read_uuid_raw_list(fresh, "curve_id")],
            [bool(cid) for cid in own],
        )
        self.assertFalse(set(dead_ids) & set(cd.read_uuid_list(fresh, "curve_id")))
