"""The sidebar's Name field must edit a name that sticks.

Typing into the sketch object's name was undone on the next depsgraph pass,
because the sketch, its plane and the mesh are labels derived from the body
(see name_after_body). The field edits the body instead.
"""

import bpy

from ..model.curve_ref import LineRef, PointRef
from ..operators.add_sketch import build_sketch_on_workplane
from ..ui.panels.sketch_select import _named_object
from ..utilities.body import body_of, ensure_body, rename_after_bodies
from ..utilities.curve_data import refresh_curve_geometry
from ..utilities.workplane import ensure_origin_workplane_empties
from .utils import BgsTestCase


class TestSidebarNameField(BgsTestCase):
    def setUp(self):
        super().setUp()
        self.entities.ensure_origin_elements(self.context)
        ensure_origin_workplane_empties(self.context)
        self.sketch = build_sketch_on_workplane(
            self.context, self.context.scene.sketcher.wp_xy
        )
        obj = self.sketch.target_object
        pts = [PointRef.create(self.sketch, c) for c in ((0, 0), (4, 0), (4, 4))]
        for i in range(3):
            LineRef.create(self.sketch, pts[i], pts[(i + 1) % 3])
        refresh_curve_geometry(self.sketch)
        self.body = body_of(obj) or ensure_body(self.context, obj, "Body")
        self.context.view_layer.update()

    def test_the_field_edits_the_body(self):
        self.assertEqual(_named_object(self.sketch), self.body)

    def test_a_name_typed_into_it_sticks(self):
        _named_object(self.sketch).name = "Bracket"
        rename_after_bodies(self.scene)

        self.assertEqual(self.body.name, "Bracket")
        self.assertEqual(self.sketch.target_object.name, "Bracket Sketch")
        self.assertEqual(self.sketch.target_object.slvs_workplane.name, "Bracket XY")
        self.assertEqual(self.body.data.name, "Bracket")

    def test_naming_the_sketch_itself_does_not_stick(self):
        """Why the field had to move: this is what it used to do."""
        self.sketch.target_object.name = "Typed By Hand"
        rename_after_bodies(self.scene)

        self.assertEqual(self.sketch.target_object.name, f"{self.body.name} Sketch")

    def test_a_sketch_without_a_body_is_still_nameable(self):
        curve = bpy.data.hair_curves.new("Loose")
        obj = bpy.data.objects.new("Loose", curve)
        self.scene.collection.objects.link(obj)
        from ..model.sketch_ref import Sketch, stamp_sketch_props

        stamp_sketch_props(obj)
        self.assertEqual(_named_object(Sketch(obj)), obj)
