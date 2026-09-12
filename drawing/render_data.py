"""Extract a sketch's renderable geometry into flat draw buckets.

Pure data — no GPU calls — so it can be unit-tested headless. Produces:

- ``point_buckets``: ``color -> (centres (K, 3), size factors (K,))``
- ``line_buckets``:  ``(construction, color) -> [(M, 2, 3) chunk, ...]``

Coordinates stay in numpy from tessellation all the way to ``batch_for_shader``
and to the picker's projection, which both take arrays directly. Materialising
them as Python tuples in between was the bulk of the extraction cost once the
tessellation itself was vectorized (issue #342).

``overlay_signature`` is a cheap hash of everything that affects the drawing, so
the overlay can skip rebuilding batches when nothing changed.
"""

import math

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


def _emit_arcs(geo_parts, params, cyclic, meta, mat):
    """Tessellate the collected arcs/circles into ``geo_parts``' array lists."""
    if not params:
        return
    pairs, nseg = _tessellate_arcs(params, cyclic, mat)
    geo_parts["seg_co"].append(pairs.astype(np.float32, copy=False))
    geo_parts["seg_counts"].append(nseg)
    for cid, construction, fixed in meta:
        geo_parts["seg_cids"].append(cid)
        geo_parts["seg_construction"].append(construction)
        geo_parts["seg_fixed"].append(fixed)


_EMPTY_CO = np.zeros((0, 3), dtype=np.float32)
_EMPTY_SEG = np.zeros((0, 2, 3), dtype=np.float32)
_EMPTY_BOOL = np.zeros(0, dtype=bool)
_EMPTY_IDX = np.zeros(0, dtype=np.intp)


class SketchGeometry:
    """A sketch's renderable geometry, independent of selection and theme.

    Everything here is a function of the curve data alone, so it survives hover
    and selection changes and is cached against ``geometry_signature``. Only
    ``colorize`` has to rerun when the selection changes, which is what lets the
    overlay and the picker share one extraction instead of building their own.

    Coordinates are numpy arrays, not Python tuples: the GPU batches and the
    picker's screen projection both consume arrays, so materialising tuples here
    only to rebuild arrays downstream was the bulk of the extraction cost.

    Segments are grouped by curve: curve ``c`` owns rows
    ``seg_offsets[c]:seg_offsets[c + 1]`` of ``seg_co``, and ``seg_owner`` maps a
    row back to ``c``. Keeping identity per *curve* rather than per *segment* is
    what removes the one-string-per-segment bookkeeping (a circle has 48).
    """

    __slots__ = (
        "point_cids",
        "point_co",
        "point_fixed",
        "seg_cids",
        "seg_construction",
        "seg_fixed",
        "seg_offsets",
        "seg_co",
        "seg_owner",
    )

    def __init__(self):
        self.point_cids = []  # [curve_id, ...] one per point curve
        self.point_co = _EMPTY_CO  # (P, 3) float32 world positions
        self.point_fixed = _EMPTY_BOOL  # (P,) bool
        self.seg_cids = []  # [curve_id, ...] one per segment curve
        self.seg_construction = _EMPTY_BOOL  # (C,) bool
        self.seg_fixed = _EMPTY_BOOL  # (C,) bool
        self.seg_offsets = _EMPTY_IDX  # (C + 1,) row bounds into seg_co
        self.seg_co = _EMPTY_SEG  # (M, 2, 3) float32 world endpoints
        self.seg_owner = _EMPTY_IDX  # (M,) -> index into seg_cids


class SketchRenderData:
    """Draw buckets extracted from one sketch's curve data."""

    __slots__ = ("point_buckets", "line_buckets")

    def __init__(self):
        self.point_buckets = {}  # color -> (centres (K, 3), size factors (K,))
        self.line_buckets = {}  # (construction, color) -> [(M, 2, 3) chunk, ...]


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


def _state_flags(cids, selected_set, hover, highlighted):
    """Per-curve ``(selected, hovered)`` flags for a list of curve ids."""
    sel = [cid in selected_set for cid in cids]
    hov = [cid == hover or cid in highlighted for cid in cids]
    return sel, hov


