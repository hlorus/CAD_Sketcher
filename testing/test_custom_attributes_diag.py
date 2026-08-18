import unittest

import bpy

from ..utilities.custom_attributes import define_attribute, set_attribute_value
from .utils import Sketch2dTestCase


@unittest.skipIf(bpy.app.version < (5, 2, 0), "diagnostic requires Blender 5.2+")
class TestCustomAttributeEvaluationDiagnostic(Sketch2dTestCase):
    def test_evaluated_mesh_contains_live_values(self):
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
        define_attribute(self.sketch, "diag_point", "INT", "POINT", 13)
        define_attribute(self.sketch, "diag_curve", "INT", "CURVE", 17)
        set_attribute_value(self.sketch, "diag_point", 29, lines[0].curve_id)
        set_attribute_value(self.sketch, "diag_curve", 31, lines[0].curve_id)

        source = self.sketch.target_object
        self.context.view_layer.update()
        depsgraph = self.context.evaluated_depsgraph_get()
        evaluated = source.evaluated_get(depsgraph)
        mesh = bpy.data.meshes.new_from_object(evaluated, depsgraph=depsgraph)
        try:
            point = mesh.attributes.get("diag_point")
            curve = mesh.attributes.get("diag_curve")
            point_values = [] if point is None else [item.value for item in point.data]
            curve_values = [] if curve is None else [item.value for item in curve.data]
            print("CUSTOM_ATTR_DIAG", {
                "names": sorted(attr.name for attr in mesh.attributes),
                "point": point_values,
                "curve": curve_values,
            })
            self.assertIsNotNone(point)
            self.assertIsNotNone(curve)
            self.assertIn(29, point_values)
            self.assertIn(31, curve_values)
        finally:
            bpy.data.meshes.remove(mesh)
