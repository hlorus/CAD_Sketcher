"""Migrate legacy entity-based sketches to the native-curve model.

Old files store geometry as SlvsPoint2D/Line2D/Arc/Circle entities under
``scene.sketcher.entities``, grouped by SlvsSketch entities on SlvsWorkplane
entities. The native-curve model stores each sketch as a Curves object (parented
to a workplane Empty) with geometry in curve data.

This module rebuilds the new representation from the old entities using the same
``PointRef/LineRef/ArcRef/CircleRef.create`` constructors the operators use.
Constraints are NOT migrated here (that's a separate phase); only geometry.

The old entity data is left intact (it's the migration source and is kept for
loading even older files).
"""

import logging

import bpy

logger = logging.getLogger(__name__)


def _iter_legacy_sketches(context):
    """Legacy SlvsSketch entities still needing migration.

    A sketch is legacy if its ``target_object`` is not (yet) a native-curve
    sketch — in old files it points at the generated mesh output instead.
    """
    from ..model.sketch import SlvsSketch
    from ..model.sketch_ref import is_sketch_object

    for e in context.scene.sketcher.entities.all:
        if not isinstance(e, SlvsSketch) or not e.wp:
            continue
        if is_sketch_object(e.target_object):
            continue
        yield e


def scene_needs_migration(context):
    return next(_iter_legacy_sketches(context), None) is not None


def _create_workplane_empty(context, wp, name):
    empty = bpy.data.objects.new(name, None)
    empty.empty_display_type = 'PLAIN_AXES'
    empty.empty_display_size = 0.5
    empty.lock_location = (True, True, True)
    empty.lock_rotation = (True, True, True)
    empty.lock_scale = (True, True, True)
    context.scene.collection.objects.link(empty)
    empty.matrix_world = wp.matrix_basis
    return empty


def _create_sketch_object(context, empty, name):
    from ..model.sketch_ref import Sketch, stamp_sketch_props
    from ..utilities.curve_data import _ensure_convert_modifier

    curve = bpy.data.hair_curves.new(name)
    obj = bpy.data.objects.new(name, curve)
    context.scene.collection.objects.link(obj)
    stamp_sketch_props(obj)
    _ensure_convert_modifier(obj)
    obj.parent = empty
    obj.lock_location = (True, True, True)
    obj.lock_rotation = (True, True, True)
    obj.lock_scale = (True, True, True)
    return Sketch(obj)


def _migrate_geometry(context, old_sketch, sketch, entity_map):
    """Rebuild an old sketch's 2D entities as curves. Returns (n_points, n_segs).

    ``entity_map`` is populated with ``old slvs_index -> (sketch, curve_id)`` for
    every migrated entity, so constraints can be remapped afterwards.
    """
    from ..model.point_2d import SlvsPoint2D
    from ..model.line_2d import SlvsLine2D
    from ..model.arc import SlvsArc
    from ..model.circle import SlvsCircle
    from ..model.curve_ref import PointRef, LineRef, ArcRef, CircleRef

    ents = list(old_sketch.sketch_entities(context))
    point_map = {}  # old slvs_index -> new PointRef
    wp_inv = old_sketch.wp.matrix_basis.inverted()

    # Points first, so segments can reference them.
    for e in ents:
        if isinstance(e, SlvsPoint2D):
            pr = PointRef.create(
                sketch, (e.co[0], e.co[1]),
                construction=getattr(e, "construction", False),
                fixed=getattr(e, "fixed", False),
            )
            point_map[e.slvs_index] = pr
            entity_map[e.slvs_index] = (sketch, pr.curve_id)

    def pt(entity):
        """Resolve a point ref, creating a local copy for cross-sketch points.

        A segment may reference a point owned by another sketch; the per-sketch
        curve model can't share it, so copy it into this sketch at the same
        position (projected into this sketch's workplane).
        """
        if entity is None:
            return None
        pr = point_map.get(entity.slvs_index)
        if pr is not None:
            return pr
        if not isinstance(entity, SlvsPoint2D):
            return None
        local = wp_inv @ entity.location
        pr = PointRef.create(
            sketch, (local.x, local.y),
            construction=getattr(entity, "construction", False),
        )
        point_map[entity.slvs_index] = pr
        return pr

    n_seg = 0
    for e in ents:
        con = getattr(e, "construction", False)
        ref = None
        if isinstance(e, SlvsLine2D):
            p1, p2 = pt(e.p1), pt(e.p2)
            if p1 and p2:
                ref = LineRef.create(sketch, p1, p2, construction=con)
        elif isinstance(e, SlvsArc):
            ct, s, en = pt(e.ct), pt(e.start), pt(e.end)
            if ct and s and en:
                ref = ArcRef.create(sketch, ct, s, en, construction=con)
        elif isinstance(e, SlvsCircle):
            ct = pt(e.ct)
            if ct:
                ref = CircleRef.create(sketch, ct, e.radius, construction=con)
        if ref is not None:
            entity_map[e.slvs_index] = (sketch, ref.curve_id)
            n_seg += 1

    return len(point_map), n_seg


