"""Per-redraw memo for values every constraint marker looks up while drawing.

Each constraint gizmo and each constraint icon resolved the active sketch, the
theme colors and its curve's placement on its own, every frame. Those depend on
the frame, not on the constraint, so with many constraints the same lookups were
repeated dozens of times per redraw (issue: drawing gets rough after a handful of
shapes). Here they are computed once per redraw.

``begin_frame`` is called from the viewport's POST_VIEW draw callback, which runs
at the start of each 3D view redraw, before the 2D gizmos and the POST_PIXEL
icon pass that read from this memo. As a guard against a redraw that skips it,
memoized values also expire after ``_MAX_AGE`` seconds.
"""

import time

import numpy as np

_MAX_AGE = 0.2

_values = {}
_frame_start = 0.0
# Incremented for every redraw, so state kept across redraws can tell it is stale.
_frame_id = 0


def begin_frame() -> None:
    """Start a new redraw: forget every memoized value."""
    global _frame_start, _frame_id
    _values.clear()
    _frame_start = time.perf_counter()
    _frame_id += 1


def frame_id() -> int:
    """Identifies the current redraw (see begin_frame)."""
    if time.perf_counter() - _frame_start > _MAX_AGE:
        begin_frame()
    return _frame_id


def _memo(key, compute):
    if time.perf_counter() - _frame_start > _MAX_AGE:
        begin_frame()
    try:
        return _values[key]
    except KeyError:
        value = _values[key] = compute()
        return value


def active_sketch(context):
    """The active sketch, resolved once per redraw."""
    from ..model.sketch_ref import get_active_sketch

    return _memo(("active_sketch",), lambda: get_active_sketch(context))


def curve_placement(sketch, curve_id):
    """World placement of a curve's marker, computed once per curve per redraw."""
    from ..utilities.curve_data import get_curve_placement

    key = ("placement", sketch.target_object.as_pointer(), curve_id)
    return _memo(key, lambda: get_curve_placement(sketch, curve_id))


def constraint_color(color_type, highlit: bool):
    """Theme color for a constraint state, reading the theme once per redraw."""
    from ..gizmos.utilities import get_color

    return _memo(("color", color_type, highlit), lambda: get_color(color_type, highlit))


def ui_scale(context) -> float:
    """The interface scale, read once per redraw."""
    return _memo(("ui_scale",), lambda: context.preferences.system.ui_scale)


def text_size() -> float:
    """The dimension text size preference, read once per redraw."""
    from ..utilities.preferences import get_prefs

    return _memo(("text_size",), lambda: get_prefs().text_size)


def constraint_at(sketch, constraint_type: str, index: int):
    """A sketch's constraint by type and index, reading each list once per redraw."""
    key = ("constraints", sketch.target_object.as_pointer(), constraint_type)
    items = _memo(key, lambda: list(sketch.constraints.get_list(constraint_type)))
    return items[index] if 0 <= index < len(items) else None


def view_scale_key(context):
    """What screen-constant sizes (arrowheads) depend on in the current view.

    Mirrors utilities.view.get_scale_from_pos: the view distance in an
    orthographic view, the perspective matrix's w row otherwise. Rotating an
    orthographic view doesn't change it.
    """
    rv3d = context.region_data
    if rv3d is None:
        return None

    def compute():
        if rv3d.view_perspective == "ORTHO":
            return ("ORTHO", rv3d.view_distance)
        return ("PERSP", tuple(rv3d.perspective_matrix[3]))

    return _memo(("view_scale", rv3d.as_pointer()), compute)


def arrow_scale() -> float:
    """The arrow size preference, read once per redraw."""
    from ..utilities.preferences import get_prefs

    return _memo(("arrow_scale",), lambda: get_prefs().arrow_scale)


# Sketch object pointer -> positions seen at its last redraw and a generation per
# curve, bumped whenever one of the curve's points moves (see _geometry).
_geometry_states = {}


def _geometry(sketch):
    """Per-curve generations of a sketch, brought current once per redraw.

    Dimensions read their placement from the curves they reference. Comparing the
    sketch's point positions with the previous redraw's in one array operation
    tells which curves moved, so a dimension can reuse its placement while none of
    its curves did.
    """
    from ..utilities.curve_data import read_uuid_list

    obj = sketch.target_object
    state = _geometry_states.get(obj.as_pointer())
    if state is not None and state["frame"] == _frame_id:
        return state

    cd = obj.data
    n, m = len(cd.curves), len(cd.points)
    co = np.empty(m * 3, dtype=np.float32)
    if m:
        cd.points.foreach_get("position", co)
    offsets = np.empty(n + 1, dtype=np.int32)
    cd.curve_offset_data.foreach_get("value", offsets)
    ids = read_uuid_list(cd, "curve_id") if n else []
    world = tuple(v for row in obj.matrix_world for v in row)

    same_layout = (
        state is not None
        and state["world"] == world
        and state["ids"] == ids
        and np.array_equal(state["offsets"], offsets)
    )
    if same_layout:
        moved = np.flatnonzero((co != state["co"]).reshape(-1, 3).any(axis=1))
        if moved.size:
            curves = np.unique(np.searchsorted(offsets, moved, side="right") - 1)
            state["counter"] += 1
            state["generations"][curves] = state["counter"]
    else:
        # Curves were added, removed or reordered, or the sketch moved: start over.
        counter = state["counter"] + 1 if state is not None else 1
        state = {
            "counter": counter,
            "generations": np.full(n, counter, dtype=np.int64),
            "index": {cid: i for i, cid in enumerate(ids)},
            "bases": {},
        }
        _geometry_states[obj.as_pointer()] = state
    state.update(frame=_frame_id, co=co, offsets=offsets, ids=list(ids), world=world)
    return state


def dimension_basis(sketch, constraint):
    """A dimension's ``matrix_basis``, recomputed only when its curves moved.

    Only for drawing: the positions are compared once per redraw, so a change made
    after the redraw started is seen by the next one.
    """
    # The dimension's gizmo and its value label both ask within one redraw.
    return _memo(
        ("basis", constraint.as_pointer()),
        lambda: _dimension_basis(sketch, constraint),
    )


def dimension_geometry_key(sketch, constraint):
    """Changes whenever a curve the constraint refers to moved (see _geometry)."""
    return _memo(
        ("geometry_key", constraint.as_pointer()),
        lambda: _geometry_key(sketch, constraint),
    )


def _geometry_key(sketch, constraint):
    state = _geometry(sketch)
    ids = tuple(
        getattr(constraint, name, "")
        for name in ("curve_id_1", "curve_id_2", "curve_id_3")
    )
    index = state["index"]
    generations = state["generations"]
    return (
        constraint.type,
        ids,
        tuple(int(generations[index[cid]]) if cid in index else -1 for cid in ids),
        getattr(constraint, "align", None),
        getattr(constraint, "setting", None),
    )


def _dimension_basis(sketch, constraint):
    state = _geometry(sketch)
    key = dimension_geometry_key(sketch, constraint)
    slot = key[:2]
    cached = state["bases"].get(slot)
    if cached is not None and cached[0] == key:
        return cached[1]
    basis = constraint.matrix_basis()
    state["bases"][slot] = (key, basis)
    return basis
