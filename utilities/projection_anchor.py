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
from ..model.curve_ref import ArcRef, CircleRef, LineRef, PointRef
from ..utilities.curve_data import (
    batch_update,
    ensure_attribute,
    get_curve_data,
    read_curve_id_list,
    read_uuid_list,
)
from ..utilities.view import _dbg_vec  # TEMP DEBUG -- remove before merging

# Persistent identity on the SOURCE mesh/sketch (POINT domain). It must NOT share
# a name with the CURVE-domain binding attributes below: attribute names are
# unique per datablock regardless of domain, and a sketch can be both a source
# and a destination (projecting between two sketches). One name for both roles
# made the binding read point data by curve index, inventing bindings on ordinary
# curves that then resolved to source point 0 -- dragging them to the origin.
VERTEX_ID_ATTR = "slvs_project_src_vertex_id"
# Files written before the rename carry the source ids under the old name.
LEGACY_VERTEX_ID_ATTR = "slvs_project_vertex_id"

# Binding metadata on the SKETCH Curves datablock (CURVE domain).
PROJECT_SRC_SLOT_ATTR = "slvs_project_src_slot"
PROJECT_VERTEX_ID_ATTR = "slvs_project_vertex_id"
PROJECT_VERTEX_INDEX_ATTR = "slvs_project_vertex_index"
PROJECT_LAST_CO_ATTR = "slvs_project_last_co"

_updating = False


def source_id_attr(data, create=False):
    """The POINT-domain source-id attribute of ``data``, or None.

    Migrates a legacy attribute written under the old name, but only when it
    really is the source id (POINT domain) -- on a sketch the same old name may
    be a CURVE-domain binding attribute instead, which belongs to the other role.
    """
    attributes = data.attributes
    attr = attributes.get(VERTEX_ID_ATTR)
    if attr is not None:
        return attr if attr.domain == "POINT" else None

    legacy = attributes.get(LEGACY_VERTEX_ID_ATTR)
    if legacy is not None and legacy.domain == "POINT":
        legacy.name = VERTEX_ID_ATTR
        return attributes.get(VERTEX_ID_ATTR)

    if not create:
        return None
    attributes.new(VERTEX_ID_ATTR, "INT", "POINT")
    return attributes.get(VERTEX_ID_ATTR)


def _allocate_vertex_id(mesh):
    attr = source_id_attr(mesh)
    if attr is None or len(attr.data) == 0:
        return 1
    return max((int(item.value) for item in attr.data), default=0) + 1


def ensure_vertex_id(mesh, vertex_index):
    """Return a persistent non-zero id for ``mesh.vertices[vertex_index]``."""
    attr = source_id_attr(mesh, create=True)

    current = int(attr.data[vertex_index].value)
    if current:
        return current

    current = _allocate_vertex_id(mesh)
    attr.data[vertex_index].value = current
    return current


def _ensure_projection_attributes(curve_data):
    # A sketch that was projected FROM under the old name holds the source id on
    # the POINT domain under the binding's name. Move it aside first, or the
    # ensure below adopts it and the binding reads point data by curve index.
    source_id_attr(curve_data)
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


def _source_point_count(source):
    """Number of source elements (mesh vertices or curve control points)."""
    data = source.data
    return len(data.vertices if source.type in _MESH_SOURCE else data.points)


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
    attrs = (slot_attr, vertex_id_attr, fallback_attr, last_co_attr)
    if not all(attrs) or any(a.domain != "CURVE" for a in attrs):
        # A binding is per curve. A same-named POINT attribute is the source id
        # of a sketch that is also projected FROM, not a binding (see the note on
        # VERTEX_ID_ATTR); reading it by curve index invents bindings.
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
    attr = source_id_attr(mesh)
    if attr is not None and vertex_id:
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
    attr = source_id_attr(curve_data)
    if attr is not None and vertex_id:
        for i, item in enumerate(attr.data):
            if int(item.value) == vertex_id and i < len(points):
                return Vector(points[i].position)
    if 0 <= fallback_index < len(points):
        return Vector(points[fallback_index].position)
    return None