def migrate_scene(context):
    """Migrate all legacy sketches (geometry + constraints). Returns a summary."""
    summary = {
        "sketches": 0, "points": 0, "segments": 0,
        "constraints": 0, "constraints_skipped": 0, "errors": [],
    }

    # One Empty per distinct legacy workplane (sketches sharing a plane share it).
    wp_empties = {}
    # old entity slvs_index -> (new Sketch, curve_id) for constraint remapping.
    entity_map = {}

    for old_sketch in list(_iter_legacy_sketches(context)):
        try:
            wp = old_sketch.wp
            empty = wp_empties.get(wp.slvs_index)
            if empty is None:
                empty = _create_workplane_empty(
                    context, wp, f"WP_{getattr(wp, 'name', 'Workplane')}"
                )
                wp_empties[wp.slvs_index] = empty

            sketch = _create_sketch_object(
                context, empty, old_sketch.name or "Sketch"
            )
            # Link old->new so re-runs skip it and future phases can find it.
            old_sketch.target_object = sketch.target_object

            n_pts, n_seg = _migrate_geometry(context, old_sketch, sketch, entity_map)
            summary["sketches"] += 1
            summary["points"] += n_pts
            summary["segments"] += n_seg
        except Exception as e:
            logger.exception("Failed to migrate sketch %s", old_sketch)
            summary["errors"].append(f"{old_sketch.name}: {e!r}")

    _migrate_constraints(context, entity_map, summary)
    return summary


# ---------------------------------------------------------------------------
# Constraints
# ---------------------------------------------------------------------------

# Simple (non-dimensional) two-reference constraints: type -> add method name.
_SIMPLE_CONSTRAINTS = {
    "COINCIDENT": "add_coincident",
    "EQUAL": "add_equal",
    "VERTICAL": "add_vertical",
    "HORIZONTAL": "add_horizontal",
    "PARALLEL": "add_parallel",
    "PERPENDICULAR": "add_perpendicular",
    "TANGENT": "add_tangent",
    "MIDPOINT": "add_midpoint",
}


def _dim_settings(old):
    """Value/flag settings carried onto a migrated dimensional constraint.

    The legacy numeric value is a raw ID-property (``old["value"]``); the RNA
    ``value`` getter shadows it (it reads the new uid-keyed scene storage), so
    read the ID-property directly.
    """
    s = {}
    val = old.get("value")
    if val is not None:
        s["value"] = float(val)
    for key in ("setting", "is_reference"):
        if hasattr(old, key):
            s[key] = getattr(old, key)
    return s


def _add_migrated_constraint(cons, ctype, cids, old):
    """Create the new constraint on ``cons`` (a sketch's SlvsConstraints)."""
    c1, c2, c3 = cids
    if ctype in _SIMPLE_CONSTRAINTS:
        getattr(cons, _SIMPLE_CONSTRAINTS[ctype])(c1, c2)
    elif ctype == "DISTANCE":
        cons.add_distance(curve_id_1=c1, curve_id_2=c2, **_dim_settings(old))
    elif ctype == "ANGLE":
        cons.add_angle(curve_id_1=c1, curve_id_2=c2, **_dim_settings(old))
    elif ctype == "DIAMETER":
        cons.add_diameter(curve_id_1=c1, **_dim_settings(old))
    elif ctype == "RATIO":
        cons.add_ratio(curve_id_1=c1, curve_id_2=c2, **_dim_settings(old))
    elif ctype == "SYMMETRY":
        cons.add_symmetry(c1, c2, c3)
    else:
        return False
    return True


def _migrate_constraints(context, entity_map, summary):
    """Rebuild legacy constraints on the migrated sketches via curve_id refs."""
    for old in list(context.scene.sketcher.constraints.all):
        try:
            ctype = getattr(old, "type", None)
            refs = [getattr(old, n, None) for n in ("entity1", "entity2", "entity3")]
            mapped = [
                entity_map.get(r.slvs_index) if r is not None else None
                for r in refs
            ]
            present = [m for m in mapped if m]
            if not present:
                summary["constraints_skipped"] += 1
                continue

            # Place the constraint on the sketch of its first mapped reference.
            sketch = present[0][0]
            cids = [m[1] if m else "" for m in mapped]
            if _add_migrated_constraint(sketch.constraints, ctype, cids, old):
                summary["constraints"] += 1
            else:
                summary["constraints_skipped"] += 1
        except Exception as e:
            logger.exception("Failed to migrate constraint %s", old)
            summary["errors"].append(f"constraint {ctype}: {e!r}")
