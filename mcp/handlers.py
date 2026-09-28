"""The tools themselves. Every one of these runs on Blender's main thread.

A handler returns either a JSON-safe dict, or an ``(image_bytes, mime)`` pair for
a tool that answers with a picture. Raising :class:`ToolError` reports a problem
to the agent as a failed tool call, which it can read and retry; anything else
escaping is a bug and is reported as one.
"""

from typing import Any, Dict, Optional, Tuple, Union

import bpy

from ..curve_solver import solve_system
from ..model.sketch_ref import Sketch, get_sketches, set_active_sketch
from ..utilities.curve_data import refresh_curve_geometry
from . import describe, render
from .ops import OpError, apply_ops

Result = Union[Dict[str, Any], Tuple[bytes, str]]


class ToolError(Exception):
    """A tool could not do what was asked, for a reason the agent should read."""


def _sketch(context, params: Dict[str, Any]) -> Sketch:
    try:
        return describe.find_sketch(context, params.get("sketch"))
    except LookupError as e:
        raise ToolError(str(e)) from e


def _guard_writes(context) -> None:
    """Refuse to write while Blender is somewhere a write would misbehave."""
    from .. import global_data

    if global_data.stateful_op_running:
        raise ToolError(
            "A CAD Sketcher tool is running in Blender right now. "
            "Ask the user to finish or cancel it, then retry."
        )
    if context.mode != "OBJECT":
        raise ToolError(
            f"Blender is in {context.mode} mode. Writes need Object mode; "
            "ask the user to leave Edit mode."
        )


def _undo_push(message: str) -> bool:
    """Make the edit one step in the user's undo stack.

    Returns whether a step was actually pushed, which is what makes rolling
    back safe: ``ed.undo`` walks the *global* stack, so undoing when nothing was
    pushed takes back whatever the user did last instead.
    """
    if bpy.app.background:
        # No undo stack without a window: pushing does nothing and undoing
        # would roll the file back past state this session is holding on to.
        return False
    try:
        bpy.ops.ed.undo_push(message=message)
    except RuntimeError:
        return False
    return True


# -- Read --------------------------------------------------------------------


def describe_scene(context, params: Dict[str, Any]) -> Result:
    """List the scene's sketches and unit settings."""
    return describe.scene_data(context)


def describe_sketch(context, params: Dict[str, Any]) -> Result:
    """Dump one sketch."""
    return describe.sketch_data(_sketch(context, params))


def render_sketch(context, params: Dict[str, Any]) -> Result:
    """Render one sketch square-on to its plane."""
    sketch = _sketch(context, params)
    size = int(params.get("size") or 800)
    size = max(256, min(2048, size))
    try:
        return render.sketch_png(context, sketch, size), "image/png"
    except render.RenderUnavailable as e:
        raise ToolError(str(e)) from e


# -- Write -------------------------------------------------------------------


def edit_sketch(context, params: Dict[str, Any]) -> Result:
    """Apply an op list, solve, and report the sketch."""
    _guard_writes(context)
    sketch = _sketch(context, params)

    # Undo before the edit, so the user's Ctrl-Z lands on the state they had.
    pushed = _undo_push(f"MCP edit {sketch.name}")

    try:
        entities, constraints = apply_ops(sketch, params.get("ops"))
    except OpError as e:
        _undo_and_restore(context, pushed)
        raise ToolError(str(e)) from e

    solved = solve_system(context, sketch=sketch)
    refresh_curve_geometry(sketch)
    _redraw()

    result = describe.sketch_data(sketch)
    result["applied"] = {"entities_added": entities, "constraints_added": constraints}
    if not solved:
        result["warning"] = (
            "The solver could not satisfy these constraints. Any marked failed "
            "contradict the others; remove or change one of them."
        )
    return result


def create_sketch(context, params: Dict[str, Any]) -> Result:
    """Create a sketch on a base plane and activate it."""
    _guard_writes(context)

    plane_name = (params.get("plane") or "XY").upper()
    planes = {"XY": "wp_xy", "XZ": "wp_xz", "YZ": "wp_yz"}
    if plane_name not in planes:
        raise ToolError(f"plane must be XY, XZ or YZ, got {plane_name!r}")

    from ..operators.add_sketch import build_sketch_on_workplane
    from ..utilities.body import body_of, name_after_body
    from ..utilities.workplane import ensure_origin_workplane_empties

    _undo_push("MCP create sketch")

    ensure_origin_workplane_empties(context)
    workplane = getattr(context.scene.sketcher, planes[plane_name])
    if workplane is None:
        raise ToolError(f"The scene has no {plane_name} base plane to sketch on.")

    sketch = build_sketch_on_workplane(context, workplane)

    # A sketch is named after the body it sits on, and a depsgraph pass
    # re-derives it, so naming the sketch object directly would not survive.
    name = params.get("name")
    body = body_of(sketch.target_object)
    if name and body is not None:
        body.name = name
        name_after_body(body, sketch.target_object, sketch.target_object.slvs_workplane)

    _activate(context, sketch)
    _redraw()

    return describe.sketch_data(sketch)


