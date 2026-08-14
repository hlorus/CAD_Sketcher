import bpy

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

        # Point entities remain independently addressable on the same native
        # source even though conversion consumes the complete Curves datablock.
        set_attribute_value(self.sketch, "weight", 8.0, points[0].curve_id)
        self.assertEqual(
            get_attribute_value(self.sketch, "weight", points[0].curve_id), [8.0]
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
        """The native source keeps the named attribute through a conversion rebuild.

        Blender's background runner cannot materialize a Mesh from the Curves
        object after its Geometry Nodes modifier, so the regression boundary is
        the native named attribute that the conversion graph consumes.
        """
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
