"""Auto-detect boolean targets and a default operation for extrude/revolve.

When a sketch is extruded/revolved into a solid, the "boolean directly from the
tool" flow needs to know *which* bodies to cut/join and *whether* to cut or join.
Two signals drive it:

- Provenance: a sketch drawn on a mesh face records that body on its workplane
  (``face_anchor``). It is the primary, unambiguous target -- push/pull into the
  solid you sketched on.
- Spatial overlap: the extruded solid is tested against candidate bodies so it
  also cuts/joins everything it actually passes through (multiple targets).

The operation (Difference/Union) is only a default here; the caller exposes it so
the user can override it.
"""

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from .face_anchor import KEY_SOURCE

# Object types a boolean can operate on: a mesh, or a sketch/curve whose modifier
# produces a solid mesh (read through Object Info in the boolean group).
_BODY_TYPES = {"MESH", "CURVE", "CURVES"}


def sketch_source_body(sketch):
    """The body a face-anchored sketch was drawn on, or None.

    Reads the workplane empty's ``slvs_wp_source`` (stamped by face_anchor when a
    workplane is created from a mesh face). Free/base-plane sketches have none.
    """
    wp = getattr(sketch, "workplane_object", None)
    if wp is None:
        target = getattr(sketch, "target_object", None)
        wp = target.parent if target is not None else None
    if wp is None:
        return None
    source = wp.get(KEY_SOURCE)
    return source if isinstance(source, bpy.types.Object) else None


def _world_geometry(obj, depsgraph):
    """Return ``(bvh, aabb_min, aabb_max)`` in world space, or None if no solid.

    Built from the *evaluated* mesh, so it reflects the object's modifiers (a
    sketch's fill, its extrude/revolve). Returns None when the object yields no
    faces (e.g. a flat, unextruded profile), which can't participate in a boolean.
    """
    ev = obj.evaluated_get(depsgraph)
    try:
        mesh = ev.to_mesh()
    except Exception:
        return None
    if mesh is None or len(mesh.polygons) == 0:
        if mesh is not None:
            ev.to_mesh_clear()
        return None

    mw = obj.matrix_world
    verts = [mw @ v.co for v in mesh.vertices]
    polys = [tuple(p.vertices) for p in mesh.polygons]
    ev.to_mesh_clear()

    lo = Vector(
        (min(v.x for v in verts), min(v.y for v in verts), min(v.z for v in verts))
    )
    hi = Vector(
        (max(v.x for v in verts), max(v.y for v in verts), max(v.z for v in verts))
    )
    return BVHTree.FromPolygons(verts, polys), lo, hi


def _aabb_overlap(a, b):
    """Whether two world-space AABBs (each ``(min, max)``) intersect."""
    (a_lo, a_hi), (b_lo, b_hi) = a, b
    return all(a_lo[i] <= b_hi[i] and b_lo[i] <= a_hi[i] for i in range(3))


def overlapping_bodies(cutter, candidates, depsgraph):
    """Subset of ``candidates`` whose solid geometry actually overlaps ``cutter``.

    An AABB pre-filter (cheap, no BVH) gates the exact ``BVHTree.overlap`` test, so
    the expensive check only runs on plausibly-touching bodies. Order preserved.
    """
    cutter_geo = _world_geometry(cutter, depsgraph)
    if cutter_geo is None:
        return []
    cutter_bvh, cutter_lo, cutter_hi = cutter_geo

    hits = []
    for obj in candidates:
        geo = _world_geometry(obj, depsgraph)
        if geo is None:
            continue
        bvh, lo, hi = geo
        if not _aabb_overlap((cutter_lo, cutter_hi), (lo, hi)):
            continue
        if cutter_bvh.overlap(bvh):
            hits.append(obj)
    return hits


def candidate_bodies(context, cutter):
    """Visible boolean-capable objects that are safe targets for ``cutter``.

    Excludes the cutter itself, non-solid types, hidden objects, and anything that
    would close a boolean dependency cycle (the cutter already depends on it).
    """
    from ..operators.modifiers import creates_boolean_cycle

    result = []
    for obj in context.view_layer.objects:
        if obj == cutter or obj.type not in _BODY_TYPES:
            continue
        if not obj.visible_get():
            continue
        if creates_boolean_cycle(obj, cutter):
            continue
        result.append(obj)
    return result


def detect_targets(context, cutter, sketch, depsgraph=None):
    """Ordered bodies to boolean ``cutter`` into: source body first, then overlaps.

    The provenance source body (if any) leads and is included whether or not the
    overlap test catches it; the remaining overlapping bodies follow. Deduplicated,
    order stable.
    """
    if depsgraph is None:
        depsgraph = context.evaluated_depsgraph_get()

    candidates = candidate_bodies(context, cutter)
    overlaps = overlapping_bodies(cutter, candidates, depsgraph)

    ordered = []
    source = sketch_source_body(sketch) if sketch is not None else None
    if source is not None and source in candidates:
        ordered.append(source)
    for obj in overlaps:
        if obj not in ordered:
            ordered.append(obj)
    return ordered


def default_operation(offset, has_source_body):
    """Guess Difference vs Union for the auto-detected targets.

    Push/pull semantics: extruding *outward* from the face you sketched on adds
    material (Union); extruding *into* the solid removes it (Difference). Without a
    source body to orient against, default to Difference (the common "cut with this
    shape"). Always a guess -- the caller lets the user override it.
    """
    if has_source_body and offset > 0.0:
        return "Union"
    return "Difference"
