"""Extract a sketch's renderable geometry into flat draw buckets.

Pure data — no GPU calls — so it can be unit-tested headless. Produces:

- ``point_buckets``: ``color -> [(world position, size factor), ...]``
- ``line_buckets``:  ``(construction, color) -> [segment endpoint, ...]`` (pairs)
- ``point_ids`` / ``segment_ids``: the ``curve_id`` behind each point / segment,
  kept for CPU picking (phase 2); unused by the overlay itself.

``overlay_signature`` is a cheap hash of everything that affects the drawing, so
the overlay can skip rebuilding batches when nothing changed.
"""

import math
from itertools import chain, repeat

import numpy as np
from mathutils import Vector

from ..model.constants import SketchCurveType
from ..utilities.curve_data import (
    get_curve_data,
    has_uuid_field,
    read_curve_id_list,
    read_uuid_list,
)
from ..utilities.math import range_2pi
from . import selection

# Segments for a full circle; arcs use a proportional share (min 4).
ARC_SEGMENTS = 48

# Per-point size multipliers over the (0.75x) base point size, so hovered and
# selected points read as noticeably bigger (applied per-vertex on the quads).
POINT_SIZE_HOVER = 1.667
POINT_SIZE_SELECTED = 1.667


def _bulk_bool(attr, n):
    out = np.zeros(n, dtype=bool)
    if attr is not None:
        attr.data.foreach_get("value", out)
    return out


def _bulk_int(attr, n):
    out = np.full(n, -1, dtype=np.int32)
    if attr is not None:
        attr.data.foreach_get("value", out)
    return out


def _world_matrix(sketch):
    """Return the transform that owns a sketch's local curve coordinates.

    Delegates to ``Sketch.world_matrix`` (the single source of truth): a native
    free-3D sketch keeps its Curves child at identity and uses the parent origin
    Empty as the movable frame, so overlay/picking follow an interactive origin
    transform immediately instead of the child's lagging derived matrix.
    """
    return sketch.world_matrix


def curve_color(ts, selected, hover, fixed, active=True):
    """Theme color for a curve given its state (mirrors the legacy drawing)."""
    if not active:
        return ts.inactive_selected if selected else ts.inactive
    if selected:
        return ts.selected_highlight if hover else ts.selected
    if hover:
        return ts.highlight
    if fixed:
        return ts.fixed
    return ts.default


def geometry_signature(sketch):
    """Fingerprint of the geometry that determines pickable positions.

    Positions + the persistent curve attributes (type/construction/visible/...),
    the sketch's effective world matrix, plus counts. Excludes transient
    selection/hover -- those change colours (the overlay), not the projected
    points/segments (picking), so picking can cache its extraction against this
    and skip rebuilding while the cursor just hovers.

    ``build`` bakes the effective world transform into every point/segment
    position, so it must be part of the fingerprint. For native 3D sketches that
    transform is the origin Empty; for normal sketches it is the Curves object.
    """
    cd = sketch.data
    n_curves = len(cd.curves)
    n_points = len(cd.points)
    if n_points == 0:
        return (0, 0, 0)

    pos = np.empty(n_points * 3, dtype=np.float32)
    cd.points.foreach_get("position", pos)

    parts = [pos.tobytes()]
    for name in ("construction", "fixed", "visible", "cyclic"):
        parts.append(_bulk_bool(cd.attributes.get(name), n_curves).tobytes())
    parts.append(_bulk_int(cd.attributes.get("sketch_type"), n_curves).tobytes())
    parts.append(np.array(_world_matrix(sketch), dtype=np.float32).tobytes())
    # curve_id is the pick result build() returns; the validate self-heal can
    # re-mint ids in place (same count/positions), so it belongs in the key too.
    parts.append("".join(read_curve_id_list(cd)).encode())

    return (n_curves, n_points, hash(b"".join(parts)))


def overlay_signature(sketch, is_active, theme_sig):
    """Cheap, hashable fingerprint of everything that affects the overlay.

    Reading the flat attribute arrays with ``foreach_get`` is far cheaper than
    rebuilding GPU batches, so the overlay computes this every frame and only
    rebuilds when it changes.

    Hover and highlight are set only by picking, which is active-only, so they
    never reference an inactive sketch's curves. Folding them into every sketch's
    signature made unrelated visible sketches rebuild their batches on every
    hover change (each mouse-move). Inactive sketches therefore track only their
    geometry and the selection set (which can still contain their curves after an
    active-sketch switch); the per-frame hover/highlight go to the active sketch
    alone.
    """
    if len(sketch.data.points) == 0:
        return (0, 0, is_active, theme_sig)

    if not is_active:
        return (
            geometry_signature(sketch),
            False,
            theme_sig,
            frozenset(selection.selected),
        )

    return (
        geometry_signature(sketch),
        True,
        theme_sig,
        frozenset(selection.selected),
        selection.hover,
        frozenset(selection.highlight_curve_ids),
    )


