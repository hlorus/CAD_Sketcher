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
import numpy as np
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
        return None
    source = wp.get(KEY_SOURCE)
    return source if isinstance(source, bpy.types.Object) else None


def _is_closed(polys) -> bool:
    """Whether polygons bound a volume: every edge shared by exactly two faces."""
    used = {}
    for poly in polys:
        for i, a in enumerate(poly):
            b = poly[(i + 1) % len(poly)]
            edge = (a, b) if a < b else (b, a)
            used[edge] = used.get(edge, 0) + 1
    return bool(used) and all(count == 2 for count in used.values())


def _mesh_arrays(mesh, matrix):
    """``(world verts, polygon index lists)`` for ``mesh``, read in bulk.

    ``foreach_get`` fills a flat buffer in one call, where walking ``mesh.vertices``
    and ``poly.vertices`` in Python pays RNA overhead per element -- which was the
    single most expensive thing an extrude did on every mouse move.
    """
    count = len(mesh.vertices)
    co = np.empty(count * 3, dtype=np.float64)
    mesh.vertices.foreach_get("co", co)
    co = co.reshape(count, 3)
    # World space: mathutils composes as ``matrix @ v`` for column vectors, which
    # for rows is ``v @ Mᵀ + t``.
    basis = np.array(matrix.to_3x3()).T
    world = co @ basis + np.array(matrix.translation)

    loop_total = np.empty(len(mesh.polygons), dtype=np.int32)
    mesh.polygons.foreach_get("loop_total", loop_total)
    loops = np.empty(len(mesh.loops), dtype=np.int32)
    mesh.loops.foreach_get("vertex_index", loops)

    return world, loop_total, loops


def _polygon_lists(loop_total, loops, base):
    """Polygon index lists for ``BVHTree.FromPolygons``, offset by ``base``.

    Loops are packed in polygon order, so a mesh whose faces all have the same
    number of sides -- every mesh a boolean is likely to meet, quads or tris --
    converts in a single reshape. Mixed n-gons fall back to slicing per face.
    """
    indices = loops + base
    if loop_total.size and bool((loop_total == loop_total[0]).all()):
        return indices.reshape(-1, int(loop_total[0])).tolist()

    ends = np.cumsum(loop_total)
    return [chunk.tolist() for chunk in np.split(indices, ends[:-1])]


def _world_geometry_map(depsgraph, wanted, closed_only=False):
    """Map each object in ``wanted`` to ``(bvh, aabb_min, aabb_max)`` in world space.

    Reads the *evaluated* geometry from depsgraph instances in a single pass. This
    is what makes it work for a sketch: its extrude/revolve modifier OUTPUTS a mesh
    from a Curves object, and that mesh surfaces as a depsgraph instance rather
    than on the evaluated object (``to_mesh``/``new_from_object`` raise "does not
    have geometry data" there). Objects yielding no faces (an unfilled profile)
    are simply absent from the map.

    Building one of these is not cheap, so ``wanted`` should be as small as the
    caller can make it -- see :func:`overlapping_bodies`, which narrows by bounds
    first.
    """
    from ..stateful_operator.utilities.geometry import instance_origin

    wanted = set(wanted)
    if not wanted:
        return {}

    accum = {}  # origin object -> ([world vert arrays], [poly index lists])
    for inst in depsgraph.object_instances:
        ob = inst.object
        origin = instance_origin(inst)
        if origin not in wanted:
            continue
        try:
            mesh = ob.to_mesh()
        except Exception:
            mesh = None
        if mesh is None or len(mesh.polygons) == 0:
            if mesh is not None:
                ob.to_mesh_clear()
            continue

        chunks, polys = accum.setdefault(origin, ([], []))
        base = sum(len(c) for c in chunks)
        world, loop_total, loops = _mesh_arrays(mesh, inst.matrix_world)
        chunks.append(world)
        polys.extend(_polygon_lists(loop_total, loops, base))
        ob.to_mesh_clear()

    result = {}
    for obj, (chunks, polys) in accum.items():
        if closed_only and not _is_closed(polys):
            continue
        verts = np.concatenate(chunks) if len(chunks) > 1 else chunks[0]
        lo = Vector(verts.min(axis=0))
        hi = Vector(verts.max(axis=0))
        result[obj] = (BVHTree.FromPolygons(verts.tolist(), polys), lo, hi)
    return result


