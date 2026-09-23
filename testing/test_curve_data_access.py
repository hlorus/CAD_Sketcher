"""Reading a sketch's curves never creates anything.

The read is reached from solving and drawing, where a new object -- worse, one
with a node group bound to it -- appearing mid-solve takes Blender down. Making
a sketch is its own call, for the paths that are allowed to: the Add Sketch
tool, the file update, and harnesses that drive the model directly.
"""

import inspect

import bpy

from ..utilities.curve_data import create_sketch_curve_object, sketch_curve_data
from .utils import Sketch2dTestCase


class TestCurveDataAccess(Sketch2dTestCase):
    def test_reading_a_sketch_with_no_object_creates_nothing(self):
        entity_sketch = self.entities.add_sketch(self.entities.origin_plane_XY)
        before = len(bpy.data.objects)

        self.assertIsNone(sketch_curve_data(entity_sketch))
        self.assertEqual(len(bpy.data.objects), before)

    def test_creating_is_its_own_call(self):
        entity_sketch = self.entities.add_sketch(self.entities.origin_plane_XY)

        data = create_sketch_curve_object(self.context, entity_sketch)

        self.assertIsNotNone(data)
        self.assertIsNotNone(entity_sketch.target_object)

    def test_drawing_geometry_goes_through_the_reading_path(self):
        from ..model import curve_ref

        source = inspect.getsource(curve_ref._ensure_curve_data)
        self.assertIn("sketch_curve_data", source)
        self.assertNotIn("create_", source)
