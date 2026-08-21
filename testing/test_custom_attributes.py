import unittest

import bpy

from ..operators.modifiers import get_modifier_input, set_modifier_input
from ..utilities.custom_attributes import (
    define_attribute,
    definition,
    get_attribute_value,
    remove_attribute,
    set_attribute_value,
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
        duplicate = source.copy()
        duplicate.data = source.data.copy()
        self.context.collection.objects.link(duplicate)
        modifier = duplicate.modifiers.get("CAD Sketcher Convert")
        if node_group is not None:
            self.assertIsNotNone(modifier)
            modifier.node_group = node_group
        if fill is not None:
            self.assertIsNotNone(modifier)
            fill_socket = next(
                item
                for item in modifier.node_group.interface.items_tree
                if getattr(item, "item_type", "") == "SOCKET"
                and getattr(item, "in_out", "") == "INPUT"
                and item.name == "Fill"
            )
            set_modifier_input(modifier, fill_socket.identifier, bool(fill))
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

    def _evaluated_attribute_values(self, source, attr_name):
        """Read a named attribute from the real evaluated GN mesh output."""
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
            attr = mesh.attributes.get(attr_name)
            if attr is not None:
                values = [item.value for item in attr.data]
            instance.object.to_mesh_clear()
        return values

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

    def test_point_domain_uses_native_curve_data(self):
        points, lines = self._square()
        define_attribute(self.sketch, "weight", "FLOAT", "POINT", 1.25)
        set_attribute_value(self.sketch, "weight", 3.5, lines[0].curve_id)
        values = get_attribute_value(self.sketch, "weight", lines[0].curve_id)
        self.assertTrue(values)
        self.assertTrue(all(abs(v - 3.5) < 1e-6 for v in values))

        set_attribute_value(self.sketch, "weight", 8.0, points[0].curve_id)
        self.assertEqual(
            get_attribute_value(self.sketch, "weight", points[0].curve_id), [8.0]
        )
        attr = self.sketch.data.attributes.get("weight")
        self.assertIsNotNone(attr)
        self.assertEqual(attr.domain, "POINT")

    def test_object_domain_is_deferred(self):
        self._square()
        with self.assertRaisesRegex(
            ValueError, "OBJECT-domain attributes are deferred"
        ):
            define_attribute(self.sketch, "part_number", "INT", "OBJECT", 42)

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
    def test_domain_capture_conversion_preserves_named_attributes(self):
        """Wire conversion preserves exact per-segment values without sampling."""
        _, lines = self._square()
        define_attribute(self.sketch, "wire_point_tag", "INT", "POINT", 13)
        define_attribute(self.sketch, "wire_curve_tag", "INT", "CURVE", 0)
        set_attribute_value(self.sketch, "wire_point_tag", 29)
        for line, value in zip(lines, (10, 20, 30, 40)):
            set_attribute_value(self.sketch, "wire_curve_tag", value, line.curve_id)

        source = self.sketch.target_object
        modifier = source.modifiers.get("CAD Sketcher Convert")
        self.assertIsNotNone(modifier)
        group = modifier.node_group
        self.assertEqual(group.name, "CAD Sketcher Convert")
        self.assertFalse(
            any(
                node.bl_idname
                in {"GeometryNodeSampleNearest", "GeometryNodeSampleIndex"}
                for node in group.nodes
            )
        )

        segment_stores = [
            node
            for node in group.nodes
            if node.bl_idname == "GeometryNodeStoreNamedAttribute"
            and node.domain == "EDGE"
            and node.inputs["Name"].default_value == "wire_curve_tag"
        ]
        self.assertTrue(segment_stores)

        converted = None
        try:
            converted = self._convert_copy(source, fill=False)
            point_attr = converted.data.attributes.get("wire_point_tag")
            curve_attr = converted.data.attributes.get("wire_curve_tag")
            self.assertIsNotNone(point_attr)
            self.assertIsNotNone(curve_attr)
            self.assertIn(29, [item.value for item in point_attr.data])
            curve_values = [item.value for item in curve_attr.data]
            for expected in (10, 20, 30, 40):
                self.assertIn(expected, curve_values)
            self.assertNotIn(15, curve_values)
            self.assertNotIn(25, curve_values)
            self.assertNotIn(35, curve_values)
        finally:
            self._remove_converted(converted)

    @unittest.skipIf(bpy.app.version < (5, 2, 0), "evaluated GN output requires 5.2+")
    def test_filled_conversion_preserves_exact_segment_values(self):
        """The evaluated fill keeps exact segment values across weld + Fill Curve."""
        _, lines = self._square()
        define_attribute(self.sketch, "fill_curve_tag", "INT", "CURVE", 0)
        for line, value in zip(lines, (10, 20, 30, 40)):
            set_attribute_value(self.sketch, "fill_curve_tag", value, line.curve_id)

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

        values = self._evaluated_attribute_values(source, "fill_curve_tag")
        distinct = {value for value in values if value != 0}
        self.assertEqual(distinct, {10, 20, 30, 40})
        self.assertTrue(distinct.isdisjoint({15, 25, 35}))

    @unittest.skipIf(bpy.app.version < (5, 2, 0), "shared converter requires 5.2+")
    def test_attribute_schema_changes_keep_shared_convert_group(self):
        self._square()
        modifier = self.sketch.target_object.modifiers.get("CAD Sketcher Convert")
        self.assertIsNotNone(modifier)
        shared_group = modifier.node_group
        self.assertEqual(shared_group.name, "CAD Sketcher Convert")

        define_attribute(self.sketch, "first_attr", "INT", "CURVE", 1)
        define_attribute(self.sketch, "second_attr", "FLOAT", "POINT", 2.0)
        self.assertIs(modifier.node_group, shared_group)
        remove_attribute(self.sketch, "second_attr")
        self.assertIs(modifier.node_group, shared_group)

    @unittest.skipIf(bpy.app.version < (5, 2, 0), "shared converter requires 5.2+")
    def test_attribute_schema_change_preserves_fill_modifier_binding(self):
        """Rebuilding the shared group must preserve the modifier's Fill value."""
        self._square()
        source = self.sketch.target_object
        modifier = source.modifiers.get("CAD Sketcher Convert")
        self.assertIsNotNone(modifier)
        group = modifier.node_group
        fill_socket = next(
            item
            for item in group.interface.items_tree
            if getattr(item, "item_type", "") == "SOCKET"
            and getattr(item, "in_out", "") == "INPUT"
            and item.name == "Fill"
        )
        set_modifier_input(modifier, fill_socket.identifier, True)

        define_attribute(self.sketch, "fill_survival_tag", "INT", "CURVE", 7)

        fill_socket_after = next(
            item
            for item in group.interface.items_tree
            if getattr(item, "item_type", "") == "SOCKET"
            and getattr(item, "in_out", "") == "INPUT"
            and item.name == "Fill"
        )
        self.assertTrue(get_modifier_input(modifier, fill_socket_after.identifier))

        converted = None
        try:
            converted = self._convert_copy(source)
            self.assertGreater(len(converted.data.polygons), 0)
        finally:
            self._remove_converted(converted)

    def test_remove_deletes_definition_and_source_attribute(self):
        self._square()
        define_attribute(self.sketch, "temporary", "BOOLEAN", "CURVE", True)
        self.assertTrue(remove_attribute(self.sketch, "temporary"))
        self.assertIsNone(definition(self.sketch, "temporary"))
        self.assertIsNone(self.sketch.data.attributes.get("temporary"))

    def test_operators_are_registered(self):
        self.assertTrue(hasattr(bpy.ops.view3d, "slvs_add_custom_attribute"))
        self.assertTrue(hasattr(bpy.ops.view3d, "slvs_set_custom_attribute"))
        self.assertTrue(hasattr(bpy.ops.view3d, "slvs_remove_custom_attribute"))
