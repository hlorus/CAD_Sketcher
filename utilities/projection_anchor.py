"""Live references for mesh geometry projected into native sketches.

Projected point curves keep a persistent reference to their source mesh vertex.
The reference is stored on the sketch object and backed by a POINT-domain integer
attribute on the source mesh, so normal topology edits that preserve attributes do
not depend on fragile vertex indices. A depsgraph handler reprojects changed source
vertices into the sketch plane and the connected native line curves follow through
``rebuild_segments``.
"""

from mathutils import Vector

from ..model.curve_ref import LineRef, PointRef
from ..utilities.curve_data import batch_update

VERTEX_ID_ATTR = "slvs_project_vertex_id"

_SOURCE_PREFIX = "slvs_project_src_"
_VERTEX_ID_PREFIX = "slvs_project_vid_"
_VERTEX_INDEX_PREFIX = "slvs_project_idx_"
_LAST_CO_PREFIX = "slvs_project_last_"

_updating = False


def _key(prefix, curve_id):
    return f"{prefix}{curve_id}"


def _allocate_vertex_id(mesh):
    attr = mesh.attributes.get(VERTEX_ID_ATTR)
    if attr is None or len(attr.data) == 0:
        return 1
    return max((int(item.value) for item in attr.data), default=0) + 1


def ensure_vertex_id(mesh, vertex_index):
    """Return a persistent non-zero id for ``mesh.vertices[vertex_index]``."""
    attr = mesh.attributes.get(VERTEX_ID_ATTR)
    if attr is None:
        attr = mesh.attributes.new(VERTEX_ID_ATTR, "INT", "POINT")

    current = int(attr.data[vertex_index].value)
    if current:
        return current

    current = _allocate_vertex_id(mesh)
    attr.data[vertex_index].value = current
    return current


def bind_projected_point(sketch, point, source, vertex_index):
    """Bind a native sketch point to a source mesh vertex."""
    if source is None or source.type != "MESH":
        raise TypeError("Projected geometry source must be a mesh object")

    curve_id = point.curve_id
    vertex_id = ensure_vertex_id(source.data, vertex_index)
    owner = sketch.target_object
    owner[_key(_SOURCE_PREFIX, curve_id)] = source
    owner[_key(_VERTEX_ID_PREFIX, curve_id)] = vertex_id
    owner[_key(_VERTEX_INDEX_PREFIX, curve_id)] = int(vertex_index)
    owner[_key(_LAST_CO_PREFIX, curve_id)] = list(source.data.vertices[vertex_index].co)
    return vertex_id


def clear_projected_point_binding(sketch, curve_id):
    owner = sketch.target_object
    for prefix in (
        _SOURCE_PREFIX,
        _VERTEX_ID_PREFIX,
        _VERTEX_INDEX_PREFIX,
        _LAST_CO_PREFIX,
    ):
        key = _key(prefix, curve_id)
        if key in owner:
            del owner[key]


def iter_projected_point_bindings(sketch):
    """Yield ``(curve_id, source, vertex_id, fallback_index, last_co)``."""
    owner = sketch.target_object
    if owner is None:
        return

    for prop_key in list(owner.keys()):
        if not str(prop_key).startswith(_SOURCE_PREFIX):
            continue
        curve_id = str(prop_key)[len(_SOURCE_PREFIX) :]
        source = owner.get(prop_key)
        vertex_id = int(owner.get(_key(_VERTEX_ID_PREFIX, curve_id), 0))
        fallback = int(owner.get(_key(_VERTEX_INDEX_PREFIX, curve_id), -1))
        last_co = owner.get(_key(_LAST_CO_PREFIX, curve_id))
        yield curve_id, source, vertex_id, fallback, last_co


def _resolve_evaluated_vertex(eval_ob, vertex_id, fallback_index, last_co):
    mesh = eval_ob.data
    candidates = []
    attr = mesh.attributes.get(VERTEX_ID_ATTR)
    if attr is not None and attr.domain == "POINT":
        for i, item in enumerate(attr.data):
            if int(item.value) == vertex_id and i < len(mesh.vertices):
                candidates.append(i)

    if candidates:
        if len(candidates) == 1 or last_co is None:
            return mesh.vertices[candidates[0]]
        last = Vector(last_co)
        index = min(candidates, key=lambda i: (mesh.vertices[i].co - last).length)
        return mesh.vertices[index]

    # Some modifiers do not propagate arbitrary attributes. Keep a conservative
    # fallback for the unmodified/simple-mesh case instead of silently detaching.
    if 0 <= fallback_index < len(mesh.vertices):
        return mesh.vertices[fallback_index]
    return None


