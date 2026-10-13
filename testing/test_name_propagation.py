"""What a part's sketch, planes and mesh are called when they are made.

The body is how a part is named, so what hangs under it is named after it: the
outliner reads as one named thing with its source under it. Those names are
given where a part gains or absorbs something, not re-derived on every depsgraph
update, so a name the user types afterwards is theirs and stands.
"""

from ..operators.add_sketch import build_sketch_on_workplane
from ..utilities.body import body_of, name_after_body
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
        obj = sketch.target_object
        body = body_of(obj)
        mark_part_root(body)
        ensure_part_planes(self.context, body)
        body.name = name
        name_after_body(body, obj, obj.slvs_workplane)
        return obj, body

    def test_the_sketch_planes_and_mesh_follow(self):
        sketch_obj, body = self._part("Bracket")

        self.assertEqual(sketch_obj.name, "Bracket Sketch")
        self.assertEqual(sketch_obj.data.name, "Bracket Sketch")
        self.assertEqual(body.data.name, "Bracket")
        for axis in ("XY", "XZ", "YZ"):
            self.assertEqual(existing_part_plane(body, axis).name, f"Bracket {axis}")

    def test_a_second_pass_changes_nothing(self):
        # Assigning a name that is taken appends .001, so a pass that reassigns
        # what it just set would walk the numbers up every time it ran.
        sketch_obj, body = self._part("Latch")

        self.assertFalse(name_after_body(body, sketch_obj, sketch_obj.slvs_workplane))
        self.assertEqual(sketch_obj.name, "Latch Sketch")
        self.assertEqual(existing_part_plane(body, "XY").name, "Latch XY")

    def test_a_name_typed_on_the_sketch_stands(self):
        # Nothing re-derives these names, so what the user types is what is
        # there afterwards -- including after the updates a rename itself causes.
        sketch_obj, _body = self._part("Plate")
        sketch_obj.name = "Outline"

        self.context.view_layer.update()

        self.assertEqual(sketch_obj.name, "Outline")

    def test_a_name_typed_on_a_base_plane_stands(self):
        _sketch_obj, body = self._part("Flange")
        plane = existing_part_plane(body, "XZ")
        plane.name = "Mirror Plane"

        self.context.view_layer.update()

        self.assertEqual(plane.name, "Mirror Plane")

    def test_renaming_the_body_does_not_reach_under_it_on_its_own(self):
        # Naming happens where a part is made or absorbs something. Following a
        # body rename from the handler is what made these names untypeable, so
        # it is gone and the sketch keeps the name it was given.
        sketch_obj, body = self._part("Spacer")

        body.name = "Shim"
        self.context.view_layer.update()

        self.assertEqual(sketch_obj.name, "Spacer Sketch")

    def test_a_linked_plane_keeps_the_name_its_own_file_gave_it(self):
        """The pass names what hangs under a body, but a linked or overridden
        datablock's name is read-only: assigning it raises, and the name is not
        the add-on's to give anyway."""
        import os
        import tempfile

        import bpy

        sketch_obj, body = self._part("Hinge")

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "lib.blend")
            source = bpy.data.objects.new("Foreign", None)
            self.scene.collection.objects.link(source)
            bpy.data.libraries.write(path, {source})
            bpy.data.objects.remove(source)

            with bpy.data.libraries.load(path, link=True) as (_src, dst):
                dst.objects = ["Foreign"]
            linked = bpy.data.objects["Foreign"]
            self.addCleanup(bpy.data.batch_remove, [linked, linked.library])
            self.assertFalse(linked.is_editable)

            sketch_obj.slvs_workplane = linked
            body.name = "Pivot"
            name_after_body(body, sketch_obj, linked)

        self.assertEqual(linked.name, "Foreign")
        self.assertEqual(sketch_obj.name, "Pivot Sketch", "the rest still follows")

    def test_an_evaluated_plane_is_left_to_the_depsgraph(self):
        """A plane can reach the pass as an evaluated copy rather than the
        original. Its name is read-only too, so the pass must not try."""
        import bpy

        sketch_obj, body = self._part("Lever")
        # A plane the body owns, so the pass would name it after the body.
        plane = bpy.data.objects.new("Free Plane", None)
        self.scene.collection.objects.link(plane)
        self.addCleanup(bpy.data.objects.remove, plane)
        evaluated = plane.evaluated_get(self.context.evaluated_depsgraph_get())
        self.assertTrue(evaluated.is_runtime_data)

        body.name = "Crank"
        name_after_body(body, sketch_obj, evaluated)

        self.assertEqual(plane.name, "Free Plane", "the depsgraph owns that name")
        self.assertEqual(sketch_obj.name, "Crank Sketch", "the rest still follows")
