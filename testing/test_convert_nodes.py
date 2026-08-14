"""The Blender 5.2+ identity-weld convert node group.

Only runs on 5.2+, where the ``Merge Points`` node exists. On older Blender the
convert modifier keeps loading the merge-by-distance asset, so there is nothing
to build here. Besides weld identity, the 5.2 group materializes deterministic
vertex/face ids on the generated mesh for consumers that keep element links.
"""

import unittest
from unittest import TestCase

import bpy


@unittest.skipIf(bpy.app.version < (5, 2, 0), "Merge Points requires Blender 5.2+")
class TestConvertNodeGroup(TestCase):
    def test_builds_identity_group(self):
        from ..utilities.convert_nodes import (
            _is_identity_group,
            build_convert_node_group,
        )

        ng = build_convert_node_group("test_convert_id")
        try:
            self.assertTrue(_is_identity_group(ng))
            ids = {n.bl_idname for n in ng.nodes}
            for expected in (
                "GeometryNodeMergePoints",
                "GeometryNodeInputMeshVertexNeighbors",
                "GeometryNodeCurveToMesh",
                "GeometryNodeFillCurve",
                "GeometryNodeStoreNamedAttribute",
            ):
                self.assertIn(expected, ids)
        finally:
            bpy.data.node_groups.remove(ng)

    def test_idempotent(self):
        from ..utilities.convert_nodes import build_convert_node_group

        a = build_convert_node_group("test_convert_id2")
        b = build_convert_node_group("test_convert_id2")
        try:
            self.assertIs(a, b)
        finally:
            bpy.data.node_groups.remove(a)

    def test_excludes_zero_id(self):
        """The weld must AND valence with merge_id != 0, so a not-yet-computed
        id (0) can't collapse every endpoint into one point (draw-time glitch)."""
        from ..utilities.convert_nodes import (
            CONVERT_VERSION,
            build_convert_node_group,
        )

        ng = build_convert_node_group("test_convert_zero")
        try:
            self.assertEqual(ng.get("cad_convert_version"), CONVERT_VERSION)
            ands = [
                n
                for n in ng.nodes
                if n.bl_idname == "FunctionNodeBooleanMath" and n.operation == "AND"
            ]
            self.assertTrue(ands, "weld selection does not exclude merge_id 0")
        finally:
            bpy.data.node_groups.remove(ng)

    def test_generated_id_nodes_have_expected_domains(self):
        from ..utilities.convert_nodes import (
            FACE_ID_ATTR,
            VERTEX_ID_ATTR,
            build_convert_node_group,
        )

        ng = build_convert_node_group("test_generated_ids")
        try:
            stores = {
                n.inputs["Name"].default_value: n
                for n in ng.nodes
                if n.bl_idname == "GeometryNodeStoreNamedAttribute"
            }
            self.assertEqual(stores[VERTEX_ID_ATTR].data_type, "INT")
            self.assertEqual(stores[VERTEX_ID_ATTR].domain, "POINT")
            self.assertEqual(stores[FACE_ID_ATTR].data_type, "INT")
            self.assertEqual(stores[FACE_ID_ATTR].domain, "FACE")

            # Both ids are explicitly driven by the Index field. Blender's
            # background test runner cannot materialize a Mesh from this Curves
            # object after the GN modifier, so the node wiring itself is the
            # regression boundary: identical topology -> identical indices.
            index_nodes = {
                n for n in ng.nodes if n.bl_idname == "GeometryNodeInputIndex"
            }
            self.assertEqual(len(index_nodes), 2)
            for store in stores.values():
                value_links = [link for link in store.inputs["Value"].links]
                self.assertEqual(len(value_links), 1)
                self.assertIn(value_links[0].from_node, index_nodes)
        finally:
            bpy.data.node_groups.remove(ng)

    def test_version_marker_rebuilds_stale(self):
        """A group with an old version marker is rebuilt in place (so modifiers
        bound to it upgrade without rebinding)."""
        from ..utilities.convert_nodes import (
            CONVERT_VERSION,
            build_convert_node_group,
        )

        ng = build_convert_node_group("test_convert_stale")
        try:
            ng["cad_convert_version"] = 0
            again = build_convert_node_group("test_convert_stale")
            self.assertIs(again, ng)
            self.assertEqual(ng.get("cad_convert_version"), CONVERT_VERSION)
        finally:
            bpy.data.node_groups.remove(ng)
