"""Stable generated ids for both CAD Sketcher conversion paths."""

import unittest
from unittest import TestCase

import bpy


class TestGeneratedIds(TestCase):
    def test_active_conversion_path_emits_stable_ids(self):
        from ..utilities.convert_nodes import (
            FACE_ID_ATTR,
            VERTEX_ID_ATTR,
        )
        from ..utilities.curve_data import _get_convert_node_group

        self.assertEqual(VERTEX_ID_ATTR, "id")
        group = _get_convert_node_group()
        self.assertIsNotNone(group)
        stores = {
            node.inputs["Name"].default_value: node
            for node in group.nodes
            if node.bl_idname == "GeometryNodeStoreNamedAttribute"
        }
        self.assertEqual(stores[VERTEX_ID_ATTR].domain, "POINT")
        self.assertEqual(stores[FACE_ID_ATTR].domain, "FACE")
        self.assertFalse(
            any(node.bl_idname == "GeometryNodeInputIndex" for node in group.nodes),
            "generated ids must not depend on topology-global Index",
        )

    def test_unaffected_ids_survive_neighbor_insert_and_remove(self):
        """Verify public `id` and face ids persist on evaluated mesh topology edits."""
        from ..utilities.convert_nodes import (
            FACE_ID_ATTR,
            SOURCE_CURVE_ID_ATTR,
            SOURCE_ENDPOINT_ID_ATTR,
            VERTEX_ID_ATTR,
            add_generated_id_nodes,
        )

        self.assertEqual(VERTEX_ID_ATTR, "id")
        group = bpy.data.node_groups.new(
            "test_stable_generated_ids", "GeometryNodeTree"
        )
        group.interface.new_socket(
            "Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry"
        )
        group.interface.new_socket(
            "Geometry", in_out="INPUT", socket_type="NodeSocketGeometry"
        )
        nodes, links = group.nodes, group.links
        group_input = nodes.new("NodeGroupInput")
        group_output = nodes.new("NodeGroupOutput")
        geometry = add_generated_id_nodes(nodes, links, group_input.outputs["Geometry"])
        links.new(geometry, group_output.inputs["Geometry"])

        mesh = bpy.data.meshes.new("test_stable_generated_ids")
        obj = bpy.data.objects.new("test_stable_generated_ids", mesh)
        bpy.context.scene.collection.objects.link(obj)
        modifier = obj.modifiers.new("stable ids", "NODES")
        modifier.node_group = group

        def set_topology(vertices, faces, seeds):
            for name in (SOURCE_CURVE_ID_ATTR, SOURCE_ENDPOINT_ID_ATTR):
                attribute = mesh.attributes.get(name)
                if attribute:
                    mesh.attributes.remove(attribute)
            mesh.clear_geometry()
            mesh.from_pydata(vertices, [], faces)
            curve_source = mesh.attributes.new(SOURCE_CURVE_ID_ATTR, "INT", "POINT")
            endpoint_source = mesh.attributes.new(
                SOURCE_ENDPOINT_ID_ATTR, "INT", "POINT"
            )
            curve_source.data.foreach_set("value", seeds)
            endpoint_source.data.foreach_set("value", [0] * len(vertices))
            mesh.update()
            obj.update_tag()

        def evaluated_ids():
            depsgraph = bpy.context.evaluated_depsgraph_get()
            depsgraph.update()
            evaluated = obj.evaluated_get(depsgraph)
            result = bpy.data.meshes.new_from_object(evaluated, depsgraph=depsgraph)
            try:
                self.assertIn("id", result.attributes)
                vertex_ids = result.attributes[VERTEX_ID_ATTR]
                face_ids = result.attributes[FACE_ID_ATTR]
                vertices = {
                    tuple(round(value, 4) for value in vertex.co): vertex_ids.data[
                        vertex.index
                    ].value
                    for vertex in result.vertices
                }
                faces = {
                    tuple(
                        sorted(
                            tuple(round(value, 4) for value in result.vertices[i].co)
                            for i in polygon.vertices
                        )
                    ): face_ids.data[polygon.index].value
                    for polygon in result.polygons
                }
                return vertices, faces
            finally:
                bpy.data.meshes.remove(result)

        kept_vertices = [
            (0, 0, 0),
            (1, 0, 0),
            (0, 1, 0),
            (3, 0, 0),
            (4, 0, 0),
            (3, 1, 0),
        ]
        kept_faces = [(0, 1, 2), (3, 4, 5)]

        try:
            set_topology(kept_vertices, kept_faces, [101] * 3 + [202] * 3)
            baseline = evaluated_ids()

            neighbor = [(-3, 0, 0), (-2, 0, 0), (-3, 1, 0)]
            shifted_faces = [(0, 1, 2), (3, 4, 5), (6, 7, 8)]
            set_topology(
                neighbor + kept_vertices,
                shifted_faces,
                [303] * 3 + [101] * 3 + [202] * 3,
            )
            inserted = evaluated_ids()
            for key, value in baseline[0].items():
                self.assertEqual(inserted[0][key], value)
            for key, value in baseline[1].items():
                self.assertEqual(inserted[1][key], value)

            set_topology(kept_vertices, kept_faces, [101] * 3 + [202] * 3)
            self.assertEqual(evaluated_ids(), baseline)
        finally:
            bpy.data.objects.remove(obj, do_unlink=True)
            bpy.data.meshes.remove(mesh)
            bpy.data.node_groups.remove(group)


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

    def test_generated_id_nodes_use_source_local_indices(self):
        from ..utilities.convert_nodes import (
            FACE_ID_ATTR,
            VERTEX_ID_ATTR,
            build_convert_node_group,
        )

        self.assertEqual(VERTEX_ID_ATTR, "id")
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

            self.assertFalse(
                any(node.bl_idname == "GeometryNodeInputIndex" for node in ng.nodes)
            )
            accumulates = [
                node
                for node in ng.nodes
                if node.bl_idname == "GeometryNodeAccumulateField"
            ]
            self.assertEqual({node.domain for node in accumulates}, {"POINT", "FACE"})
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


