"""CPU screen-space picking for the active sketch.

Replaces the GPU id-buffer (offscreen render + pixel readback): project the
active sketch's points and segments to screen with numpy and find what's under
the cursor / inside a box. No offscreen, no readback, no descriptor pressure --
which is what the GPU id-buffer cost on the Vulkan backend.

Only the active sketch is pickable (other sketches are read-only reference), and
curves in ``selection.ignore_list`` are skipped, matching the old behavior.
"""

import numpy as np

from ..model.sketch_ref import get_active_sketch
from ..utilities.preferences import get_prefs, get_scale
from ..utilities.view import _project_points_to_region
from . import render_data, selection

# Pick radius in pixels (scaled by UI scale). Points grab a bit wider than edges
# and take priority, so a vertex is easy to hit even when it sits on a line.
_POINT_RADIUS = 11.0
_EDGE_RADIUS = 8.0


# (sketch object name) -> (geometry_signature, point_ids, segment_ids). Picking
# only needs the projected points/segments, which depend on geometry, not on the
# hover/selection state that changes every mouse-move -- so we rebuild the
# extraction only when the geometry actually changes, not on every hover.
_pick_cache = {}


def _active_data(context):
    sketch = get_active_sketch(context)
    if not sketch or not sketch.is_visible(context):
        return None

    obj = sketch.target_object
    sig = render_data.geometry_signature(sketch)
    cached = _pick_cache.get(obj.name)
    if cached is not None and cached[0] == sig:
        return cached[1]

    ts = get_prefs().theme_settings.entity
    data = render_data.build(sketch, ts, is_active=True)
    _pick_cache[obj.name] = (sig, data)
    return data


def _points_screen(items, region, rv3d):
    """Project [(cid, world_pos), ...] -> (cids, screen (N,2), valid (N,))."""
    cids = [cid for cid, _ in items]
    world = np.array([p for _, p in items], dtype=np.float64)
    screen, valid = _project_points_to_region(world, region, rv3d)
    return cids, screen, valid


def _seg_screen(items, region, rv3d):
    """Project [(cid, a, b), ...] -> (cids, screen (N,2,2), valid (N,2))."""
    cids = [cid for cid, _, _ in items]
    world = np.array([[a, b] for _, a, b in items], dtype=np.float64).reshape(-1, 3)
    screen, valid = _project_points_to_region(world, region, rv3d)
    n = len(items)
    return cids, screen.reshape(n, 2, 2), valid.reshape(n, 2)


def _dist_to_segment(a, b, px, py):
    abx, aby = b[0] - a[0], b[1] - a[1]
    seg2 = abx * abx + aby * aby
    if seg2 < 1e-9:
        return ((px - a[0]) ** 2 + (py - a[1]) ** 2) ** 0.5
    t = ((px - a[0]) * abx + (py - a[1]) * aby) / seg2
    t = min(1.0, max(0.0, t))
    cx, cy = a[0] + t * abx, a[1] + t * aby
    return ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5


def pick_ranked(context, coords):
    """curve_ids of every active-sketch element under ``coords``, nearest first.

    Points take priority over edges (a vertex on a line is still grabbable), then
    by screen distance. Unlike ``pick`` this keeps *all* candidates within the hit
    radius, so overlapping entities can be cycled through instead of only ever
    getting the topmost one (issue #50)."""
    data = _active_data(context)
    region, rv3d = context.region, context.region_data
    if data is None or region is None or rv3d is None:
        return []

    ignore = selection.ignore_list
    scale = get_scale()
    cx, cy = float(coords[0]), float(coords[1])
    hits = []  # (priority, distance, cid)

    pts = [(cid, p) for cid, p in data.point_ids if cid not in ignore]
    if pts:
        cids, screen, valid = _points_screen(pts, region, rv3d)
        d = np.hypot(screen[:, 0] - cx, screen[:, 1] - cy)
        r = _POINT_RADIUS * scale
        for i, cid in enumerate(cids):
            if valid[i] and d[i] <= r:
                hits.append((0, float(d[i]), cid))

    segs = [(cid, a, b) for cid, a, b in data.segment_ids if cid not in ignore]
    if segs:
        cids, screen, valid = _seg_screen(segs, region, rv3d)
        r = _EDGE_RADIUS * scale
        for i, cid in enumerate(cids):
            if not (valid[i, 0] and valid[i, 1]):
                continue
            dist = _dist_to_segment(screen[i, 0], screen[i, 1], cx, cy)
            if dist <= r:
                hits.append((1, float(dist), cid))

    hits.sort(key=lambda h: (h[0], h[1]))
    ranked, seen = [], set()
    for _, _, cid in hits:
        if cid not in seen:
            seen.add(cid)
            ranked.append(cid)
    return ranked


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
    data = _active_data(context)
    region, rv3d = context.region, context.region_data
    if data is None or region is None or rv3d is None:
        return []

    ignore = selection.ignore_list
    x0, x1 = sorted((float(min_co[0]), float(max_co[0])))
    y0, y1 = sorted((float(min_co[1]), float(max_co[1])))

    found, seen = [], set()

    pts = [(cid, p) for cid, p in data.point_ids if cid not in ignore]
    if pts:
        cids, screen, valid = _points_screen(pts, region, rv3d)
        inside = (
            valid
            & (screen[:, 0] >= x0)
            & (screen[:, 0] <= x1)
            & (screen[:, 1] >= y0)
            & (screen[:, 1] <= y1)
        )
        for i, cid in enumerate(cids):
            if inside[i] and cid not in seen:
                seen.add(cid)
                found.append(cid)

    segs = [(cid, a, b) for cid, a, b in data.segment_ids if cid not in ignore]
    if segs:
        cids, screen, valid = _seg_screen(segs, region, rv3d)
        for i, cid in enumerate(cids):
            if cid in seen or not (valid[i, 0] and valid[i, 1]):
                continue
            if _seg_intersects_box(screen[i, 0], screen[i, 1], x0, y0, x1, y1):
                seen.add(cid)
                found.append(cid)

    return found