def _source_changed(source, changed):
    """Whether this update touched ``source``. Names, see the handler body."""
    if changed is None:
        return True
    return source.name in changed or source.data.name in changed


def _set_last_source_co(sketch, curve_id, last_co):
    curve_data, curve_index, _ = get_curve_data(sketch, curve_id)
    if curve_data is None:
        return
    attr = curve_data.attributes.get(PROJECT_LAST_CO_ATTR)
    if attr is not None:
        attr.data[curve_index].vector = last_co


def _shift_circle_anchors(sketch, center_curve_id, delta):
    """Offset the anchor point of circles centered at ``center_curve_id`` by ``delta``."""
    if delta.length_squared < 1e-12:
        return
    curve_data = sketch.data
    type_attr = curve_data.attributes.get("sketch_type")
    if not type_attr:
        return
    centers = read_uuid_list(curve_data, "center_point_id")
    for index in range(len(curve_data.curves)):
        if type_attr.data[index].value != SketchCurveType.CIRCLE:
            continue
        if centers[index] == center_curve_id:
            anchor = curve_data.curves[index].points[0].index
            pos = curve_data.points[anchor].position
            curve_data.points[anchor].position = (
                pos[0] + delta[0],
                pos[1] + delta[1],
                pos[2],
            )


def refresh_projection_for_sketch(sketch, depsgraph, changed=None, force=False):
    """Reproject bound points for one sketch. Returns number of moved points."""
    owner = sketch.target_object
    if owner is None:
        return 0

    sketch_changed = (
        force or changed is None or owner.name in changed or owner.data.name in changed
    )
    if (
        owner.parent is not None
        and changed is not None
        and owner.parent.name in changed
    ):
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
            # ``source`` is a pointer property, so already an original.
            source_co = _resolve_curve_point(
                source.data, vertex_id, fallback_index, last_co
            )
            if source_co is None:
                continue
            world = source.matrix_world @ source_co

        local = owner.matrix_world.inverted() @ world
        new_co = Vector((local.x, local.y))
        if (point.co - new_co).length > 1e-7:
            # TEMP DEBUG -- remove before merging
            print(
                "[SNAP] reproject %s in %s: %s -> %s (src %s id=%s fallback=%s "
                "local=%s)"
                % (
                    curve_id[:8],
                    owner.name,
                    _dbg_vec(point.co),
                    _dbg_vec(new_co),
                    source.name,
                    vertex_id,
                    fallback_index,
                    _dbg_vec(source_co),
                ),
                flush=True,
            )
            updates[curve_id] = (point, new_co, tuple(source_co))

    if not updates:
        return 0

    with batch_update(sketch, point_ids=set(updates.keys())):
        for curve_id, (point, co, last_co) in updates.items():
            delta = co - point.co
            point.co = co
            _shift_circle_anchors(sketch, curve_id, delta)
            _set_last_source_co(sketch, curve_id, last_co)

    return len(updates)


def update_projected_geometry(context, depsgraph):
    """Depsgraph handler body for all live projected mesh references."""
    global _updating
    if _updating:
        return

    # What this update touched, by name. Matching an evaluated id to its
    # original means reading ``id.original``, and following that pointer crashes
    # Blender when the update list holds an id that is still being built -- which
    # an update right after creating objects does, so drawing a sketch could take
    # the whole session down. A name collision across id types at worst
    # reprojects something that did not need it.
    changed = set()
    for update in depsgraph.updates:
        try:
            changed.add(update.id.name)
        except (AttributeError, ReferenceError):
            continue

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


def find_projected_vertex_point(sketch, source, vertex_id):
    """Return an existing live point bound to ``source``'s ``vertex_id``, or None.

    The single dedup used by both the projection tool and the snap path: matches
    on the persistent source vertex id, which survives topology edits that
    reshuffle indices, rather than the creation-time index.
    """
    for (
        curve_id,
        bound_source,
        bound_vid,
        _fallback,
        _last_co,
    ) in iter_projected_point_bindings(sketch):
        if bound_source == source and bound_vid == vertex_id:
            existing = PointRef(sketch, curve_id)
            if existing.valid:
                return existing
    return None


