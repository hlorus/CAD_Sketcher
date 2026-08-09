"""The Blender 5.2+ identity-weld convert node group.

Only runs on 5.2+, where the ``Merge Points`` node exists. On older Blender the
convert modifier keeps loading the merge-by-distance asset, so there is nothing
to build here. The weld *behaviour* is validated separately (test_merge_id for
the ids; viewport verification for the fill).
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