def delete_sketch(context, params: Dict[str, Any]) -> Result:
    """Delete a sketch and what was built from it."""
    _guard_writes(context)
    sketch = _sketch(context, params)
    name = sketch.name

    _undo_push(f"MCP delete {name}")

    from ..model.sketch_ref import get_active_sketch

    active = get_active_sketch(context)
    if active and active.name == name:
        _activate(context, None)
    sketch.remove_objects()
    _redraw()

    return {"deleted": name, "remaining": [s.name for s in get_sketches(context)]}


def solve_sketch(context, params: Dict[str, Any]) -> Result:
    """Re-solve a sketch and report its state."""
    sketch = _sketch(context, params)
    solved = solve_system(context, sketch=sketch)
    _redraw()
    result = describe.sketch_data(sketch)
    result["solved"] = bool(solved)
    return result


# -- Blender plumbing --------------------------------------------------------


def _undo_and_restore(context, pushed: bool) -> None:
    """Take back the ops that ran before the failing one.

    An op list can only be fully checked as it is applied, since later ops name
    geometry earlier ops create. So a rejected list is undone rather than
    prevented, which is what makes the call all-or-nothing from outside.

    Only ever after our own push landed. ``ed.undo`` steps the whole file back,
    not just this call, so undoing without a matching push reverts the user's
    previous action, and where the step does not exist at all it can take the
    scene with it.
    """
    if not pushed:
        return
    override = view3d_override(context)
    try:
        if override is not None:
            with context.temp_override(**override):
                bpy.ops.ed.undo()
        else:
            bpy.ops.ed.undo()
    except RuntimeError:
        pass


def _activate(context, sketch: Optional[Sketch]) -> None:
    """Enter or leave a sketch the way the sidebar does.

    Through the operator rather than the pointer, so everything activation
    carries (view alignment, what is hidden, the tool state) happens too.
    """
    override = view3d_override(context)
    name = sketch.target_object.name if sketch is not None else ""
    try:
        if override is not None:
            with context.temp_override(**override):
                bpy.ops.view3d.slvs_set_active_sketch(sketch_name=name)
            return
        bpy.ops.view3d.slvs_set_active_sketch(sketch_name=name)
    except RuntimeError:
        # No viewport to activate into (background mode): the pointer is what
        # the rest of the add-on reads, so set it directly.
        set_active_sketch(context, sketch)


def _redraw() -> None:
    """Tag the 3D views, so the user sees the change without touching anything."""
    window_manager = bpy.context.window_manager
    for window in getattr(window_manager, "windows", ()):
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


def view3d_override(context) -> Optional[Dict[str, Any]]:
    """A context override naming a 3D viewport, or None when there is none.

    Handlers run from a timer, where the context carries no area, so anything
    that needs a viewport has to name one itself.
    """
    for window in getattr(context.window_manager, "windows", ()):
        for area in window.screen.areas:
            if area.type != "VIEW_3D":
                continue
            for region in area.regions:
                if region.type == "WINDOW":
                    return {
                        "window": window,
                        "screen": window.screen,
                        "area": area,
                        "region": region,
                        "space_data": area.spaces.active,
                    }
    return None


# -- Features ----------------------------------------------------------------


def _feature(context, params: Dict[str, Any], build, label: str) -> Result:
    """Run one feature builder, then report the body it acted on."""
    _guard_writes(context)
    from . import features

    pushed = _undo_push(f"MCP {label}")
    try:
        target = build(context, params)
    except features.FeatureError as e:
        _undo_and_restore(context, pushed)
        raise ToolError(str(e)) from e

    context.view_layer.update()
    _redraw()
    result = features.body_data(target)
    result["did"] = label
    return result


def extrude(context, params: Dict[str, Any]) -> Result:
    """Give a sketch thickness."""
    from . import features

    return _feature(context, params, features.extrude, "extrude")


def revolve(context, params: Dict[str, Any]) -> Result:
    """Sweep a sketch around an axis."""
    from . import features

    return _feature(context, params, features.revolve, "revolve")


def array(context, params: Dict[str, Any]) -> Result:
    """Repeat a solid."""
    from . import features

    return _feature(context, params, features.array, "array")


def boolean(context, params: Dict[str, Any]) -> Result:
    """Cut or merge one solid with another."""
    from . import features

    return _feature(context, params, features.boolean, "boolean")


def make_part(context, params: Dict[str, Any]) -> Result:
    """Make a body (and anything named with it) into one part."""
    from . import features

    return _feature(context, params, features.make_part, "make_part")
