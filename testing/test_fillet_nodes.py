"""The generic CAD Sketcher Fillet node group (Mesh Bevel based).

Rounds corners/edges of any mesh: a flat profile's corners (Vertices) or a 3D
solid's edges (Edges), auto-detected, with a Selection field for specific
elements. Independent of sketch data, so most tests drive it on plain meshes.
"""

import unittest
from unittest import TestCase

import bpy

from .utils import Sketch2dTestCase


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


class TestFilletPicks(TestCase):
    """Picked elements: the tool stores what was clicked, no rule to author."""

    def _cube(self):
        bpy.ops.mesh.primitive_cube_add(size=2)
        return bpy.context.active_object

    def _fillet(self, ob):
        from ..operators.fillet import add_fillet_modifier

        return add_fillet_modifier(ob, 0.2)

    def _eval(self, ob):
        dg = bpy.context.evaluated_depsgraph_get()
        ev = ob.evaluated_get(dg)
        me = ev.to_mesh()
        counts = (len(me.vertices), len(me.polygons))
        ev.to_mesh_clear()
        return counts

    def test_picks_are_stored_on_the_modifier(self):
        from ..utilities.fillet_nodes import get_domain, get_picks, set_picks

        ob = self._cube()
        try:
            mod = self._fillet(ob)
            set_picks(mod, [3, 1, 1], "EDGE")
            self.assertEqual(get_picks(mod), [1, 3])
            self.assertEqual(get_domain(mod), "EDGE")
        finally:
            bpy.data.objects.remove(ob, do_unlink=True)

    def test_picking_fillets_fewer_edges_than_all(self):
        from ..utilities.fillet_nodes import set_picks

        ob = self._cube()
        try:
            mod = self._fillet(ob)
            set_picks(mod, range(12), "EDGE")  # every edge
            all_verts, _ = self._eval(ob)
            set_picks(mod, [0, 1], "EDGE")
            some_verts, _ = self._eval(ob)
            plain = 8
            self.assertGreater(some_verts, plain, "picked edges should be rounded")
            self.assertLess(some_verts, all_verts, "only the picks should round")
        finally:
            bpy.data.objects.remove(ob, do_unlink=True)

    def test_picks_get_their_own_group(self):
        """Two objects with different picks must not share one node group."""
        from ..utilities.fillet_nodes import FILLET_NODE_GROUP, set_picks

        first, second = self._cube(), self._cube()
        try:
            mod1, mod2 = self._fillet(first), self._fillet(second)
            self.assertIs(mod1.node_group, mod2.node_group)  # shared while unpicked
            set_picks(mod1, [0], "EDGE")
            set_picks(mod2, [5], "EDGE")
            self.assertIsNot(mod1.node_group, mod2.node_group)
            self.assertNotEqual(mod1.node_group.name, FILLET_NODE_GROUP)
        finally:
            for ob in (first, second):
                bpy.data.objects.remove(ob, do_unlink=True)

    def test_clearing_picks_returns_to_the_shared_group(self):
        from ..utilities.fillet_nodes import FILLET_NODE_GROUP, set_picks

        ob = self._cube()
        try:
            mod = self._fillet(ob)
            set_picks(mod, [2], "EDGE")
            set_picks(mod, [], "EDGE")
            self.assertEqual(mod.node_group.name, FILLET_NODE_GROUP)
        finally:
            bpy.data.objects.remove(ob, do_unlink=True)

    def test_corner_picks_use_the_vertex_domain(self):
        from ..operators.modifiers import get_modifier_input
        from ..utilities.fillet_nodes import (
            AFFECT_VERTICES,
            fillet_input_ids,
            set_picks,
        )

        ob = self._cube()
        try:
            mod = self._fillet(ob)
            set_picks(mod, [0], "POINT")
            ids = fillet_input_ids(mod.node_group)
            self.assertEqual(get_modifier_input(mod, ids["Affect"]), AFFECT_VERTICES)
        finally:
            bpy.data.objects.remove(ob, do_unlink=True)


class TestPickedEdgeDrawing(Sketch2dTestCase):
    """The picked edges are read back from the body's geometry, to draw them."""

    def test_points_of_picks_on_a_sketch_body(self):
        from ..model.curve_ref import CircleRef, PointRef
        from ..operators.add_sketch import build_sketch_on_workplane
        from ..operators.fillet import picked_edge_points
        from ..utilities.body import body_of
        from ..utilities.workplane import ensure_origin_workplane_empties

        ensure_origin_workplane_empties(self.context)
        sketch = build_sketch_on_workplane(
            self.context, self.context.scene.sketcher.wp_xy
        )
        CircleRef.create(sketch, PointRef.create(sketch, (0.0, 0.0)), 1.0)
        body = body_of(sketch.target_object)
        self.assertIsNotNone(body, "a sketch is realised on a body")

        points = picked_edge_points(self.context, body, [0, 1], "EDGE")
        self.assertEqual(len(points), 4)


