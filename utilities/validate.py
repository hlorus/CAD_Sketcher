"""Self-heal validation for native sketch curve data.

Curve identity lives in INT attributes that survive Blender's curve removal and
re-index correctly, so a native Edit-Mode *delete* no longer corrupts a sketch.
Only two situations still need repair when a built-in tool touches the data:

- a natively-added curve has no id (all-zero) -> mint one,
- a natively-duplicated curve carries a copied id -> mint a fresh id for the copy.

Minting is safe here because it only ever happens to genuinely new geometry
(the original of a duplicate keeps its id). Constraints that reference a curve
which no longer exists in any sketch are then pruned. Position-only edits pass
straight through — the solver treats them as tweaks on the next solve.
"""

import logging
import math
import secrets

from ..model.constants import SketchCurveType
from .curve_data import (
    UUID_FIELDS,
    _get_original_data,
    default_curve_name,
    ensure_standard_attributes,
    get_uuid,
    has_uuid_field,
    invalidate_curve_id_cache,
    new_uuid,
    remove_native_curve_by_id,
    set_uuid,
)

logger = logging.getLogger(__name__)

# Start/end points closer than this (sketch units) make an arc zero-sweep.
_DEGEN_ARC_EPS = 1e-4

# The origin point sits exactly at the workplane's local (0, 0).
_ORIGIN_EPS = 1e-6

# object.name -> signature of the last validated state
_validated = {}

# Attributes the model depends on (the identity sub-attributes plus type/name).
_REQUIRED_ATTRS = tuple(
    f".{field}_{k}" for field in UUID_FIELDS for k in range(4)
) + ("sketch_type", "name")


def reset_cache():
    """Drop the validation signature cache (e.g. on file load)."""
    _validated.clear()


def _signature(curve_data):
    """Cheap fingerprint of the state that matters to validation."""
    attrs = curve_data.attributes
    n = len(curve_data.curves)
    ends = ()
    if has_uuid_field(curve_data, "curve_id") and n:
        ends = (get_uuid(curve_data, "curve_id", 0), get_uuid(curve_data, "curve_id", n - 1))
    return (
        n,
        len(curve_data.points),
        tuple(attrs.get(name) is not None for name in _REQUIRED_ATTRS),
        ends,
    )


def _other_sketch_ids(obj):
    """Curve ids belonging to every *other* sketch (cross-sketch references)."""
    import bpy

    from ..model.sketch_ref import get_sketches

    ids = set()
    scene = bpy.context.scene
    if not scene:
        return ids
    for sk in get_sketches(scene):
        o = sk.target_object
        if o is obj or not o.data or not has_uuid_field(o.data, "curve_id"):
            continue
        for i in range(len(o.data.curves)):
            v = get_uuid(o.data, "curve_id", i)
            if v:
                ids.add(v)
    return ids


def _prune_dangling_constraints(sketch, valid_ids):
    """Remove constraints referencing a curve_id that exists in no sketch."""
    valid_ids = valid_ids | _other_sketch_ids(sketch.target_object)
    try:
        constraints = sketch.constraints
    except Exception:
        return False
    removed = False
    for coll in constraints.get_lists():
        for i in reversed(range(len(coll))):
            c = coll[i]
            refs = (
                getattr(c, "curve_id_1", ""),
                getattr(c, "curve_id_2", ""),
                getattr(c, "curve_id_3", ""),
            )
            if any(r and r not in valid_ids for r in refs):
                coll.remove(i)
                removed = True
    return removed


def _remove_orphan_points(sketch, candidate_ids):
    """Remove point curves in ``candidate_ids`` no segment still references."""
    cd = sketch.target_object.data
    type_attr = cd.attributes.get("sketch_type")
    if not type_attr:
        return
    referenced = set()
    for i in range(len(cd.curves)):
        if type_attr.data[i].value == SketchCurveType.POINT:
            continue
        for field in ("start_point_id", "end_point_id", "center_point_id"):
            referenced.add(get_uuid(cd, field, i))
    for cid in candidate_ids:
        if cid and cid not in referenced:
            remove_native_curve_by_id(sketch, cid)


def _ensure_origin(sketch, cd):
    """Guarantee the sketch keeps its protected origin point.

    A native Edit-Mode delete can remove the origin like any other point.
    Restore it by adopting an existing fixed point at local (0, 0) — which also
    migrates sketches created before origins were tagged — or minting a fresh
    one when none is present. Returns True if the data was changed.
    """
    type_attr = cd.attributes.get("sketch_type")
    if type_attr is None:
        return False

    origin_attr = cd.attributes.get("is_origin")
    if origin_attr is None:
        ensure_standard_attributes(cd)
        origin_attr = cd.attributes.get("is_origin")
        if origin_attr is None:
            return False

    # Already flagged — nothing to do.
    for i in range(len(cd.curves)):
        if origin_attr.data[i].value:
            return False

    # Migration/restore: adopt a pre-existing fixed point at local (0, 0).
    fixed_attr = cd.attributes.get("fixed")
    for i in range(len(cd.curves)):
        if type_attr.data[i].value != SketchCurveType.POINT:
            continue
        pos = cd.points[cd.curves[i].points[0].index].position
        at_origin = math.hypot(pos[0], pos[1]) < _ORIGIN_EPS
        is_fixed = fixed_attr is None or fixed_attr.data[i].value
        if at_origin and is_fixed:
            origin_attr.data[i].value = True
            return True

    # None to adopt — recreate the origin from scratch.
    from ..model.curve_ref import PointRef

    PointRef.create(sketch, (0.0, 0.0), fixed=True, is_origin=True)
    return True


