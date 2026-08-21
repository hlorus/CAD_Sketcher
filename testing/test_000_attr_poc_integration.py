import unittest

import bpy

from ..model.constants import SketchCurveType
from ..operators.modifiers import set_modifier_input
from .utils import Sketch2dTestCase


class TestAttributePOCIntegration(Sketch2dTestCase):
    def _build_square_with_values(self, attr_name):
        p1 = self.add_point((0.0, 0.0))
        p2 = self.add_point((2.0, 0.0))
        p3 = self.add_point((2.0, 2.0))
        p4 = self.add_point((0.0, 2.0))
        self.add_line(p1, p2)
        self.add_line(p2, p3)
        self.add_line(p3, p4)
        self.add_line(p4, p1)

        cd = self.sketch.data
        attr = cd.attributes.get(attr_name) or cd.attributes.new(
            attr_name, "INT", "CURVE"
        )
        type_attr = cd.attributes["sketch_type"]
        line_indices = [
            i
            for i in range(len(cd.curves))
            if type_attr.data[i].value == SketchCurveType.LINE
        ]
        self.assertEqual(len(line_indices), 4)
        for value, idx in zip((10, 20, 30, 40), line_indices):
            attr.data[idx].value = value
        cd.update_tag()

    def _set_fill(self, modifier, enabled=True):
        fill_socket = next(
            item
            for item in modifier.node_group.interface.items_tree
            if getattr(item, "item_type", "") == "SOCKET"
            and getattr(item, "in_out", "") == "INPUT"
            and item.name == "Fill"
        )
        set_modifier_input(modifier, fill_socket.identifier, enabled)

    def _evaluated_values(self, attr_name):
        from ..utilities.curve_data import refresh_curve_geometry

        source = self.sketch.target_object
        refresh_curve_geometry(self.sketch)
        self.context.view_layer.update()
        depsgraph = self.context.evaluated_depsgraph_get()
        original = source.original
        values = []
        for instance in depsgraph.object_instances:
            if instance.object.original is not original:
                continue
            try:
                mesh = instance.object.to_mesh()
            except RuntimeError:
                continue
            mesh_attr = mesh.attributes.get(attr_name)
            if mesh_attr is not None:
                values = [item.value for item in mesh_attr.data]
            instance.object.to_mesh_clear()
        return values

    @unittest.skipIf(bpy.app.version < (5, 2, 0), "evaluated GN output requires 5.2+")
    def test_exact_maintainer_poc_sequence(self):
        from ..utilities.convert_nodes import build_convert_node_group
        from ..utilities.curve_data import compute_merge_ids

        attr_name = "poc_segment_tag"
        self._build_square_with_values(attr_name)
        compute_merge_ids(self.sketch)
        build_convert_node_group(
            attribute_definitions=[
                {"name": attr_name, "type": "INT", "domain": "CURVE"}
            ]
        )

        modifier = self.sketch.target_object.modifiers.get("CAD Sketcher Convert")
        self.assertIsNotNone(modifier)
        self._set_fill(modifier)

        distinct = {value for value in self._evaluated_values(attr_name) if value != 0}
        self.assertEqual(distinct, {10, 20, 30, 40})
        self.assertTrue(distinct.isdisjoint({15, 25, 35}))

    @unittest.skipIf(bpy.app.version < (5, 2, 0), "evaluated GN output requires 5.2+")
    def test_fresh_isolated_group_matches_maintainer_poc(self):
        from ..utilities.convert_nodes import build_convert_node_group
        from ..utilities.curve_data import compute_merge_ids

        attr_name = "poc_isolated_segment_tag"
        self._build_square_with_values(attr_name)
        compute_merge_ids(self.sketch)

        group = build_convert_node_group(
            name="CAD Sketcher POC Isolated",
            attribute_definitions=[
                {"name": attr_name, "type": "INT", "domain": "CURVE"}
            ],
        )
        modifier = self.sketch.target_object.modifiers.get("CAD Sketcher Convert")
        self.assertIsNotNone(modifier)
        modifier.node_group = group
        self._set_fill(modifier)

        distinct = {value for value in self._evaluated_values(attr_name) if value != 0}
        self.assertEqual(distinct, {10, 20, 30, 40})
        self.assertTrue(distinct.isdisjoint({15, 25, 35}))
