"""CPU screen-space picking for the active sketch.

Replaces the GPU id-buffer (offscreen render + pixel readback): project the
active sketch's points and segments to screen with numpy and find what's under
the cursor / inside a box. No offscreen, no readback, no descriptor pressure --
which is what the GPU id-buffer cost on the Vulkan backend.

Only the active sketch is pickable (other sketches are read-only reference), and
curves in ``selection.ignore_list`` are skipped, matching the old behavior.
"""

from typing import NamedTuple

import numpy as np

from ..model.sketch_ref import get_active_sketch
from ..utilities.preferences import get_scale
from ..utilities.view import _project_points_to_region
from . import render_data, selection

# Pick radius in pixels (scaled by UI scale). Points grab a bit wider than edges
# and take priority, so a vertex is easy to hit even when it sits on a line.
_POINT_RADIUS = 11.0
_EDGE_RADIUS = 8.0


class PickSet(NamedTuple):
    """Pickable geometry in the array form the screen projection consumes.

    ``point_keys`` is aligned with ``point_co`` rows. Segment identity is per
    *curve*: ``seg_keys`` holds one key per curve and ``seg_owner`` maps each row
    of ``seg_co`` back into it, so a 48-segment circle carries one key, not 48.
    """

    point_keys: list
    point_co: np.ndarray  # (P, 3)
    seg_keys: list
    seg_co: np.ndarray  # (M, 2, 3)
    seg_owner: np.ndarray  # (M,) -> index into seg_keys


EMPTY_PICKSET = PickSet(
    [],
    np.zeros((0, 3), dtype=np.float32),
    [],
    np.zeros((0, 2, 3), dtype=np.float32),
    np.zeros(0, dtype=np.intp),
)


def _active_data(context):
    """The active sketch's pickable geometry, from the shared extraction cache.

    Picking needs only the projected points and segments, which depend on the
    geometry and not on the hover/selection state that changes every mouse-move.
    ``render_data.geometry`` caches exactly that against the geometry signature,
    and the overlay draws from the same entry, so a frame in which the geometry
    changed extracts once rather than once here and once for the overlay.
    """
    sketch = get_active_sketch(context)
    if not sketch or not sketch.is_visible(context):
        return None
    return render_data.geometry(sketch)


def _active_pickset(context):
    """``PickSet`` for the active sketch, honouring ``selection.ignore_list``."""
    geo = _active_data(context)
    if geo is None:
        return None

    pick = PickSet(
        geo.point_cids, geo.point_co, geo.seg_cids, geo.seg_co, geo.seg_owner
    )
    ignore = selection.ignore_list
    if not ignore:
        # The common case: the arrays are handed straight through, no filtering.
        return pick
    return _without(pick, ignore)


def _without(pick, ignore):
    """Drop every point/segment whose key is in ``ignore``."""
    keep_pts = [i for i, k in enumerate(pick.point_keys) if k not in ignore]
    drop_curves = {c for c, k in enumerate(pick.seg_keys) if k in ignore}
    if drop_curves:
        keep_rows = ~np.isin(pick.seg_owner, list(drop_curves))
        seg_co = pick.seg_co[keep_rows]
        seg_owner = pick.seg_owner[keep_rows]
    else:
        seg_co, seg_owner = pick.seg_co, pick.seg_owner
    return PickSet(
        [pick.point_keys[i] for i in keep_pts],
        pick.point_co[keep_pts],
        pick.seg_keys,
        seg_co,
        seg_owner,
    )