class TestFilletTool(TestCase):
    """The Fillet workspace tool: pick elements, no rule to author."""

    def test_tool_is_registered_with_the_object_tools(self):
        from ..declarations import Operators, WorkSpaceTools
        from ..workspacetools.manager import ToolGroup, _registry

        entries = {cls.bl_idname: group for cls, _kwargs, group in _registry}
        self.assertEqual(entries.get(WorkSpaceTools.Fillet), ToolGroup.NON_SKETCH)
        self.assertTrue(hasattr(bpy.types, "VIEW3D_OT_slvs_fillet_select"))
        self.assertEqual(Operators.FilletSelect, "view3d.slvs_fillet_select")

    def test_tool_is_stateful_like_the_other_node_tools(self):
        from ..operators.fillet import View3D_OT_slvs_fillet_select
        from ..stateful_operator.logic import StatefulOperatorLogic
        from ..workspacetools.fillet import VIEW3D_T_slvs_fillet

        self.assertTrue(issubclass(View3D_OT_slvs_fillet_select, StatefulOperatorLogic))
        states = View3D_OT_slvs_fillet_select.get_states_definition()
        self.assertEqual([s.name for s in states], ["Edge"])
        self.assertIs(states[0].types[0], bpy.types.MeshEdge)
        # Drives the tool through the framework's operator access keymap.
        idnames = {item[0] for item in VIEW3D_T_slvs_fillet.bl_keymap}
        self.assertIn(View3D_OT_slvs_fillet_select.bl_idname, idnames)

    def test_tool_has_a_shortcut(self):
        from .. import keymaps
        from ..declarations import WorkSpaceTools

        keys = {row[0]: row[2:] for row in keymaps.NODE_TOOL_KEYS}
        self.assertEqual(keys.get(WorkSpaceTools.Fillet), ("F", "F"))

    def test_fillet_modifier_is_found_by_its_group(self):
        from ..operators.fillet import add_fillet_modifier, fillet_modifier

        bpy.ops.mesh.primitive_cube_add(size=2)
        ob = bpy.context.active_object
        try:
            self.assertIsNone(fillet_modifier(ob))
            modifier = add_fillet_modifier(ob)
            found = fillet_modifier(ob)
            self.assertIsNotNone(found)
            self.assertEqual(found.name, modifier.name)
        finally:
            bpy.data.objects.remove(ob, do_unlink=True)


class TestFilletHover(TestCase):
    def test_tool_previews_the_edge_under_the_cursor(self):
        """The hover gizmo highlights edges while the tool idles, as for the
        projection tool -- otherwise nothing shows until a click."""
        from ..declarations import WorkSpaceTools
        from ..gizmos.object_hover import _IDLE_HOVER_TYPES

        self.assertEqual(
            _IDLE_HOVER_TYPES.get(WorkSpaceTools.Fillet), (bpy.types.MeshEdge,)
        )


class TestFilletRun(TestCase):
    """One run keeps picking: status text, Esc/right-click and undo per pick all
    come from the framework, as in the other tools."""

    def test_operator_repeats_its_states(self):
        from ..operators.fillet import View3D_OT_slvs_fillet_select

        self.assertTrue(View3D_OT_slvs_fillet_select.repeat_states)

    def test_repeating_run_starts_the_states_over(self):
        from ..stateful_operator.logic import StatefulOperatorLogic

        calls = {}

        class Op(StatefulOperatorLogic):
            bl_label = "Repeat"

            def _end(self, context, succeede, **kwargs):
                calls["end"] = kwargs.get("keep_stateful_running")

            def _reset_op(self):
                calls["reset"] = True

            def _capture_baseline(self, context):
                pass

            def set_state(self, context, index):
                calls["state"] = index

            def create_snapshot(self, context):
                return None

        Op().do_repeat_states(bpy.context)
        self.assertTrue(calls["end"], "the run must not end between picks")
        self.assertTrue(calls["reset"])
        self.assertEqual(calls["state"], 0, "picking starts over on the first state")

    def test_every_filleted_object_is_shown_unrounded(self):
        """Not just the active one: the object under the cursor is often not the
        selected one, and a visible rounded edge renumbers the elements, which
        would make every pick after the first land somewhere else."""
        from unittest import mock

        from ..operators import fillet

        bpy.ops.mesh.primitive_cube_add(size=2)
        first = bpy.context.active_object
        bpy.ops.mesh.primitive_cube_add(size=2, location=(4, 0, 0))
        second = bpy.context.active_object
        try:
            mods = [fillet.add_fillet_modifier(ob) for ob in (first, second)]
            bpy.context.view_layer.objects.active = second  # the other one is not

            with mock.patch.object(fillet, "fillet_tool_active", return_value=True):
                fillet.sync_fillet_visibility(bpy.context)
            self.assertFalse(any(m.show_viewport for m in mods), "all shown unrounded")

            with mock.patch.object(fillet, "fillet_tool_active", return_value=False):
                fillet.sync_fillet_visibility(bpy.context)
            self.assertTrue(all(m.show_viewport for m in mods), "all restored")
        finally:
            fillet.restore_fillets(bpy.context)
            for ob in (first, second):
                bpy.data.objects.remove(ob, do_unlink=True)

    def test_the_session_lasts_as_long_as_the_tool(self):
        """The fillet is hidden while its tool is active (so clicks land on the
        geometry the node tree indexes) and shown again for any other tool."""
        from unittest import mock

        from ..operators import fillet

        bpy.ops.mesh.primitive_cube_add(size=2)
        ob = bpy.context.active_object
        try:
            modifier = fillet.add_fillet_modifier(ob)
            with mock.patch.object(fillet, "fillet_tool_active", return_value=True):
                fillet.sync_fillet_visibility(bpy.context)
                self.assertFalse(modifier.show_viewport, "hidden while picking")
                fillet.sync_fillet_visibility(bpy.context)  # idempotent
                self.assertFalse(modifier.show_viewport)
            with mock.patch.object(fillet, "fillet_tool_active", return_value=False):
                fillet.sync_fillet_visibility(bpy.context)
            self.assertTrue(modifier.show_viewport, "shown again for another tool")
        finally:
            fillet.restore_fillets(bpy.context)
            bpy.data.objects.remove(ob, do_unlink=True)


