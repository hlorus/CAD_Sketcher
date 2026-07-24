from unittest import TestCase

class BgsTestCase(TestCase):
    interactive = False
    log_level = "INFO"

    @classmethod
    def is_interactive(cls):
        """Check if interactive mode is enabled via environment variable or class attribute"""
        import os
        return os.environ.get("RUN_TESTS_INTERACTIVE", "").lower() in ("true", "1", "yes") or cls.interactive

    @classmethod
    def setUpClass(cls):
        print(f"BgsTestCase.setUpClass - interactive: {cls.interactive}")
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
        if cls.is_interactive():
            # In interactive mode, keep scenes alive
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
        from ..curve_solver import solve_system

        self.assertTrue(solve_system(self.context))


class Sketch2dTestCase(BgsTestCase):
    def new_sketch(self):
        self.entities.ensure_origin_elements(self.context)
        wp = self.entities.origin_plane_XY
        entity_sketch = self.entities.add_sketch(wp)
        from ..utilities.curve_data import ensure_sketch_curve_object
        ensure_sketch_curve_object(entity_sketch)
        # Wrap as Sketch accessor
        from ..model.sketch_ref import Sketch, stamp_sketch_props
        stamp_sketch_props(entity_sketch.target_object)
        return Sketch(entity_sketch.target_object)

    def add_point(self, co, **kwargs):
        from ..model.curve_ref import PointRef
        return PointRef.create(self.sketch, co, **kwargs)

    def add_line(self, p1, p2, **kwargs):
        from ..model.curve_ref import LineRef
        return LineRef.create(self.sketch, p1, p2, **kwargs)

    def add_arc(self, ct, start, end, **kwargs):
        from ..model.curve_ref import ArcRef
        return ArcRef.create(self.sketch, ct, start, end, **kwargs)

    def add_circle(self, ct, radius, **kwargs):
        from ..model.curve_ref import CircleRef
        return CircleRef.create(self.sketch, ct, radius, **kwargs)

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.entities.ensure_origin_elements(cls.context)

    @classmethod
    def tearDownClass(cls):
        if cls.is_interactive():
            # In interactive mode, skip teardown
            return
        super().tearDownClass()

    def setUp(self) -> None:
        self.sketch = self.new_sketch()
        self.sketch.name = self._testMethodName
        from ..model.sketch_ref import set_active_sketch, Sketch
        if hasattr(self.sketch, 'target_object'):
            set_active_sketch(self.context, self.sketch.target_object)
        return super().setUp()

    def tearDown(self) -> None:
        from ..model.sketch_ref import set_active_sketch
        set_active_sketch(self.context, None)
        return super().tearDown()

    def solve(self):
        self.assertTrue(self.sketch.solve(self.context))
