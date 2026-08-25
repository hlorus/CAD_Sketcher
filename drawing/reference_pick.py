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

from mathutils import Vector

from ..utilities.curve_data import has_uuid_field
from . import picking


def _is_sketch(curve_data) -> bool:
    """Whether a Curves datablock is a CAD Sketcher sketch (has our attributes)."""
    return (
        curve_data.attributes.get("sketch_type") is not None
        and has_uuid_field(curve_data, "curve_id") is not None
    )


def _sketch_geometry(obj):
    """Pickable points/segments of a sketch, keyed by ``curve_id``.

    Reuses ``render_data.build``, which already projects points and tessellates
    lines/arcs/circles into ``point_ids`` / ``segment_ids`` for picking.
    """
    from ..model.sketch_ref import Sketch
    from ..utilities.preferences import get_prefs
    from . import render_data

    sketch = Sketch(obj)
    ts = get_prefs().theme_settings.entity
    rd = render_data.build(sketch, ts, is_active=False)
    return rd.point_ids, rd.segment_ids


def _raw_curves_geometry(obj):
    """Pickable points/segments of a raw Curves object, keyed by index.

    Each control point is a pickable point; each span between consecutive points
    of a curve is a pickable segment. No arc concept exists on a raw Curves
    object, so its curves are treated as polylines.
    """
    data = obj.data
    mat = obj.matrix_world
    points, segments = [], []
    for ci, curve in enumerate(data.curves):
        n = curve.points_length
        if n == 0:
            continue
        first = curve.points[0].index
        world = [(mat @ Vector(data.points[first + k].position))[:] for k in range(n)]
        for k in range(n):
            points.append((("point", first + k), world[k]))
        for k in range(n - 1):
            segments.append((("seg", ci, k), world[k], world[k + 1]))
    return points, segments


def extract_pickable_geometry(obj):
    """Return ``(points, segments)`` of a curve object in world space.

    ``points``:   ``[(key, world_pos), ...]``
    ``segments``: ``[(key, world_a, world_b), ...]`` (arcs/circles tessellated)

    ``key`` identifies the source element: a sketch's ``curve_id`` string, or an
    index-based tuple for a raw Curves object. Non-Curves or legacy ``Curve``
    objects return empty (legacy bezier/nurbs support is a later slice).
    """
    if obj is None or obj.type != "CURVES" or obj.data is None:
        return [], []
    if _is_sketch(obj.data):
        return _sketch_geometry(obj)
    return _raw_curves_geometry(obj)


def pick_object_ranked(obj, context, coords):
    """Keys of ``obj``'s elements under ``coords``, nearest first (points first)."""
    points, segments = extract_pickable_geometry(obj)
    return picking.rank_hits(points, segments, context, coords)


def pick_reference_element(context, coords, exclude=None):
    """Nearest ``(object, element_key)`` across visible curve objects under coords.

    Merges every visible curve object's pickable geometry into one screen-space
    ranking so the closest element wins regardless of which object it belongs to.
    ``exclude`` skips an object (e.g. the active sketch, to avoid self-reference).
    """
    objs = {}
    point_items, seg_items = [], []
    for ob in context.visible_objects:
        if ob.type != "CURVES" or ob == exclude:
            continue
        pts, segs = extract_pickable_geometry(ob)
        if not pts and not segs:
            continue
        objs[ob.name] = ob
        point_items += [((ob.name, key), pos) for key, pos in pts]
        seg_items += [((ob.name, key), a, b) for key, a, b in segs]

    ranked = picking.rank_hits(point_items, seg_items, context, coords)
    if not ranked:
        return None
    obj_name, key = ranked[0]
    return objs[obj_name], key


def element_geometry(obj, key):
    """World-space ``(points, segments)`` of just element ``key`` of ``obj``.

    Used to highlight one hovered element: a point returns its position, a line
    its single segment, an arc/circle its tessellated segments.
    """
    pts, segs = extract_pickable_geometry(obj)
    points = [pos for k, pos in pts if k == key]
    segments = [(a, b) for k, a, b in segs if k == key]
    return points, segments
