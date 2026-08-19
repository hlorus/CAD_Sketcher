"""The nondestructive boolean node group cuts a mesh with a Curves cutter.

Guards the core regression behind PR: a sketch is a Curves object, which
Blender's Boolean *modifier* refuses, but the boolean node group consumes the
cutter's evaluated mesh through Object Info and so works with a sketch (or any
Curves object whose modifier produces a solid).
"""

import bpy

from ..utilities.boolean_nodes import (
    BOOLEAN_NODE_GROUP,
    BOOLEAN_VERSION,
    build_boolean_node_group,
)
from .utils import BgsTestCase


class TestBooleanNodeGroup(BgsTestCase):
    def _solid_cutter(self):
        """A CURVES object whose GN modifier outputs a unit cube in the target's
        +++ corner (spans [0,1]^3), i.e. fully inside the size-2 target."""
        curves = self.data.hair_curves.new("Cutter")
        obj = self.data.objects.new("Cutter", curves)
        self.scene.collection.objects.link(obj)

        ng = self.data.node_groups.new("cutter_solid", "GeometryNodeTree")
        ng.interface.new_socket(
            "Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry"
        )
        out = ng.nodes.new("NodeGroupOutput")
        cube = ng.nodes.new("GeometryNodeMeshCube")
        cube.inputs["Size"].default_value = (1.0, 1.0, 1.0)
        xf = ng.nodes.new("GeometryNodeTransform")
        xf.inputs["Translation"].default_value = (0.5, 0.5, 0.5)
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

    def _poly_count_after_boolean(self, group, cutter, operation):
        bpy.ops.mesh.primitive_cube_add(size=2.0)
        target = self.context.active_object
        try:
            modifier = target.modifiers.new("CAD_Sketcher Boolean", "NODES")
            modifier.node_group = group
            ids = self._input_ids(group)
            inputs = modifier.properties.inputs
            getattr(inputs, ids["Cutter"]).value = cutter
            getattr(inputs, ids["Operation"]).value = operation
            depsgraph = self.context.evaluated_depsgraph_get()
            mesh = target.evaluated_get(depsgraph).to_mesh()
            return len(mesh.polygons) if mesh else None
        finally:
            bpy.data.objects.remove(target, do_unlink=True)

    def test_group_builds_and_is_versioned(self):
        group = build_boolean_node_group()
        self.assertEqual(group.name, BOOLEAN_NODE_GROUP)
        self.assertEqual(group.get("cad_boolean_version"), BOOLEAN_VERSION)
        # Flagged so it appears in the Add Modifier > Geometry Nodes picker.
        self.assertTrue(group.is_modifier)
        # Idempotent: a second call returns the same up-to-date group.
        self.assertIs(build_boolean_node_group(), group)

    def test_boolean_operations_consume_curves_cutter(self):
        group = build_boolean_node_group()
        cutter = self._solid_cutter()

        # Target: size-2 cube (6 faces). Cutter: unit cube fully inside its
        # +++ corner. Difference notches the corner (more faces); Union leaves
        # the body unchanged (cutter contained); Intersect yields the cutter.
        difference = self._poly_count_after_boolean(group, cutter, "Difference")
        union = self._poly_count_after_boolean(group, cutter, "Union")
        intersect = self._poly_count_after_boolean(group, cutter, "Intersect")

        self.assertEqual(union, 6, "union with a fully-contained cutter is the body")
        self.assertEqual(
            intersect, 6, "intersect with a contained cutter is the cutter"
        )
        self.assertGreater(difference, 6, "difference must add the notch faces")

    def test_missing_cutter_is_a_noop_not_a_crash(self):
        group = build_boolean_node_group()
        # No cutter assigned -> Object Info yields empty geometry -> body passes
        # through unchanged rather than erroring.
        polys = self._poly_count_after_boolean(group, None, "Difference")
        self.assertEqual(polys, 6)
