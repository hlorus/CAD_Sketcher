"""The sketch list: what it shows now that sketches belong to parts.

It is the only way to reach a cutter, which is hidden from the viewport while it
is cutting, so it stays. What changed is scope: with a part in focus it lists
that part's sketches rather than every sketch in the file.
"""

import bmesh
import bpy

from ..operators.modifiers import apply_boolean
from ..ui.sketches_list import VIEW3D_UL_sketches, _cutting_sketches
from ..utilities.part import join_part, mark_part_root
from .utils import Sketch2dTestCase


class _Filter:
    """Stands in for the UIList while filtering.

    Blender only builds a real UIList to draw one, and refuses to construct a
    bpy_struct subclass from Python, so the method is called unbound against a
    plain object carrying the two attributes it reads.
    """

    filter_name = ""
    bitflag_filter_item = 1 << 30

    def shown(self, context):
        flags, _order = VIEW3D_UL_sketches.filter_items(
            self, context, context.scene, "objects"
        )
        return {
            obj.name
            for obj, flag in zip(context.scene.objects, flags)
            if flag & self.bitflag_filter_item
        }


class TestSketchList(Sketch2dTestCase):
    def _cube(self, name):
        me = bpy.data.meshes.new(name)
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=2.0)
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(name, me)
        self.scene.collection.objects.link(ob)
        return ob

    def test_every_sketch_is_listed_when_no_part_is_in_focus(self):
        bpy.ops.object.select_all(action="DESELECT")
        self.context.view_layer.objects.active = None

        shown = _Filter().shown(self.context)
        self.assertIn(self.sketch.target_object.name, shown)

    def test_the_list_narrows_to_the_part_in_focus(self):
        mine = self.sketch.target_object
        other = self.new_sketch().target_object

        body = self._cube("host")
        mark_part_root(body)
        join_part(body, mine)

        bpy.ops.object.select_all(action="DESELECT")
        body.select_set(True)
        self.context.view_layer.objects.active = body

        shown = _Filter().shown(self.context)
        self.assertIn(mine.name, shown)
        self.assertNotIn(other.name, shown, "a sketch of another part is not listed")

    def test_a_cutting_sketch_is_recognised(self):
        # Its row shows that it is cutting rather than an eye toggle: the hide is
        # the display rule's, not the user's to hand back.
        body = self._cube("body")
        cutter = self.sketch.target_object
        apply_boolean(body, cutter, "Difference")

        self.assertIn(cutter.name, _cutting_sketches(self.scene))

    def test_a_plain_sketch_is_not_marked_as_cutting(self):
        self.assertNotIn(self.sketch.target_object.name, _cutting_sketches(self.scene))