def find_projected_point(sketch, source, vertex_index):
    """Return an existing valid ``PointRef`` bound to ``(source, vertex_index)``.

    Resolves the vertex to its persistent source id and matches on that (via
    :func:`find_projected_vertex_point`), so repeated element picks reuse a
    shared corner even after topology edits shuffle the raw indices.
    """
    vertex_id = ensure_vertex_id(source.data, int(vertex_index))
    return find_projected_vertex_point(sketch, source, vertex_id)


def _line_curve_id_between(sketch, p1, p2):
    """curve_id of a native line connecting ``p1`` and ``p2`` (either order), or None."""
    curve_data = sketch.data
    type_attr = curve_data.attributes.get("sketch_type")
    if not type_attr:
        return None
    starts = read_uuid_list(curve_data, "start_point_id")
    ends = read_uuid_list(curve_data, "end_point_id")
    curve_ids = read_curve_id_list(curve_data)
    wanted = {p1.curve_id, p2.curve_id}
    for index in range(len(curve_data.curves)):
        if type_attr.data[index].value != SketchCurveType.LINE:
            continue
        if {starts[index], ends[index]} == wanted:
            return curve_ids[index]
    return None


def _line_exists_between(sketch, p1, p2):
    """Whether a native line already connects ``p1`` and ``p2`` (either order).

    Re-projecting the same edge or face reuses its already-projected points, so
    without this the connecting lines would stack a fresh duplicate every time.
    """
    return _line_curve_id_between(sketch, p1, p2) is not None


def _planes_are_parallel(sketch_a, sketch_b):
    """Whether two sketches have parallel (or anti-parallel) plane frames.

    Returns ``(is_parallel, is_aligned)`` where ``is_aligned`` is True when
    plane normals point in the same direction, or False when anti-parallel.
    """
    m_a = getattr(sketch_a, "plane_matrix", None)
    m_b = getattr(sketch_b, "plane_matrix", None)
    if m_a is None or m_b is None:
        return True, True
    n_a = Vector(m_a.col[2][:3])
    n_b = Vector(m_b.col[2][:3])
    if n_a.length_squared == 0 or n_b.length_squared == 0:
        return True, True
    dot = n_a.normalized().dot(n_b.normalized())
    if abs(abs(dot) - 1.0) < 1e-4:
        return True, dot > 0
    return False, False


def _arc_exists_between(sketch, ct, start, end):
    """Whether a native arc already connects ``start`` to ``end`` around ``ct``."""
    curve_data = sketch.data
    type_attr = curve_data.attributes.get("sketch_type")
    if not type_attr:
        return False
    centers = read_uuid_list(curve_data, "center_point_id")
    starts = read_uuid_list(curve_data, "start_point_id")
    ends = read_uuid_list(curve_data, "end_point_id")
    for index in range(len(curve_data.curves)):
        if type_attr.data[index].value != SketchCurveType.ARC:
            continue
        if (
            centers[index] == ct.curve_id
            and starts[index] == start.curve_id
            and ends[index] == end.curve_id
        ):
            return True
    return False


def _circle_exists_at(sketch, ct, radius):
    """Whether a native circle already exists at center ``ct`` with approximately ``radius``."""
    curve_data = sketch.data
    type_attr = curve_data.attributes.get("sketch_type")
    if not type_attr:
        return False
    centers = read_uuid_list(curve_data, "center_point_id")
    curve_ids = read_curve_id_list(curve_data)
    for index in range(len(curve_data.curves)):
        if type_attr.data[index].value != SketchCurveType.CIRCLE:
            continue
        if centers[index] == ct.curve_id:
            c = CircleRef(sketch, curve_ids[index])
            if abs(c.radius - radius) < 1e-4:
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
        # An edge perpendicular to the sketch plane collapses to a point (e.g. a
        # side face of a cube projected edge-on). A zero-length line is useless
        # for the solver and the fill, so drop it rather than project it.
        if (p0.co - p1.co).length < 1e-6:
            return
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