def _tessellate_arcs(params, cyclic, mat):
    """World-space segment endpoints for *every* arc/circle, in one vectorized pass.

    ``params`` holds one ``_arc_params`` tuple per curve and ``cyclic`` the
    matching flags. Returns ``(pairs, nseg)``: an ``(S, 2, 3)`` array of
    per-segment endpoints, and how many of those segments each arc owns. Segments
    stay grouped by arc, so arc ``a`` owns one contiguous slice of ``pairs``.

    Tessellating arc by arc was the single biggest cost in ``build`` -- a Python
    loop doing one ``mat @ Vector(...)`` per point, ~58% of the call on a
    circle-heavy sketch. Vectorizing one arc at a time is *slower* (49 points is
    too few to amortize the numpy setup), so all arcs are flattened into one
    angle array and transformed with a single matmul instead.

    A cyclic curve emits ``segments`` points over ``[0, tau)`` and wraps, so a
    circle yields exactly ``ARC_SEGMENTS`` segments; the per-arc version closed
    the loop with a duplicate point and a zero-length segment.
    """
    n = len(params)
    p = np.asarray(params, dtype=np.float64)  # (n, 6)
    cx, cy, radius, start, sweep = (p[:, k] for k in range(5))
    nseg = p[:, 5].astype(np.intp)
    cyc = np.asarray(cyclic, dtype=bool)

    # An open arc needs its closing point; a cyclic one wraps to its first.
    npts = nseg + ~cyc
    pt_off = np.concatenate(([0], np.cumsum(npts)[:-1]))

    # Flatten every arc's points into one angle array: which arc each point
    # belongs to (pt_arc) and its position within that arc (pt_j).
    pt_arc = np.repeat(np.arange(n), npts)
    pt_j = np.arange(npts.sum()) - np.repeat(pt_off, npts)
    ang = start[pt_arc] + sweep[pt_arc] * pt_j / nseg[pt_arc]

    local = np.empty((len(pt_arc), 4))
    local[:, 0] = cx[pt_arc] + radius[pt_arc] * np.cos(ang)
    local[:, 1] = cy[pt_arc] + radius[pt_arc] * np.sin(ang)
    local[:, 2] = 0.0
    local[:, 3] = 1.0
    world = local @ np.asarray(mat, dtype=np.float64).T

    # Segments join consecutive points, wrapping to the first on a cyclic curve.
    seg_arc = np.repeat(np.arange(n), nseg)
    seg_off = np.concatenate(([0], np.cumsum(nseg)[:-1]))
    seg_j = np.arange(nseg.sum()) - np.repeat(seg_off, nseg)
    i0 = np.repeat(pt_off, nseg) + seg_j
    i1 = i0 + 1
    wrap = cyc[seg_arc] & (seg_j == nseg[seg_arc] - 1)
    i1[wrap] = np.repeat(pt_off, nseg)[wrap]

    pairs = world[np.stack((i0, i1), axis=1).ravel(), :3].reshape(-1, 2, 3)
    return pairs, nseg


def _emit_arcs(geo, params, cyclic, meta, mat):
    """Tessellate the collected arcs/circles and append them to ``geo``."""
    if not params:
        return
    pairs, nseg = _tessellate_arcs(params, cyclic, mat)

    # One trip out of numpy, flattened to bare endpoints: the very same vertex
    # lists are sliced into the colour buckets and referenced by ``segment_ids``,
    # so each vertex is allocated once. Keeping the (S, 2, 3) nesting would
    # allocate a wrapper list per segment on top of that, which at a few thousand
    # segments costs more than the tessellation itself.
    verts = pairs.reshape(-1, 3).tolist()
    counts = nseg.tolist()

    offset = len(geo.seg_verts)
    geo.seg_verts.extend(verts)
    for idx, (cid, construction, fixed) in enumerate(meta):
        width = counts[idx] * 2
        geo.seg_ranges.append((cid, construction, fixed, offset, offset + width))
        offset += width

    # ``segment_ids`` keeps picking's (curve_id, a, b) shape; repeat/chain expands
    # the per-arc ids without indexing ``meta`` once per segment.
    cids = chain.from_iterable(
        repeat(cid, counts[idx]) for idx, (cid, _c, _f) in enumerate(meta)
    )
    geo.segment_ids.extend(
        (cid, verts[i * 2], verts[i * 2 + 1]) for i, cid in enumerate(cids)
    )