def _world_bounds_map(depsgraph, wanted):
    """World-space AABB per object, from ``bound_box``: no meshing, no BVH.

    The cheap half of :func:`_world_geometry_map`, for deciding which bodies are
    worth the expensive half. An evaluated object's ``bound_box`` already covers
    what its modifiers produce, and an object whose bounds are wrong or empty is
    simply kept as a candidate, so narrowing this way can only drop bodies that
    are provably nowhere near.
    """
    from ..stateful_operator.utilities.geometry import instance_origin

    wanted = set(wanted)
    bounds = {}
    for inst in depsgraph.object_instances:
        origin = instance_origin(inst)
        if origin not in wanted:
            continue
        mw = inst.matrix_world
        corners = [mw @ Vector(corner) for corner in inst.object.bound_box]
        lo = Vector(map(min, zip(*corners)))
        hi = Vector(map(max, zip(*corners)))
        if origin in bounds:
            was_lo, was_hi = bounds[origin]
            lo = Vector(map(min, zip(lo, was_lo)))
            hi = Vector(map(max, zip(hi, was_hi)))
        bounds[origin] = (lo, hi)
    return bounds


def _aabb_overlap(a, b):
    """Whether two world-space AABBs (each ``(min, max)``) intersect."""
    (a_lo, a_hi), (b_lo, b_hi) = a, b
    return all(a_lo[i] <= b_hi[i] and b_lo[i] <= a_hi[i] for i in range(3))


def is_closed_solid(obj, depsgraph) -> bool:
    """Whether ``obj``'s evaluated geometry is a closed volume.

    The Manifold boolean solver silently drops an operand that is not, which is
    how a flat profile came out empty instead of holed; the Exact solver handles
    it. Read from the geometry so it also covers meshes from anywhere else.
    """
    geo = _world_geometry_map(depsgraph, [obj], closed_only=True)
    return obj in geo


def overlapping_bodies(cutter, candidates, depsgraph, geo=None):
    """Subset of ``candidates`` whose solid geometry actually overlaps ``cutter``.

    An AABB pre-filter (cheap, no BVH) gates the exact ``BVHTree.overlap`` test, so
    the expensive check only runs on plausibly-touching bodies. Order preserved.
    """
    if geo is None:
        # The cutter always has to be built; the candidates are narrowed by their
        # bounds first, so nothing far away is meshed or BVH'd at all. That test
        # used to run *after* the whole scene had been built, which is most of
        # what an extrude spent its time on while the mouse moved.
        geo = _world_geometry_map(depsgraph, [cutter])
        cutter_geo = geo.get(cutter)
        if cutter_geo is None:
            return []
        _bvh, cutter_lo, cutter_hi = cutter_geo
        bounds = _world_bounds_map(depsgraph, candidates)
        near = [
            obj
            for obj in candidates
            if obj not in bounds or _aabb_overlap((cutter_lo, cutter_hi), bounds[obj])
        ]
        geo.update(_world_geometry_map(depsgraph, near))

    cutter_geo = geo.get(cutter)
    if cutter_geo is None:
        return []
    cutter_bvh, cutter_lo, cutter_hi = cutter_geo

    hits = []
    for obj in candidates:
        og = geo.get(obj)
        if og is None:
            continue
        bvh, lo, hi = og
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
    from .body import body_of, sketch_of

    cutter_sketch = sketch_of(cutter)

    result = []
    for obj in context.view_layer.objects:
        if obj == cutter or obj.type not in _BODY_TYPES:
            continue
        if obj == cutter_sketch:
            continue  # a body never cuts the sketch it is made from
        if body_of(obj) is not None:
            # A sketch that has a body is source, not a target: its body is.
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
