"""Drive drawing tools through their real live-update loop, headless.

``OpHarness`` (testing/utils.py) jumps straight to ``redo_states`` + ``main``. That
skips exactly what a tool does while the mouse moves: the per-move undo and
rebuild, hover picks, snapping, live projection and inferred constraints. This
harness calls the operator's own ``check_event`` / ``evaluate_state`` for every
move and click instead, so those paths run as they do in the modal.

Only the view-dependent inputs are stubbed: cursor positions are given directly
in sketch-local coordinates, and the hovered element and snap target are set per
event. ``capture_sketch`` then reduces the committed sketch to a comparable,
id-independent form, so two runs can be compared exactly.
"""

import types
from contextlib import ExitStack
from unittest import mock

import bpy
from mathutils import Vector

from .utils import make_operator_double

# Modules that import the view helpers by name, so each needs its own stub.
_VIEW_IMPORTERS = (
    "operators.base_2d",
    "operators.add_circle",
    "operators.add_arc",
    "operators.bevel",
)


class _Properties:
    """Stand-in for ``Operator.properties`` on a non-registered operator twin."""

    def __init__(self, op):
        self._op = op

    def is_property_set(self, name):
        return name in vars(self._op)


class _LiveContext:
    """``bpy.context`` with the window/area UI sinks a modal expects stubbed."""

    def __init__(self, context):
        self._context = context
        noop = types.SimpleNamespace
        self.area = noop(type="VIEW_3D", tag_redraw=lambda: None)
        self.window = noop(
            cursor_modal_restore=lambda: None, cursor_modal_set=lambda *_: None
        )
        self.workspace = noop(status_text_set=lambda *_: None)
        self.space_data = None
        self.region = None
        self.region_data = None

    def __getattr__(self, name):
        return getattr(self._context, name)


class LiveOpHarness:
    """Run a stateful drawing tool the way the modal does, one event at a time."""

    def __init__(self, real_cls, sketch, context, **props):
        from .. import global_data
        from ..stateful_operator.utilities.numeric import NumericInput

        op = make_operator_double(real_cls)()
        op._state_data = {}
        op.state_index = 0
        op._undo = False
        op.state_init_coords = None
        op.executed = False
        op.continuous_draw = False
        op.edit_state = -1
        op.wait_for_input = True
        op._numeric = NumericInput()
        op.properties = _Properties(op)
        # The class bl_rna lists Operator's own fields; the tool's properties
        # (e.g. a point's ``coordinates``) are on the registered op's RNA type.
        category, name = real_cls.bl_idname.split(".")
        op.rna_type = getattr(getattr(bpy.ops, category), name).get_rna_type()
        op.bl_label = real_cls.bl_label
        for name, value in props.items():
            setattr(op, name, value)

        self.op = op
        self.context = _LiveContext(context)
        self.snap = None
        self.result = None

        global_data.stateful_op_running = True
        op._state_snapshot = op.create_snapshot(self.context)
        op.init(self.context, None)
        op._capture_baseline(self.context)

    # -- input stubs ------------------------------------------------------

    def _stubs(self):
        import importlib
        import sys

        pkg = __package__.rsplit(".", 1)[0]
        stack = ExitStack()

        def pos_2d(context, wp, coords, respect_snapping=False):
            return None if coords is None else Vector((coords[0], coords[1]))

        def snap_info(context, coords):
            return self.snap

        for name in _VIEW_IMPORTERS:
            module = sys.modules.get(f"{pkg}.{name}") or importlib.import_module(
                f"{pkg}.{name}"
            )
            if hasattr(module, "get_pos_2d"):
                stack.enter_context(mock.patch.object(module, "get_pos_2d", pos_2d))
            if hasattr(module, "get_blender_snap_info"):
                stack.enter_context(
                    mock.patch.object(module, "get_blender_snap_info", snap_info)
                )
        return stack

    def _event(self, co, kind, value, shift):
        return types.SimpleNamespace(
            mouse_region_x=float(co[0]),
            mouse_region_y=float(co[1]),
            type=kind,
            value=value,
            shift=shift,
            alt=False,
            ctrl=False,
        )

    def _dispatch(self, co, hover, snap, shift, click):
        from ..drawing import selection

        if self.result is not None:
            raise RuntimeError("the operator already finished")
        selection.hover = hover or ""
        self.snap = snap
        event = (
            self._event(co, "LEFTMOUSE", "PRESS", shift)
            if click
            else self._event(co, "MOUSEMOVE", "NOTHING", shift)
        )
        with self._stubs():
            triggered = self.op.check_event(event)
            ret = self.op.evaluate_state(self.context, event, triggered)
        if isinstance(ret, set) and ret & {"FINISHED", "CANCELLED"}:
            self.result = ret
            self._teardown()
        return ret

    def _teardown(self):
        from .. import global_data
        from ..drawing import selection

        global_data.stateful_op_running = False
        selection.hover = ""

    # -- public -----------------------------------------------------------

    def move(self, co, hover="", snap=None, shift=False):
        """A mouse move to sketch-local ``co``, hovering ``hover`` (a curve_id)."""
        return self._dispatch(co, hover, snap, shift, click=False)

    def click(self, co, hover="", snap=None, shift=False):
        """A left click at ``co``: confirms the current state."""
        return self._dispatch(co, hover, snap, shift, click=True)

    def cancel(self):
        """Right-click: end the tool without committing."""
        if self.result is None:
            self.result = self.op._end(self.context, False)
            self._teardown()
        return self.result


