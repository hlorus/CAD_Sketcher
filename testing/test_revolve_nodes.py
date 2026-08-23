"""The from-source revolve node group.

Guards the #634 regression: revolving a *filled* sketch used to sweep the
profile's interior fill triangulation into the surface, producing redundant,
self-intersecting geometry that broke the result, while the same sketch with fill
off revolved cleanly. The from-source group normalizes any profile down to its
boundary loop before sweeping, so the lateral surface is identical whether fill
was on or off -- fill only adds end caps on a partial turn.
"""

import math

import bmesh
import bpy

from ..operators.modifiers import View3D_OT_node_revolve, set_modifier_input
from ..utilities.revolve_nodes import (
    REVOLVE_NODE_GROUP,
    REVOLVE_VERSION,
    _input_ids,
    build_revolve_node_group,
)
from .utils import BgsTestCase, Sketch2dTestCase


def _bm(ob):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    mesh = ob.evaluated_get(depsgraph).to_mesh()
    bm = bmesh.new()
    if mesh is not None:
        bm.from_mesh(mesh)
    return bm


def _stats(bm):
    return {
        "verts": len(bm.verts),
        "faces": len(bm.faces),
        "nonmanifold": sum(1 for e in bm.edges if len(e.link_faces) > 2),
        "boundary": sum(1 for e in bm.edges if len(e.link_faces) == 1),
    }


def _vertset(bm):
    return {tuple(round(c, 5) for c in v.co) for v in bm.verts}


