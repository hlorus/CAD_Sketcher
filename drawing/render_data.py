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

import numpy as np
from mathutils import Vector

from ..model.constants import SketchCurveType
from ..utilities.curve_data import (
    get_curve_data,
    get_uuid,
    has_uuid_field,
    read_curve_id_list,
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
    the object's world matrix, plus counts. Excludes transient selection/hover --
    those change colours (the overlay), not the projected points/segments
    (picking), so picking can cache its extraction against this and skip
    rebuilding while the cursor just hovers.

    ``build`` bakes ``matrix_world`` into every point/segment position, so it
    must be part of the fingerprint: a sketch on a workplane whose transform
    moves (or settles as the depsgraph first evaluates a parented sketch) changes
    the world positions without touching any local attribute -- omitting it left
    the pick/overlay cache serving stale world coordinates.
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
    parts.append(
        np.array(sketch.target_object.matrix_world, dtype=np.float32).tobytes()
    )
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


def _arc_points(center, radius, start_angle, arc_angle, segments, mat):
    pts = []
    for i in range(segments + 1):
        a = start_angle + arc_angle * i / segments
        pts.append(
            (
                mat
                @ Vector(
                    (
                        center.x + radius * math.cos(a),
                        center.y + radius * math.sin(a),
                        0,
                    )
                )
            )[:]
        )
    return pts


class SketchRenderData:
    """Draw buckets extracted from one sketch's curve data."""

    __slots__ = ("point_buckets", "line_buckets", "point_ids", "segment_ids")

    def __init__(self):
        self.point_buckets = {}  # color(tuple) -> [(pos, size_factor), ...]
        self.line_buckets = {}  # (construction, color) -> [pos, pos, ...]
        self.point_ids = []  # [(curve_id, pos), ...]  (for picking)
        self.segment_ids = []  # [(curve_id, p0, p1), ...] (for picking)

    def _line_bucket(self, construction, col):
        return self.line_buckets.setdefault((construction, tuple(col)), [])


def build(sketch, ts, is_active):
    """Extract ``SketchRenderData`` for one sketch (no GPU work)."""
    rd = SketchRenderData()
    cd = sketch.data
    n_curves = len(cd.curves)
    if n_curves == 0:
        return rd

    type_attr = cd.attributes.get("sketch_type")
    if type_attr is None or not has_uuid_field(cd, "curve_id"):
        return rd

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

    # Selection/hover are transient runtime state (not persisted attributes).
    selected_set = set(selection.selected)
    hover = selection.hover
    highlighted = set(selection.highlight_curve_ids)

    mat = sketch.target_object.matrix_world
    cp_present = has_uuid_field(cd, "center_point_id")

    for i in range(n_curves):
        if not vis[i]:
            continue
        ctype = types[i]
        cid = cids[i]
        is_sel = cid in selected_set
        is_hov = cid == hover or cid in highlighted
        col = curve_color(ts, is_sel, is_hov, bool(fix[i]), active=is_active)
        curve_slice = cd.curves[i]

        if ctype == SketchCurveType.POINT:
            pos = (mat @ Vector(cd.points[curve_slice.points[0].index].position))[:]
            psize = (
                POINT_SIZE_SELECTED if is_sel else (POINT_SIZE_HOVER if is_hov else 1.0)
            )
            rd.point_buckets.setdefault(tuple(col), []).append((pos, psize))
            rd.point_ids.append((cid, pos))

        elif ctype == SketchCurveType.LINE and curve_slice.points_length >= 2:
            first = curve_slice.points[0].index
            p1 = (mat @ Vector(cd.points[first].position))[:]
            p2 = (mat @ Vector(cd.points[first + 1].position))[:]
            bucket = rd._line_bucket(bool(con[i]), col)
            bucket += [p1, p2]
            rd.segment_ids.append((cid, p1, p2))

        elif ctype in (SketchCurveType.ARC, SketchCurveType.CIRCLE) and cp_present:
            arc_pts = _arc_points_for_curve(
                sketch, cd, i, curve_slice, bool(cyc[i]), mat
            )
            if arc_pts and len(arc_pts) >= 2:
                bucket = rd._line_bucket(bool(con[i]), col)
                for j in range(len(arc_pts) - 1):
                    bucket += [arc_pts[j], arc_pts[j + 1]]
                    rd.segment_ids.append((cid, arc_pts[j], arc_pts[j + 1]))
                if cyc[i]:
                    bucket += [arc_pts[-1], arc_pts[0]]
                    rd.segment_ids.append((cid, arc_pts[-1], arc_pts[0]))

    return rd


def _arc_points_for_curve(sketch, cd, curve_idx, curve_slice, is_cyclic, mat):
    cp_cid = get_uuid(cd, "center_point_id", curve_idx)
    _, _, cp_slice = get_curve_data(sketch, cp_cid)
    if not cp_slice:
        return None
    center = Vector(cd.points[cp_slice.points[0].index].position[:2])

    if is_cyclic:
        edge = Vector(cd.points[curve_slice.points[0].index].position[:2])
        radius = (edge - center).length
        return _arc_points(center, radius, 0, math.tau, ARC_SEGMENTS, mat)

    sp_cid = get_uuid(cd, "start_point_id", curve_idx)
    ep_cid = get_uuid(cd, "end_point_id", curve_idx)
    _, _, s_slice = get_curve_data(sketch, sp_cid) if sp_cid else (None, None, None)
    _, _, e_slice = get_curve_data(sketch, ep_cid) if ep_cid else (None, None, None)
    if not (s_slice and e_slice):
        return None

    start = Vector(cd.points[s_slice.points[0].index].position[:2])
    end = Vector(cd.points[e_slice.points[0].index].position[:2])
    radius = (start - center).length
    s_angle = math.atan2((start - center).y, (start - center).x)
    arc_angle = range_2pi(math.atan2((end - center).y, (end - center).x) - s_angle)
    segments = max(int(arc_angle / math.tau * ARC_SEGMENTS), 4)
    return _arc_points(center, radius, s_angle, arc_angle, segments, mat)