def validate_sketch(sketch):
    """Repair invariants on one sketch's curve data.

    Returns True if anything was changed (caller may want to re-solve).
    """
    obj = sketch.target_object
    if not obj or not obj.data:
        return False
    # Don't fight edits mid-Edit/Sculpt; a depsgraph update fires on mode exit.
    if getattr(obj, "mode", "OBJECT") != "OBJECT":
        return False

    cd = _get_original_data(sketch)
    if cd is None:
        return False

    sig = _signature(cd)
    if _validated.get(obj.name) == sig:
        return False

    changed = False

    # 1. Recreate any dropped standard attributes (purely additive).
    if any(cd.attributes.get(name) is None for name in _REQUIRED_ATTRS):
        ensure_standard_attributes(cd)
        changed = True

    # 2. Give every curve a unique, non-empty id. Empty ids come from natively
    #    added curves, duplicates from natively copied ones — both get a fresh id.
    type_attr = cd.attributes.get("sketch_type")
    seen = set()
    for i in range(len(cd.curves)):
        cid = get_uuid(cd, "curve_id", i)
        if not cid or cid in seen:
            cid = new_uuid()
            set_uuid(cd, "curve_id", i, cid)
            name_attr = cd.attributes.get("name")
            if name_attr and not name_attr.data[i].value:
                ctype = type_attr.data[i].value if type_attr else -1
                name_attr.data[i].value = default_curve_name(cd, ctype).encode()
            changed = True
        seen.add(cid)

    # 2b. Guarantee the protected origin point survives a native delete.
    if _ensure_origin(sketch, cd):
        changed = True

    # 3. Remove segments left degenerate by a native edit — e.g. a line whose
    #    endpoint was deleted in Edit Mode, leaving a 1-point "line".
    if type_attr:
        degenerate = [
            get_uuid(cd, "curve_id", i)
            for i in range(len(cd.curves))
            if type_attr.data[i].value == SketchCurveType.LINE
            and cd.curves[i].points_length < 2
        ]
        for cid in degenerate:
            if cid:
                remove_native_curve_by_id(sketch, cid)
                changed = True

    # 3b. Remove degenerate arcs whose start and end points coincide (zero
    #     sweep). Trimming a circle down to nothing can leave these; their
    #     bezier degenerates into a stray sliver (the "trim leftover" lens).
    #     Drop the arc and any points it orphans.
    if type_attr:
        pos_by_id = {
            get_uuid(cd, "curve_id", i): tuple(
                cd.points[cd.curves[i].points[0].index].position[:2]
            )
            for i in range(len(cd.curves))
            if type_attr.data[i].value == SketchCurveType.POINT
        }
        degenerate_arcs = []
        orphaned = set()
        for i in range(len(cd.curves)):
            if type_attr.data[i].value != SketchCurveType.ARC:
                continue
            sp = get_uuid(cd, "start_point_id", i)
            ep = get_uuid(cd, "end_point_id", i)
            a, b = pos_by_id.get(sp), pos_by_id.get(ep)
            coincident = sp and (
                sp == ep
                or (a and b and math.hypot(a[0] - b[0], a[1] - b[1]) < _DEGEN_ARC_EPS)
            )
            if coincident:
                degenerate_arcs.append(get_uuid(cd, "curve_id", i))
                orphaned.update((sp, ep, get_uuid(cd, "center_point_id", i)))
        for cid in degenerate_arcs:
            if cid:
                remove_native_curve_by_id(sketch, cid)
                changed = True
        if degenerate_arcs:
            _remove_orphan_points(sketch, orphaned)

    # 4. Prune constraints referencing a curve that exists in no sketch.
    valid_ids = {get_uuid(cd, "curve_id", i) for i in range(len(cd.curves))}
    if _prune_dangling_constraints(sketch, valid_ids):
        changed = True

    if changed:
        invalidate_curve_id_cache(sketch)
        cd.update_tag()

    _validated[obj.name] = _signature(cd)
    return changed


def _dedup_constraint_uids(scene):
    """Give duplicated sketches independent constraint uids.

    Dimensional values live in ``scene["slvs:c:<uid>"]``, so two sketches sharing
    a constraint uid (e.g. after duplicating a sketch object) share the value.
    Keep each uid's first occurrence; re-mint later ones and copy their current
    value across so the copy stays independent.
    """
    from ..model.sketch_ref import get_sketches

    seen = set()
    changed = False
    for sketch in get_sketches(scene):
        try:
            constraints = sketch.constraints
        except Exception:
            continue
        for c in constraints.all:
            uid = getattr(c, "constraint_uid", "")
            if uid and uid not in seen:
                seen.add(uid)
                continue

            new = secrets.token_hex(8)
            while new in seen:
                new = secrets.token_hex(8)
            c.constraint_uid = new
            # Carry the stored value over so the copy keeps its current value
            # (dimensional constraints only; geometric ones store nothing).
            old_key = f"slvs:c:{uid}" if uid else None
            new_key = f"slvs:c:{new}"
            if old_key and old_key in scene and new_key not in scene:
                scene[new_key] = scene[old_key]
            seen.add(new)
            changed = True
    return changed


def validate_all_sketches(scene):
    """Validate every sketch in the scene. Returns True if anything changed."""
    from ..model.sketch_ref import get_sketches

    any_changed = False
    for sketch in get_sketches(scene):
        try:
            if validate_sketch(sketch):
                any_changed = True
        except Exception:
            logger.exception("Sketch validation failed for '%s'", sketch.name)

    try:
        if _dedup_constraint_uids(scene):
            any_changed = True
    except Exception:
        logger.exception("Constraint uid dedup failed")

    return any_changed
