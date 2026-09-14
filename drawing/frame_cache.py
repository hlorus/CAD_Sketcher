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

_MAX_AGE = 0.2

_values = {}
_frame_start = 0.0


def begin_frame() -> None:
    """Start a new redraw: forget every memoized value."""
    global _frame_start
    _values.clear()
    _frame_start = time.perf_counter()


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
