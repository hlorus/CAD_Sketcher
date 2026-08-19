"""The nondestructive boolean node group cuts a mesh with a Curves cutter.

Guards the core regression behind PR: a sketch is a Curves object, which
Blender's Boolean *modifier* refuses, but the boolean node group consumes the
cutter's evaluated mesh through Object Info and so works with a sketch (or any
Curves object whose modifier produces a solid).
"""

import bpy

from ..operators.modifiers import (
    View3D_OT_node_boolean,
    set_boolean_operation,
    set_modifier_input,
)
from ..utilities.boolean_nodes import (
    BOOLEAN_NODE_GROUP,
    BOOLEAN_VERSION,
    build_boolean_node_group,
)
from .utils import BgsTestCase


class TestBooleanNodeGroup(BgsTestCase):
    def _solid_cutter(self):
        """A CURVES object whose GN modifier outputs a size-2 cube translated to
        (1,1,1), spanning [0,2]^3 -- partially overlapping the [-1,1]^3 target so
        union/intersect results are distinct from either operand alone."""
        curves = self.data.hair_curves.new("Cutter")
        obj = self.data.objects.new("Cutter", curves)
        self.scene.collection.objects.link(obj)

        ng = self.data.node_groups.new("cutter_solid", "GeometryNodeTree")
        ng.interface.new_socket(
            "Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry"
        )
        out = ng.nodes.new("NodeGroupOutput")
        cube = ng.nodes.new("GeometryNodeMeshCube")
        cube.inputs["Size"].default_value = (2.0, 2.0, 2.0)
        xf = ng.nodes.new("GeometryNodeTransform")
        xf.inputs["Translation"].default_value = (1.0, 1.0, 1.0)
        ng.links.new(cube.outputs["Mesh"], xf.inputs["Geometry"])
        ng.links.new(xf.outputs["Geometry"], out.inputs["Geometry"])
        obj.modifiers.new("Convert", "NODES").node_group = ng
        return obj

    def _input_ids(self, group):
        return {
            s.name: s.identifier
            for s in group.interface.items_tree
            if getattr(s, "in_out", "") == "INPUT"
        }

    def _result(self, group, cutter, operation):
        """Return (poly_count, bbox_min, bbox_max) of the boolean output.

        The bounding box is what makes union/intersect verifiable: passing
        through a single operand would give that operand's box, not the combined
        (union) or overlap (intersect) box.
        """
        bpy.ops.mesh.primitive_cube_add(size=2.0)  # target [-1,1]^3
        target = self.context.active_object
        try:
            modifier = target.modifiers.new("CAD_Sketcher Boolean", "NODES")
            modifier.node_group = group
            ids = self._input_ids(group)
            # Version-aware setters (menu socket differs on 5.0 vs 5.2).
            set_modifier_input(modifier, ids["Cutter"], cutter)
            set_boolean_operation(modifier, ids["Operation"], operation)
            depsgraph = self.context.evaluated_depsgraph_get()
            mesh = target.evaluated_get(depsgraph).to_mesh()
            if mesh is None or len(mesh.vertices) == 0:
                return 0, None, None
            xs = [v.co.x for v in mesh.vertices]
            ys = [v.co.y for v in mesh.vertices]
            zs = [v.co.z for v in mesh.vertices]
            lo = (min(xs), min(ys), min(zs))
            hi = (max(xs), max(ys), max(zs))
            return len(mesh.polygons), lo, hi
        finally:
            bpy.data.objects.remove(target, do_unlink=True)

    def _assert_vec(self, got, expected):
        for g, e in zip(got, expected):
            self.assertAlmostEqual(g, e, places=4, msg=f"{got} != {expected}")

    def test_group_builds_and_is_versioned(self):
        group = build_boolean_node_group()
        self.assertEqual(group.name, BOOLEAN_NODE_GROUP)
        self.assertEqual(group.get("cad_boolean_version"), BOOLEAN_VERSION)
        # Flagged so it appears in the Add Modifier > Geometry Nodes picker.
        self.assertTrue(group.is_modifier)
        # Idempotent: a second call returns the same up-to-date group.
        self.assertIs(build_boolean_node_group(), group)

    def test_difference_notches_the_body(self):
        group = build_boolean_node_group()
        polys, lo, hi = self._result(group, self._solid_cutter(), "Difference")
        # Body minus the +++ octant: bbox stays [-1,1]^3, but the notch adds faces.
        self._assert_vec(lo, (-1.0, -1.0, -1.0))
        self._assert_vec(hi, (1.0, 1.0, 1.0))
        self.assertGreater(polys, 6, "difference must add the notch faces")

    def test_union_combines_body_and_cutter(self):
        group = build_boolean_node_group()
        _, lo, hi = self._result(group, self._solid_cutter(), "Union")
        # Combined solid spans both cubes; a single operand would be [-1,1] or [0,2].
        self._assert_vec(lo, (-1.0, -1.0, -1.0))
        self._assert_vec(hi, (2.0, 2.0, 2.0))

    def test_intersect_is_the_overlap(self):
        group = build_boolean_node_group()
        _, lo, hi = self._result(group, self._solid_cutter(), "Intersect")
        # Only the shared [0,1]^3 region remains.
        self._assert_vec(lo, (0.0, 0.0, 0.0))
        self._assert_vec(hi, (1.0, 1.0, 1.0))

    def test_missing_cutter_is_a_noop_not_a_crash(self):
        group = build_boolean_node_group()
        # No cutter assigned -> Object Info yields empty geometry -> body passes
        # through unchanged rather than erroring.
        polys, lo, hi = self._result(group, None, "Difference")
        self.assertEqual(polys, 6)
        self._assert_vec(lo, (-1.0, -1.0, -1.0))
        self._assert_vec(hi, (1.0, 1.0, 1.0))

    # -- operator ---------------------------------------------------------

    def test_operator_registered(self):
        self.assertTrue(hasattr(bpy.ops.view3d, "slvs_node_boolean"))

    def test_is_valid_target_gate(self):
        op = View3D_OT_node_boolean
        curves = self._solid_cutter()  # CURVES object
        bpy.ops.mesh.primitive_cube_add(size=1.0)
        mesh = self.context.active_object
        empty = self.data.objects.new("empty", None)
        self.scene.collection.objects.link(empty)
        try:
            self.assertTrue(op.is_valid_target(None, mesh))
            self.assertTrue(op.is_valid_target(None, curves))
            self.assertFalse(op.is_valid_target(None, empty))
            self.assertFalse(op.is_valid_target(None, None))
        finally:
            bpy.data.objects.remove(mesh, do_unlink=True)
            bpy.data.objects.remove(empty, do_unlink=True)

    def test_operator_socket_contract_and_wiring(self):
        # The names the operator's set_props writes must exist on the group, and
        # driving them the way it does must produce a real cut. Guards against the
        # operator and the group drifting apart.
        group = build_boolean_node_group()
        ids = View3D_OT_node_boolean._input_ids(group)
        for name in ("Cutter", "Operation", "Self Intersection", "Hole Tolerant"):
            self.assertIn(name, ids)

        cutter = self._solid_cutter()
        bpy.ops.mesh.primitive_cube_add(size=2.0)
        body = self.context.active_object
        try:
            modifier = body.modifiers.new("CAD_Sketcher Boolean", "NODES")
            modifier.node_group = group
            set_modifier_input(modifier, ids["Cutter"], cutter)
            set_boolean_operation(modifier, ids["Operation"], "Difference")
            set_modifier_input(modifier, ids["Self Intersection"], True)
            set_modifier_input(modifier, ids["Hole Tolerant"], False)
            depsgraph = self.context.evaluated_depsgraph_get()
            mesh = body.evaluated_get(depsgraph).to_mesh()
            self.assertGreater(len(mesh.polygons), 6, "operator wiring must cut")
        finally:
            bpy.data.objects.remove(body, do_unlink=True)

    def _apply_via_operator(self, cutter, cutter_display):
        bpy.ops.mesh.primitive_cube_add(size=2.0)
        body = self.context.active_object
        body.name = "boolean_body"
        for obj in self.context.selected_objects:
            obj.select_set(False)
        cutter.select_set(True)
        body.select_set(True)
        self.context.view_layer.objects.active = body
        result = bpy.ops.view3d.slvs_node_boolean(
            "EXEC_DEFAULT",
            target_name=body.name,
            cutter_name=cutter.name,
            operation="Difference",
            cutter_display=cutter_display,
        )
        self.assertEqual(result, {"FINISHED"})
        return body

    def test_operator_wireframes_cutter_by_default(self):
        # display_type is set immediately (a draw-only property, no depsgraph
        # rebuild), so the wireframe applies without a crash.
        cutter = self._solid_cutter()
        cutter.display_type = "SOLID"
        body = self._apply_via_operator(cutter, "WIRE")
        try:
            self.assertEqual(cutter.display_type, "WIRE")
        finally:
            bpy.data.objects.remove(body, do_unlink=True)

    def test_cutter_equal_body_is_rejected(self):
        # Using an object as its own cutter makes the Object Info node read the
        # object the modifier is on -- a depsgraph cycle that crashes Blender.
        # The operator must refuse it and not add a modifier.
        bpy.ops.mesh.primitive_cube_add(size=2.0)
        obj = self.context.active_object
        obj.name = "self_cutter_body"
        try:
            result = bpy.ops.view3d.slvs_node_boolean(
                "EXEC_DEFAULT",
                target_name=obj.name,
                cutter_name=obj.name,
                operation="Difference",
            )
            self.assertEqual(result, {"CANCELLED"})
            self.assertNotIn("CAD_Sketcher Boolean", [m.name for m in obj.modifiers])
        finally:
            bpy.data.objects.remove(obj, do_unlink=True)

    def test_non_geometry_cutter_is_rejected(self):
        # An empty/light/camera cutter has no mesh, so the boolean would silently
        # do nothing. The operator must refuse it instead.
        bpy.ops.mesh.primitive_cube_add(size=2.0)
        body = self.context.active_object
        body.name = "body_for_empty_cutter"
        empty = self.data.objects.new("empty_cutter", None)
        self.scene.collection.objects.link(empty)
        try:
            result = bpy.ops.view3d.slvs_node_boolean(
                "EXEC_DEFAULT",
                target_name=body.name,
                cutter_name=empty.name,
                operation="Difference",
            )
            self.assertEqual(result, {"CANCELLED"})
            self.assertNotIn("CAD_Sketcher Boolean", [m.name for m in body.modifiers])
        finally:
            bpy.data.objects.remove(body, do_unlink=True)
            bpy.data.objects.remove(empty, do_unlink=True)

    def _boolean(self, body, cutter, expect="FINISHED"):
        result = bpy.ops.view3d.slvs_node_boolean(
            "EXEC_DEFAULT",
            target_name=body.name,
            cutter_name=cutter.name,
            operation="Difference",
        )
        self.assertEqual(result, {expect})

    def test_mutual_cycle_is_rejected(self):
        # A cut by B is fine; then B cut by A would close a dependency cycle
        # (A reads B, B reads A) and crash Blender. The second must be refused.
        bpy.ops.mesh.primitive_cube_add(size=2.0)
        a = self.context.active_object
        a.name = "cycle_a"
        bpy.ops.mesh.primitive_cube_add(size=1.5, location=(1, 0, 0))
        b = self.context.active_object
        b.name = "cycle_b"
        try:
            self._boolean(a, b)  # A reads B -- ok
            self._boolean(b, a, expect="CANCELLED")  # B reads A -- would cycle
            self.assertFalse(
                any(m.name.startswith("CAD_Sketcher Boolean") for m in b.modifiers)
            )
        finally:
            bpy.data.objects.remove(a, do_unlink=True)
            bpy.data.objects.remove(b, do_unlink=True)

    def test_multiple_cutters_stack_on_one_body(self):
        # Two different cutters must produce two boolean modifiers that both
        # apply, not one that overwrites the other.
        cutter1 = self._solid_cutter()  # spans [0,2]^3 -> notches the +++ corner
        cutter2 = self._solid_cutter()  # move it to notch the --- corner
        for node in cutter2.modifiers[0].node_group.nodes:
            if node.type == "TRANSFORM_GEOMETRY":
                node.inputs["Translation"].default_value = (-1.0, -1.0, -1.0)
        bpy.ops.mesh.primitive_cube_add(size=2.0)
        body = self.context.active_object
        body.name = "stack_body"
        try:
            self._boolean(body, cutter1)
            self._boolean(body, cutter2)
            bool_mods = [
                m
                for m in body.modifiers
                if m.type == "NODES" and m.name.startswith("CAD_Sketcher Boolean")
            ]
            self.assertEqual(
                len(bool_mods), 2, "each cutter should add its own modifier"
            )
            # Both notches present: a size-2 cube with two opposite corners cut
            # has more than the 6 original faces.
            depsgraph = self.context.evaluated_depsgraph_get()
            mesh = body.evaluated_get(depsgraph).to_mesh()
            self.assertGreater(len(mesh.polygons), 9)
        finally:
            bpy.data.objects.remove(body, do_unlink=True)

    def test_same_cutter_is_idempotent(self):
        # Re-applying with the same cutter edits its modifier, not a duplicate.
        cutter = self._solid_cutter()
        bpy.ops.mesh.primitive_cube_add(size=2.0)
        body = self.context.active_object
        body.name = "idempotent_body"
        try:
            self._boolean(body, cutter)
            self._boolean(body, cutter)
            bool_mods = [
                m
                for m in body.modifiers
                if m.type == "NODES" and m.name.startswith("CAD_Sketcher Boolean")
            ]
            self.assertEqual(len(bool_mods), 1)
        finally:
            bpy.data.objects.remove(body, do_unlink=True)