def colorize(geo: SketchGeometry, ts, is_active: bool) -> SketchRenderData:
    """Assign theme colours to a cached extraction and bucket it for drawing.

    The only part that depends on selection/hover/theme, so it is all that reruns
    on a mouse-move over unchanged geometry. Buckets are views into ``geo``'s
    arrays rather than copies -- nothing mutates them.
    """
    rd = SketchRenderData()

    # Selection/hover are transient runtime state (not persisted attributes).
    selected_set = set(selection.selected)
    hover = selection.hover
    highlighted = set(selection.highlight_curve_ids)

    if geo.point_cids:
        sel, hov = _state_flags(geo.point_cids, selected_set, hover, highlighted)
        fixed = geo.point_fixed
        by_color = {}
        for i in range(len(geo.point_cids)):
            col = curve_color(ts, sel[i], hov[i], bool(fixed[i]), active=is_active)
            psize = (
                POINT_SIZE_SELECTED if sel[i] else (POINT_SIZE_HOVER if hov[i] else 1.0)
            )
            by_color.setdefault(tuple(col), ([], []))
            rows, sizes = by_color[tuple(col)]
            rows.append(i)
            sizes.append(psize)
        for col, (rows, sizes) in by_color.items():
            rd.point_buckets[col] = (
                geo.point_co[rows],
                np.asarray(sizes, dtype=np.float32),
            )

    if geo.seg_cids:
        sel, hov = _state_flags(geo.seg_cids, selected_set, hover, highlighted)
        con = geo.seg_construction
        fixed = geo.seg_fixed
        offsets = geo.seg_offsets
        # Merge runs of consecutive curves that land in the same bucket into one
        # slice. With nothing selected the whole sketch is one run, so a bucket
        # holds a single view over the full array.
        key = None
        run_start = 0
        for c in range(len(geo.seg_cids)):
            col = curve_color(ts, sel[c], hov[c], bool(fixed[c]), active=is_active)
            entry = (bool(con[c]), tuple(col))
            if entry == key:
                continue
            if key is not None:
                rd.line_buckets.setdefault(key, []).append(
                    geo.seg_co[offsets[run_start] : offsets[c]]
                )
            key, run_start = entry, c
        if key is not None:
            rd.line_buckets.setdefault(key, []).append(
                geo.seg_co[offsets[run_start] : offsets[-1]]
            )

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

    point_rows, point_fixed = [], []
    # Lines contribute one segment each and are collected locally; arcs are only
    # *measured* here and tessellated together afterwards.
    parts = {
        "seg_co": [],
        "seg_counts": [],
        "seg_cids": [],
        "seg_construction": [],
        "seg_fixed": [],
    }
    line_co = []
    arc_params, arc_cyclic, arc_meta = [], [], []

    for i in range(n_curves):
        if not vis[i]:
            continue
        ctype = types[i]
        cid = cids[i]
        curve_slice = cd.curves[i]

        if ctype == SketchCurveType.POINT:
            geo.point_cids.append(cid)
            point_rows.append(cd.points[curve_slice.points[0].index].position[:])
            point_fixed.append(bool(fix[i]))

        elif ctype == SketchCurveType.LINE and curve_slice.points_length >= 2:
            first = curve_slice.points[0].index
            line_co.append(
                (cd.points[first].position[:], cd.points[first + 1].position[:])
            )
            parts["seg_cids"].append(cid)
            parts["seg_construction"].append(bool(con[i]))
            parts["seg_fixed"].append(bool(fix[i]))

        elif ctype in (SketchCurveType.ARC, SketchCurveType.CIRCLE) and has_arcs:
            params = _arc_params(
                sketch, cd, i, curve_slice, bool(cyc[i]), cp_ids, sp_ids, ep_ids
            )
            if params is not None:
                arc_params.append(params)
                arc_cyclic.append(bool(cyc[i]))
                arc_meta.append((cid, bool(con[i]), bool(fix[i])))

    # Lines first (one segment each), then the tessellated arcs, so each curve
    # still owns a contiguous run of rows.
    if line_co:
        parts["seg_co"].insert(0, _to_world(np.asarray(line_co, dtype=np.float64), mat))
        parts["seg_counts"].insert(0, np.ones(len(line_co), dtype=np.intp))
    _emit_arcs(parts, arc_params, arc_cyclic, arc_meta, mat)

    if point_rows:
        geo.point_co = _to_world(np.asarray(point_rows, dtype=np.float64), mat)
        geo.point_fixed = np.asarray(point_fixed, dtype=bool)

    if parts["seg_cids"]:
        geo.seg_cids = parts["seg_cids"]
        geo.seg_construction = np.asarray(parts["seg_construction"], dtype=bool)
        geo.seg_fixed = np.asarray(parts["seg_fixed"], dtype=bool)
        geo.seg_co = np.concatenate(parts["seg_co"])
        counts = np.concatenate(parts["seg_counts"])
        geo.seg_offsets = np.concatenate(([0], np.cumsum(counts))).astype(np.intp)
        geo.seg_owner = np.repeat(np.arange(len(counts), dtype=np.intp), counts)

    return geo


def _to_world(local, mat):
    """Transform an ``(..., 3)`` array of sketch-local points into world space."""
    shape = local.shape
    flat = local.reshape(-1, 3)
    homogeneous = np.empty((len(flat), 4), dtype=np.float64)
    homogeneous[:, :3] = flat
    homogeneous[:, 3] = 1.0
    world = homogeneous @ np.asarray(mat, dtype=np.float64).T
    return world[:, :3].reshape(shape).astype(np.float32, copy=False)


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
