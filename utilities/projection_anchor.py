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

from ..model.constants import SketchCurveType
from ..model.curve_ref import LineRef, PointRef
from ..utilities.curve_data import (
    batch_update,
    ensure_attribute,
    get_curve_data,
    read_curve_id_list,
    read_uuid_list,
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


# Source object types that can drive a projection. A mesh binds to its vertices;
# a sketch/curve binds to its control points. Both carry the persistent id on the
# same POINT-domain INT attribute (INT attributes survive edits on either type).
_MESH_SOURCE = {"MESH"}
_CURVE_SOURCE = {"CURVES", "CURVE"}


def _source_point_index(source, vertex_index):
    """Local position of source element ``vertex_index`` (mesh vert or curve point)."""
    if source.type in _MESH_SOURCE:
        return Vector(source.data.vertices[vertex_index].co)
    return Vector(source.data.points[vertex_index].position)


def bind_projected_point(sketch, point, source, vertex_index):
    """Bind a native sketch point to a source element.

    The source is a mesh (bind to a vertex) or another sketch/curve (bind to a
    control point). Both mint the persistent id on the source's POINT-domain
    ``VERTEX_ID_ATTR`` so the reproject can find the element after edits.
    """
    if source is None or source.type not in (_MESH_SOURCE | _CURVE_SOURCE):
        raise TypeError("Projected geometry source must be a mesh or sketch/curve")

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
    attributes[PROJECT_LAST_CO_ATTR].data[curve_index].vector = _source_point_index(
        source, vertex_index
    )
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


def _resolve_curve_point(curve_data, vertex_id, fallback_index, last_co):
    """Position of the source control point bound by ``vertex_id`` (curve source).

    Reads the ORIGINAL curve data (a sketch's control points hold the solved
    positions), not an evaluated object -- the evaluated geometry of a sketch is
    its generated mesh, which does not carry the control points.
    """
    points = getattr(curve_data, "points", None)
    if points is None:
        return None
    attr = curve_data.attributes.get(VERTEX_ID_ATTR)
    if attr is not None and attr.domain == "POINT":
        for i, item in enumerate(attr.data):
            if int(item.value) == vertex_id and i < len(points):
                return Vector(points[i].position)
    if 0 <= fallback_index < len(points):
        return Vector(points[fallback_index].position)
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
        source_type = getattr(source, "type", None)
        if source is None or source_type not in (_MESH_SOURCE | _CURVE_SOURCE):
            continue
        if not (sketch_changed or force or _source_changed(source, changed)):
            continue
        if source.mode == "EDIT":
            # The original mesh/attribute state is transient in Edit Mode. It is
            # reconciled when Blender emits the update on leaving Edit Mode.
            continue

        # A mesh source reads its evaluated vertices (deform/modifiers apply); a
        # sketch/curve source reads its original control points (the solver
        # writes solved positions there, and its evaluated data is a mesh).
        if source_type in _MESH_SOURCE:
            eval_ob = source_cache.get(source)
            if eval_ob is None:
                eval_ob = source.evaluated_get(depsgraph)
                source_cache[source] = eval_ob
            vertex = _resolve_evaluated_vertex(
                eval_ob, vertex_id, fallback_index, last_co
            )
            if vertex is None:
                continue
            source_co = Vector(vertex.co)
            world = eval_ob.matrix_world @ source_co
        else:
            source_co = _resolve_curve_point(
                source.original.data, vertex_id, fallback_index, last_co
            )
            if source_co is None:
                continue
            world = source.matrix_world @ source_co

        local = owner.matrix_world.inverted() @ world
        new_co = Vector((local.x, local.y))
        if (point.co - new_co).length > 1e-7:
            updates[curve_id] = (point, new_co, tuple(source_co))

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


def find_projected_point(sketch, source, vertex_index):
    """Return an existing valid ``PointRef`` bound to ``(source, vertex_index)``.

    Lets repeated element picks reuse a shared corner instead of stacking
    duplicate points, so an edge and an adjacent face project as one connected
    outline. Matched on the fallback vertex index (stable at creation time).
    """
    for curve_id, bound_source, _vid, fallback, _last in iter_projected_point_bindings(
        sketch
    ):
        if bound_source == source and fallback == int(vertex_index):
            point = PointRef(sketch, curve_id)
            if point.valid:
                return point
    return None


def _line_exists_between(sketch, p1, p2):
    """Whether a native line already connects ``p1`` and ``p2`` (either order).

    Re-projecting the same edge or face reuses its already-projected points, so
    without this the connecting lines would stack a fresh duplicate every time.
    """
    curve_data = sketch.data
    type_attr = curve_data.attributes.get("sketch_type")
    if not type_attr:
        return False
    starts = read_uuid_list(curve_data, "start_point_id")
    ends = read_uuid_list(curve_data, "end_point_id")
    wanted = {p1.curve_id, p2.curve_id}
    for index in range(len(curve_data.curves)):
        if type_attr.data[index].value != SketchCurveType.LINE:
            continue
        if {starts[index], ends[index]} == wanted:
            return True
    return False


def project_mesh_element(sketch, source, elem_type, elem_index, construction=True):
    """Project a single picked mesh element (``VERTEX``/``EDGE``/``FACE``).

    Returns ``(new_points, new_lines)``. Shared vertices are reused within the
    call and against already-projected points, so picking several elements builds
    one connected set of live native curves. This is the element-granular
    counterpart to :func:`project_mesh_object`; both go through
    :func:`bind_projected_point`, so the live-binding storage is identical.

    NOTE (prototype): ``elem_index`` is treated as an index into the source's
    original mesh. Index-changing modifiers on the source are not yet remapped.
    """
    if source is None or source.type != "MESH":
        raise TypeError("Source must be a mesh object")
    mesh = source.data
    owner = sketch.target_object
    inv = owner.matrix_world.inverted()

    local_points = {}
    counters = {"points": 0, "lines": 0}

    def get_point(vertex_index):
        vertex_index = int(vertex_index)
        cached = local_points.get(vertex_index)
        if cached is not None:
            return cached
        existing = find_projected_point(sketch, source, vertex_index)
        if existing is not None:
            local_points[vertex_index] = existing
            return existing
        co = inv @ (source.matrix_world @ mesh.vertices[vertex_index].co)
        point = PointRef.create(
            sketch,
            (co.x, co.y),
            construction=construction,
            fixed=True,
            name="Projected Point",
        )
        bind_projected_point(sketch, point, source, vertex_index)
        local_points[vertex_index] = point
        counters["points"] += 1
        return point

    def connect(v0, v1):
        p0, p1 = get_point(v0), get_point(v1)
        # Reuse an existing projected line so re-picking the same edge/face
        # doesn't stack duplicate segments on the shared points.
        if _line_exists_between(sketch, p0, p1):
            return
        LineRef.create(
            sketch,
            p0,
            p1,
            construction=construction,
            name="Projected Line",
        )
        counters["lines"] += 1

    with batch_update(sketch):
        if elem_type == "VERTEX":
            get_point(elem_index)
        elif elem_type == "EDGE":
            v0, v1 = mesh.edges[elem_index].vertices
            connect(v0, v1)
        elif elem_type == "FACE":
            verts = list(mesh.polygons[elem_index].vertices)
            for i, v0 in enumerate(verts):
                connect(v0, verts[(i + 1) % len(verts)])
        else:
            raise ValueError(f"Unsupported element type: {elem_type!r}")

    return counters["points"], counters["lines"]


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


def _source_point_flat_index(source_point):
    """Flat index of a source PointRef's control point in ``source.data.points``."""
    if not source_point._resolve():
        return None
    return source_point._curve_slice.points[0].index


def project_curves_object(sketch, source, construction=True):
    """Project a source sketch's line segments onto ``sketch`` as live curves.

    Reads the source sketch's line curves and their endpoint points, creating a
    projected point per shared source point (deduplicated) and a projected line
    per source segment. Endpoints are fixed; their positions are driven by the
    source sketch's control points. Standalone points and arcs/circles are not
    projected in this first slice (an arc/circle projects to an ellipse on a
    non-parallel plane, which has no native representation). Returns
    ``(points, lines, skipped_curves)`` where ``skipped_curves`` counts the
    arcs/circles that were not projected, for user feedback.
    """
    if source is None or source.type not in _CURVE_SOURCE:
        raise TypeError("Source must be a sketch or curve object")

    from ..model.constants import SketchCurveType
    from ..model.curve_ref import LineRef as _LineRef
    from ..model.sketch_ref import Sketch
    from ..utilities.curve_data import get_curve_type, read_curve_id_list

    src_sketch = Sketch(source)
    src_data = source.data
    owner = sketch.target_object
    inv = owner.matrix_world.inverted()

    projected_by_src_point = {}
    points = []
    lines = []
    skipped_curves = 0

    def _project_point(src_point):
        # Deduplicate shared endpoints so coincident source points become one
        # projected point (and thus a shared line endpoint).
        src_cid = src_point.curve_id
        existing = projected_by_src_point.get(src_cid)
        if existing is not None:
            return existing
        flat_index = _source_point_flat_index(src_point)
        if flat_index is None:
            return None
        local = inv @ src_point.location  # source world -> active sketch local
        projected = PointRef.create(
            sketch,
            (local.x, local.y),
            construction=construction,
            fixed=True,
            name="Projected Point",
        )
        bind_projected_point(sketch, projected, source, flat_index)
        projected_by_src_point[src_cid] = projected
        points.append(projected)
        return projected

    with batch_update(sketch):
        for src_cid in read_curve_id_list(src_data):
            if not src_cid:
                continue
            src_type = get_curve_type(src_sketch, src_cid)
            if src_type == SketchCurveType.LINE:
                src_line = _LineRef(src_sketch, src_cid)
                p1_src, p2_src = src_line.p1, src_line.p2
                if p1_src is None or p2_src is None:
                    continue
                p1 = _project_point(p1_src)
                p2 = _project_point(p2_src)
                if p1 is None or p2 is None:
                    continue
                line = LineRef.create(
                    sketch, p1, p2, construction=construction, name="Projected Line"
                )
                lines.append(line)
            elif src_type == SketchCurveType.POINT:
                # A point projects to a point at any angle -- project standalone
                # points too. Line endpoints are already deduped via curve_id, so
                # a point that is also an endpoint is not duplicated.
                _project_point(PointRef(src_sketch, src_cid))
            elif src_type in (SketchCurveType.ARC, SketchCurveType.CIRCLE):
                skipped_curves += 1

    return points, lines, skipped_curves