def capture_sketch(sketch):
    """The sketch's curves and constraints in an id-independent, comparable form.

    Curve ids are random, so every id is replaced by the curve's position in the
    curve order (which is creation order, hence deterministic). Coordinates are
    rounded to absorb float32 noise.
    """
    from ..model.constants import SketchCurveType
    from ..utilities.curve_data import get_uuid, has_uuid_field
    from ..utilities.projection_anchor import iter_projected_point_bindings

    cd = sketch.target_object.data
    n = len(cd.curves)
    ids = [get_uuid(cd, "curve_id", i) for i in range(n)] if n else []
    canon = {cid: i for i, cid in enumerate(ids)}

    def ref(cid):
        return canon.get(cid, None) if cid else None

    def flag(name, i):
        attr = cd.attributes.get(name)
        return bool(attr.data[i].value) if attr else None

    def rounded(vec):
        return [round(float(c), 4) for c in vec]

    type_attr = cd.attributes.get("sketch_type")
    type_names = {
        SketchCurveType.POINT: "POINT",
        SketchCurveType.LINE: "LINE",
        SketchCurveType.ARC: "ARC",
        SketchCurveType.CIRCLE: "CIRCLE",
    }
    curves = []
    for i in range(n):
        curve = cd.curves[i]
        entry = {
            "type": type_names.get(type_attr.data[i].value, "UNKNOWN"),
            "construction": flag("construction", i),
            "fixed": flag("fixed", i),
            "points": [rounded(cd.points[p.index].position) for p in curve.points],
        }
        for field in ("start_point_id", "end_point_id", "center_point_id"):
            if has_uuid_field(cd, field):
                entry[field] = ref(get_uuid(cd, field, i))
        curves.append(entry)

    constraints = []
    for c in sketch.constraints.all:
        item = {
            "type": c.type,
            "refs": [
                ref(getattr(c, f"curve_id_{k}", ""))
                for k in (1, 2, 3)
                if hasattr(c, f"curve_id_{k}")
            ],
        }
        if hasattr(c, "value") and c.type in (
            "DISTANCE",
            "DIAMETER",
            "ANGLE",
            "RATIO",
        ):
            item["value"] = round(float(c.value), 4)
        constraints.append(item)
    constraints.sort(key=lambda item: (item["type"], str(item["refs"])))

    bindings = sorted(
        [ref(cid), getattr(source, "name", str(source)), int(fallback)]
        for cid, source, _vertex_id, fallback, _last in iter_projected_point_bindings(
            sketch
        )
    )
    return {"curves": curves, "constraints": constraints, "projections": bindings}


def new_mesh_object(context, name, verts, edges=()):
    """A mesh object linked to the scene, to snap and project onto."""
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], list(edges), [])
    ob = bpy.data.objects.new(name, me)
    context.scene.collection.objects.link(ob)
    return ob
