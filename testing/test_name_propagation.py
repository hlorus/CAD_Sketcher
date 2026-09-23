"""Renaming a body renames what is named after it.

The body is how a part is named; its sketch, planes and mesh carry labels
derived from that name rather than names of their own, so they are re-derived
rather than remembered (see utilities.body.rename_after_bodies).
"""

from ..operators.add_sketch import build_sketch_on_workplane
from ..utilities.body import body_of, rename_after_bodies
from ..utilities.part import ensure_part_planes, existing_part_plane, mark_part_root
from ..utilities.workplane import ensure_origin_workplane_empties
from .utils import BgsTestCase


class TestNamePropagation(BgsTestCase):
    def setUp(self):
        super().setUp()
        self.entities.ensure_origin_elements(self.context)
        ensure_origin_workplane_empties(self.context)
        self.datum = self.context.scene.sketcher.wp_xy

    def _part(self, name):
        sketch = build_sketch_on_workplane(self.context, self.datum)
        body = body_of(sketch.target_object)
        mark_part_root(body)
        ensure_part_planes(self.context, body)
        body.name = name
        rename_after_bodies(self.scene)
        return sketch.target_object, body

    def test_the_sketch_planes_and_mesh_follow(self):
        sketch_obj, body = self._part("Bracket")

        self.assertEqual(sketch_obj.name, "Bracket Sketch")
        self.assertEqual(sketch_obj.data.name, "Bracket Sketch")
        self.assertEqual(body.data.name, "Bracket")
        for axis in ("XY", "XZ", "YZ"):
            self.assertEqual(existing_part_plane(body, axis).name, f"Bracket {axis}")

    def test_a_second_pass_changes_nothing(self):
        # Assigning a name that is taken appends .001, so a pass that reassigns
        # what it just set would walk the numbers up on every update.
        sketch_obj, body = self._part("Latch")

        self.assertFalse(rename_after_bodies(self.scene))
        self.assertEqual(sketch_obj.name, "Latch Sketch")
        self.assertEqual(existing_part_plane(body, "XY").name, "Latch XY")

    def test_a_name_typed_on_the_sketch_is_derived_away(self):
        # The sketch's name is a label for the body's, not a name of its own.
        sketch_obj, _body = self._part("Plate")
        sketch_obj.name = "Outline"

        self.assertTrue(rename_after_bodies(self.scene))
        self.assertEqual(sketch_obj.name, f"{_body.name} Sketch")

    def test_only_what_this_update_touched_is_looked_at(self):
        # The pass runs on every depsgraph update, so it is scoped to the ids
        # that changed; a body nobody touched cannot have drifted.
        sketch_obj, body = self._part("Plate")
        sketch_obj.name = "Outline"

        class _Update:
            def __init__(self, id):
                self.id = id

        class _Depsgraph:
            updates = ()

        quiet = _Depsgraph()
        self.assertFalse(rename_after_bodies(self.scene, quiet))
        self.assertEqual(sketch_obj.name, "Outline", "not touched, not looked at")

        touched = _Depsgraph()
        touched.updates = (_Update(body),)
        self.assertTrue(rename_after_bodies(self.scene, touched))
        self.assertEqual(sketch_obj.name, f"{body.name} Sketch")
