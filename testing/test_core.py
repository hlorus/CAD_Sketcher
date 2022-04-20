from unittest import skip
from CAD_Sketcher.testing.utils import BgsTestCase
from CAD_Sketcher import class_defines

from sys import float_info

class TestEntities(BgsTestCase):

    def test_point_3d(self):
        sketcher = self.sketcher
        entities = self.entities

        # Point at origin
        p1 = entities.add_point_3d((0, 0, 0))
        self.assertIsInstance(p1, class_defines.SlvsPoint3D)
        self.assertEqual(tuple(p1.location), (0, 0, 0))



    def test_entity_pointer(self):
        import bpy
        from bpy.types import PropertyGroup
        from bpy.utils import register_class, unregister_class
        from bpy.props import PointerProperty

        class PointerTest(PropertyGroup):
            pass
        class_defines.slvs_entity_pointer(PointerTest, "pointer")

        register_class(PointerTest)

        bpy.types.Scene.test_group = PointerProperty(type=PointerTest)

        scene = bpy.context.scene

        self.assertIsInstance(PointerTest.pointer, property)
        self.assertEqual(scene.test_group.rna_type.properties["pointer_i"].type, "INT")
        self.assertEqual(scene.test_group.pointer_i, -1)
        self.assertEqual(scene.test_group.pointer, None)


        del bpy.types.Scene.test_group
        unregister_class(PointerTest)
