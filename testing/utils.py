from unittest import TestCase


def make_operator_double(real_cls):
    """Build a non-bpy, instantiable twin of a stateful operator class.

    A registered operator is ``class View3D_OT_...(bpy.types.Operator, Operator2d)``.
    ``bpy.types.Operator``'s metaclass blocks ``__new__``, so the real class can't be
    instantiated outside a modal invoke. This reflects the class into an identical one
    with ``bpy.types.Operator`` dropped from the bases and the *real* class body copied
    verbatim (``states``, ``main``, ``init``, any overrides). No logic is duplicated —
    the twin runs the same code, it just isn't a Blender-registered operator.

    Only bpy-registration bits don't survive: property *annotations*
    (``continuous_draw: BoolProperty(...)``) are inert, so a test sets a plain attribute
    where a value is needed. UI sinks touched by the state machine are stubbed to no-ops.
    """
    import bpy
    import types

    def _noop(self, *args, **kwargs):
        return None

    bases = tuple(b for b in real_cls.__bases__ if b is not bpy.types.Operator)
    ns = {
        k: v
        for k, v in real_cls.__dict__.items()
        if k not in ("__dict__", "__weakref__")
    }
    # UI-only sinks the pure state machine calls through set_state / status updates.
    ns.setdefault("set_status_text", _noop)
    ns.setdefault("init_numeric", _noop)
    cls = type(real_cls.__name__ + "_Double", bases, ns)

    # Methods copied verbatim from the concrete class keep a hidden ``__class__``
    # closure cell pointing at the *original* class, so their zero-arg ``super()``
    # (e.g. a constraint's ``main`` calling ``super().main``) fails against a twin
    # instance. Re-bind that cell to the twin -- on a *copy* of the function so the
    # real registered operator is left untouched.
    for name, value in list(real_cls.__dict__.items()):
        func = value
        wrapper = None
        if isinstance(value, (classmethod, staticmethod)):
            func, wrapper = value.__func__, type(value)
        if not isinstance(func, types.FunctionType):
            continue
        if "__class__" not in func.__code__.co_freevars:
            continue
        idx = func.__code__.co_freevars.index("__class__")
        cells = list(func.__closure__ or ())
        cells[idx] = types.CellType(cls)
        rebound = types.FunctionType(
            func.__code__, func.__globals__, func.__name__,
            func.__defaults__, tuple(cells),
        )
        rebound.__dict__.update(func.__dict__)
        setattr(cls, name, wrapper(rebound) if wrapper else rebound)

    return cls


class OpHarness:
    """Drive a stateful operator the way a user does, without a modal region.

    Mirrors the real lifecycle:
      - ``prefill()``      -> the invoke-time selection prefill (prefill_state_props)
      - ``pick(ref)``      -> click an existing entity for the current state
      - ``place_point(co)``-> click empty space, placing a new point for the current state
      - ``finish()``       -> redo_states + main + fini, i.e. commit the operator

    ``pick``/``place_point`` advance to the next state exactly like the modal loop's
    state transition; placed points aren't created until ``finish`` runs ``redo_states``,
    matching the real deferred-creation flow.
    """

    def __init__(self, real_cls, sketch, context):
        self.context = context
        op = make_operator_double(real_cls)()
        op._state_data = {}
        op.state_index = 0
        op._active_sketch = sketch
        op._undo = False
        op.state_init_coords = None
        op.executed = False
        # Don't chain into a fresh segment when the last state is committed.
        op.continuous_draw = False
        # bpy property annotations are inert on the twin; supply the flags the
        # lifecycle reads. (Constraint ops gate sync_settings on `initialized`.)
        op.initialized = False
        self.op = op

    def prefill(self):
        return self.op.prefill_state_props(self.context)

    def _advance(self):
        self.op.next_state(self.context)

    def pick(self, ref):
        """Use an existing entity for the current state (mirrors a pick_element hit)."""
        i = self.op.state_index
        data = self.op.get_state_data(i)
        data["type"] = type(ref)
        data["is_existing_entity"] = True
        self.op.set_state_pointer([ref.curve_id], index=i, implicit=True)
        self._advance()
        return self

    def set_value(self, value):
        """Set the current state's property value(s) (mirrors a numeric/placement input).

        Works for both a point pointer's fallback vector (deferred point creation in
        redo_states) and a plain property state (e.g. a circle's radius).
        """
        i = self.op.state_index
        for p in self.op.get_property(index=i) or []:
            setattr(self.op, p, value)
        self.op.get_state_data(i)["is_existing_entity"] = False
        self._advance()
        return self

    def place_point(self, co):
        """Place a new point for the current state (mirrors state_func + deferred create)."""
        from mathutils import Vector

        return self.set_value(Vector(co))

    def finish(self, run_fini=True):
        """Commit: recreate deferred elements, run main, then fini."""
        self.op.redo_states(self.context)
        result = self.op.main(self.context)
        self.op.executed = True
        if run_fini and hasattr(self.op, "fini"):
            self.op.fini(self.context, bool(result))
        return result

    def state_curve_id(self, index):
        return self.op.get_state_data(index).get("curve_id")

    def get_point(self, index):
        return self.op.get_point(self.context, index)


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