class TestRevolveNodeGroup(BgsTestCase):
    # X-axis revolve; profiles sit at +Y so they never cross the axis.
    AXIS_ORIGIN = (0.0, 0.0, 0.0)
    AXIS_DIR = (1.0, 0.0, 0.0)

    def _revolve(self, ob, angle, resolution=math.radians(15), axis=None, origin=None):
        ng = build_revolve_node_group()
        mod = ob.modifiers.new("Revolve", "NODES")
        mod.node_group = ng
        ids = _input_ids(ng)
        set_modifier_input(mod, ids["Axis Origin"], origin or self.AXIS_ORIGIN)
        set_modifier_input(mod, ids["Axis Direction"], axis or self.AXIS_DIR)
        set_modifier_input(mod, ids["Angle"], angle)
        set_modifier_input(mod, ids["Angular Resolution"], resolution)
        return mod

    def _octagon(self, fill_type):
        """A radius-0.5 octagon at +Y (so the X axis is clear of it)."""
        bpy.ops.mesh.primitive_circle_add(
            vertices=8, radius=0.5, location=(0, 2, 0), fill_type=fill_type
        )
        ob = self.context.active_object
        bpy.ops.object.transform_apply(location=True, rotation=False, scale=False)
        return ob

    # -- build / versioning ----------------------------------------------

    def test_group_builds_and_is_versioned(self):
        group = build_revolve_node_group()
        self.assertEqual(group.name, REVOLVE_NODE_GROUP)
        self.assertEqual(group.get("cad_revolve_version"), REVOLVE_VERSION)
        self.assertTrue(group.is_modifier)
        self.assertIs(build_revolve_node_group(), group)

    def test_stale_version_rebuilds_in_place(self):
        group = build_revolve_node_group()
        group["cad_revolve_version"] = 0
        again = build_revolve_node_group()
        self.assertIs(again, group)
        self.assertEqual(group.get("cad_revolve_version"), REVOLVE_VERSION)

    # -- geometry --------------------------------------------------------

    def test_filled_full_turn_is_watertight_torus_without_caps(self):
        # A filled profile revolved a full turn closes on itself: watertight, no
        # non-manifold edges, and no caps needed (the surface is a torus).
        ob = self._octagon("NGON")
        try:
            self._revolve(ob, math.tau)
            bm = _bm(ob)
            stats = _stats(bm)
            bm.free()
            self.assertGreater(stats["faces"], 0)
            self.assertEqual(stats["boundary"], 0, "full turn must be closed")
            self.assertEqual(stats["nonmanifold"], 0)
        finally:
            bpy.data.objects.remove(ob, do_unlink=True)

    def test_filled_partial_turn_is_capped_solid(self):
        # A filled profile revolved a partial turn caps both ends -> watertight
        # solid, no boundary edges, no non-manifold edges.
        ob = self._octagon("NGON")
        try:
            self._revolve(ob, math.pi)
            bm = _bm(ob)
            stats = _stats(bm)
            bm.free()
            self.assertEqual(stats["boundary"], 0, "partial fill must be capped")
            self.assertEqual(stats["nonmanifold"], 0)
        finally:
            bpy.data.objects.remove(ob, do_unlink=True)

    def test_unfilled_partial_turn_is_open_shell(self):
        # An unfilled profile has no face to cap with, so a partial turn is an
        # open tube: it has boundary edges (the two end rings) but is still a
        # clean, non-self-intersecting surface.
        ob = self._octagon("NOTHING")
        try:
            self._revolve(ob, math.pi)
            bm = _bm(ob)
            stats = _stats(bm)
            bm.free()
            self.assertGreater(stats["boundary"], 0, "unfilled ends stay open")
            self.assertEqual(stats["nonmanifold"], 0)
        finally:
            bpy.data.objects.remove(ob, do_unlink=True)

    def test_fill_does_not_leak_interior_triangulation(self):
        # The #634 core: a *triangulated* fill has interior edges. Sweeping those
        # (the old behavior) made redundant, self-intersecting geometry. The
        # boundary-loop normalization must drop them -> zero non-manifold edges.
        ob = self._octagon("TRIFAN")
        try:
            self._revolve(ob, math.pi)
            bm = _bm(ob)
            stats = _stats(bm)
            bm.free()
            self.assertEqual(
                stats["nonmanifold"], 0, "interior fill edges must not be swept"
            )
        finally:
            bpy.data.objects.remove(ob, do_unlink=True)

    def test_lateral_surface_identical_with_and_without_fill(self):
        # The heart of the fix: the swept lateral surface is the same whether the
        # profile was filled or not. The unfilled result (pure lateral) must be a
        # vertex-for-vertex subset of the filled one, and the same size.
        filled = self._octagon("NGON")
        unfilled = self._octagon("NOTHING")
        try:
            self._revolve(filled, math.pi)
            self._revolve(unfilled, math.pi)
            bm_f, bm_u = _bm(filled), _bm(unfilled)
            set_f, set_u = _vertset(bm_f), _vertset(bm_u)
            stats_f = _stats(bm_f)
            bm_f.free()
            bm_u.free()
            self.assertEqual(len(set_u), len(set_f), "lateral vertex counts differ")
            self.assertEqual(set_u - set_f, set(), "lateral surfaces differ")
            # And the fill still added the caps that closed it.
            self.assertEqual(stats_f["boundary"], 0)
        finally:
            bpy.data.objects.remove(filled, do_unlink=True)
            bpy.data.objects.remove(unfilled, do_unlink=True)

    def test_open_profile_makes_a_cylinder_not_a_closed_band(self):
        # An open profile (a line) must NOT get a wrap column: it sweeps to a tube
        # open along its length (a cylinder), never a closed cross-section band.
        cu = bpy.data.curves.new("line", "CURVE")
        sp = cu.splines.new("POLY")
        sp.points.add(4)
        for i in range(5):
            sp.points[i].co = (2.0, 0.0, i * 0.25, 1.0)
        ob = bpy.data.objects.new("line", cu)
        self.scene.collection.objects.link(ob)
        try:
            # 16 steps around Z; 5 profile points -> 5 * 16 verts after welding the
            # 360 seam, and open top/bottom rings (no wrap column).
            self._revolve(ob, math.tau, resolution=math.tau / 16, axis=(0.0, 0.0, 1.0))
            bm = _bm(ob)
            stats = _stats(bm)
            bm.free()
        finally:
            bpy.data.objects.remove(ob, do_unlink=True)
        self.assertEqual(stats["verts"], 5 * 16)
        self.assertEqual(stats["nonmanifold"], 0)
        self.assertGreater(stats["boundary"], 0, "cylinder ends stay open")

    # -- operator contract -----------------------------------------------

    def test_operator_socket_contract(self):
        # The names the operator's set_props writes must exist on the group.
        group = build_revolve_node_group()
        ids = View3D_OT_node_revolve._input_ids(group)
        for name in ("Axis Origin", "Axis Direction", "Angle", "Angular Resolution"):
            self.assertIn(name, ids)


