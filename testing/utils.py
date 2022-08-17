from unittest import TestCase

class BgsTestCase(TestCase):
    interactive = False
    log_level = "INFO"

    @classmethod
    def setUpClass(cls):
        from CAD_Sketcher.functions import get_prefs
        prefs = get_prefs()
        prefs.logging_level = cls.log_level

        import bpy

        # Create new scene for tests
        cls.scene = bpy.data.scenes.new(cls.__name__)
        bpy.context.window.scene = cls.scene

        cls.ops = bpy.ops
        cls.data = bpy.data
        cls.context = bpy.context
        cls.sketcher = cls.context.scene.sketcher
        cls.entities = cls.sketcher.entities
        cls.constraints = cls.sketcher.constraints

    @classmethod
    def tearDownClass(cls):
        if cls.interactive:
            return

        # Delete scene
        context = cls.context
        data = cls.data
        data.scenes.remove(cls.scene)


    @staticmethod
    def force_entity_update(scene):
        for entity in scene.sketcher.entities.all:
            entity.update()

class Sketch2dTestCase(BgsTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.entities.ensure_origin_elements(cls.context)
        wp = cls.entities.origin_plane_XY
        cls.sketch = cls.entities.add_sketch(wp)


    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        if cls.interactive:
            return

        cls.ops.view3d.slvs_delete_entity(index=cls.sketch.slvs_index)
