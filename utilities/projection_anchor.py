"""Live references for mesh geometry projected into native sketches.

Projected point curves keep their binding metadata on the Curves datablock:
source slot, persistent source vertex id, fallback vertex index and last source
coordinate are CURVE-domain attributes, so they re-index and disappear together
with their curve. The only non-POD value is the source Object pointer; it lives in
a compact per-sketch pointer collection and is referenced by integer slot.

The source mesh itself carries a POINT-domain persistent vertex id attribute, so
normal topology edits that preserve attributes do not depend on fragile vertex
indices. A depsgraph handler reprojects changed source vertices into the sketch
plane and connected native line curves follow through ``rebuild_segments``.
"""

from mathutils import Vector

from ..model.curve_ref import LineRef, PointRef
from ..utilities.curve_data import (
    batch_update,
    ensure_attribute,
    get_curve_data,
    read_curve_id_list,
)

# Persistent identity on the SOURCE mesh (POINT domain).
VERTEX_ID_ATTR = "slvs_project_vertex_id"

# Binding metadata on the SKETCH Curves datablock (CURVE domain).
PROJECT_SRC_SLOT_ATTR = "slvs_project_src_slot"
PROJECT_VERTEX_ID_ATTR = "slvs_project_vertex_id"
PROJECT_VERTEX_INDEX_ATTR = "slvs_project_vertex_index"
PROJECT_LAST_CO_ATTR = "slvs_project_last_co"

_updating = False


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


def _ensure_projection_attributes(curve_data):
    attributes = curve_data.attributes
    ensure_attribute(attributes, PROJECT_SRC_SLOT_ATTR, "INT", "CURVE")
    ensure_attribute(attributes, PROJECT_VERTEX_ID_ATTR, "INT", "CURVE")
    ensure_attribute(attributes, PROJECT_VERTEX_INDEX_ATTR, "INT", "CURVE")
    ensure_attribute(attributes, PROJECT_LAST_CO_ATTR, "FLOAT_VECTOR", "CURVE")


def _get_or_add_source_slot(owner, source):
    """Return a stable slot for ``source`` in the sketch's pointer table."""
    slots = owner.slvs_project_sources
    for index, slot in enumerate(slots):
        if slot.source == source:
            return index

    slot = slots.add()
    slot.source = source
    return len(slots) - 1


def bind_projected_point(sketch, point, source, vertex_index):
    """Bind a native sketch point to a source mesh vertex."""
    if source is None or source.type != "MESH":
        raise TypeError("Projected geometry source must be a mesh object")

    curve_data, curve_index, _ = get_curve_data(sketch, point.curve_id)
    if curve_data is None:
        raise ValueError("Projected point is not part of the sketch")

    _ensure_projection_attributes(curve_data)
    vertex_id = ensure_vertex_id(source.data, vertex_index)
    source_slot = _get_or_add_source_slot(sketch.target_object, source)
    attributes = curve_data.attributes

    attributes[PROJECT_SRC_SLOT_ATTR].data[curve_index].value = source_slot
    attributes[PROJECT_VERTEX_ID_ATTR].data[curve_index].value = vertex_id
    attributes[PROJECT_VERTEX_INDEX_ATTR].data[curve_index].value = int(vertex_index)
    attributes[PROJECT_LAST_CO_ATTR].data[curve_index].vector = source.data.vertices[
        vertex_index
    ].co
    return vertex_id


def iter_projected_point_bindings(sketch):
    """Yield ``(curve_id, source, vertex_id, fallback_index, last_co)``."""
    owner = sketch.target_object
    curve_data = sketch.data
    if owner is None or curve_data is None:
        return

    attributes = curve_data.attributes
    slot_attr = attributes.get(PROJECT_SRC_SLOT_ATTR)
    vertex_id_attr = attributes.get(PROJECT_VERTEX_ID_ATTR)
    fallback_attr = attributes.get(PROJECT_VERTEX_INDEX_ATTR)
    last_co_attr = attributes.get(PROJECT_LAST_CO_ATTR)
    if not all((slot_attr, vertex_id_attr, fallback_attr, last_co_attr)):
        return

    curve_ids = read_curve_id_list(curve_data)
    slots = owner.slvs_project_sources
    for index, curve_id in enumerate(curve_ids):
        vertex_id = int(vertex_id_attr.data[index].value)
        # All generic/native curves default to zero. A non-zero persistent
        # source vertex id is therefore the binding marker.
        if vertex_id <= 0:
            continue

        slot_index = int(slot_attr.data[index].value)
        source = slots[slot_index].source if 0 <= slot_index < len(slots) else None
        fallback = int(fallback_attr.data[index].value)
        last_co = tuple(last_co_attr.data[index].vector)
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


def _set_last_source_co(sketch, curve_id, last_co):
    curve_data, curve_index, _ = get_curve_data(sketch, curve_id)
    if curve_data is None:
        return
    attr = curve_data.attributes.get(PROJECT_LAST_CO_ATTR)
    if attr is not None:
        attr.data[curve_index].vector = last_co


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

    for curve_id, source, vertex_id, fallback_index, last_co in list(
        iter_projected_point_bindings(sketch)
    ):
        point = PointRef(sketch, curve_id)
        # Removed curves remove/re-index their CURVE-domain binding attributes
        # automatically, so there is no orphan property bookkeeping here.
        if not point.valid:
            continue
        if source is None or getattr(source, "type", None) != "MESH":
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
            updates[curve_id] = (point, new_co, tuple(vertex.co))

    if not updates:
        return 0

    with batch_update(sketch, point_ids=set(updates.keys())):
        for curve_id, (point, co, last_co) in updates.items():
            point.co = co
            _set_last_source_co(sketch, curve_id, last_co)

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