class SketchGeometry:
    """A sketch's renderable geometry, independent of selection and theme.

    Everything here is a function of the curve data alone, so it survives hover
    and selection changes and is cached against ``geometry_signature``. Only
    ``colorize`` has to rerun when the selection changes, which is what lets the
    overlay and the picker share one extraction instead of building their own.

    ``seg_ranges`` carries ``(curve_id, construction, fixed, lo, hi)`` per segment
    curve, where ``lo``/``hi`` bound that curve's vertices in ``seg_verts``. Curves
    stay in order, so neighbouring curves of one colour merge into a single slice.
    """

    __slots__ = ("point_entries", "point_ids", "seg_verts", "seg_ranges", "segment_ids")

    def __init__(self):
        self.point_entries = []  # [(curve_id, pos, fixed), ...]
        self.point_ids = []  # [(curve_id, pos), ...]  (for picking)
        self.seg_verts = []  # flat LINES endpoints, 2 per segment
        self.seg_ranges = []  # [(curve_id, construction, fixed, lo, hi), ...]
        self.segment_ids = []  # [(curve_id, p0, p1), ...] (for picking)


class SketchRenderData:
    """Draw buckets extracted from one sketch's curve data."""

    __slots__ = ("point_buckets", "line_buckets", "point_ids", "segment_ids")

    def __init__(self):
        self.point_buckets = {}  # color(tuple) -> [(pos, size_factor), ...]
        self.line_buckets = {}  # (construction, color) -> [pos, pos, ...]
        self.point_ids = []  # [(curve_id, pos), ...]  (for picking)
        self.segment_ids = []  # [(curve_id, p0, p1), ...] (for picking)


# obj name -> (geometry_signature, SketchGeometry). Shared by the overlay and by
# picking: both used to run their own extraction, so every frame in which the
# geometry changed paid for it twice (issue #342).
_geometry_cache = {}

# Cache entries are keyed by object name, so a renamed or deleted sketch leaves
# one behind. Prune against the real datablocks once the cache grows past this.
_CACHE_PRUNE_AT = 64


def invalidate():
    """Drop the shared geometry cache (file load, unregister, theme reload)."""
    _geometry_cache.clear()


def _prune_cache():
    import bpy

    for name in [n for n in _geometry_cache if n not in bpy.data.objects]:
        del _geometry_cache[name]


def geometry(sketch) -> SketchGeometry:
    """Cached, selection-independent extraction for one sketch."""
    obj = sketch.target_object
    if obj is None:
        return SketchGeometry()

    name = obj.name
    sig = geometry_signature(sketch)
    cached = _geometry_cache.get(name)
    if cached is not None and cached[0] == sig:
        return cached[1]

    if len(_geometry_cache) >= _CACHE_PRUNE_AT:
        _prune_cache()
    geo = _extract_geometry(sketch)
    _geometry_cache[name] = (sig, geo)
    return geo


def colorize(geo: SketchGeometry, ts, is_active: bool) -> SketchRenderData:
    """Assign theme colours to a cached extraction and bucket it for drawing.

    The only part that depends on selection/hover/theme, so it is all that reruns
    on a mouse-move over unchanged geometry. Vertex lists are shared with ``geo``
    rather than copied -- nothing mutates them.
    """
    rd = SketchRenderData()
    rd.point_ids = geo.point_ids
    rd.segment_ids = geo.segment_ids

    # Selection/hover are transient runtime state (not persisted attributes).
    selected_set = set(selection.selected)
    hover = selection.hover
    highlighted = set(selection.highlight_curve_ids)

    for cid, pos, fixed in geo.point_entries:
        is_sel = cid in selected_set
        is_hov = cid == hover or cid in highlighted
        col = curve_color(ts, is_sel, is_hov, fixed, active=is_active)
        psize = POINT_SIZE_SELECTED if is_sel else (POINT_SIZE_HOVER if is_hov else 1.0)
        rd.point_buckets.setdefault(tuple(col), []).append((pos, psize))

    # Merge runs of consecutive curves that land in the same bucket into one slice
    # copy. With nothing selected the whole sketch is one run, so this is a single
    # extend instead of one per curve.
    key = None
    run_lo = run_hi = 0
    for cid, construction, fixed, lo, hi in geo.seg_ranges:
        is_sel = cid in selected_set
        is_hov = cid == hover or cid in highlighted
        col = curve_color(ts, is_sel, is_hov, fixed, active=is_active)
        entry = (construction, tuple(col))
        if entry == key and lo == run_hi:
            run_hi = hi
            continue
        if key is not None:
            rd.line_buckets.setdefault(key, []).extend(geo.seg_verts[run_lo:run_hi])
        key, run_lo, run_hi = entry, lo, hi
    if key is not None:
        rd.line_buckets.setdefault(key, []).extend(geo.seg_verts[run_lo:run_hi])

    return rd


def build(sketch, ts, is_active) -> SketchRenderData:
    """Extract ``SketchRenderData`` for one sketch (no GPU work)."""
    return colorize(geometry(sketch), ts, is_active)