def resolve_source_vertex_index(source, eval_source, eval_vertex_index):
    """Map an evaluated-mesh vertex index back to the original mesh vertex.

    Snapping picks a vertex on the *evaluated* mesh, but a live projection must
    bind the *original* vertex. When the evaluated mesh carries the persistent
    vertex id (already-tagged / previously projected vertices), match on that so
    the binding is index-independent and survives index-shuffling modifiers.
    Otherwise the index only corresponds when the modifier stack preserves vertex
    order, which we approximate by an equal vertex count. Returns the original
    index, or None when the correspondence can't be trusted.
    """
    orig_mesh = source.data
    eval_mesh = eval_source.data
    if not (0 <= eval_vertex_index < len(eval_mesh.vertices)):
        return None

    eval_attr = source_id_attr(eval_mesh)
    if eval_attr is not None:
        vid = int(eval_attr.data[eval_vertex_index].value)
        if vid:
            orig_attr = source_id_attr(orig_mesh)
            if orig_attr is not None:
                for index, item in enumerate(orig_attr.data):
                    if int(item.value) == vid and index < len(orig_mesh.vertices):
                        return index

    # No id to match on: trust the index only when topology is preserved.
    if len(eval_mesh.vertices) == len(orig_mesh.vertices):
        return eval_vertex_index
    return None


def project_mesh_vertex(sketch, source, vertex_index, construction=True, world_co=None):
    """Project a single source mesh vertex onto ``sketch`` as a live point.

    Unlike :func:`project_mesh_object` (which projects a whole mesh), this is the
    granular path used by snapping: a point snapped to one vertex gets one live
    projected reference. Repeated snaps to the same vertex are deduplicated so
    they share a single projected point (and thus become coincident). Returns the
    ``PointRef`` (fixed, driven by the source vertex), or None if the index is out
    of range.

    ``world_co`` is the world-space position to place the point at, typically the
    snap's evaluated hit. Passing it avoids a one-frame jump when the source has a
    vertex-moving modifier (the original vertex position differs from the snapped,
    evaluated one). It defaults to the original vertex position.
    """
    if source is None or source.type not in (_MESH_SOURCE | _CURVE_SOURCE):
        raise TypeError("Source must be a mesh or curve object")
    if not (0 <= vertex_index < _source_point_count(source)):
        return None

    vertex_id = ensure_vertex_id(source.data, vertex_index)
    existing = find_projected_vertex_point(sketch, source, vertex_id)
    if existing is not None:
        # TEMP DEBUG -- remove before merging
        print(
            "[SNAP] project %s#%s (id=%s): reused %s at %s"
            % (
                source.name,
                vertex_index,
                vertex_id,
                existing.curve_id[:8],
                _dbg_vec(existing.co),
            ),
            flush=True,
        )
        return existing

    owner = sketch.target_object
    if world_co is not None:
        local = owner.matrix_world.inverted() @ Vector(world_co)
    else:
        local = owner.matrix_world.inverted() @ (
            source.matrix_world @ _source_point_index(source, vertex_index)
        )
    with batch_update(sketch):
        point = PointRef.create(
            sketch,
            (local.x, local.y),
            construction=construction,
            fixed=True,
            name="Projected Point",
        )
        bind_projected_point(sketch, point, source, vertex_index)
    # TEMP DEBUG -- remove before merging
    print(
        "[SNAP] project %s#%s (id=%s): created %s at %s (world_co %s)"
        % (
            source.name,
            vertex_index,
            vertex_id,
            point.curve_id[:8],
            _dbg_vec(point.co),
            _dbg_vec(world_co),
        ),
        flush=True,
    )
    return point


