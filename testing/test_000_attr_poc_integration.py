import unittest

import bpy

from ..operators.modifiers import set_modifier_input
from ..utilities.custom_attributes import define_attribute, set_attribute_value
from .utils import Sketch2dTestCase


class TestAttributePOCIntegration(Sketch2dTestCase):
    @unittest.skipIf(bpy.app.version < (5, 2, 0), "evaluated GN output requires 5.2+")
    def test_single_curve_attribute_survives_fill(self):
        p1 = self.add_point((0.0, 0.0))
        p2 = self.add_point((2.0, 0.0))
        p3 = self.add_point((2.0, 2.0))
        p4 = self.add_point((0.0, 2.0))
        lines = (
            self.add_line(p1, p2),
            self.add_line(p2, p3),
            self.add_line(p3, p4),
            self.add_line(p4, p1),
        )

        define_attribute(self.sketch, "poc_segment_tag", "INT", "CURVE", 0)
        for line, value in zip(lines, (10, 20, 30, 40)):
            set_attribute_value(self.sketch, "poc_segment_tag", value, line.curve_id)

        source = self.sketch.target_object
        modifier = source.modifiers.get("CAD Sketcher Convert")
        self.assertIsNotNone(modifier)
        fill_socket = next(
            item
            for item in modifier.node_group.interface.items_tree
            if getattr(item, "item_type", "") == "SOCKET"
            and getattr(item, "in_out", "") == "INPUT"
            and item.name == "Fill"
        )
        set_modifier_input(modifier, fill_socket.identifier, True)

        from ..utilities.curve_data import refresh_curve_geometry

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
            attr = mesh.attributes.get("poc_segment_tag")
            if attr is not None:
                values = [item.value for item in attr.data]
            instance.object.to_mesh_clear()

        distinct = {value for value in values if value != 0}
        self.assertEqual(distinct, {10, 20, 30, 40})
        self.assertTrue(distinct.isdisjoint({15, 25, 35}))
