"""The generic CAD Sketcher Fillet node group.

Rounds the corners of any curve/mesh-wire geometry: Mesh to Curve -> Fillet Curve
-> (Fill Curve | wire). Independent of sketch data, so these tests drive it on
plain meshes; a rounded corner drops the filled area below the sharp shape and
raises the boundary vertex count, and the ``Fill`` toggle switches surface/wire.
"""

import math
import unittest
from unittest import TestCase

import bpy


def _loops_mesh(with_hole):
    """A rectangle loop (8 x 4), optionally with an inner circle loop (r=1)."""
    verts, edges = [], []
    rect = [(-4, -2, 0), (4, -2, 0), (4, 2, 0), (-4, 2, 0)]
    verts += rect
    edges += [(i, (i + 1) % 4) for i in range(4)]
    if with_hole:
        n = 48
        base = len(verts)
        verts += [
            (math.cos(2 * math.pi * k / n), math.sin(2 * math.pi * k / n), 0)
            for k in range(n)
        ]
        edges += [(base + k, base + (k + 1) % n) for k in range(n)]
    me = bpy.data.meshes.new("loops")
    me.from_pydata(verts, edges, [])
    me.update()
    ob = bpy.data.objects.new("loops", me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


class TestFilletNodes(TestCase):
    def _add_fillet(self, ob, radius, fill=True, count=6):
        from ..operators.modifiers import set_modifier_input
        from ..utilities.fillet_nodes import build_fillet_node_group, fillet_input_ids

        group = build_fillet_node_group()
        mod = ob.modifiers.new("fillet", "NODES")
        mod.node_group = group
        ids = fillet_input_ids(group)
        set_modifier_input(mod, ids["Radius"], radius)
        set_modifier_input(mod, ids["Count"], count)
        set_modifier_input(mod, ids["Fill"], fill)
        return mod

    def _eval(self, ob):
        dg = bpy.context.evaluated_depsgraph_get()
        ev = ob.evaluated_get(dg)
        me = ev.to_mesh()
        area = sum(p.area for p in me.polygons)
        nfaces = len(me.polygons)
        nverts = len(me.vertices)
        ev.to_mesh_clear()
        return nfaces, nverts, area

    def test_group_builds_and_is_a_modifier(self):
        from ..utilities.fillet_nodes import build_fillet_node_group

        group = build_fillet_node_group("test_fillet_build")
        try:
            self.assertTrue(group.is_modifier)
            ids = {s.name for s in group.interface.items_tree}
            for expected in ("Radius", "Count", "Fill", "Geometry"):
                self.assertIn(expected, ids)
            kinds = {n.bl_idname for n in group.nodes}
            self.assertIn("GeometryNodeFilletCurve", kinds)
            self.assertIn("GeometryNodeFillCurve", kinds)
        finally:
            bpy.data.node_groups.remove(group)

    def test_fillet_rounds_corners_and_keeps_hole(self):
        ob = _loops_mesh(with_hole=True)
        try:
            self._add_fillet(ob, 0.0)
            nf0, nv0, a0 = self._eval(ob)
            ob.modifiers.clear()
            self._add_fillet(ob, 1.0)
            nf1, nv1, a1 = self._eval(ob)

            # Still a ring (two n-gon faces = outer + hole), rounded corners cut
            # a little area and add boundary points.
            self.assertEqual(nf0, 2)
            self.assertEqual(nf1, 2, "fillet must not destroy the hole")
            self.assertLess(a1, a0, "rounded corners should reduce the filled area")
            self.assertGreater(nv1, nv0, "rounded corners add boundary vertices")
        finally:
            bpy.data.objects.remove(ob, do_unlink=True)

    def test_fill_toggle_switches_surface_and_wire(self):
        ob = _loops_mesh(with_hole=False)
        try:
            self._add_fillet(ob, 0.5, fill=True)
            faces_filled, _, area = self._eval(ob)
            ob.modifiers.clear()
            self._add_fillet(ob, 0.5, fill=False)
            faces_wire, verts_wire, _ = self._eval(ob)

            self.assertGreater(faces_filled, 0)
            self.assertGreater(area, 0.0)
            self.assertEqual(faces_wire, 0, "Fill off must emit a wire (no faces)")
            self.assertGreater(verts_wire, 0)
        finally:
            bpy.data.objects.remove(ob, do_unlink=True)


@unittest.skipIf(bpy.app.version < (5, 2, 0), "requires Blender 5.2+")
class TestFilletOnSketch(TestCase):
    """Integration: the fillet stacks on a real sketch's convert output."""

    def test_fillet_after_convert_rounds_the_sketch(self):
        from ..curve_solver import solve_system

        # Reuse the 2D sketch harness inline to build a rectangle + circle.
        from ..model.curve_ref import CircleRef, LineRef, PointRef
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
        from .utils import Sketch2dTestCase  # noqa: F401  (ensure test env)

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

        corners = [(-4, -2), (4, -2), (4, 2), (-4, 2)]
        pts = [PointRef.create(sketch, c) for c in corners]
        for i in range(4):
            LineRef.create(sketch, pts[i], pts[(i + 1) % 4])
        CircleRef.create(sketch, PointRef.create(sketch, (0, 0)), 1.0)
        self.assertTrue(solve_system(ctx))
        refresh_curve_geometry(sketch)

        ob = sketch.target_object

        def area():
            dup = ob.copy()
            dup.data = ob.data.copy()
            scene.collection.objects.link(dup)
            for o in scene.collection.objects:
                o.select_set(False)
            dup.select_set(True)
            ctx.view_layer.objects.active = dup
            bpy.ops.object.convert(target="MESH")
            a = sum(p.area for p in dup.data.polygons)
            bpy.data.objects.remove(dup, do_unlink=True)
            return a

        sharp = area()
        group = build_fillet_node_group()
        mod = ob.modifiers.new("CAD Sketcher Fillet", "NODES")
        mod.node_group = group
        set_modifier_input(mod, fillet_input_ids(group)["Radius"], 1.0)
        rounded = area()

        self.assertLess(rounded, sharp, "fillet did not round the sketch output")
        self.assertGreater(rounded, 0.0)