class TestFilletRedo(TestCase):
    """The redo panel adjusts the last pick instead of undoing it."""

    def _op(self, ob, index):
        from ..operators.fillet import View3D_OT_slvs_fillet_select
        from .utils import make_operator_double

        op = make_operator_double(View3D_OT_slvs_fillet_select)()
        op.amount = 0.2
        op.target_name = ob.name
        op._picked = lambda: (ob, index)
        return op

    def test_redo_keeps_the_pick_and_applies_the_amount(self):
        from ..operators.fillet import add_fillet_modifier, fillet_modifier
        from ..operators.modifiers import get_modifier_input
        from ..utilities.fillet_nodes import fillet_input_ids, get_picks, set_picks

        bpy.ops.mesh.primitive_cube_add(size=2)
        ob = bpy.context.active_object
        try:
            modifier = add_fillet_modifier(ob, 0.1)
            set_picks(modifier, [3], "EDGE")

            op = self._op(ob, 3)
            op._redoing = True
            op.main(bpy.context)

            modifier = fillet_modifier(ob)
            self.assertEqual(get_picks(modifier), [3], "a redo must not toggle it off")
            ids = fillet_input_ids(modifier.node_group)
            self.assertAlmostEqual(
                get_modifier_input(modifier, ids["Amount"]), 0.2, places=5
            )
        finally:
            bpy.data.objects.remove(ob, do_unlink=True)

    def test_interactive_click_toggles_the_pick_off(self):
        from ..operators.fillet import add_fillet_modifier, fillet_modifier
        from ..utilities.fillet_nodes import set_picks

        bpy.ops.mesh.primitive_cube_add(size=2)
        ob = bpy.context.active_object
        try:
            modifier = add_fillet_modifier(ob, 0.1)
            set_picks(modifier, [3], "EDGE")

            op = self._op(ob, 3)
            op.main(bpy.context)
            self.assertIsNone(
                fillet_modifier(ob), "the last pick dropped, so no fillet"
            )
        finally:
            bpy.data.objects.remove(ob, do_unlink=True)

    def test_a_picked_object_reuses_its_group(self):
        from ..operators.fillet import add_fillet_modifier
        from ..utilities.fillet_nodes import set_picks

        bpy.ops.mesh.primitive_cube_add(size=2)
        ob = bpy.context.active_object
        try:
            modifier = add_fillet_modifier(ob, 0.1)
            first = set_picks(modifier, [1], "EDGE").name
            second = set_picks(modifier, [1, 2], "EDGE").name
            self.assertEqual(first, second, "picking again must not copy the group")
        finally:
            bpy.data.objects.remove(ob, do_unlink=True)


class TestFilletDefaults(TestCase):
    def test_default_is_a_flat_fillet(self):
        """One segment by default: a flat fillet, raised to round the edge."""
        from ..utilities.fillet_nodes import build_fillet_node_group

        group = build_fillet_node_group("test_fillet_defaults")
        try:
            segments = next(
                item
                for item in group.interface.items_tree
                if item.name == "Segments" and item.in_out == "INPUT"
            )
            self.assertEqual(segments.default_value, 1)
            self.assertEqual(segments.min_value, 1)
        finally:
            bpy.data.node_groups.remove(group)

    def test_the_panel_activates_the_tool(self):
        """The sidebar button starts the Fillet tool, so picking behaves the same
        as from the toolbar, and the one-shot Add Fillet operator is gone."""
        import inspect

        from ..declarations import Operators
        from ..ui.panels.tools import VIEW3D_PT_sketcher_tools

        source = inspect.getsource(VIEW3D_PT_sketcher_tools._draw_node_tools)
        self.assertIn("InvokeTool", source)
        self.assertIn("WorkSpaceTools.Fillet", source)
        self.assertIn("Operators.FilletSelect", source)
        self.assertFalse(hasattr(bpy.types, "VIEW3D_OT_slvs_add_fillet"))
        self.assertFalse(hasattr(Operators, "AddFillet"))


if __name__ == "__main__":
    unittest.main()