def _source_changed(source, changed):
    if changed is None:
        return True
    if source in changed or source.data in changed:
        return True
    original = getattr(source, "original", None)
    return original is not None and original in changed


def refresh_projection_for_sketch(sketch, depsgraph, changed=None, force=False):
    """Reproject bound points for one sketch. Returns number of moved points."""
    owner = sketch.target_object
    if owner is None:
        return 0

    sketch_changed = (
        force or changed is None or owner in changed or owner.data in changed
    )
    if owner.parent is not None and changed is not None and owner.parent in changed:
        sketch_changed = True

    updates = {}
    source_cache = {}
    stale = []

    for curve_id, source, vertex_id, fallback_index, last_co in list(
        iter_projected_point_bindings(sketch)
    ):
        point = PointRef(sketch, curve_id)
        if not point.valid:
            stale.append(curve_id)
            continue
        if source is None or getattr(source, "type", None) != "MESH":
            stale.append(curve_id)
            continue
        if not (sketch_changed or force or _source_changed(source, changed)):
            continue
        if source.mode == "EDIT":
            # The original mesh/attribute state is transient in Edit Mode. It is
            # reconciled when Blender emits the update on leaving Edit Mode.
            continue

        eval_ob = source_cache.get(source)
        if eval_ob is None:
            eval_ob = source.evaluated_get(depsgraph)
            source_cache[source] = eval_ob

        vertex = _resolve_evaluated_vertex(
            eval_ob,
            vertex_id,
            fallback_index,
            last_co,
        )
        if vertex is None:
            continue

        world = eval_ob.matrix_world @ vertex.co
        local = owner.matrix_world.inverted() @ world
        new_co = Vector((local.x, local.y))
        if (point.co - new_co).length > 1e-7:
            updates[curve_id] = (point, new_co, list(vertex.co))

    for curve_id in stale:
        clear_projected_point_binding(sketch, curve_id)

    if not updates:
        return 0

    with batch_update(sketch, point_ids=set(updates.keys())):
        for curve_id, (point, co, last_co) in updates.items():
            point.co = co
            owner[_key(_LAST_CO_PREFIX, curve_id)] = last_co

    return len(updates)


def update_projected_geometry(context, depsgraph):
    """Depsgraph handler body for all live projected mesh references."""
    global _updating
    if _updating:
        return

    changed = set()
    for update in depsgraph.updates:
        changed.add(update.id)
        original = getattr(update.id, "original", None)
        if original is not None:
            changed.add(original)

    from .. import global_data
    from ..model.sketch_ref import get_sketches

    if global_data.stateful_op_running:
        return

    _updating = True
    try:
        moved = 0
        for sketch in get_sketches(context.scene):
            moved += refresh_projection_for_sketch(
                sketch,
                depsgraph,
                changed=changed,
            )
    finally:
        _updating = False

    if moved:
        global_data.needs_solve = True
        global_data.needs_redraw = True


def project_mesh_object(sketch, source, construction=True):
    """Project every edge of ``source`` onto ``sketch`` as live native curves.

    Returns ``(points, lines)``. Endpoints are fixed because their positions are
    driven by the source mesh reference rather than by SolveSpace.
    """
    if source is None or source.type != "MESH":
        raise TypeError("Source must be a mesh object")
    mesh = source.data
    if len(mesh.edges) == 0:
        return [], []

    owner = sketch.target_object
    inv = owner.matrix_world.inverted()
    used_indices = sorted({int(i) for edge in mesh.edges for i in edge.vertices})
    point_by_index = {}
    points = []
    lines = []

    with batch_update(sketch):
        for vertex_index in used_indices:
            vertex = mesh.vertices[vertex_index]
            local = inv @ (source.matrix_world @ vertex.co)
            point = PointRef.create(
                sketch,
                (local.x, local.y),
                construction=construction,
                fixed=True,
                name="Projected Point",
            )
            bind_projected_point(sketch, point, source, vertex_index)
            point_by_index[vertex_index] = point
            points.append(point)

        for edge in mesh.edges:
            p1 = point_by_index.get(int(edge.vertices[0]))
            p2 = point_by_index.get(int(edge.vertices[1]))
            if p1 is None or p2 is None:
                continue
            line = LineRef.create(
                sketch,
                p1,
                p2,
                construction=construction,
                name="Projected Line",
            )
            lines.append(line)

    return points, lines
