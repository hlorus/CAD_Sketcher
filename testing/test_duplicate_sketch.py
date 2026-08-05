"""Duplicating a sketch object must yield independent constraint values (#14)."""

import bpy

from .utils import Sketch2dTestCase


class TestDuplicateSketch(Sketch2dTestCase):
    def _duplicate(self):
        obj_a = self.sketch.target_object
        obj_b = obj_a.copy()
        obj_b.data = obj_a.data.copy()
        bpy.context.scene.collection.objects.link(obj_b)
        from ..model.sketch_ref import Sketch, stamp_sketch_props
        stamp_sketch_props(obj_b)
        return Sketch(obj_b)

    def test_duplicate_gets_independent_constraint_value(self):
        sc = self.sketch.constraints
        p0 = self.add_point((0, 0), fixed=True)
        p1 = self.add_point((2, 0))
        line = self.add_line(p0, p1)
        sc.add_distance(init=True, value=2.0, curve_id_1=line.curve_id)

        sketch_b = self._duplicate()

        # Right after duplication the copy shares the uid...
        ca = list(self.sketch.constraints.all)[0]
        cb = list(sketch_b.constraints.all)[0]
        self.assertEqual(ca.constraint_uid, cb.constraint_uid)

        # ...validation re-mints the copy's uid and preserves the value.
        from ..utilities.validate import validate_all_sketches
        validate_all_sketches(self.context.scene)

        ca = list(self.sketch.constraints.all)[0]
        cb = list(sketch_b.constraints.all)[0]
        self.assertNotEqual(ca.constraint_uid, cb.constraint_uid,
                            "duplicate must get its own constraint uid")
        self.assertAlmostEqual(ca.value, 2.0)
        self.assertAlmostEqual(cb.value, 2.0, msg="copy keeps its value")

        # Editing one no longer affects the other.
        cb.value = 9.0
        self.assertAlmostEqual(ca.value, 2.0, msg="editing copy must not change original")
        self.assertAlmostEqual(cb.value, 9.0)