def _dist_to_segments(screen, cx, cy):
    """Perpendicular distance from ``(cx, cy)`` to each of N screen segments.

    ``screen`` is ``(N, 2, 2)``. Vectorized: the per-segment Python loop this
    replaces ran once per tessellated segment, so a sketch of circles paid for it
    thousands of times per mouse-move.
    """
    a = screen[:, 0]
    b = screen[:, 1]
    ab = b - a
    seg2 = (ab * ab).sum(axis=1)
    ap = np.stack((cx - a[:, 0], cy - a[:, 1]), axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        t = np.where(seg2 > 1e-9, (ap * ab).sum(axis=1) / seg2, 0.0)
    t = np.clip(t, 0.0, 1.0)
    closest = a + t[:, None] * ab
    return np.hypot(closest[:, 0] - cx, closest[:, 1] - cy)


def rank_hits(pick, context, coords):
    """Ranked element keys from a ``PickSet`` under ``coords``.

    Points take priority over segments, then nearest first, and keys are deduped.
    Shared by the active-sketch picker and reference curve-object picking
    (``reference_pick``), so it must stay independent of any sketch specifics.
    """
    region, rv3d = context.region, context.region_data
    if region is None or rv3d is None:
        return []

    scale = get_scale()
    cx, cy = float(coords[0]), float(coords[1])
    order = []  # (priority, distance, key), gathered vectorized then sorted

    if len(pick.point_co):
        screen, valid = _project_points_to_region(pick.point_co, region, rv3d)
        d = np.hypot(screen[:, 0] - cx, screen[:, 1] - cy)
        hit = valid & (d <= _POINT_RADIUS * scale)
        for i in np.flatnonzero(hit).tolist():
            order.append((0, float(d[i]), pick.point_keys[i]))

    if len(pick.seg_co):
        n = len(pick.seg_co)
        screen, valid = _project_points_to_region(
            pick.seg_co.reshape(-1, 3), region, rv3d
        )
        screen = screen.reshape(n, 2, 2)
        valid = valid.reshape(n, 2).all(axis=1)
        d = _dist_to_segments(screen, cx, cy)
        hit = valid & (d <= _EDGE_RADIUS * scale)
        owners = pick.seg_owner
        for i in np.flatnonzero(hit).tolist():
            order.append((1, float(d[i]), pick.seg_keys[owners[i]]))

    order.sort(key=lambda h: (h[0], h[1]))
    ranked, seen = [], set()
    for _, _, key in order:
        if key not in seen:
            seen.add(key)
            ranked.append(key)
    return ranked


def pick_ranked(context, coords):
    """curve_ids of every active-sketch element under ``coords``, nearest first.

    Points take priority over edges (a vertex on a line is still grabbable), then
    by screen distance. Unlike ``pick`` this keeps *all* candidates within the hit
    radius, so overlapping entities can be cycled through instead of only ever
    getting the topmost one (issue #50)."""
    pick = _active_pickset(context)
    if pick is None:
        return []
    return rank_hits(pick, context, coords)


def pick(context, coords):
    """curve_id of the active sketch's nearest element under ``coords``, or ``""``."""
    ranked = pick_ranked(context, coords)
    return ranked[0] if ranked else ""


def update_hover(context, coords):
    """Cycle-aware hover resolution shared by the preselection gizmo and picking.

    Stores the ranked candidate list on ``selection.hover_candidates`` and returns
    the curve_id to hover: the current hover is kept if it is still under the
    cursor (so a cycled choice survives small mouse moves), otherwise the nearest.
    """
    ranked = pick_ranked(context, coords)
    selection.hover_candidates = ranked
    if selection.hover in ranked:
        return selection.hover
    # Moved to a different element (or off geometry): drop any wheel-set lock.
    selection.hover_locked = False
    return ranked[0] if ranked else ""


def _seg_intersects_box(a, b, x0, y0, x1, y1):
    # Endpoint inside?
    for px, py in (a, b):
        if x0 <= px <= x1 and y0 <= py <= y1:
            return True
    # Else does the segment cross any box edge? Liang-Barvey-ish clip test.
    dx, dy = b[0] - a[0], b[1] - a[1]
    p = (-dx, dx, -dy, dy)
    q = (a[0] - x0, x1 - a[0], a[1] - y0, y1 - a[1])
    t0, t1 = 0.0, 1.0
    for pi, qi in zip(p, q):
        if pi == 0:
            if qi < 0:
                return False
        else:
            t = qi / pi
            if pi < 0:
                t0 = max(t0, t)
            else:
                t1 = min(t1, t)
    return t0 <= t1


def pick_box(context, min_co, max_co):
    """curve_ids of the active sketch whose geometry overlaps the screen box."""
    pick = _active_pickset(context)
    region, rv3d = context.region, context.region_data
    if pick is None or region is None or rv3d is None:
        return []

    x0, x1 = sorted((float(min_co[0]), float(max_co[0])))
    y0, y1 = sorted((float(min_co[1]), float(max_co[1])))

    found, seen = [], set()

    if len(pick.point_co):
        screen, valid = _project_points_to_region(pick.point_co, region, rv3d)
        inside = (
            valid
            & (screen[:, 0] >= x0)
            & (screen[:, 0] <= x1)
            & (screen[:, 1] >= y0)
            & (screen[:, 1] <= y1)
        )
        for i in np.flatnonzero(inside).tolist():
            key = pick.point_keys[i]
            if key not in seen:
                seen.add(key)
                found.append(key)

    if len(pick.seg_co):
        n = len(pick.seg_co)
        screen, valid = _project_points_to_region(
            pick.seg_co.reshape(-1, 3), region, rv3d
        )
        screen = screen.reshape(n, 2, 2)
        valid = valid.reshape(n, 2).all(axis=1)
        owners = pick.seg_owner
        for i in np.flatnonzero(valid).tolist():
            key = pick.seg_keys[owners[i]]
            if key in seen:
                continue
            if _seg_intersects_box(screen[i, 0], screen[i, 1], x0, y0, x1, y1):
                seen.add(key)
                found.append(key)

    return found
