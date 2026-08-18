import unittest

import bpy

from ..utilities.custom_attributes import define_attribute, set_attribute_value
from .utils import Sketch2dTestCase


@unittest.skipIf(bpy.app.version < (5, 2, 0), "diagnostic requires Blender 5.2+")
class TestCustomAttributeTopologyDiagnostic(Sketch2dTestCase):
    def _source(self):
        p1 = self.add_point((0.0, 0.0))
        p2 = self.add_point((2.0, 0.0))
        line = self.add_line(p1, p2)
        define_attribute(self.sketch, "diag_value", "INT", "POINT", 13)
        set_attribute_value(self.sketch, "diag_value", 29, line.curve_id)
        return self.sketch.target_object

    def _evaluate_group(self, source, group):
        duplicate = source.copy()
        duplicate.data = source.data.copy()
        self.context.collection.objects.link(duplicate)
        for modifier in list(duplicate.modifiers):
            duplicate.modifiers.remove(modifier)
        modifier = duplicate.modifiers.new("diag", "NODES")
        modifier.node_group = group
        self.context.view_layer.update()
        depsgraph = self.context.evaluated_depsgraph_get()
        evaluated = duplicate.evaluated_get(depsgraph)
        mesh = bpy.data.meshes.new_from_object(evaluated, depsgraph=depsgraph)
        try:
            attr = mesh.attributes.get("diag_out")
            return [] if attr is None else [item.value for item in attr.data]
        finally:
            bpy.data.meshes.remove(mesh)
            bpy.data.objects.remove(duplicate, do_unlink=True)

    def _group(self, name, stages):
        group = bpy.data.node_groups.new(name, "GeometryNodeTree")
        group.interface.new_socket(
            "Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry"
        )
        group.interface.new_socket(
            "Geometry", in_out="INPUT", socket_type="NodeSocketGeometry"
        )
        nodes, links = group.nodes, group.links
        gi = nodes.new("NodeGroupInput")
        go = nodes.new("NodeGroupOutput")

        named = nodes.new("GeometryNodeInputNamedAttribute")
        named.data_type = "INT"
        named.inputs["Name"].default_value = "diag_value"
        capture = nodes.new("GeometryNodeCaptureAttribute")
        capture.domain = "POINT"
        capture.capture_items.clear()
        capture.capture_items.new("INT", "diag_value")
        links.new(gi.outputs["Geometry"], capture.inputs["Geometry"])
        links.new(named.outputs["Attribute"], capture.inputs["diag_value"])
        geometry = capture.outputs["Geometry"]
        value = capture.outputs["diag_value"]

        if "curve_to_mesh" in stages:
            node = nodes.new("GeometryNodeCurveToMesh")
            links.new(geometry, node.inputs["Curve"])
            geometry = node.outputs["Mesh"]
        if "merge" in stages:
            node = nodes.new("GeometryNodeMergePoints")
            links.new(geometry, node.inputs["Geometry"])
            geometry = node.outputs["Geometry"]
        if "mesh_to_curve" in stages:
            node = nodes.new("GeometryNodeMeshToCurve")
            links.new(geometry, node.inputs["Mesh"])
            geometry = node.outputs["Curve"]
        if "fill" in stages:
            node = nodes.new("GeometryNodeFillCurve")
            links.new(geometry, node.inputs["Curve"])
            geometry = node.outputs["Mesh"]

        store = nodes.new("GeometryNodeStoreNamedAttribute")
        store.data_type = "INT"
        store.domain = "POINT"
        store.inputs["Name"].default_value = "diag_out"
        links.new(geometry, store.inputs["Geometry"])
        links.new(value, store.inputs["Value"])
        links.new(store.outputs["Geometry"], go.inputs["Geometry"])
        return group

    def test_locate_first_attribute_loss(self):
        source = self._source()
        variants = {
            "capture_only": (),
            "curve_to_mesh": ("curve_to_mesh",),
            "merge": ("curve_to_mesh", "merge"),
            "mesh_to_curve": ("curve_to_mesh", "merge", "mesh_to_curve"),
        }
        results = {}
        groups = []
        try:
            for name, stages in variants.items():
                group = self._group(f"diag_{name}", stages)
                groups.append(group)
                results[name] = self._evaluate_group(source, group)
            print("CUSTOM_ATTRIBUTE_TOPOLOGY_DIAGNOSTIC", results)
            self.assertIn(29, results["capture_only"])
            self.assertIn(29, results["curve_to_mesh"])
            self.assertIn(29, results["merge"])
            self.assertIn(29, results["mesh_to_curve"])
        finally:
            for group in groups:
                if group.users == 0:
                    bpy.data.node_groups.remove(group)