class TestFillWinding(TestCase):
    """Fill Curve (N-gons) is winding-sensitive: a hole vanishes when its loop is
    wound opposite the container. Mesh to Curve derives winding from edge order,
    which is not stable, so _normalize_winding must pin all loops to one winding
    and make the ring deterministic regardless of input winding/order."""

    import math as _math

    RECT = [(-4, -2, 0), (4, -2, 0), (4, 2, 0), (-4, 2, 0)]
    RECT_AREA = 32.0
    CIRCLE_R = 1.5
    RING_AREA = 32.0 - _math.pi * 1.5**2

    def _circle(self, reverse):
        import math

        n = 32
        v = [
            (
                self.CIRCLE_R * math.cos(2 * math.pi * k / n),
                self.CIRCLE_R * math.sin(2 * math.pi * k / n),
                0,
            )
            for k in range(n)
        ]
        return list(reversed(v)) if reverse else v

    def _loops_object(self, rect_rev, circ_rev, circle_first):
        rect = list(reversed(self.RECT)) if rect_rev else list(self.RECT)
        loops = (
            [self._circle(circ_rev), rect]
            if circle_first
            else [rect, self._circle(circ_rev)]
        )
        verts, edges = [], []
        for vs in loops:
            base = len(verts)
            verts += vs
            edges += [(base + i, base + (i + 1) % len(vs)) for i in range(len(vs))]
        me = bpy.data.meshes.new("winding_loops")
        me.from_pydata(verts, edges, [])
        me.update()
        ob = bpy.data.objects.new("winding_loops", me)
        bpy.context.scene.collection.objects.link(ob)
        return ob

    def _fill_group(self):
        from ..utilities.convert_nodes import _normalize_winding

        ng = bpy.data.node_groups.new("test_fill_winding", "GeometryNodeTree")
        ng.interface.new_socket(
            "Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry"
        )
        ng.interface.new_socket(
            "Geometry", in_out="INPUT", socket_type="NodeSocketGeometry"
        )
        n, links = ng.nodes, ng.links
        gi, go = n.new("NodeGroupInput"), n.new("NodeGroupOutput")
        m2c = n.new("GeometryNodeMeshToCurve")
        fc = n.new("GeometryNodeFillCurve")
        try:
            fc.inputs["Mode"].default_value = "N-gons"
        except Exception:
            pass
        links.new(gi.outputs["Geometry"], m2c.inputs["Mesh"])
        links.new(
            _normalize_winding(n, links, m2c.outputs["Curve"]), fc.inputs["Curve"]
        )
        links.new(fc.outputs["Mesh"], go.inputs["Geometry"])
        return ng

    def test_ring_is_winding_independent(self):
        ng = self._fill_group()
        created = [ng]
        try:
            for circle_first in (False, True):
                for rect_rev in (False, True):
                    for circ_rev in (False, True):
                        ob = self._loops_object(rect_rev, circ_rev, circle_first)
                        created.append(ob)
                        mod = ob.modifiers.new("fill", "NODES")
                        mod.node_group = ng
                        dg = bpy.context.evaluated_depsgraph_get()
                        ev = ob.evaluated_get(dg)
                        me = ev.to_mesh()
                        area = sum(p.area for p in me.polygons)
                        ev.to_mesh_clear()
                        self.assertAlmostEqual(
                            area,
                            self.RING_AREA,
                            delta=0.5,
                            msg=(
                                f"circle_first={circle_first} rect_rev={rect_rev} "
                                f"circ_rev={circ_rev}: area {area:.3f} is not the ring "
                                f"{self.RING_AREA:.3f} -> winding flipped the fill"
                            ),
                        )
        finally:
            for d in created:
                if isinstance(d, bpy.types.Object):
                    bpy.data.objects.remove(d, do_unlink=True)
                else:
                    bpy.data.node_groups.remove(d)
