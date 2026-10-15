"""A scene-only update rebuilds the sketch mesh only if the re-solve moved it.

Any scene property change re-solves the active sketch. Rebuilding the curve
topology re-runs the whole Geometry Nodes conversion, so it is skipped when
the solve left the curve data unchanged -- and still done when it did not.
"""

from unittest import mock

from .. import global_data
from ..handlers import on_depsgraph_update
from ..model.sketch_ref import set_active_sketch
from ..utilities import curve_data
from .utils import Sketch2dTestCase


class _Update:
    updates = ()

    def __init__(self, **updated):
        self._updated = updated

    def id_type_updated(self, id_type: str) -> bool:
        return self._updated.get(id_type, False)


class TestSceneUpdateRefresh(Sketch2dTestCase):
    def setUp(self):
        super().setUp()
        set_active_sketch(self.context, self.sketch.target_object)
        p0 = self.add_point((0, 0), fixed=True)
        p1 = self.add_point((2, 0))
        self.add_line(p0, p1)
        self.p0, self.p1 = p0, p1
        self.dist = self.sketch.constraints.add_distance(
            init=True, curve_id_1=p0.curve_id, curve_id_2=p1.curve_id
        )
        global_data.needs_solve = False
        # Settle: the first solve may legitimately move things.
        on_depsgraph_update(self.scene, _Update(SCENE=True))

    def _refreshes(self, update):
        with mock.patch.object(
            curve_data,
            "refresh_curve_geometry",
            wraps=curve_data.refresh_curve_geometry,
        ) as spy:
            on_depsgraph_update(self.scene, update)
        return spy.call_count

    def test_idle_scene_update_skips_the_rebuild(self):
        self.assertEqual(self._refreshes(_Update(SCENE=True)), 0)

    def test_scene_update_that_moves_geometry_rebuilds(self):
        self.dist.value = self.dist.value + 1.0
        self.assertEqual(self._refreshes(_Update(SCENE=True)), 1)
        self.assertAlmostEqual((self.p1.co - self.p0.co).length, 3.0, places=3)

    def test_other_triggers_still_rebuild(self):
        global_data.needs_solve = True
        self.assertEqual(self._refreshes(_Update(SCENE=True)), 1)

    def test_fingerprint_tracks_positions(self):
        before = curve_data.geometry_fingerprint(self.sketch)
        self.assertEqual(before, curve_data.geometry_fingerprint(self.sketch))
        self.dist.value = self.dist.value + 1.0
        from ..curve_solver import solve_system

        solve_system(self.context, sketch=self.sketch)
        self.assertAlmostEqual((self.p1.co - self.p0.co).length, 3.0, places=3)
        self.assertNotEqual(before, curve_data.geometry_fingerprint(self.sketch))
