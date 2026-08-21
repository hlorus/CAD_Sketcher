import unittest

import bpy

from ..operators.modifiers import get_modifier_input, set_modifier_input
from ..utilities.custom_attributes import define_attribute
from .utils import Sketch2dTestCase


class TestConvertInterfaceStability(Sketch2dTestCase):
    def _square(self):
        p1 = self.add_point((0.0, 0.0))
        p2 = self.add_point((2.0, 0.0))
        p3 = self.add_point((2.0, 2.0))
        p4 = self.add_point((0.0, 2.0))
        self.add_line(p1, p2)
        self.add_line(p2, p3)
        self.add_line(p3, p4)
        self.add_line(p4, p1)

    @unittest.skipIf(bpy.app.version < (5, 2, 0), "shared converter requires 5.2+")
    def test_fill_socket_identifier_survives_attribute_schema_change(self):
        """Internal bridge rebuilds must never remint the public Fill socket."""
        self._square()
        modifier = self.sketch.target_object.modifiers.get("CAD Sketcher Convert")
        self.assertIsNotNone(modifier)
        group = modifier.node_group
        self.assertIsNotNone(group)

        fill_before = next(
            item
            for item in group.interface.items_tree
            if getattr(item, "item_type", "") == "SOCKET"
            and getattr(item, "in_out", "") == "INPUT"
            and item.name == "Fill"
        )
        identifier_before = fill_before.identifier
        set_modifier_input(modifier, identifier_before, True)

        define_attribute(self.sketch, "stable_fill_tag", "INT", "CURVE", 7)

        fill_after = next(
            item
            for item in group.interface.items_tree
            if getattr(item, "item_type", "") == "SOCKET"
            and getattr(item, "in_out", "") == "INPUT"
            and item.name == "Fill"
        )
        self.assertEqual(fill_after.identifier, identifier_before)
        self.assertTrue(get_modifier_input(modifier, fill_after.identifier))
