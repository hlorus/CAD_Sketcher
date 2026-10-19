"""Undo drops the curve id caches, since it restores curve data under the same key."""

from ..handlers import on_undo_redo
from ..utilities import curve_data
from .utils import Sketch2dTestCase


class TestUndoCurveCache(Sketch2dTestCase):
    def setUp(self):
        super().setUp()
        p0 = self.add_point((0, 0))
        p1 = self.add_point((2, 0))
        self.add_line(p0, p1)
        self.cd = self.sketch.target_object.data

    def _cached_ids(self):
        return curve_data._uuid_list_cache.get(
            (curve_data._data_key(self.cd), "curve_id")
        )

    def test_undo_drops_id_caches(self):
        curve_data.read_uuid_list(self.cd, "curve_id")
        self.assertIsNotNone(self._cached_ids())
        on_undo_redo(self.scene)
        self.assertIsNone(self._cached_ids())

    def test_ids_after_undo_match_the_data(self):
        curve_data.read_uuid_list(self.cd, "curve_id")
        on_undo_redo(self.scene)
        fresh = [
            curve_data.get_uuid(self.cd, "curve_id", i)
            for i in range(len(self.cd.curves))
        ]
        self.assertEqual(curve_data.read_uuid_list(self.cd, "curve_id"), fresh)