def project_mesh_edge(sketch, source, vertex_index, vertex_index_2, construction=True):
    """Project a source edge onto ``sketch`` as a live line, returning its ``LineRef``.

    The snap counterpart for snapping *along* an edge (not at a vertex or the
    midpoint): the edge is projected as a live construction line bound to both
    endpoints, and the caller coincides the placed point onto that line so it
    slides along the edge instead of being pinned. Endpoints and the line are
    deduplicated, so re-snapping the same edge reuses them. Returns None if an
    index is out of range, the indices coincide, or the edge collapses to a point
    on the sketch plane (a zero-length line the solver cannot use).
    """
    if source is None or source.type not in (_MESH_SOURCE | _CURVE_SOURCE):
        raise TypeError("Source must be a mesh or curve object")
    n = _source_point_count(source)
    if not (0 <= vertex_index < n and 0 <= vertex_index_2 < n):
        return None
    if vertex_index == vertex_index_2:
        return None

    owner = sketch.target_object
    inv = owner.matrix_world.inverted()

    def _endpoint(index):
        existing = find_projected_point(sketch, source, index)
        if existing is not None:
            return existing
        local = inv @ (source.matrix_world @ _source_point_index(source, index))
        point = PointRef.create(
            sketch,
            (local.x, local.y),
            construction=construction,
            fixed=True,
            name="Projected Point",
        )
        bind_projected_point(sketch, point, source, index)
        return point

    with batch_update(sketch):
        p0 = _endpoint(vertex_index)
        p1 = _endpoint(vertex_index_2)
        # An edge perpendicular to the sketch plane collapses to a point; a
        # zero-length line is useless to the solver and to a point-on-line
        # coincidence, so bail to the static fallback.
        if (p0.co - p1.co).length < 1e-6:
            return None
        existing_line = _line_curve_id_between(sketch, p0, p1)
        if existing_line:
            return LineRef(sketch, existing_line)
        return LineRef.create(
            sketch, p0, p1, construction=construction, name="Projected Line"
        )


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
    """Project a source sketch's segments onto ``sketch`` as live curves.

    Reads the source sketch's curves and their control points, creating a
    projected point per shared source point (deduplicated) and a projected
    segment per source curve. Endpoints are fixed; their positions are driven by
    the source sketch's control points. Arcs and circles are projected when the
    source and target sketch planes are parallel; non-parallel arcs and circles
    (which project to ellipses with no native sketch representation) are skipped
    and counted in ``skipped_curves`` for user feedback. Returns
    ``(points, lines, skipped_curves)``.
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

    is_parallel, is_aligned = _planes_are_parallel(sketch, src_sketch)

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
            elif src_type == SketchCurveType.ARC:
                if not is_parallel:
                    skipped_curves += 1
                    continue
                src_arc = ArcRef(src_sketch, src_cid)
                ct_src, start_src, end_src = src_arc.ct, src_arc.start, src_arc.end
                if ct_src is None or start_src is None or end_src is None:
                    continue
                ct = _project_point(ct_src)
                p_start = _project_point(start_src)
                p_end = _project_point(end_src)
                if ct is None or p_start is None or p_end is None:
                    continue
                if not is_aligned:
                    p_start, p_end = p_end, p_start
                if not _arc_exists_between(sketch, ct, p_start, p_end):
                    arc = ArcRef.create(
                        sketch,
                        ct,
                        p_start,
                        p_end,
                        construction=construction,
                        name="Projected Arc",
                    )
                    lines.append(arc)
            elif src_type == SketchCurveType.CIRCLE:
                if not is_parallel:
                    skipped_curves += 1
                    continue
                src_circle = CircleRef(src_sketch, src_cid)
                ct_src = src_circle.ct
                if ct_src is None:
                    continue
                ct = _project_point(ct_src)
                if ct is None:
                    continue
                src_perim_world = src_sketch.plane_matrix @ Vector(
                    (ct_src.co.x + src_circle.radius, ct_src.co.y, 0.0)
                )
                target_perim_local = inv @ src_perim_world
                proj_radius = (
                    Vector((target_perim_local.x, target_perim_local.y)) - ct.co
                ).length
                if not _circle_exists_at(sketch, ct, proj_radius):
                    circle = CircleRef.create(
                        sketch,
                        ct,
                        proj_radius,
                        construction=construction,
                        name="Projected Circle",
                    )
                    lines.append(circle)

    return points, lines, skipped_curves


def project_curves_element(sketch, source, curve_id, construction=True):
    """Project a single line, arc, circle, or point of a source sketch into ``sketch``.

    ``curve_id`` is a source sketch element's id (what the reference pick returns
    for a sketch). Returns ``(points, lines, skipped)``: ``skipped`` is 1 when the
    element has no planar projection yet (arc/circle on non-parallel planes) or the
    key is not a sketch element (e.g. a raw Curves index) -- both are hoverable but
    not projectable. Endpoints and center points are reused across calls via
    ``find_projected_point``, so re-projecting the same element is idempotent.
    """
    if source is None or source.type not in _CURVE_SOURCE:
        raise TypeError("Source must be a sketch or curve object")
    if not isinstance(curve_id, str):
        return [], [], 1  # a raw Curves index key: not projectable yet

    from ..model.constants import SketchCurveType
    from ..model.curve_ref import LineRef as _LineRef
    from ..model.sketch_ref import Sketch
    from ..utilities.curve_data import get_curve_type

    src_sketch = Sketch(source)
    src_type = get_curve_type(src_sketch, curve_id)
    owner = sketch.target_object
    inv = owner.matrix_world.inverted()
    points, lines = [], []

    is_parallel, is_aligned = _planes_are_parallel(sketch, src_sketch)

    def _project(src_point):
        flat_index = _source_point_flat_index(src_point)
        if flat_index is None:
            return None
        existing = find_projected_point(sketch, source, flat_index)
        if existing is not None:
            return existing
        local = inv @ src_point.location
        projected = PointRef.create(
            sketch,
            (local.x, local.y),
            construction=construction,
            fixed=True,
            name="Projected Point",
        )
        bind_projected_point(sketch, projected, source, flat_index)
        points.append(projected)
        return projected

    with batch_update(sketch):
        if src_type == SketchCurveType.LINE:
            src_line = _LineRef(src_sketch, curve_id)
            p1_src, p2_src = src_line.p1, src_line.p2
            if p1_src is None or p2_src is None:
                return points, lines, 0
            p1 = _project(p1_src)
            p2 = _project(p2_src)
            if p1 and p2 and not _line_exists_between(sketch, p1, p2):
                lines.append(
                    LineRef.create(
                        sketch, p1, p2, construction=construction, name="Projected Line"
                    )
                )
            return points, lines, 0
        if src_type == SketchCurveType.POINT:
            _project(PointRef(src_sketch, curve_id))
            return points, lines, 0
        if src_type == SketchCurveType.ARC:
            if not is_parallel:
                return points, lines, 1
            src_arc = ArcRef(src_sketch, curve_id)
            ct_src, start_src, end_src = src_arc.ct, src_arc.start, src_arc.end
            if ct_src is None or start_src is None or end_src is None:
                return points, lines, 0
            ct = _project(ct_src)
            p_start = _project(start_src)
            p_end = _project(end_src)
            if ct and p_start and p_end:
                if not is_aligned:
                    p_start, p_end = p_end, p_start
                if not _arc_exists_between(sketch, ct, p_start, p_end):
                    lines.append(
                        ArcRef.create(
                            sketch,
                            ct,
                            p_start,
                            p_end,
                            construction=construction,
                            name="Projected Arc",
                        )
                    )
            return points, lines, 0
        if src_type == SketchCurveType.CIRCLE:
            if not is_parallel:
                return points, lines, 1
            src_circle = CircleRef(src_sketch, curve_id)
            ct_src = src_circle.ct
            if ct_src is None:
                return points, lines, 0
            ct = _project(ct_src)
            if ct:
                src_perim_world = src_sketch.plane_matrix @ Vector(
                    (ct_src.co.x + src_circle.radius, ct_src.co.y, 0.0)
                )
                target_perim_local = inv @ src_perim_world
                proj_radius = (
                    Vector((target_perim_local.x, target_perim_local.y)) - ct.co
                ).length
                if not _circle_exists_at(sketch, ct, proj_radius):
                    lines.append(
                        CircleRef.create(
                            sketch,
                            ct,
                            proj_radius,
                            construction=construction,
                            name="Projected Circle",
                        )
                    )
            return points, lines, 0
        return points, lines, 1
