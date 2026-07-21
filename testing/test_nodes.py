"""Tests for the node tools (extrude / linear array).

Exercises the real code paths the operators use: asset loading via
assets_manager and the geometry-nodes modifier + input setting from
operators/modifiers.py, asserting the evaluated geometry actually changes.
"""

import bmesh
import bpy

from .utils import BgsTestCase
from .. import assets_manager as am
from ..global_data import LIB_NAME
from ..operators.modifiers import (
    is_2d_profile,
    View3D_OT_node_extrude,
    View3D_OT_node_array_linear,
)

EXTRUDE = "CAD Sketcher Extrude"
ARRAY = "CAD Sketcher Linear Array"


class TestNodeTools(BgsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        am.load()  # register the "CAD Sketcher Assets" library

    def tearDown(self):
        for ob in list(self.scene.collection.objects):
            me = ob.data
            bpy.data.objects.remove(ob, do_unlink=True)
            if isinstance(me, bpy.types.Mesh) and me.users == 0:
                bpy.data.meshes.remove(me)

    # -- helpers ----------------------------------------------------------

    def _plane(self):
        me = bpy.data.meshes.new("plane")
        bm = bmesh.new()
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=1.0)
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new("plane", me)
        self.scene.collection.objects.link(ob)
        return ob

    def _cube(self):
        me = bpy.data.meshes.new("cube")
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0)
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new("cube", me)
        self.scene.collection.objects.link(ob)
        return ob

    def _add_node_mod(self, ob, group):
        mod = ob.modifiers.new(f"CAD_Sketcher {group}", "NODES")
        mod.node_group = bpy.data.node_groups.get(group)
        return mod

    def _eval_mesh(self, ob):
        ob.update_tag()  # pick up modifier-input changes (as the operator does)
        dg = self.context.evaluated_depsgraph_get()
        dg.update()
        return ob.evaluated_get(dg).to_mesh()

    @staticmethod
    def _extent(me, axis):
        vals = [getattr(v.co, axis) for v in me.vertices]
        return (max(vals) - min(vals)) if vals else 0.0

    # -- tests ------------------------------------------------------------

    def test_operators_registered(self):
        self.assertTrue(hasattr(bpy.ops.view3d, "slvs_node_extrude"))
        self.assertTrue(hasattr(bpy.ops.view3d, "slvs_node_array_linear"))

    def _link(self, name, data):
        ob = bpy.data.objects.new(name, data)
        self.scene.collection.objects.link(ob)
        return ob

    def test_extrude_target_gate(self):
        # Extrude accepts sketches/curves (2D profiles) but not 3D meshes.
        mesh_ob = self._link("mesh", bpy.data.meshes.new("m"))
        curve_ob = self._link("curve", bpy.data.curves.new("c", "CURVE"))
        curves_ob = self._link("curves", bpy.data.hair_curves.new("cv"))

        self.assertFalse(is_2d_profile(mesh_ob))
        self.assertTrue(is_2d_profile(curve_ob))
        self.assertTrue(is_2d_profile(curves_ob))
        self.assertFalse(is_2d_profile(None))

        # is_valid_target ignores self, so unbound calls are fine.
        self.assertFalse(View3D_OT_node_extrude.is_valid_target(None, mesh_ob))
        self.assertTrue(View3D_OT_node_extrude.is_valid_target(None, curve_ob))
        # Array keeps the permissive default (any object).
        self.assertTrue(View3D_OT_node_array_linear.is_valid_target(None, mesh_ob))

    def test_asset_library_registered(self):
        libs = self.context.preferences.filepaths.asset_libraries
        self.assertIn(LIB_NAME, [l.name for l in libs])

    def test_extrude_adds_thickness(self):
        self.assertTrue(am.load_asset(LIB_NAME, "node_groups", EXTRUDE))
        ob = self._plane()
        z0 = self._extent(self._eval_mesh(ob), "z")
        mod = self._add_node_mod(ob, EXTRUDE)
        mod["Input_2"] = 1.5  # Size (as the operator's set_props sets it)
        z1 = self._extent(self._eval_mesh(ob), "z")
        self.assertGreater(z1, z0 + 0.5)

    def test_array_multiplies_geometry(self):
        self.assertTrue(am.load_asset(LIB_NAME, "node_groups", ARRAY))
        ob = self._cube()
        base = self._eval_mesh(ob)
        x0, n0 = self._extent(base, "x"), len(base.vertices)
        mod = self._add_node_mod(ob, ARRAY)
        mod["Input_21"][:] = (1.0, 0.0, 0.0)  # Direction
        mod["Input_23"] = 3.0  # Spacing
        mod["Input_22"] = 3  # Count
        me = self._eval_mesh(ob)
        self.assertGreater(len(me.vertices), n0)
        self.assertGreater(self._extent(me, "x"), x0 + 2.0)

    def test_extrude_mirror_option(self):
        # Mirror Extrude (Input_3) extrudes both ways -> ~double the span.
        self.assertTrue(am.load_asset(LIB_NAME, "node_groups", EXTRUDE))
        ob = self._plane()
        mod = self._add_node_mod(ob, EXTRUDE)
        mod["Input_2"] = 1.0
        mod["Input_3"] = False
        z1 = self._extent(self._eval_mesh(ob), "z")
        mod["Input_3"] = True
        z2 = self._extent(self._eval_mesh(ob), "z")
        self.assertGreater(z2, z1 * 1.6)

    def test_array_use_total_distance_option(self):
        # Use Total Distance (Input_24) reinterprets distance as the total span.
        self.assertTrue(am.load_asset(LIB_NAME, "node_groups", ARRAY))
        ob = self._cube()
        mod = self._add_node_mod(ob, ARRAY)
        mod["Input_21"][:] = (1.0, 0.0, 0.0)
        mod["Input_22"] = 4
        mod["Input_23"] = 6.0
        mod["Input_24"] = False
        x_spacing = self._extent(self._eval_mesh(ob), "x")
        mod["Input_24"] = True
        x_total = self._extent(self._eval_mesh(ob), "x")
        self.assertLess(x_total, x_spacing - 2.0)
