"""Which sketches can be picked as a reference, and why.

A sketch's curves are a hidden object: the add-on draws them itself so they do
not double up on the body's mesh. Asking Blender whether they are visible said
no to every sketch, so a plainly visible, greyed sketch could not be snapped to
or projected from.
"""

import bpy

from ..drawing.reference_pick import is_reference_source
from ..operators.add_sketch import build_sketch_on_workplane
from ..utilities.workplane import ensure_origin_workplane_empties
from .utils import BgsTestCase


class TestReferenceSource(BgsTestCase):
    def setUp(self):
        super().setUp()
        ensure_origin_workplane_empties(self.context)
        self.sk = self.context.scene.sketcher

    def test_a_drawn_coplanar_sketch_is_offered(self):
        """The reported bug: visible on screen, but not pickable."""
        active = build_sketch_on_workplane(self.context, self.sk.wp_xy)
        other = build_sketch_on_workplane(self.context, self.sk.wp_xy)
        ob = other.target_object

        # As created: hidden to Blender, drawn by the overlay.
        self.assertTrue(ob.hide_viewport)
        self.assertNotIn(ob, list(self.context.visible_objects))
        self.assertTrue(other.is_visible(self.context))

        self.assertTrue(is_reference_source(ob, self.context, active))

    def test_a_sketch_the_user_hid_is_not_offered(self):
        active = build_sketch_on_workplane(self.context, self.sk.wp_xy)
        other = build_sketch_on_workplane(self.context, self.sk.wp_xy)
        ob = other.target_object
        ob.hide_set(True)

        self.assertFalse(other.is_visible(self.context), "the eye hides it")
        self.assertFalse(is_reference_source(ob, self.context, active))
        ob.hide_set(False)

    def test_another_plane_is_not_offered_until_it_is_shown(self):
        """Referencing means coplanar; showing a sketch's curves widens it."""
        active = build_sketch_on_workplane(self.context, self.sk.wp_xy)
        other = build_sketch_on_workplane(self.context, self.sk.wp_xz)
        ob = other.target_object
        self.assertFalse(is_reference_source(ob, self.context, active))

        bpy.ops.view3d.slvs_set_sketch_visibility(sketch_name=ob.name)
        self.assertFalse(ob.hide_viewport)
        self.assertTrue(
            is_reference_source(ob, self.context, active),
            "an explicitly shown sketch is offered from any plane",
        )

    def test_a_raw_curves_object_still_follows_blender(self):
        """Only sketches are hidden by us; everything else keeps Blender's rule."""
        active = build_sketch_on_workplane(self.context, self.sk.wp_xy)
        raw = bpy.data.objects.new("rs_raw", bpy.data.hair_curves.new("rs_raw"))
        self.scene.collection.objects.link(raw)
        self.context.view_layer.update()
        self.assertTrue(is_reference_source(raw, self.context, active))
        raw.hide_set(True)
        self.assertFalse(is_reference_source(raw, self.context, active))


class TestOriginPoint(BgsTestCase):
    """A sketch has exactly one origin point.

    Linking the curves object lets the depsgraph handler run mid-build, and its
    validation gives an origin to a sketch that has none yet. Creating a second
    unconditionally left every sketch with two coincident origins, which tie in
    the snap ranking and flip under the cursor.
    """

    def test_a_new_sketch_has_one_origin(self):
        from ..model.curve_ref import curve_ref
        from ..utilities.curve_data import read_uuid_list, sketch_curve_data

        ensure_origin_workplane_empties(self.context)
        sketch = build_sketch_on_workplane(
            self.context, self.context.scene.sketcher.wp_xy
        )

        cd = sketch_curve_data(sketch)
        origins = [
            cid
            for cid in read_uuid_list(cd, "curve_id")
            if cid and getattr(curve_ref(sketch, cid), "is_origin", False)
        ]
        self.assertEqual(len(origins), 1, "a sketch must have exactly one origin")


class TestSnapCandidateDedupe(BgsTestCase):
    """One candidate per position, so the choice cannot flip between frames."""

    def test_the_most_specific_candidate_wins_a_tie(self):
        from ..utilities.view import _best_per_position

        here = (1.0, 2.0, 0.0)
        vertex = (0, 0.0, None, {"type": "VERTEX", "world_point": here})
        edge = (2, 0.0, None, {"type": "EDGE", "world_point": here})
        elsewhere = (0, 5.0, None, {"type": "VERTEX", "world_point": (9.0, 9.0, 0.0)})

        kept = _best_per_position([edge, vertex, elsewhere])

        self.assertEqual(len(kept), 2, "the two at one position collapse")
        types = {c[3]["type"] for c in kept}
        self.assertEqual(types, {"VERTEX"}, "a vertex beats an edge at the same spot")

    def test_order_does_not_decide(self):
        from ..utilities.view import _best_per_position

        here = (1.0, 2.0, 0.0)
        a = (0, 0.0, None, {"type": "VERTEX", "world_point": here})
        b = (2, 0.0, None, {"type": "EDGE", "world_point": here})

        self.assertEqual(
            _best_per_position([a, b])[0][3]["type"],
            _best_per_position([b, a])[0][3]["type"],
        )
