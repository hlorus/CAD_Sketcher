"""The generic CAD Sketcher Fillet node group (Mesh Bevel based).

Rounds corners/edges of any mesh: a flat profile's corners (Vertices) or a 3D
solid's edges (Edges), auto-detected, with a Selection field for specific
elements. Independent of sketch data, so most tests drive it on plain meshes.
"""

import unittest
from unittest import TestCase

import bpy


def _flat_quad():
    """A single flat filled n-gon (like a sketch fill)."""
    me = bpy.data.meshes.new("quad")
    me.from_pydata([(-2, -1, 0), (2, -1, 0), (2, 1, 0), (-2, 1, 0)], [], [(0, 1, 2, 3)])
    me.update()
    ob = bpy.data.objects.new("quad", me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


class TestFilletNodes(TestCase):
    def _add(self, ob, amount, affect=0, segments=4):
        from ..operators.modifiers import set_modifier_input
        from ..utilities.fillet_nodes import build_fillet_node_group, fillet_input_ids

        group = build_fillet_node_group()
        mod = ob.modifiers.new("fillet", "NODES")
        mod.node_group = group
        ids = fillet_input_ids(group)
        set_modifier_input(mod, ids["Amount"], amount)
        set_modifier_input(mod, ids["Affect"], affect)
        set_modifier_input(mod, ids["Segments"], segments)
        return mod, ids

    def _eval(self, ob):
        dg = bpy.context.evaluated_depsgraph_get()
        ev = ob.evaluated_get(dg)
        me = ev.to_mesh()
        r = (len(me.vertices), len(me.polygons), sum(p.area for p in me.polygons))
        ev.to_mesh_clear()
        return r

    def test_group_builds_with_mesh_bevel(self):
        from ..utilities.fillet_nodes import build_fillet_node_group

        group = build_fillet_node_group("test_fillet_build")
        try:
            self.assertTrue(group.is_modifier)
            names = {s.name for s in group.interface.items_tree}
            for expected in ("Amount", "Segments", "Affect", "Selection", "Geometry"):
                self.assertIn(expected, names)
            self.assertIn("GeometryNodeMeshBevel", {n.bl_idname for n in group.nodes})
        finally:
            bpy.data.node_groups.remove(group)

    def test_flat_profile_rounds_corners(self):
        """Auto picks Vertices on a flat face: corners round, area shrinks."""
        ob = _flat_quad()
        try:
            v0, f0, a0 = self._eval(ob)
            self._add(ob, 0.3)  # Affect = Auto
            v1, f1, a1 = self._eval(ob)
            self.assertGreater(v1, v0, "corners should gain vertices")
            self.assertLess(a1, a0, "rounded corners cut a little area")
            self.assertGreaterEqual(f1, 1)
        finally:
            bpy.data.objects.remove(ob, do_unlink=True)

    def test_amount_controls_width(self):
        """A larger Amount bevels more -- guards the bug where Amount was wired to
        Mesh Bevel's inert 'Offset' instead of the per-side offsets, so editing it
        did nothing."""

        def beveled_area(amount):
            bpy.ops.mesh.primitive_cube_add(size=2)
            ob = bpy.context.active_object
            try:
                self._add(ob, amount, affect=2)  # Edges
                return self._eval(ob)[2]
            finally:
                bpy.data.objects.remove(ob, do_unlink=True)

        small = beveled_area(0.1)
        large = beveled_area(0.5)
        self.assertLess(
            large, small, "a larger Amount must bevel more (less surface area)"
        )

    def test_3d_solid_rounds_edges(self):
        """The case that broke the curve pipeline: a cube's edges round."""
        bpy.ops.mesh.primitive_cube_add(size=2)
        ob = bpy.context.active_object
        try:
            v0, f0, _ = self._eval(ob)
            self.assertEqual((v0, f0), (8, 6))
            self._add(ob, 0.3)  # Auto -> Edges (closed solid)
            v1, f1, _ = self._eval(ob)
            self.assertGreater(v1, v0, "beveled edges add vertices")
            self.assertGreater(f1, f0, "beveled edges add faces")
        finally:
            bpy.data.objects.remove(ob, do_unlink=True)

    def test_selection_fillets_only_chosen_elements(self):
        """A per-element Selection field fillets a subset (fewer new verts)."""
        from ..operators.modifiers import set_modifier_input
        from ..utilities.fillet_nodes import build_fillet_node_group, fillet_input_ids

        # A DEDICATED group whose Selection is driven by a 'sel' edge attribute,
        # so the shared group is never mutated (that would leak into other tests).
        group = build_fillet_node_group("test_fillet_selection")
        named = group.nodes.new("GeometryNodeInputNamedAttribute")
        named.data_type = "BOOLEAN"
        named.inputs["Name"].default_value = "sel"
        gi = next(n for n in group.nodes if n.bl_idname == "NodeGroupInput")
        for link in list(group.links):
            if link.from_socket == gi.outputs["Selection"]:
                group.links.new(named.outputs["Attribute"], link.to_socket)
        ids = fillet_input_ids(group)

        def beveled_verts(ob, sel_flags):
            attr = ob.data.attributes.new("sel", "BOOLEAN", "EDGE")
            attr.data.foreach_set("value", sel_flags)
            mod = ob.modifiers.new("f", "NODES")
            mod.node_group = group
            set_modifier_input(mod, ids["Amount"], 0.3)
            set_modifier_input(mod, ids["Affect"], 2)  # Edges
            return self._eval(ob)[0]

        def cube():
            bpy.ops.mesh.primitive_cube_add(size=2)
            return bpy.context.active_object

        all_ob = sub_ob = None
        try:
            all_ob = cube()
            v_all = beveled_verts(all_ob, [True] * len(all_ob.data.edges))
            sub_ob = cube()
            v_sub = beveled_verts(
                sub_ob, [i < 3 for i in range(len(sub_ob.data.edges))]
            )
            self.assertGreater(v_sub, 8, "selected edges should still bevel")
            self.assertLess(
                v_sub, v_all, "a subset selection must add fewer vertices than all"
            )
        finally:
            for ob in (all_ob, sub_ob):
                if ob is not None:
                    bpy.data.objects.remove(ob, do_unlink=True)
            bpy.data.node_groups.remove(group)


@unittest.skipIf(bpy.app.version < (5, 2, 0), "requires Blender 5.2+")
class TestFilletOnSketch(TestCase):
    """Integration: the fillet rounds a real sketch's convert output."""

    def test_fillet_rounds_the_sketch_output(self):
        from ..curve_solver import solve_system
        from ..model.curve_ref import LineRef, PointRef
        from ..model.sketch_ref import (
            Sketch,
            set_active_sketch,
            stamp_sketch_props,
        )
        from ..operators.modifiers import set_modifier_input
        from ..utilities.curve_data import (
            ensure_sketch_curve_object,
            refresh_curve_geometry,
        )
        from ..utilities.fillet_nodes import (
            build_fillet_node_group,
            fillet_input_ids,
        )

        scene = bpy.data.scenes.new("fillet_sketch")
        bpy.context.window.scene = scene
        ctx = bpy.context
        ents = scene.sketcher.entities
        ents.ensure_origin_elements(ctx)
        esk = ents.add_sketch(ents.origin_plane_XY)
        ensure_sketch_curve_object(esk)
        stamp_sketch_props(esk.target_object)
        sketch = Sketch(esk.target_object)
        set_active_sketch(ctx, esk.target_object)

        # A plain rectangle: global vertex-fillet rounds its 4 corners cleanly.
        # (A dense inner circle would need a Selection to avoid scalloping it --
        # the per-element follow-up; see the module note.)
        corners = [(-4, -2), (4, -2), (4, 2), (-4, 2)]
        pts = [PointRef.create(sketch, c) for c in corners]
        for i in range(4):
            LineRef.create(sketch, pts[i], pts[(i + 1) % 4])
        self.assertTrue(solve_system(ctx))
        refresh_curve_geometry(sketch)

        ob = sketch.target_object

        # Bake the sketch's convert output to a static mesh once, then drive the
        # fillet on that mesh via to_mesh (robust; ops.convert with a second live
        # modifier is context-sensitive across tests).
        baked = ob.copy()
        baked.data = ob.data.copy()
        scene.collection.objects.link(baked)
        for o in scene.collection.objects:
            o.select_set(False)
        baked.select_set(True)
        ctx.view_layer.objects.active = baked
        bpy.ops.object.convert(target="MESH")
        sharp = sum(p.area for p in baked.data.polygons)
        self.assertAlmostEqual(sharp, 32.0, delta=0.01, msg="baked rectangle fill")

        group = build_fillet_node_group()
        mod = baked.modifiers.new("CAD Sketcher Fillet", "NODES")
        mod.node_group = group
        set_modifier_input(mod, fillet_input_ids(group)["Amount"], 0.3)

        dg = ctx.evaluated_depsgraph_get()
        me = baked.evaluated_get(dg).to_mesh()
        rounded = sum(p.area for p in me.polygons)
        baked.evaluated_get(dg).to_mesh_clear()

        self.assertLess(rounded, sharp, "fillet did not round the sketch output")
        self.assertGreater(rounded, 0.0)
