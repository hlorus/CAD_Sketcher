"""The body a sketch is realised on.

The sketch stays a Curves object with no modifiers; its curves are read by the
body's convert modifier, so the body is a plain mesh that can be applied,
exported and read with ``to_mesh`` (issue #723).
"""

import math

from ..model.curve_ref import CircleRef
from ..operators.add_sketch import build_sketch_on_workplane
from ..utilities.body import body_of, sketch_of
from ..utilities.curve_data import CONVERT_MODIFIER_NAME
from .utils import Sketch2dTestCase


class TestBody(Sketch2dTestCase):
    def setUp(self):
        super().setUp()
        from ..utilities.workplane import ensure_origin_workplane_empties

        ensure_origin_workplane_empties(self.context)
        self.datum = self.context.scene.sketcher.wp_xy

    def _disc(self, radius=1.0):
        """A sketch of one circle, and the body it is realised on."""
        from ..model.curve_ref import PointRef

        sketch = build_sketch_on_workplane(self.context, self.datum)
        center = PointRef.create(sketch, (0.0, 0.0))
        CircleRef.create(sketch, center, radius)
        return sketch, body_of(sketch.target_object)

    def _eval_mesh(self, ob):
        ob.update_tag()
        dg = self.context.evaluated_depsgraph_get()
        dg.update()
        return ob.evaluated_get(dg).to_mesh()

    def test_the_sketch_carries_no_modifiers(self):
        sketch, body = self._disc()

        self.assertEqual(list(sketch.target_object.modifiers), [])
        self.assertEqual(sketch_of(body), sketch.target_object)

    def test_one_modifier_reads_the_sketch_and_meshes_it(self):
        # Reading the source and converting it is one step, not two: the body's
        # stack starts at Convert the way a sketch's used to.
        sketch, body = self._disc()

        names = [m.name for m in body.modifiers]
        self.assertEqual(names, [CONVERT_MODIFIER_NAME])

    def test_the_body_evaluates_to_the_sketch_geometry(self):
        sketch, body = self._disc(radius=1.0)

        me = self._eval_mesh(body)
        area = sum(p.area for p in me.polygons)
        # Tessellated, so a little under the true area of the circle.
        self.assertGreater(area, math.pi * 0.95)
        self.assertLess(area, math.pi * 1.01)

    def test_the_sketch_curves_are_out_of_the_viewport(self):
        # They would sit on top of the body's mesh as a second outline; the
        # overlay is what draws a sketch.
        sketch, body = self._disc()
        obj = sketch.target_object

        self.assertTrue(obj.hide_viewport)
        # Still drawn and pickable as a sketch, and still read by the body.
        from ..model.sketch_ref import set_active_sketch

        set_active_sketch(self.context, None)
        self.assertTrue(sketch.is_visible(self.context))

        me = self._eval_mesh(body)
        self.assertGreater(sum(p.area for p in me.polygons), 0.0)

    def test_hiding_it_by_hand_still_hides_it(self):
        sketch, body = self._disc()
        obj = sketch.target_object
        from ..model.sketch_ref import set_active_sketch

        set_active_sketch(self.context, None)
        self.context.view_layer.update()
        obj.hide_set(True)

        self.assertFalse(sketch.is_visible(self.context))
