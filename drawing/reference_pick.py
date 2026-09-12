"""Screen-space picking of *reference* curve objects (not the active sketch).

Phase 1 of per-element curve hover/pick: extract a curve object's pickable
geometry (points and tessellated segments) in world space, then rank it under
the cursor with the same screen-space test the active-sketch picker uses
(``picking.rank_hits``).

Supported sources:
- CAD Sketcher sketches (a Curves object carrying ``sketch_type``/``curve_id``):
  reuse the sketch extraction, so elements are keyed by ``curve_id`` and
  arcs/circles are already tessellated into pickable segments.
- Raw Blender Curves objects: control points and the polyline between them,
  keyed by index.

Legacy ``Curve`` (bezier/nurbs) objects are not handled yet; they return empty.
"""

import numpy as np

from ..utilities.curve_data import has_uuid_field
from . import picking


def _is_sketch(curve_data) -> bool:
    """Whether a Curves datablock is a CAD Sketcher sketch (has our attributes)."""
    return (
        curve_data.attributes.get("sketch_type") is not None
        and has_uuid_field(curve_data, "curve_id") is not None
    )


def _sketch_geometry(obj) -> picking.PickSet:
    """Pickable geometry of a sketch, keyed by ``curve_id``.

    Reuses the shared, cached extraction, which already projects points and
    tessellates lines/arcs/circles. Colours are irrelevant here, so this skips the
    colour pass -- reference picking walks every visible curve object, so it would
    otherwise pay for it once per object per mouse-move.
    """
    from ..model.sketch_ref import Sketch
    from . import render_data

    geo = render_data.geometry(Sketch(obj))
    return picking.PickSet(
        geo.point_cids, geo.point_co, geo.seg_cids, geo.seg_co, geo.seg_owner
    )


def _raw_curves_geometry(obj) -> picking.PickSet:
    """Pickable geometry of a raw Curves object, keyed by index.

    Each control point is a pickable point; each span between consecutive points
    of a curve is a pickable segment. No arc concept exists on a raw Curves
    object, so its curves are treated as polylines.
    """
    data = obj.data
    n_points = len(data.points)
    if n_points == 0:
        return picking.EMPTY_PICKSET

    local = np.empty(n_points * 3, dtype=np.float32)
    data.points.foreach_get("position", local)
    world = _to_world(local.reshape(-1, 3), obj.matrix_world)

    point_keys, seg_keys, spans = [], [], []
    for ci, curve in enumerate(data.curves):
        n = curve.points_length
        if n == 0:
            continue
        first = curve.points[0].index
        for k in range(n):
            point_keys.append(("point", first + k))
        for k in range(n - 1):
            seg_keys.append(("seg", ci, k))
            spans.append((first + k, first + k + 1))

    point_co = (
        world[[i for _t, i in point_keys]]
        if point_keys
        else picking.EMPTY_PICKSET.point_co
    )
    if spans:
        idx = np.asarray(spans, dtype=np.intp)
        seg_co = world[idx.ravel()].reshape(-1, 2, 3)
        seg_owner = np.arange(len(spans), dtype=np.intp)
    else:
        seg_co = picking.EMPTY_PICKSET.seg_co
        seg_owner = picking.EMPTY_PICKSET.seg_owner
    return picking.PickSet(point_keys, point_co, seg_keys, seg_co, seg_owner)


def _to_world(local, mat):
    """Transform an ``(N, 3)`` array of local points into world space."""
    homogeneous = np.empty((len(local), 4), dtype=np.float64)
    homogeneous[:, :3] = local
    homogeneous[:, 3] = 1.0
    world = homogeneous @ np.asarray(mat, dtype=np.float64).T
    return world[:, :3].astype(np.float32, copy=False)


def extract_pickable_geometry(obj) -> picking.PickSet:
    """Return a curve object's pickable geometry in world space.

    Keys identify the source element: a sketch's ``curve_id`` string, or an
    index-based tuple for a raw Curves object. Non-Curves or legacy ``Curve``
    objects return an empty set (legacy bezier/nurbs support is a later slice).
    """
    if obj is None or obj.type != "CURVES" or obj.data is None:
        return picking.EMPTY_PICKSET
    if _is_sketch(obj.data):
        return _sketch_geometry(obj)
    return _raw_curves_geometry(obj)


def pick_object_ranked(obj, context, coords):
    """Keys of ``obj``'s elements under ``coords``, nearest first (points first)."""
    return picking.rank_hits(extract_pickable_geometry(obj), context, coords)


def pick_reference_element(context, coords, exclude=None):
    """Nearest ``(object, element_key)`` across visible curve objects under coords.

    Merges every visible curve object's pickable geometry into one screen-space
    ranking so the closest element wins regardless of which object it belongs to.
    ``exclude`` skips an object (e.g. the active sketch, to avoid self-reference).
    """
    objs = {}
    point_keys, point_co = [], []
    seg_keys, seg_co, seg_owner = [], [], []
    for ob in context.visible_objects:
        if ob.type != "CURVES" or ob == exclude:
            continue
        pick = extract_pickable_geometry(ob)
        if not len(pick.point_co) and not len(pick.seg_co):
            continue
        objs[ob.name] = ob
        # Keys are namespaced per object, and the owner indices shift by however
        # many curves were merged already. Both are per-curve, not per-segment.
        point_keys += [(ob.name, key) for key in pick.point_keys]
        point_co.append(pick.point_co)
        seg_owner.append(pick.seg_owner + len(seg_keys))
        seg_keys += [(ob.name, key) for key in pick.seg_keys]
        seg_co.append(pick.seg_co)

    if not objs:
        return None
    merged = picking.PickSet(
        point_keys,
        np.concatenate(point_co) if point_co else picking.EMPTY_PICKSET.point_co,
        seg_keys,
        np.concatenate(seg_co) if seg_co else picking.EMPTY_PICKSET.seg_co,
        np.concatenate(seg_owner) if seg_owner else picking.EMPTY_PICKSET.seg_owner,
    )

    ranked = picking.rank_hits(merged, context, coords)
    if not ranked:
        return None
    obj_name, key = ranked[0]
    return objs[obj_name], key


def element_geometry(obj, key):
    """World-space ``(points, segments)`` of just element ``key`` of ``obj``.

    Used to highlight one hovered element: a point returns its position, a line
    its single segment, an arc/circle its tessellated segments. Returns plain
    tuples -- this is one element, and the hover draw code wants sequences.
    """
    pick = extract_pickable_geometry(obj)
    points = [
        tuple(pick.point_co[i]) for i, k in enumerate(pick.point_keys) if k == key
    ]
    segments = []
    if key in pick.seg_keys:
        rows = pick.seg_co[pick.seg_owner == pick.seg_keys.index(key)]
        segments = [(tuple(a), tuple(b)) for a, b in rows]
    return points, segments
