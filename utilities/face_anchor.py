"""Persistent face-anchored workplanes.

A workplane empty created from a mesh face is anchored to that face by stamping
a unique id into a FACE-domain INT attribute (``slvs_face_id``) on the source
mesh. A depsgraph handler then re-derives the empty's ``matrix_world`` from the
*evaluated* mesh whenever the source changes, so the workplane follows edits and
deformation instead of only the object transform.

Why an attribute rather than a face index: face/vertex indices are renumbered by
topology edits, but FACE attributes are copied onto faces derived from the
anchor (subdivide/extrude/inset all keep the id). We therefore look the face up
*by id* each update. Validated behaviour (see the validation spike):

  - subdivide/extrude/inset/bevel/poke  -> id survives, plane tracks
  - Subsurf/Triangulate/Boolean/Mirror  -> id survives on the evaluated mesh
  - Mirror (and duplicated geometry) yields a second, disjoint face-set with the
    same id -> we cluster the id-faces and pick the cluster nearest the last
    known position, so the plane stays on the picked face.
  - Reads inside edit mode don't see the id -> we skip while the source is in
    edit mode and reconcile on exit (no false "detached").
  - Deleting the anchor face removes the id -> flagged detached.
"""

import bpy
import numpy as np
from mathutils import Matrix, Vector

from .geometry import orientation_from_normal_ref

# FACE-domain INT attribute stamped on the source mesh.
FACE_ID_ATTR = "slvs_face_id"

# ID custom-property keys on the workplane empty.
KEY_SOURCE = "slvs_wp_source"      # source Object (ID reference)
KEY_FACE_ID = "slvs_wp_face_id"    # int id anchored to
KEY_DETACHED = "slvs_wp_detached"  # bool, set when the id can't be found
KEY_LAST_CO = "slvs_wp_last_co"    # last cluster centroid in source-local space
KEY_REF = "slvs_wp_ref"            # in-plane X axis in source-local space


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------

def _allocate_face_id(mesh):
    """A face id unique within ``mesh`` (max existing + 1)."""
    attr = mesh.attributes.get(FACE_ID_ATTR)
    if attr is None or len(attr.data) == 0:
        return 1
    ids = np.empty(len(attr.data), dtype=np.int32)
    attr.data.foreach_get("value", ids)
    return int(ids.max()) + 1


def stamp_face_anchor(empty, source_ob, face_index):
    """Stamp a unique id on ``source_ob``'s face and anchor ``empty`` to it.

    ``empty.matrix_world`` must already hold the intended frame; its X axis is
    stored in source-local space as the in-plane reference so the recomputed
    orientation stays rigid with the mesh as the object rotates.
    """
    mesh = source_ob.data
    attr = mesh.attributes.get(FACE_ID_ATTR)
    if attr is None:
        attr = mesh.attributes.new(FACE_ID_ATTR, "INT", "FACE")
    face_id = _allocate_face_id(mesh)
    attr.data[face_index].value = face_id

    # Store the creation-time X axis in the source's local frame so the initial
    # recompute reproduces the current frame and it then rotates with the mesh.
    x_world = empty.matrix_world.to_3x3().col[0].normalized()
    ref_local = (source_ob.matrix_world.to_3x3().inverted() @ x_world).normalized()

    empty[KEY_SOURCE] = source_ob
    empty[KEY_FACE_ID] = face_id
    empty[KEY_DETACHED] = False
    empty[KEY_LAST_CO] = list(mesh.polygons[face_index].center)
    empty[KEY_REF] = list(ref_local)


# ---------------------------------------------------------------------------
# Iteration
# ---------------------------------------------------------------------------

def iter_face_workplanes(scene):
    """Yield empties that are anchored to a mesh face."""
    for obj in scene.objects:
        if obj.type == 'EMPTY' and KEY_FACE_ID in obj:
            yield obj


# ---------------------------------------------------------------------------
# Attribute cleanup on workplane deletion
# ---------------------------------------------------------------------------

# Anchors seen with a live empty last pass, as {(mesh_name, face_id)}. When an
# entry disappears the empty was deleted, so we clear its id from the mesh.
_live_anchors = set()


def clear_face_id(mesh, face_id):
    """Reset faces carrying ``face_id`` to 0; drop the attribute if now empty."""
    attr = mesh.attributes.get(FACE_ID_ATTR)
    if attr is None or len(attr.data) == 0:
        return
    ids = np.empty(len(attr.data), dtype=np.int32)
    attr.data.foreach_get("value", ids)
    ids[ids == face_id] = 0
    if ids.any():
        attr.data.foreach_set("value", ids)
    else:
        mesh.attributes.remove(attr)


def clear_anchor(empty):
    """Turn a face-anchored empty into a free workplane.

    Clears the mesh face id (if the source still exists) and removes the anchor
    custom properties, leaving the empty static at its current transform.
    """
    source = empty.get(KEY_SOURCE)
    face_id = empty.get(KEY_FACE_ID)
    if source is not None and source.type == 'MESH' and face_id is not None:
        clear_face_id(source.data, face_id)
        _live_anchors.discard((source.data.name, face_id))
    for key in (KEY_SOURCE, KEY_FACE_ID, KEY_DETACHED, KEY_LAST_CO, KEY_REF):
        if key in empty:
            del empty[key]