class TestRevolveThroughConvert(Sketch2dTestCase):
    """The gold-standard integration: revolve reads the *real* convert modifier's
    output, and that output revolves the same whether the sketch's Fill is on or
    off (bar the caps).

    A native-curves sketch object can't be read with ``to_mesh`` (its evaluated
    type stays CURVES). So a proxy mesh object pulls the sketch's convert output
    through an Object Info node -- exactly how the boolean tool consumes a sketch
    -- and revolves that, which is what the geometry-nodes graph does at runtime.
    """

    def _revolve_with_fill(self, fill):
        from ..utilities.curve_data import (
            CONVERT_MODIFIER_NAME,
            refresh_curve_geometry,
        )

        # A fresh sketch each call, with one closed circle at +Y (clear of the X
        # revolve axis).
        self.sketch = self.new_sketch()
        center = self.add_point((0.0, 2.0))
        self.add_circle(center, 0.5)
        refresh_curve_geometry(self.sketch)

        sketch_ob = self.sketch.target_object
        conv = sketch_ob.modifiers.get(CONVERT_MODIFIER_NAME)
        self.assertIsNotNone(conv)
        set_modifier_input(conv, _input_ids(conv.node_group)["Fill"], fill)

        # Proxy mesh object: Object Info(sketch) -> revolve group.
        proxy = bpy.data.objects.new("proxy", bpy.data.meshes.new("proxy"))
        self.scene.collection.objects.link(proxy)
        ng = bpy.data.node_groups.new("proxy_revolve", "GeometryNodeTree")
        ng.interface.new_socket(
            "Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry"
        )
        out = ng.nodes.new("NodeGroupOutput")
        info = ng.nodes.new("GeometryNodeObjectInfo")
        info.transform_space = "RELATIVE"
        info.inputs["Object"].default_value = sketch_ob
        rev = ng.nodes.new("GeometryNodeGroup")
        rev.node_tree = build_revolve_node_group()
        ng.links.new(info.outputs["Geometry"], rev.inputs["Geometry"])
        rev.inputs["Axis Origin"].default_value = (0.0, 0.0, 0.0)
        rev.inputs["Axis Direction"].default_value = (1.0, 0.0, 0.0)
        rev.inputs["Angle"].default_value = math.pi
        rev.inputs["Angular Resolution"].default_value = math.radians(15)
        ng.links.new(rev.outputs["Geometry"], out.inputs["Geometry"])
        proxy.modifiers.new("proxy", "NODES").node_group = ng
        return _bm(proxy)

    def test_revolve_output_matches_across_fill_toggle(self):
        bm_fill = self._revolve_with_fill(True)
        stats_fill = _stats(bm_fill)
        verts_fill = _vertset(bm_fill)
        bm_fill.free()

        bm_nofill = self._revolve_with_fill(False)
        stats_nofill = _stats(bm_nofill)
        verts_nofill = _vertset(bm_nofill)
        bm_nofill.free()

        # Both are clean surfaces (no self-intersection from swept fill).
        self.assertEqual(stats_fill["nonmanifold"], 0)
        self.assertEqual(stats_nofill["nonmanifold"], 0)
        # The lateral surface is identical; fill only adds the caps.
        self.assertEqual(verts_nofill - verts_fill, set(), "lateral surfaces differ")
        self.assertEqual(stats_fill["boundary"], 0, "filled partial turn is capped")
        self.assertGreater(stats_nofill["boundary"], 0, "unfilled stays open")
