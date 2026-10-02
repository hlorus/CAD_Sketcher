"""Where the Part menu shows up, and what it offers there.

The menu is the one home for the part verbs, drawn into the viewport context
menu, the outliner's, the Object menu and the sidebar. It must stay out of the
way of objects that have nothing to do with parts, and still be reachable when
nothing is selected, since that is how an empty assembly is started.
"""

import bmesh
import bpy

from ..ui.part_menu import has_part_entries
from ..utilities.collections import sync_part_collections
from ..utilities.part import create_assembly, join_assembly, join_part, mark_part_root
from .utils import BgsTestCase


class TestPartMenuVisibility(BgsTestCase):
    def _cube(self, name):
        me = bpy.data.meshes.new(name)
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=2.0)
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(name, me)
        self.scene.collection.objects.link(ob)
        return ob

    def _active(self, obj):
        self.context.view_layer.objects.active = obj
        return has_part_entries(self.context)

    def test_a_mesh_can_become_a_part(self):
        self.assertTrue(self._active(self._cube("pm_mesh")))

    def test_a_camera_is_left_alone(self):
        """Make Part accepts one, but its context menu should not carry ours."""
        cam = bpy.data.objects.new("pm_cam", bpy.data.cameras.new("pm_cam"))
        self.scene.collection.objects.link(cam)
        self.assertFalse(self._active(cam))

    def test_a_member_of_a_part_qualifies_whatever_it_is(self):
        root = self._cube("pm_root")
        mark_part_root(root)
        empty = bpy.data.objects.new("pm_empty", None)
        self.scene.collection.objects.link(empty)
        join_part(root, empty)
        sync_part_collections(self.scene)

        # An Empty can never become a part, but a workplane inside one still
        # needs the menu.
        self.assertTrue(self._active(empty))

    def test_an_assembly_root_qualifies(self):
        assembly = create_assembly(self.context, "pm_asm")
        part = self._cube("pm_asm_part")
        mark_part_root(part)
        join_assembly(assembly, part)
        self.assertTrue(self._active(assembly))

    def test_nothing_active_offers_nothing_in_a_context_menu(self):
        self.context.view_layer.objects.active = None
        self.assertFalse(has_part_entries(self.context))

    def test_the_menu_itself_is_always_available(self):
        """The sidebar draws it unconditionally: Add Assembly needs no selection."""
        menu = bpy.types.VIEW3D_MT_slvs_part
        self.context.view_layer.objects.active = None
        self.assertTrue(menu.poll(self.context))