def reconcile_orphan_anchors(scene):
    """Clear face ids whose anchoring empty was deleted since the last pass."""
    live = set()
    for empty in iter_face_workplanes(scene):
        source = empty.get(KEY_SOURCE)
        if source is not None and source.type == 'MESH':
            live.add((source.data.name, empty[KEY_FACE_ID]))

    for mesh_name, face_id in _live_anchors - live:
        mesh = bpy.data.meshes.get(mesh_name)
        if mesh is not None:
            clear_face_id(mesh, face_id)

    _live_anchors.clear()
    _live_anchors.update(live)


# ---------------------------------------------------------------------------
# Recompute
# ---------------------------------------------------------------------------

def _clusters(mesh, idxs):
    """Group face indices that are connected through shared vertices."""
    parent = {fi: fi for fi in idxs}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        parent[find(a)] = find(b)

    vert_faces = {}
    for fi in idxs:
        for v in mesh.polygons[fi].vertices:
            vert_faces.setdefault(v, []).append(fi)
    for faces in vert_faces.values():
        first = faces[0]
        for other in faces[1:]:
            union(first, other)

    groups = {}
    for fi in idxs:
        groups.setdefault(find(fi), []).append(fi)
    return list(groups.values())


def _plane_from_faces(mesh, faces):
    """Area-weighted (centroid_local, normal_local) over ``faces``."""
    centroid = Vector()
    normal = Vector()
    area = 0.0
    for fi in faces:
        p = mesh.polygons[fi]
        centroid += p.center * p.area
        normal += p.normal * p.area
        area += p.area
    if area > 0.0:
        centroid /= area
    return centroid, normal


def recompute_anchor_matrix(eval_ob, face_id, last_co, ref_local=None):
    """World matrix for a face-anchored workplane, or None if detached.

    Returns ``(matrix_world, new_last_co_local)``. ``last_co`` disambiguates
    between disjoint face clusters sharing the id (e.g. mirrored geometry).
    ``ref_local`` is the in-plane X reference in source-local space; the object
    rotation carries it so the frame stays rigid with the mesh.
    """
    mesh = eval_ob.data
    attr = mesh.attributes.get(FACE_ID_ATTR)
    if attr is None or attr.domain != 'FACE' or len(mesh.polygons) == 0:
        return None

    ids = np.empty(len(mesh.polygons), dtype=np.int32)
    attr.data.foreach_get("value", ids)
    idxs = [int(i) for i in np.nonzero(ids == face_id)[0]]
    if not idxs:
        return None

    clusters = _clusters(mesh, idxs)
    ref = Vector(last_co) if last_co is not None else None

    def cluster_centroid(faces):
        return _plane_from_faces(mesh, faces)[0]

    if ref is not None and len(clusters) > 1:
        faces = min(clusters, key=lambda c: (cluster_centroid(c) - ref).length)
    else:
        faces = max(clusters, key=len)

    centroid_local, normal_local = _plane_from_faces(mesh, faces)
    if normal_local.length == 0.0:
        return None

    mw = eval_ob.matrix_world
    pos = mw @ centroid_local
    rot = mw.to_3x3()
    normal_world = (rot @ normal_local).normalized()
    if ref_local is not None:
        ref_world = rot @ Vector(ref_local)
    else:
        ref_world = Vector((1.0, 0.0, 0.0))
    quat = orientation_from_normal_ref(normal_world, ref_world)
    return Matrix.LocRotScale(pos, quat, None), list(centroid_local)


# ---------------------------------------------------------------------------
# Depsgraph handler body
# ---------------------------------------------------------------------------

def _matrix_differs(a, b, eps=1e-6):
    return any(abs(a[i][j] - b[i][j]) > eps for i in range(4) for j in range(4))


def update_face_workplanes(context, depsgraph):
    """Re-derive matrix_world of face-anchored workplanes from changed sources."""
    from .. import global_data

    if global_data.updating_face_wp or global_data.stateful_op_running:
        return

    scene = context.scene

    # Clear ids left behind by deleted workplane empties (writes to mesh data,
    # so guard against the resulting depsgraph re-entry).
    global_data.updating_face_wp = True
    try:
        reconcile_orphan_anchors(scene)
    finally:
        global_data.updating_face_wp = False

    # Datablocks that changed this update — gate work to affected sources.
    changed = set()
    for u in depsgraph.updates:
        changed.add(u.id)
        orig = getattr(u.id, "original", None)
        if orig is not None:
            changed.add(orig)

    resolved = False
    for empty in iter_face_workplanes(scene):
        source = empty.get(KEY_SOURCE)
        if source is None or source.type != 'MESH':
            continue
        if source not in changed and source.data not in changed:
            continue
        # Edit-mode reads don't expose the id; reconcile on exit instead of
        # falsely detaching.
        if source.mode == 'EDIT':
            continue

        eval_ob = source.evaluated_get(depsgraph)
        result = recompute_anchor_matrix(
            eval_ob, empty[KEY_FACE_ID], empty.get(KEY_LAST_CO), empty.get(KEY_REF)
        )
        if result is None:
            if not empty.get(KEY_DETACHED, False):
                empty[KEY_DETACHED] = True
            continue

        matrix, last_co = result
        empty[KEY_DETACHED] = False
        empty[KEY_LAST_CO] = last_co
        if _matrix_differs(empty.matrix_world, matrix):
            global_data.updating_face_wp = True
            try:
                empty.matrix_world = matrix
            finally:
                global_data.updating_face_wp = False
            resolved = True

    if resolved:
        # Workplane moved -> re-solve dependent sketches on the next tick.
        global_data.needs_solve = True
