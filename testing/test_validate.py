"""Tests for the self-heal validation sweep (utilities.validate).

Identity is stored as INT attributes that survive Blender's curve removal, so a
native delete keeps every survivor's id. Validation only needs to mint ids for
natively-added (empty) or duplicated curves, and prune constraints that
reference a curve which no longer exists.
"""

from .utils import Sketch2dTestCase
from ..utilities.curve_data import (
    get_uuid,
    set_uuid,
    remove_native_curve_by_id,
)
from ..utilities.validate import validate_sketch, reset_cache


def _ids(sketch):
    cd = sketch.target_object.data
    return [get_uuid(cd, "curve_id", i) for i in range(len(cd.curves))]


class TestValidate(Sketch2dTestCase):
    def setUp(self):
        super().setUp()
        reset_cache()

    def test_int_ids_survive_native_removal(self):
        p1 = self.add_point((0.0, 0.0))
        p2 = self.add_point((1.0, 0.0))
        p3 = self.add_point((2.0, 0.0))
        keep = {p1.curve_id, p3.curve_id}
        # remove_curves() drops STRING attrs but INT identity survives + reindexes.
        remove_native_curve_by_id(self.sketch, p2.curve_id)
        self.assertEqual(set(_ids(self.sketch)), keep)

    def test_mints_empty_curve_id(self):
        p1 = self.add_point((0.0, 0.0))
        p2 = self.add_point((1.0, 0.0))
        self.add_line(p1, p2)
        set_uuid(self.sketch.target_object.data, "curve_id", 2, "")  # stray add

        self.assertTrue(validate_sketch(self.sketch))
        ids = _ids(self.sketch)
        self.assertTrue(all(ids) and len(set(ids)) == len(ids))

    def test_mints_duplicate_curve_id(self):
        p1 = self.add_point((0.0, 0.0))
        self.add_point((1.0, 0.0))
        set_uuid(self.sketch.target_object.data, "curve_id", 1, p1.curve_id)  # copy

        self.assertTrue(validate_sketch(self.sketch))
        ids = _ids(self.sketch)
        self.assertEqual(len(set(ids)), len(ids))
        self.assertIn(p1.curve_id, ids)  # original keeps its id

    def test_recreates_dropped_attribute(self):
        self.add_point((0.0, 0.0))
        cd = self.sketch.target_object.data
        cd.attributes.remove(cd.attributes.get("name"))
        self.assertIsNone(cd.attributes.get("name"))

        self.assertTrue(validate_sketch(self.sketch))
        self.assertIsNotNone(cd.attributes.get("name"))

    def test_prunes_constraint_for_deleted_curve(self):
        p1 = self.add_point((0.0, 0.0))
        p2 = self.add_point((1.0, 0.0))
        self.sketch.constraints.add_coincident(p1.curve_id, p2.curve_id)

        remove_native_curve_by_id(self.sketch, p2.curve_id)
        reset_cache()

        self.assertTrue(validate_sketch(self.sketch))
        self.assertEqual(len(list(self.sketch.constraints.all)), 0)

    def test_keeps_valid_constraint(self):
        p1 = self.add_point((0.0, 0.0))
        p2 = self.add_point((1.0, 0.0))
        self.sketch.constraints.add_coincident(p1.curve_id, p2.curve_id)

        validate_sketch(self.sketch)  # nothing wrong -> constraint survives
        self.assertEqual(len(list(self.sketch.constraints.all)), 1)

    def test_removes_degenerate_line(self):
        from ..model.constants import SketchCurveType
        self.add_point((0.0, 0.0))
        self.add_point((1.0, 0.0))
        cd = self.sketch.target_object.data
        # Fake a native endpoint-delete: a 1-point curve typed as a LINE.
        cd.attributes.get("sketch_type").data[1].value = SketchCurveType.LINE
        reset_cache()

        self.assertTrue(validate_sketch(self.sketch))
        self.assertEqual(len(self.sketch.target_object.data.curves), 1)

    def test_signature_gate_skips_unchanged(self):
        p1 = self.add_point((0.0, 0.0))
        self.add_point((1.0, 0.0))
        set_uuid(self.sketch.target_object.data, "curve_id", 1, p1.curve_id)
        self.assertTrue(validate_sketch(self.sketch))   # fixes dup, caches sig
        self.assertFalse(validate_sketch(self.sketch))  # unchanged -> skip
