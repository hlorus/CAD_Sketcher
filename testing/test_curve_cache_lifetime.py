"""Curve id caches survive a lossless mesh refresh."""

from ..utilities import curve_data
from .utils import Sketch2dTestCase


class TestCurveCacheLifetime(Sketch2dTestCase):
    def setUp(self):
        super().setUp()
        p0 = self.add_point((0, 0))
        p1 = self.add_point((2, 0))
        self.add_line(p0, p1)
        self.cd = self.sketch.target_object.data

    def test_refresh_keeps_valid_id_caches(self):
        ids = curve_data.read_uuid_list(self.cd, "curve_id")
        curve_data.refresh_curve_geometry(self.sketch)
        key = (curve_data._data_key(self.cd), "curve_id")
        self.assertIs(curve_data._uuid_list_cache.get(key), ids)
        fresh = [curve_data.get_uuid(self.cd, "curve_id", i) for i in range(len(ids))]
        self.assertEqual(curve_data.read_uuid_list(self.cd, "curve_id"), fresh)
        for i, cid in enumerate(fresh):
            self.assertEqual(curve_data.get_curve_index(self.sketch, cid), i)
