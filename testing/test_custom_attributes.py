import unittest

import bpy

from ..utilities.custom_attributes import (
    define_attribute,
    definition,
    get_attribute_value,
    remove_attribute,
    set_attribute_value,
    transport_attribute_name,
)
from .utils import Sketch2dTestCase


class TestCustomAttributes(Sketch2dTestCase):
    def _square(self):
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
        return (p1, p2, p3, p4), lines

    def _convert_copy(self, source, *, node_group=None, fill=None):
        """Destructively convert a disposable copy and return the mesh object."""
        duplicate = source.copy()
        duplicate.data = source.data.copy()
        self.context.collection.objects.link(duplicate)

        modifier = duplicate.modifiers.get("CAD Sketcher Convert")
        if node_group is not None:
            self.assertIsNotNone(modifier)
            modifier.node_group = node_group
        if fill is not None:
            self.assertIsNotNone(modifier)
            group = modifier.node_group
            fill_socket = next(
                item
                for item in group.interface.items_tree
                if getattr(item, "item_type", "") == "SOCKET"
                and getattr(item, "in_out", "") == "INPUT"
                and item.name == "Fill"
            )
            fill_socket.default_value = bool(fill)

        for selected in list(self.context.selected_objects):
            selected.select_set(False)
        duplicate.select_set(True)
        self.context.view_layer.objects.active = duplicate
        self.context.view_layer.update()

        result = bpy.ops.object.convert(target="MESH")
        self.assertEqual(result, {"FINISHED"})
        converted = self.context.view_layer.objects.active
        self.assertIsNotNone(converted)
        self.assertEqual(converted.type, "MESH")
        return converted

    def _remove_converted(self, converted):
        if converted is None or converted.name not in bpy.data.objects:
            return
        data = converted.data
        bpy.data.objects.remove(converted, do_unlink=True)
        if data is not None and data.users == 0:
            if isinstance(data, bpy.types.Mesh):
                bpy.data.meshes.remove(data)
            elif isinstance(data, bpy.types.Curves):
                bpy.data.hair_curves.remove(data)

    def test_curve_attribute_values_live_on_native_source(self):
        _, lines = self._square()
        define_attribute(self.sketch, "material_slot", "INT", "CURVE", 2)
        self.assertEqual(
            get_attribute_value(self.sketch, "material_slot", lines[0].curve_id), 2
        )
        set_attribute_value(self.sketch, "material_slot", 9, lines[0].curve_id)
        self.assertEqual(
            get_attribute_value(self.sketch, "material_slot", lines[0].curve_id), 9
        )
        self.assertEqual(
            get_attribute_value(self.sketch, "material_slot", lines[1].curve_id), 2
        )

    def test_default_applies_to_geometry_created_after_definition(self):
        first = self.add_point((0.0, 0.0))
        define_attribute(self.sketch, "later_default", "INT", "CURVE", 17)
        self.assertEqual(
            get_attribute_value(self.sketch, "later_default", first.curve_id), 17
        )
        later = self.add_point((1.0, 0.0))
        self.assertEqual(
            get_attribute_value(self.sketch, "later_default", later.curve_id), 17
        )

    def test_point_and_object_domains(self):
        points, lines = self._square()
        define_attribute(self.sketch, "weight", "FLOAT", "POINT", 1.25)
        define_attribute(self.sketch, "part_number", "INT", "OBJECT", 42)
        set_attribute_value(self.sketch, "weight", 3.5, lines[0].curve_id)
        values = get_attribute_value(self.sketch, "weight", lines[0].curve_id)
        self.assertTrue(values)
        self.assertTrue(all(abs(v - 3.5) < 1e-6 for v in values))
        self.assertEqual(get_attribute_value(self.sketch, "part_number"), 42)
        self.assertEqual(self.sketch.target_object["part_number"], 42)
        self.assertEqual(self.sketch.data["part_number"], 42)
        set_attribute_value(self.sketch, "part_number", 77)
        self.assertEqual(self.sketch.target_object["part_number"], 77)
        self.assertEqual(self.sketch.data["part_number"], 77)
        set_attribute_value(self.sketch, "weight", 8.0, points[0].curve_id)
        self.assertEqual(
            get_attribute_value(self.sketch, "weight", points[0].curve_id), [8.0]
        )

    def test_set_dialog_seed_preserves_current_value(self):
        from ..operators.custom_attributes import _seed_set_value

        _, lines = self._square()
        define_attribute(self.sketch, "feature_code", "INT", "CURVE", 5)
        set_attribute_value(self.sketch, "feature_code", 77, lines[0].curve_id)
        entry = definition(self.sketch, "feature_code")
        self.assertEqual(_seed_set_value(self.sketch, entry, [lines[0].curve_id]), 77)
        self.assertEqual(
            _seed_set_value(self.sketch, entry, [lines[0].curve_id, lines[1].curve_id]),
            5,
        )

    def test_refresh_preserves_custom_data_and_definitions(self):
        from ..utilities.curve_data import refresh_curve_geometry

        _, lines = self._square()
        define_attribute(self.sketch, "feature_code", "INT", "CURVE", 5)
        set_attribute_value(self.sketch, "feature_code", 77, lines[2].curve_id)
        refresh_curve_geometry(self.sketch)
        self.assertIsNotNone(definition(self.sketch, "feature_code"))
        self.assertEqual(
            get_attribute_value(self.sketch, "feature_code", lines[2].curve_id), 77
        )

    def test_point_attribute_survives_conversion_refresh(self):
        from ..utilities.curve_data import refresh_curve_geometry

        points, _ = self._square()
        define_attribute(self.sketch, "conversion_tag", "INT", "POINT", 13)
        set_attribute_value(self.sketch, "conversion_tag", 29, points[0].curve_id)
        before = get_attribute_value(self.sketch, "conversion_tag")
        refresh_curve_geometry(self.sketch)
        self.assertIsNotNone(definition(self.sketch, "conversion_tag"))
        self.assertEqual(get_attribute_value(self.sketch, "conversion_tag"), before)
        attr = self.sketch.data.attributes.get("conversion_tag")
        self.assertIsNotNone(attr)
        self.assertEqual(attr.domain, "POINT")
        self.assertEqual(attr.data_type, "INT")

    @unittest.skipIf(bpy.app.version < (5, 2, 0), "programmatic convert requires 5.2+")
    def test_generic_wire_path_drops_unreferenced_point_attribute(self):
        from ..utilities.convert_nodes import build_convert_node_group

        _, lines = self._square()
        define_attribute(self.sketch, "wire_point_tag", "INT", "POINT", 13)
        set_attribute_value(self.sketch, "wire_point_tag", 29, lines[0].curve_id)
        generic = build_convert_node_group("test_generic_wire_custom_attrs")
        converted = None
        try:
            converted = self._convert_copy(
                self.sketch.target_object,
                node_group=generic,
                fill=False,
            )
            self.assertIsNone(converted.data.attributes.get("wire_point_tag"))
        finally:
            self._remove_converted(converted)
            if generic.users == 0:
                bpy.data.node_groups.remove(generic)

    @unittest.skipIf(bpy.app.version < (5, 2, 0), "programmatic convert requires 5.2+")
    def test_named_attributes_reach_filled_conversion_output(self):
        """Keep configured fields live through the evaluated conversion output."""
        from ..utilities.convert_nodes import (
            SOURCE_CURVE_ID_ATTR,
            SOURCE_ENDPOINT_ID_ATTR,
        )

        _, lines = self._square()
        define_attribute(self.sketch, "point_tag", "INT", "POINT", 13)
        define_attribute(self.sketch, "curve_tag", "INT", "CURVE", 17)
        define_attribute(self.sketch, "object_tag", "INT", "OBJECT", 23)
        set_attribute_value(self.sketch, "point_tag", 29, lines[0].curve_id)
        set_attribute_value(self.sketch, "curve_tag", 31, lines[0].curve_id)

        source = self.sketch.target_object
        source_modifier = source.modifiers.get("CAD Sketcher Convert")
        self.assertIsNotNone(source_modifier)
        group = source_modifier.node_group
        self.assertIsNotNone(group)
        self.assertTrue(group.name.startswith("CAD Sketcher Convert [attrs "))
        self.assertNotIn(source.data.name, group.name)
        self.assertTrue(group.get("cad_convert_attribute_signature", ""))

        set_attribute_value(self.sketch, "curve_tag", 37, lines[1].curve_id)
        self.assertIs(source_modifier.node_group, group)

        point_entry = definition(self.sketch, "point_tag")
        curve_entry = definition(self.sketch, "curve_tag")
        point_transport_name = transport_attribute_name(point_entry)
        curve_transport_name = transport_attribute_name(curve_entry)
        point_transport = source.data.attributes.get(point_transport_name)
        curve_transport = source.data.attributes.get(curve_transport_name)
        self.assertIsNotNone(point_transport)
        self.assertIsNotNone(curve_transport)
        self.assertIn(29, [item.value for item in point_transport.data])
        self.assertIn(31, [item.value for item in curve_transport.data])
        self.assertIn(37, [item.value for item in curve_transport.data])

        converted = None
        try:
            converted = self._convert_copy(source, fill=True)
            point_attr = converted.data.attributes.get("point_tag")
            curve_attr = converted.data.attributes.get("curve_tag")
            hidden_point = converted.data.attributes.get(point_transport_name)
            hidden_curve = converted.data.attributes.get(curve_transport_name)
            source_curve_ids = converted.data.attributes.get(SOURCE_CURVE_ID_ATTR)
            source_endpoint_ids = converted.data.attributes.get(SOURCE_ENDPOINT_ID_ATTR)
            diagnostic = {
                "public_point": [] if point_attr is None else [item.value for item in point_attr.data],
                "public_curve": [] if curve_attr is None else [item.value for item in curve_attr.data],
                "hidden_point": [] if hidden_point is None else [item.value for item in hidden_point.data],
                "hidden_curve": [] if hidden_curve is None else [item.value for item in hidden_curve.data],
                "source_curve_ids": [] if source_curve_ids is None else [item.value for item in source_curve_ids.data],
                "source_endpoint_ids": [] if source_endpoint_ids is None else [item.value for item in source_endpoint_ids.data],
            }
            print("CUSTOM_ATTRIBUTE_CONVERSION_DIAGNOSTIC", diagnostic)

            self.assertIsNotNone(point_attr)
            self.assertIsNotNone(curve_attr)
            self.assertIn(29, diagnostic["public_point"])
            self.assertIn(31, diagnostic["public_curve"])
            self.assertIn(37, diagnostic["public_curve"])
            self.assertEqual(source["object_tag"], 23)
            self.assertEqual(source.data["object_tag"], 23)
            self.assertEqual(converted["object_tag"], 23)
            self.assertEqual(converted.data["object_tag"], 23)
        finally:
            self._remove_converted(converted)

    @unittest.skipIf(bpy.app.version < (5, 2, 0), "schema converters require 5.2+")
    def test_schema_change_rebinds_and_discards_unused_group(self):
        self._square()
        define_attribute(self.sketch, "first_schema_attr", "INT", "CURVE", 1)
        modifier = self.sketch.target_object.modifiers.get("CAD Sketcher Convert")
        first_group = modifier.node_group
        first_name = first_group.name
        define_attribute(self.sketch, "second_schema_attr", "FLOAT", "POINT", 2.0)
        second_group = modifier.node_group
        self.assertIsNot(first_group, second_group)
        self.assertNotIn(first_name, bpy.data.node_groups)
        remove_attribute(self.sketch, "second_schema_attr")
        self.assertEqual(modifier.node_group.name, first_name)

    def test_remove_deletes_definition_and_source_attribute(self):
        self._square()
        define_attribute(self.sketch, "temporary", "BOOLEAN", "CURVE", True)
        self.assertTrue(remove_attribute(self.sketch, "temporary"))
        self.assertIsNone(definition(self.sketch, "temporary"))
        self.assertIsNone(self.sketch.data.attributes.get("temporary"))

    def test_remove_object_attribute_clears_object_and_data(self):
        self._square()
        define_attribute(self.sketch, "temporary_object", "INT", "OBJECT", 7)
        self.assertIn("temporary_object", self.sketch.target_object)
        self.assertIn("temporary_object", self.sketch.data)
        self.assertTrue(remove_attribute(self.sketch, "temporary_object"))
        self.assertNotIn("temporary_object", self.sketch.target_object)
        self.assertNotIn("temporary_object", self.sketch.data)

    def test_operators_are_registered(self):
        self.assertTrue(hasattr(bpy.ops.view3d, "slvs_add_custom_attribute"))
        self.assertTrue(hasattr(bpy.ops.view3d, "slvs_set_custom_attribute"))
        self.assertTrue(hasattr(bpy.ops.view3d, "slvs_remove_custom_attribute"))
