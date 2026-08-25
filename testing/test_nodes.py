"""Tests for the node tools (extrude / linear array).

Exercises the real code paths the operators use: asset loading via
assets_manager and the geometry-nodes modifier + input setting from
operators/modifiers.py, asserting the evaluated geometry actually changes.
"""

import bmesh
import bpy

from .. import assets_manager as am
from ..global_data import LIB_NAME
from ..operators.modifiers import (
    View3D_OT_node_array_linear,
    View3D_OT_node_extrude,
    View3D_OT_node_revolve,
    is_2d_profile,
    set_modifier_input,
)
from .utils import BgsTestCase

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

    @staticmethod
    def _max_edge_length(me):
        v = me.vertices
        return max(
            ((v[e.vertices[0]].co - v[e.vertices[1]].co).length for e in me.edges),
            default=0.0,
        )

    @staticmethod
    def _boundary_edges(me):
        import bmesh
        bm = bmesh.new()
        bm.from_mesh(me)
        n = sum(1 for e in bm.edges if len(e.link_faces) == 1)
        bm.free()
        return n

    def _closed_profile(self, radius=2.0):
        """A closed (cyclic) square-section profile offset from the Z axis."""
        cu = bpy.data.curves.new("closed", "CURVE")
        sp = cu.splines.new("POLY")
        sp.points.add(3)
        sp.use_cyclic_u = True
        for i, (x, z) in enumerate(((radius, 0), (radius + 1, 0), (radius + 1, 1), (radius, 1))):
            sp.points[i].co = (x, 0.0, z, 1.0)
        ob = bpy.data.objects.new("closed", cu)
        self.scene.collection.objects.link(ob)
        return ob

    # -- tests ------------------------------------------------------------

    def test_operators_registered(self):
        self.assertTrue(hasattr(bpy.ops.view3d, "slvs_node_extrude"))
        self.assertTrue(hasattr(bpy.ops.view3d, "slvs_node_array_linear"))
        self.assertTrue(hasattr(bpy.ops.view3d, "slvs_node_revolve"))

    def _profile_curve(self, n=5, radius=2.0, height=1.0):
        """A poly curve of ``n`` points offset from the Z axis (an open
        profile to revolve)."""
        cu = bpy.data.curves.new("profile", "CURVE")
        sp = cu.splines.new("POLY")
        sp.points.add(n - 1)
        for i in range(n):
            sp.points[i].co = (radius, 0.0, height * i / (n - 1), 1.0)
        ob = bpy.data.objects.new("profile", cu)
        self.scene.collection.objects.link(ob)
        return ob

    def _revolve(self, ob, angle, angle_step, axis=(0.0, 0.0, 1.0), origin=(0.0, 0.0, 0.0)):
        from ..utilities.revolve_nodes import _input_ids, build_revolve_node_group

        ng = build_revolve_node_group()
        mod = ob.modifiers.new("rev", "NODES")
        mod.node_group = ng
        ids = _input_ids(ng)
        set_modifier_input(mod, ids["Axis Origin"], origin)
        set_modifier_input(mod, ids["Axis Direction"], axis)
        set_modifier_input(mod, ids["Angle"], angle)
        set_modifier_input(mod, ids["Angular Resolution"], angle_step)
        return mod

    def test_revolve_target_gate(self):
        # Revolve accepts curves/sketches and mesh profiles (the node group
        # converts mesh edges to a curve), rejects only non-geometry.
        curve_ob = self._link("curve", bpy.data.curves.new("c", "CURVE"))
        self.assertTrue(View3D_OT_node_revolve.is_valid_target(None, curve_ob))
        self.assertTrue(View3D_OT_node_revolve.is_valid_target(None, self._cube()))
        self.assertFalse(View3D_OT_node_revolve.is_valid_target(None, None))

    def _profile_mesh(self, n=5, radius=2.0, height=1.0):
        """A mesh edge-path of ``n`` verts offset from the Z axis."""
        me = bpy.data.meshes.new("profile_mesh")
        bm = bmesh.new()
        verts = [bm.verts.new((radius, 0.0, height * i / (n - 1))) for i in range(n)]
        for a, b in zip(verts, verts[1:]):
            bm.edges.new((a, b))
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new("profile_mesh", me)
        self.scene.collection.objects.link(ob)
        return ob

    def test_revolve_mesh_profile(self):
        # A mesh edge-path profile revolves too (Mesh to Curve at the input).
        import math
        ob = self._profile_mesh(n=5, radius=2.0, height=1.0)
        self._revolve(ob, math.tau, math.tau / 16)
        me = self._eval_mesh(ob)
        self.assertGreater(len(me.polygons), 0)
        self.assertAlmostEqual(self._extent(me, "x"), 4.0, delta=0.05)
        self.assertAlmostEqual(self._extent(me, "y"), 4.0, delta=0.05)

    def test_revolve_creates_surface(self):
        import math
        ob = self._profile_curve(n=5, radius=2.0, height=1.0)
        steps = 16  # angle_step = tau/16 -> ceil(tau / (tau/16)) = 16 steps
        self._revolve(ob, math.tau, math.tau / steps)
        me = self._eval_mesh(ob)
        # Grid of profile_points x (steps + 1), minus the welded 360 seam ring
        # (row 0 and row `steps` coincide at a full turn) -> profile_points * steps.
        self.assertEqual(len(me.vertices), 5 * steps)
        self.assertGreater(len(me.polygons), 0)
        # Full revolution around Z -> radial span ~ 2 * radius in X and Y.
        self.assertAlmostEqual(self._extent(me, "x"), 4.0, delta=0.05)
        self.assertAlmostEqual(self._extent(me, "y"), 4.0, delta=0.05)
        self.assertAlmostEqual(self._extent(me, "z"), 1.0, delta=0.01)
        # Faces connect the right neighbours: for a radius-2 profile at 16 steps
        # the longest edge is a circumference arc (~0.78). Scrambled topology
        # (wrong vertex->face mapping) produces edges spanning the whole shape.
        self.assertLess(self._max_edge_length(me), 1.0)

    def test_revolve_angle_step_controls_resolution(self):
        import math
        ob = self._profile_curve()
        self._revolve(ob, math.tau, math.tau / 8)   # coarse: ~8 steps
        n_low = len(self._eval_mesh(ob).vertices)
        ob.modifiers.clear()
        self._revolve(ob, math.tau, math.tau / 32)  # fine: ~32 steps
        n_high = len(self._eval_mesh(ob).vertices)
        self.assertGreater(n_high, n_low)

    def test_revolve_angle_step_scales_with_angle(self):
        # Same angle step -> a quarter turn uses ~1/4 the steps of a full turn.
        import math
        step = math.radians(6)
        ob = self._profile_curve()
        self._revolve(ob, math.tau, step)
        n_full = len(self._eval_mesh(ob).vertices)
        ob.modifiers.clear()
        self._revolve(ob, math.pi / 2, step)
        n_quarter = len(self._eval_mesh(ob).vertices)
        self.assertLess(n_quarter, n_full)

    def test_revolve_closed_profile_full_is_watertight(self):
        # A full revolve of a closed profile sweeps its closing segment (cyclic
        # wrap) and welds the seam -> a watertight solid (no boundary edges).
        import math
        ob = self._closed_profile()
        self._revolve(ob, math.tau, math.radians(10))
        me = self._eval_mesh(ob)
        self.assertGreater(len(me.polygons), 0)
        self.assertEqual(self._boundary_edges(me), 0)

    def test_revolve_partial_unfilled_profile_stays_open(self):
        # A partial revolve of an *unfilled* closed profile has no face to cap
        # with, so its two angular ends stay open (boundary edges present) -- a
        # valid surface without end caps, matching the non-filled spec. (End caps
        # only appear when the profile is filled; see test_revolve_nodes.py.)
        import math
        ob = self._closed_profile()
        self._revolve(ob, math.pi / 2, math.radians(10))
        me = self._eval_mesh(ob)
        self.assertGreater(len(me.polygons), 0)
        self.assertGreater(self._boundary_edges(me), 0)

    def test_revolve_negative_angle_matches_positive(self):
        # The step count derives from |angle|, so revolving the other direction
        # keeps the same resolution (the per-step angle stays signed).
        import math
        ob = self._profile_curve()
        self._revolve(ob, math.pi / 2, math.radians(10))
        n_pos = len(self._eval_mesh(ob).vertices)
        ob.modifiers.clear()
        self._revolve(ob, -math.pi / 2, math.radians(10))
        n_neg = len(self._eval_mesh(ob).vertices)
        self.assertEqual(n_pos, n_neg)

    def test_revolve_partial_angle(self):
        import math
        ob = self._profile_curve(radius=2.0)
        self._revolve(ob, math.pi / 2, math.radians(6))  # quarter turn
        me = self._eval_mesh(ob)
        # A 90° sweep of a profile at radius 2 stays within one quadrant span,
        # so the Y extent is well under the full-revolution diameter (4).
        self.assertLess(self._extent(me, "y"), 3.0)

    def test_revolve_redo_reapplies_from_persisted_props(self):
        # The redo panel re-runs execute() on a fresh instance with no pointer
        # state -- only the persisted props survive. The operator must resolve
        # the target + axis from those and edit the *existing* modifier rather
        # than crash or spawn a duplicate.
        import math
        ob = self._profile_mesh(n=3, radius=2.0, height=1.0)
        for o in self.scene.collection.objects:
            o.select_set(False)
        bpy.context.view_layer.objects.active = ob
        ob.select_set(True)

        common = dict(
            target_name=ob.name,
            axis_origin=(0.0, 0.0, 0.0),
            axis_direction=(0.0, 0.0, 1.0),
            angle=math.pi,
            angular_resolution=math.radians(30),
        )
        res = bpy.ops.view3d.slvs_node_revolve("EXEC_DEFAULT", flip=False, **common)
        self.assertEqual(res, {"FINISHED"})
        mod = ob.modifiers.get("CAD_Sketcher Revolve")
        self.assertIsNotNone(mod)
        self.assertGreater(len(self._eval_mesh(ob).polygons), 0)

        # Re-exec (as a redo-panel tweak would) reuses the same modifier.
        res2 = bpy.ops.view3d.slvs_node_revolve("EXEC_DEFAULT", flip=True, **common)
        self.assertEqual(res2, {"FINISHED"})
        n = len([m for m in ob.modifiers if m.name == "CAD_Sketcher Revolve"])
        self.assertEqual(n, 1)

    def test_revolve_readback_seeds_props_from_modifier(self):
        # Re-invoking on an object that already has the modifier should start
        # from its current values, not the defaults. read_props pulls the angle
        # + resolution sockets back onto the operator.
        import math

        from ..operators.modifiers import get_modifier_input
        from ..utilities.revolve_nodes import _input_ids
        ob = self._profile_mesh(n=3)
        mod = self._revolve(ob, math.pi / 3, math.radians(15))

        # The version-aware getter round-trips what _revolve set.
        ids = _input_ids(mod.node_group)
        self.assertAlmostEqual(
            get_modifier_input(mod, ids["Angle"]), math.pi / 3, places=5
        )
        self.assertAlmostEqual(
            get_modifier_input(mod, ids["Angular Resolution"]),
            math.radians(15),
            places=5,
        )

        # read_props only assigns self.angle/self.angular_resolution, so a plain
        # stand-in captures them without needing a live modal operator.
        class _Stub:
            pass

        stub = _Stub()
        View3D_OT_node_revolve.read_props(stub, mod)
        self.assertAlmostEqual(stub.angle, math.pi / 3, places=5)
        self.assertAlmostEqual(stub.angular_resolution, math.radians(15), places=5)

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
        set_modifier_input(mod, "Input_2", 1.5)  # Size (as the operator's set_props sets it)
        z1 = self._extent(self._eval_mesh(ob), "z")
        self.assertGreater(z1, z0 + 0.5)

    def test_extrude_unfilled_wire_becomes_walls(self):
        # A non-filled profile converts to a face-less wire; the extrude tool must
        # extrude its edges into open walls with real thickness instead of doing
        # nothing (the face-only asset silently produced no geometry before).
        from ..utilities.extrude_nodes import ensure_extrude_edge_walls

        self.assertTrue(am.load_asset(LIB_NAME, "node_groups", EXTRUDE))
        ensure_extrude_edge_walls(bpy.data.node_groups.get(EXTRUDE))

        me = bpy.data.meshes.new("wire")
        me.from_pydata(
            [(0, 0, 0), (2, 0, 0), (2, 2, 0), (0, 2, 0)],
            [(0, 1), (1, 2), (2, 3), (3, 0)],
            [],
        )
        me.update()
        ob = self._link("wire", me)
        mod = self._add_node_mod(ob, EXTRUDE)
        set_modifier_input(mod, "Input_2", 1.5)  # Size
        out = self._eval_mesh(ob)
        self.assertGreater(len(out.polygons), 0, "no walls created from wire")
        self.assertAlmostEqual(self._extent(out, "z"), 1.5, delta=0.01)

    def test_array_multiplies_geometry(self):
        self.assertTrue(am.load_asset(LIB_NAME, "node_groups", ARRAY))
        ob = self._cube()
        base = self._eval_mesh(ob)
        x0, n0 = self._extent(base, "x"), len(base.vertices)
        mod = self._add_node_mod(ob, ARRAY)
        set_modifier_input(mod, "Input_21", (1.0, 0.0, 0.0))  # Direction
        set_modifier_input(mod, "Input_23", 3.0)  # Spacing
        set_modifier_input(mod, "Input_22", 3)  # Count
        me = self._eval_mesh(ob)
        self.assertGreater(len(me.vertices), n0)
        self.assertGreater(self._extent(me, "x"), x0 + 2.0)

    def test_extrude_mirror_option(self):
        # Mirror Extrude (Input_3) extrudes both ways -> ~double the span.
        self.assertTrue(am.load_asset(LIB_NAME, "node_groups", EXTRUDE))
        ob = self._plane()
        mod = self._add_node_mod(ob, EXTRUDE)
        set_modifier_input(mod, "Input_2", 1.0)
        set_modifier_input(mod, "Input_3", False)
        z1 = self._extent(self._eval_mesh(ob), "z")
        set_modifier_input(mod, "Input_3", True)
        z2 = self._extent(self._eval_mesh(ob), "z")
        self.assertGreater(z2, z1 * 1.6)

    def test_array_use_total_distance_option(self):
        # Use Total Distance (Input_24) reinterprets distance as the total span.
        self.assertTrue(am.load_asset(LIB_NAME, "node_groups", ARRAY))
        ob = self._cube()
        mod = self._add_node_mod(ob, ARRAY)
        set_modifier_input(mod, "Input_21", (1.0, 0.0, 0.0))
        set_modifier_input(mod, "Input_22", 4)
        set_modifier_input(mod, "Input_23", 6.0)
        set_modifier_input(mod, "Input_24", False)
        x_spacing = self._extent(self._eval_mesh(ob), "x")
        set_modifier_input(mod, "Input_24", True)
        x_total = self._extent(self._eval_mesh(ob), "x")
        self.assertLess(x_total, x_spacing - 2.0)
