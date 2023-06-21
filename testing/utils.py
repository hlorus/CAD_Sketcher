from unittest import TestCase
from CAD_Sketcher.solver import solve_system


class BgsTestCase(TestCase):
    interactive = False
    log_level = "INFO"

    @classmethod
    def setUpClass(cls):
        from CAD_Sketcher.utilities.preferences import get_prefs

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

    def solve(self):
        self.assertTrue(solve_system(self.context))


class Sketch2dTestCase(BgsTestCase):
    def new_sketch(self):
        self.entities.ensure_origin_elements(self.context)
        wp = self.entities.origin_plane_XY
        return self.entities.add_sketch(wp)

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.entities.ensure_origin_elements(cls.context)

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        if cls.interactive:
            return

    def setUp(self) -> None:
        self.sketch = self.new_sketch()
        self.sketch.name = self._testMethodName
        self.context.scene.sketcher.active_sketch = self.sketch
        return super().setUp()

    def tearDown(self) -> None:
        self.context.scene.sketcher.active_sketch = None
        return super().tearDown()

    def solve(self):
        self.assertTrue(self.sketch.solve(self.context))