def _extract_geometry(sketch) -> SketchGeometry:
    """Pull a sketch's curve data into a ``SketchGeometry`` (no colour work)."""
    geo = SketchGeometry()
    cd = sketch.data
    n_curves = len(cd.curves)
    if n_curves == 0:
        return geo

    type_attr = cd.attributes.get("sketch_type")
    if type_attr is None or not has_uuid_field(cd, "curve_id"):
        return geo

    con = _bulk_bool(cd.attributes.get("construction"), n_curves)
    fix = _bulk_bool(cd.attributes.get("fixed"), n_curves)
    vis = (
        _bulk_bool(cd.attributes.get("visible"), n_curves)
        if cd.attributes.get("visible")
        else np.ones(n_curves, bool)
    )
    cyc = _bulk_bool(cd.attributes.get("cyclic"), n_curves)
    types = _bulk_int(type_attr, n_curves)
    cids = read_curve_id_list(cd)

    mat = _world_matrix(sketch)
    cp_present = has_uuid_field(cd, "center_point_id")

    # Endpoint ids come from the cached bulk lists, not a per-curve get_uuid
    # (2 attribute lookups plus a hex conversion each) inside the loop.
    has_arcs = cp_present and bool(
        np.isin(types, (SketchCurveType.ARC, SketchCurveType.CIRCLE)).any()
    )
    if has_arcs:
        cp_ids = read_uuid_list(cd, "center_point_id")
        sp_ids = read_uuid_list(cd, "start_point_id")
        ep_ids = read_uuid_list(cd, "end_point_id")

    # Arcs/circles are only *measured* in the loop; they are tessellated together
    # afterwards, which is far cheaper than one Python loop per arc.
    arc_params, arc_cyclic, arc_meta = [], [], []

    for i in range(n_curves):
        if not vis[i]:
            continue
        ctype = types[i]
        cid = cids[i]
        curve_slice = cd.curves[i]

        if ctype == SketchCurveType.POINT:
            pos = (mat @ Vector(cd.points[curve_slice.points[0].index].position))[:]
            geo.point_entries.append((cid, pos, bool(fix[i])))
            geo.point_ids.append((cid, pos))

        elif ctype == SketchCurveType.LINE and curve_slice.points_length >= 2:
            first = curve_slice.points[0].index
            p1 = (mat @ Vector(cd.points[first].position))[:]
            p2 = (mat @ Vector(cd.points[first + 1].position))[:]
            lo = len(geo.seg_verts)
            geo.seg_verts += [p1, p2]
            geo.seg_ranges.append((cid, bool(con[i]), bool(fix[i]), lo, lo + 2))
            geo.segment_ids.append((cid, p1, p2))

        elif ctype in (SketchCurveType.ARC, SketchCurveType.CIRCLE) and has_arcs:
            params = _arc_params(
                sketch, cd, i, curve_slice, bool(cyc[i]), cp_ids, sp_ids, ep_ids
            )
            if params is not None:
                arc_params.append(params)
                arc_cyclic.append(bool(cyc[i]))
                arc_meta.append((cid, bool(con[i]), bool(fix[i])))

    _emit_arcs(geo, arc_params, arc_cyclic, arc_meta, mat)
    return geo


def _arc_params(sketch, cd, curve_idx, curve_slice, is_cyclic, cp_ids, sp_ids, ep_ids):
    """Measure one arc/circle, or ``None`` when its defining points are missing.

    Returns ``(center_x, center_y, radius, start_angle, sweep, segments)`` in the
    sketch's local 2D frame. Only the measuring happens per curve; the points
    themselves come from ``_tessellate_arcs``, which does every arc at once.
    """
    _, _, cp_slice = get_curve_data(sketch, cp_ids[curve_idx])
    if not cp_slice:
        return None
    center = Vector(cd.points[cp_slice.points[0].index].position[:2])

    if is_cyclic:
        edge = Vector(cd.points[curve_slice.points[0].index].position[:2])
        return (center.x, center.y, (edge - center).length, 0.0, math.tau, ARC_SEGMENTS)

    sp_cid, ep_cid = sp_ids[curve_idx], ep_ids[curve_idx]
    _, _, s_slice = get_curve_data(sketch, sp_cid) if sp_cid else (None, None, None)
    _, _, e_slice = get_curve_data(sketch, ep_cid) if ep_cid else (None, None, None)
    if not (s_slice and e_slice):
        return None

    start = Vector(cd.points[s_slice.points[0].index].position[:2])
    end = Vector(cd.points[e_slice.points[0].index].position[:2])
    s_angle = math.atan2((start - center).y, (start - center).x)
    arc_angle = range_2pi(math.atan2((end - center).y, (end - center).x) - s_angle)
    segments = max(int(arc_angle / math.tau * ARC_SEGMENTS), 4)
    return (center.x, center.y, (start - center).length, s_angle, arc_angle, segments)
