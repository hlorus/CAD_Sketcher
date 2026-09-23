"""Conversion-node helpers shared by the asset and programmatic paths.

The standard Blender 5.2 conversion path welds sketch endpoints by identity.
Named POINT/CURVE attributes are allowed to propagate generically through the
wire path. CURVE values are re-homed onto EDGE before the weld so different
segment values cannot be averaged at shared corners. The non-fill path keeps
that welded mesh-wire representation, which preserves exact per-segment EDGE
values and feeds downstream mesh-capable node tools directly. Fill Curve is the
only topology boundary that drops attributes, so anonymous captures bridge
values across that boundary without spatial/nearest sampling.

There is one shared ``CAD Sketcher Convert`` group. Attribute definitions only
change the small bridge section in that same group; no per-schema node-group
variants are created or rebound.
"""

import math

import bpy

from ..model.constants import SketchCurveType

CONVERT_NODE_GROUP = "CAD Sketcher Convert"
VERTEX_ID_ATTR = "id"
FACE_ID_ATTR = "cad_sketcher_face_id"
SOURCE_CURVE_ID_ATTR = ".cad_sketcher_source_curve_id"
SOURCE_ENDPOINT_ID_ATTR = ".cad_sketcher_source_endpoint_id"

GENERATED_ID_VERSION = 2
CONVERT_VERSION = 24

# Input naming the sketch a body is built from. A body is a mesh object with no
# geometry of its own: the sketch's curves are pulled in here, so one modifier
# reads the source and meshes it (see utilities/body.py). Left unset the group
# converts the geometry it is handed, which is how a sketch's own modifier ran
# before bodies existed.
SKETCH_INPUT = "Sketch"

# Input exposing how finely arcs and circles are tessellated.
ANGULAR_RESOLUTION_INPUT = "Angular Resolution"
# Matches the Bezier default of 12 edges per 90 degree segment, the output before
# the input existed.
DEFAULT_ANGULAR_RESOLUTION = math.radians(7.5)
# Finest allowed angle; also the node-side guard, since a modifier value can bypass
# the socket's soft limits (and a 0 here tessellated circles until Blender hung).
MIN_ANGULAR_RESOLUTION = math.radians(0.1)

_CHILD_ID_MULTIPLIER = 1_000_003
_VERTEX_ROLE = 0x13579
_FACE_ROLE = 0x2468B


def _int_compare(nodes, links, operation, value):
    cmp = nodes.new("FunctionNodeCompare")
    cmp.data_type = "INT"
    cmp.operation = operation
    a, b = (s for s in cmp.inputs if s.enabled and s.type == "INT")
    b.default_value = value
    return cmp, a


def _is_identity_group(ng) -> bool:
    return any(n.bl_idname == "GeometryNodeMergePoints" for n in ng.nodes)


def _identity_weld_available() -> bool:
    """Whether the Merge Points node (identity weld) exists (Blender 5.2+).

    Older Blender has no identity weld, so the converter falls back to merging
    coincident endpoints by distance (see build_convert_node_group)."""
    return bpy.app.version >= (5, 2, 0)


def normalize_attribute_definitions(attribute_definitions):
    """Return stable POINT/CURVE specs used by the shared conversion bridge."""
    specs = []
    seen = set()
    for entry in attribute_definitions or ():
        name = str(entry.get("name", "")).strip()
        data_type = str(entry.get("type", "")).upper()
        domain = str(entry.get("domain", "")).upper()
        key = (name, data_type, domain)
        if not name or key in seen:
            continue
        if data_type not in {"BOOLEAN", "INT", "FLOAT"}:
            continue
        if domain not in {"POINT", "CURVE"}:
            continue
        seen.add(key)
        specs.append({"name": name, "type": data_type, "domain": domain})
    specs.sort(key=lambda item: (item["name"], item["domain"], item["type"]))
    return specs


def attribute_signature(specs):
    return repr(tuple((x["name"], x["type"], x["domain"]) for x in specs))


def _capture_value(nodes, links, geometry, entry, domain, item_name):
    """Bake a named value anonymously on ``domain`` and return geometry/value."""
    named = nodes.new("GeometryNodeInputNamedAttribute")
    named.data_type = entry["type"]
    named.inputs["Name"].default_value = entry["name"]

    capture = nodes.new("GeometryNodeCaptureAttribute")
    capture.domain = domain
    capture.capture_items.clear()
    capture.capture_items.new(entry["type"], item_name)
    links.new(geometry, capture.inputs["Geometry"])
    links.new(named.outputs["Attribute"], capture.inputs[item_name])
    return capture.outputs["Geometry"], capture.outputs[item_name]


def _remove_named_attribute(nodes, links, geometry, name):
    remove = nodes.new("GeometryNodeRemoveAttribute")
    remove.inputs["Name"].default_value = name
    links.new(geometry, remove.inputs["Geometry"])
    return remove.outputs["Geometry"]


def _store_segment_attributes_on_edges(nodes, links, geometry, specs):
    """Move per-segment CURVE values to EDGE before Merge Points.

    Curve to Mesh initially adapts a CURVE value onto mesh elements. Merely
    storing the same name on EDGE is not sufficient when a same-named attribute
    already exists on another domain: Blender keeps that original domain and the
    shared corner can still become 15/25/35 for source values 10/20/30/40.

    Capture the value anonymously on EDGE first, remove the adapted named copy,
    then restore that name on EDGE. The weld therefore sees one value per source
    segment and never has to combine adjacent segment values at a shared point.
    """
    current = geometry
    for index, entry in enumerate(specs):
        if entry["domain"] != "CURVE":
            continue
        item_name = f"segment_{index}"
        current, value = _capture_value(nodes, links, current, entry, "EDGE", item_name)
        current = _remove_named_attribute(nodes, links, current, entry["name"])

        store = nodes.new("GeometryNodeStoreNamedAttribute")
        store.data_type = entry["type"]
        store.domain = "EDGE"
        store.inputs["Name"].default_value = entry["name"]
        links.new(current, store.inputs["Geometry"])
        links.new(value, store.inputs["Value"])
        current = store.outputs["Geometry"]
    return current


def _transfer_attributes_after_fill(nodes, links, geometry, source, specs):
    """Re-establish attribute values on the filled mesh by nearest source element.

    Fill Curve drops named attributes (and a captured anonymous value does not
    cross it either), so pull them back from the pre-fill welded ``source`` mesh,
    which still carries them: POINT values by nearest vertex, per-segment (CURVE)
    values by nearest EDGE. Each filled boundary element has an exact coincident
    source element (nearest distance 0), so boundary values are recovered exactly;
    interior fill elements take the nearest boundary value, which is harmless (a
    flat fill's interior has no owning segment by definition). Sampling reads
    straight from the source rather than merging, so there is no corner averaging.
    """
    current = geometry
    for entry in specs:
        domain = "POINT" if entry["domain"] == "POINT" else "EDGE"

        nearest = nodes.new("GeometryNodeSampleNearest")
        nearest.domain = domain
        links.new(source, nearest.inputs["Geometry"])

        named = nodes.new("GeometryNodeInputNamedAttribute")
        named.data_type = entry["type"]
        named.inputs["Name"].default_value = entry["name"]

        sample = nodes.new("GeometryNodeSampleIndex")
        sample.data_type = entry["type"]
        sample.domain = domain
        links.new(source, sample.inputs["Geometry"])
        links.new(named.outputs["Attribute"], sample.inputs["Value"])
        links.new(nearest.outputs["Index"], sample.inputs["Index"])

        # Fill Curve already dropped the name here, so Store re-creates it fresh;
        # a Remove first would only warn "attribute does not exist" on every eval.
        store = nodes.new("GeometryNodeStoreNamedAttribute")
        store.data_type = entry["type"]
        store.domain = domain
        store.inputs["Name"].default_value = entry["name"]
        links.new(current, store.inputs["Geometry"])
        links.new(sample.outputs["Value"], store.inputs["Value"])
        current = store.outputs["Geometry"]
    return current


def _named_int(nodes, name):
    node = nodes.new("GeometryNodeInputNamedAttribute")
    node.data_type = "INT"
    node.inputs["Name"].default_value = name
    return node.outputs["Attribute"]


def _local_child_index(nodes, links, source, domain):
    accumulate = nodes.new("GeometryNodeAccumulateField")
    accumulate.data_type = "INT"
    accumulate.domain = domain
    accumulate.inputs["Value"].default_value = 1
    links.new(source, accumulate.inputs["Group ID"])
    return accumulate.outputs["Leading"]


def _child_id(nodes, links, source, local_index, role):
    mix = nodes.new("FunctionNodeIntegerMath")
    mix.operation = "MULTIPLY_ADD"
    mix.inputs[1].default_value = _CHILD_ID_MULTIPLIER
    links.new(source, mix.inputs[0])
    links.new(local_index, mix.inputs[2])

    add_role = nodes.new("FunctionNodeIntegerMath")
    add_role.operation = "ADD"
    add_role.inputs[1].default_value = role
    links.new(mix.outputs[0], add_role.inputs[0])
    return add_role.outputs[0]


def _store_int_attribute(nodes, links, geometry, value, name, domain):
    store = nodes.new("GeometryNodeStoreNamedAttribute")
    store.data_type = "INT"
    store.domain = domain
    store.inputs["Name"].default_value = name
    links.new(geometry, store.inputs["Geometry"])
    links.new(value, store.inputs["Value"])
    return store.outputs["Geometry"]


def _normalize_winding(nodes, links, curve):
    """Give every spline a consistent (CCW) winding before Fill Curve.

    Fill Curve's ``N-gons`` mode decides outer-vs-hole from winding, not a pure
    even-odd rule: a loop wound opposite its container loses its hole and fills
    solid. Mesh to Curve derives each loop's winding from edge-traversal order,
    which is not stable across evaluations (it shifts when vertex indices change,
    e.g. as entities are added), so the fill would otherwise flip between a ring
    and a solid face. Reversing every spline whose signed area is negative pins
    all loops to one winding, making the fill deterministic.

    Signed area is the shoelace sum ``sum(cross(P, P_next).z)`` over each spline
    (its sign is all we need); ``P_next`` wraps within the spline for cyclic
    loops. Open (non-cyclic) splines aren't filled, so their sign is harmless.
    """
    # Per-spline group id, derived WITHOUT the topology-global Index (generated
    # ids must not depend on it; see test_generated_id_nodes_use_source_local...).
    # Spline Parameter's Index is 0 at each spline's first point, so a running
    # count of those starts numbers the splines, constant within each.
    spline_param = nodes.new("GeometryNodeSplineParameter")
    is_start, is_start_a = _int_compare(nodes, links, "EQUAL", 0)
    links.new(spline_param.outputs["Index"], is_start_a)
    spline_id = nodes.new("GeometryNodeAccumulateField")
    spline_id.data_type = "INT"
    spline_id.domain = "POINT"
    links.new(is_start.outputs["Result"], spline_id.inputs["Value"])

    # P and the next point's position within the same spline (cyclic wrap).
    pos = nodes.new("GeometryNodeInputPosition")
    offset = nodes.new("GeometryNodeOffsetPointInCurve")
    offset.inputs["Offset"].default_value = 1
    next_pos = nodes.new("GeometryNodeSampleIndex")
    next_pos.data_type = "FLOAT_VECTOR"
    next_pos.domain = "POINT"
    links.new(curve, next_pos.inputs["Geometry"])
    links.new(pos.outputs["Position"], next_pos.inputs["Value"])
    links.new(offset.outputs["Point Index"], next_pos.inputs["Index"])

    # cross(P, P_next).z = P.x * Pn.y - P.y * Pn.x -- the shoelace term.
    cross = nodes.new("ShaderNodeVectorMath")
    cross.operation = "CROSS_PRODUCT"
    links.new(pos.outputs["Position"], cross.inputs[0])
    links.new(next_pos.outputs["Value"], cross.inputs[1])
    sep = nodes.new("ShaderNodeSeparateXYZ")
    links.new(cross.outputs["Vector"], sep.inputs["Vector"])

    # Sum the term per spline; negative total => clockwise => reverse it.
    acc = nodes.new("GeometryNodeAccumulateField")
    acc.data_type = "FLOAT"
    acc.domain = "POINT"
    links.new(sep.outputs["Z"], acc.inputs["Value"])
    links.new(spline_id.outputs["Leading"], acc.inputs["Group ID"])

    cw = nodes.new("FunctionNodeCompare")
    cw.data_type = "FLOAT"
    cw.operation = "LESS_THAN"
    a_in = next(s for s in cw.inputs if s.enabled and s.type == "VALUE")
    links.new(acc.outputs["Total"], a_in)

    reverse = nodes.new("GeometryNodeReverseCurve")
    links.new(curve, reverse.inputs["Curve"])
    links.new(cw.outputs["Result"], reverse.inputs["Selection"])
    return reverse.outputs["Curve"]


def add_generated_id_nodes(nodes, links, geometry):
    """Append stable generated vertex/face ids and return the new geometry."""
    curve_source = _named_int(nodes, SOURCE_CURVE_ID_ATTR)
    endpoint_source = _named_int(nodes, SOURCE_ENDPOINT_ID_ATTR)

    vertex_local = _local_child_index(nodes, links, curve_source, "POINT")
    interior_id = _child_id(nodes, links, curve_source, vertex_local, _VERTEX_ROLE)

    endpoint_set, endpoint_a = _int_compare(nodes, links, "NOT_EQUAL", 0)
    links.new(endpoint_source, endpoint_a)
    vertex_id = nodes.new("GeometryNodeSwitch")
    vertex_id.input_type = "INT"
    links.new(endpoint_set.outputs["Result"], vertex_id.inputs["Switch"])
    links.new(interior_id, vertex_id.inputs["False"])
    links.new(endpoint_source, vertex_id.inputs["True"])

    geometry = _store_int_attribute(
        nodes,
        links,
        geometry,
        vertex_id.outputs["Output"],
        VERTEX_ID_ATTR,
        "POINT",
    )

    face_source = _named_int(nodes, VERTEX_ID_ATTR)
    face_local = _local_child_index(nodes, links, face_source, "FACE")
    face_id = _child_id(nodes, links, face_source, face_local, _FACE_ROLE)
    return _store_int_attribute(nodes, links, geometry, face_id, FACE_ID_ATTR, "FACE")


def ensure_generated_id_nodes(node_group):
    """Attach the stable-id tail to a loaded 5.0 conversion asset once."""
    if node_group.get("cad_generated_id_version") == GENERATED_ID_VERSION:
        return node_group

    output = next(
        (n for n in node_group.nodes if n.bl_idname == "NodeGroupOutput"), None
    )
    if output is None:
        return node_group
    geometry_input = output.inputs.get("Geometry")
    if geometry_input is None or not geometry_input.links:
        return node_group

    upstream = geometry_input.links[0].from_socket
    node_group.links.remove(geometry_input.links[0])
    geometry = add_generated_id_nodes(node_group.nodes, node_group.links, upstream)
    node_group.links.new(geometry, geometry_input)
    node_group["cad_generated_id_version"] = GENERATED_ID_VERSION
    return node_group


def input_identifier(node_group, name: str):
    """Identifier of the group input socket called ``name``, or None."""
    for item in node_group.interface.items_tree:
        if (
            getattr(item, "item_type", "") == "SOCKET"
            and getattr(item, "in_out", "") == "INPUT"
            and item.name == name
        ):
            return item.identifier
    return None


def _set_curve_resolution(nodes, links, curve, angle):
    """Tessellate arcs and circles by a maximum angle per edge.

    Their splines are Bezier segments of at most 90 degrees each, so giving every
    segment ``ceil(90 degrees / angle)`` edges keeps the edge angle even whatever
    the sweep. Lines are left alone (they keep resolution 1 from creation).
    """
    sketch_type = _named_int(nodes, "sketch_type")
    is_arc, arc_a = _int_compare(nodes, links, "EQUAL", SketchCurveType.ARC)
    links.new(sketch_type, arc_a)
    is_circle, circle_a = _int_compare(nodes, links, "EQUAL", SketchCurveType.CIRCLE)
    links.new(sketch_type, circle_a)
    curved = nodes.new("FunctionNodeBooleanMath")
    curved.operation = "OR"
    links.new(is_arc.outputs["Result"], curved.inputs[0])
    links.new(is_circle.outputs["Result"], curved.inputs[1])

    # Guard the divide against a zero (or absurdly small) angle.
    clamped = nodes.new("ShaderNodeMath")
    clamped.operation = "MAXIMUM"
    clamped.inputs[1].default_value = MIN_ANGULAR_RESOLUTION
    links.new(angle, clamped.inputs[0])
    steps = nodes.new("ShaderNodeMath")
    steps.operation = "DIVIDE"
    steps.inputs[0].default_value = math.pi / 2
    links.new(clamped.outputs["Value"], steps.inputs[1])
    # Float noise must not tip an exact ratio (90 / 7.5 = 12) up to the next count.
    nudge = nodes.new("ShaderNodeMath")
    nudge.operation = "SUBTRACT"
    nudge.inputs[1].default_value = 1e-3
    links.new(steps.outputs["Value"], nudge.inputs[0])
    ceil = nodes.new("ShaderNodeMath")
    ceil.operation = "CEIL"
    links.new(nudge.outputs["Value"], ceil.inputs[0])

    set_resolution = nodes.new("GeometryNodeSetSplineResolution")
    links.new(curve, set_resolution.inputs["Geometry"])
    links.new(curved.outputs["Boolean"], set_resolution.inputs["Selection"])
    links.new(ceil.outputs["Value"], set_resolution.inputs["Resolution"])
    return set_resolution.outputs["Geometry"]


def _input_sockets(node_group):
    return [
        item
        for item in node_group.interface.items_tree
        if getattr(item, "item_type", "") == "SOCKET"
        and getattr(item, "in_out", "") == "INPUT"
        and item.socket_type != "NodeSocketGeometry"
    ]


def _snapshot_modifier_inputs(node_group):
    """Input values of every modifier using ``node_group``, keyed by socket name.

    Rebuilding recreates the interface, which re-mints socket identifiers, and
    modifier inputs are keyed by identifier: without this a rebuild (a version
    bump or an attribute definition change) would reset every sketch's Fill and
    Angular Resolution to the defaults.
    """
    from ..operators.modifiers import get_modifier_input

    sockets = _input_sockets(node_group)
    saved = []
    for obj in bpy.data.objects:
        for mod in obj.modifiers:
            if getattr(mod, "type", None) != "NODES" or mod.node_group != node_group:
                continue
            values = {}
            for item in sockets:
                try:
                    values[item.name] = get_modifier_input(mod, item.identifier)
                except Exception:
                    pass
            saved.append((mod, values))
    return saved


def _restore_modifier_inputs(node_group, saved) -> None:
    """Re-apply values from :func:`_snapshot_modifier_inputs` by socket name.

    A socket the old group didn't have gets its default. Left alone, the
    modifier's value for it reads as 0: an upgraded file then meshed every circle
    at a 0 angular resolution and hung Blender.
    """
    from ..operators.modifiers import set_modifier_input

    sockets = _input_sockets(node_group)
    for mod, values in saved:
        for item in sockets:
            value = values.get(item.name, item.default_value)
            # Files saved after that broken upgrade carry the 0; repair them too.
            if item.name == ANGULAR_RESOLUTION_INPUT and value < MIN_ANGULAR_RESOLUTION:
                value = item.default_value
            try:
                set_modifier_input(mod, item.identifier, value)
            except Exception:
                pass


def _source_geometry(nodes, links, gi):
    """The curves to convert: the sketch named by ``Sketch``, plus our own.

    Read in the modifier object's own space, so a body whose transform matches
    its sketch holds the geometry planar locally and correct in the world.
    Realized, so an instanced source still resolves to real data downstream.
    """
    info = nodes.new("GeometryNodeObjectInfo")
    info.transform_space = "RELATIVE"
    links.new(gi.outputs[SKETCH_INPUT], info.inputs["Object"])

    realize = nodes.new("GeometryNodeRealizeInstances")
    links.new(info.outputs["Geometry"], realize.inputs["Geometry"])

    join = nodes.new("GeometryNodeJoinGeometry")
    links.new(gi.outputs["Geometry"], join.inputs["Geometry"])
    links.new(realize.outputs["Geometry"], join.inputs["Geometry"])
    return join.outputs["Geometry"]


def build_convert_node_group(
    name: str = CONVERT_NODE_GROUP, attribute_definitions=None
):
    """Build/update the one shared identity-weld converter in place.

    Passing ``attribute_definitions`` updates only this same group's domain-aware
    bridge. Omitting it reuses a current group unchanged, which lets every sketch
    keep the same modifier binding.
    """
    requested = attribute_definitions is not None
    specs = normalize_attribute_definitions(attribute_definitions)
    signature = attribute_signature(specs)

    ng = bpy.data.node_groups.get(name)
    saved = []
    if ng is not None:
        if ng.get("cad_convert_version") == CONVERT_VERSION and (
            not requested or ng.get("cad_convert_attribute_signature", "") == signature
        ):
            return ng
        saved = _snapshot_modifier_inputs(ng)
        ng.nodes.clear()
        ng.links.clear()
        ng.interface.clear()
    else:
        ng = bpy.data.node_groups.new(name, "GeometryNodeTree")

    iface = ng.interface
    iface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    iface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    sketch = iface.new_socket(
        SKETCH_INPUT, in_out="INPUT", socket_type="NodeSocketObject"
    )
    sketch.description = "Sketch whose curves this body is built from"
    fill = iface.new_socket("Fill", in_out="INPUT", socket_type="NodeSocketBool")
    fill.default_value = True
    resolution = iface.new_socket(
        ANGULAR_RESOLUTION_INPUT, in_out="INPUT", socket_type="NodeSocketFloat"
    )
    resolution.subtype = "ANGLE"
    resolution.default_value = DEFAULT_ANGULAR_RESOLUTION
    resolution.min_value = MIN_ANGULAR_RESOLUTION
    resolution.max_value = math.radians(90)
    resolution.description = "Maximum angle per edge when arcs and circles are meshed"

    nodes, links = ng.nodes, ng.links
    gi = nodes.new("NodeGroupInput")
    go = nodes.new("NodeGroupOutput")

    construction = nodes.new("GeometryNodeInputNamedAttribute")
    construction.data_type = "BOOLEAN"
    construction.inputs["Name"].default_value = "construction"

    spline_len = nodes.new("GeometryNodeSplineLength")
    degenerate, degen_a = _int_compare(nodes, links, "LESS_THAN", 2)
    links.new(spline_len.outputs["Point Count"], degen_a)

    drop = nodes.new("FunctionNodeBooleanMath")
    drop.operation = "OR"
    links.new(construction.outputs["Attribute"], drop.inputs[0])
    links.new(degenerate.outputs["Result"], drop.inputs[1])

    delete = nodes.new("GeometryNodeDeleteGeometry")
    delete.domain = "CURVE"
    links.new(_source_geometry(nodes, links, gi), delete.inputs["Geometry"])
    links.new(drop.outputs["Boolean"], delete.inputs["Selection"])

    to_mesh = nodes.new("GeometryNodeCurveToMesh")
    curve = _set_curve_resolution(
        nodes, links, delete.outputs["Geometry"], gi.outputs[ANGULAR_RESOLUTION_INPUT]
    )
    links.new(curve, to_mesh.inputs["Curve"])
    wire_mesh = _store_segment_attributes_on_edges(
        nodes, links, to_mesh.outputs["Mesh"], specs
    )

    merge_id = nodes.new("GeometryNodeInputNamedAttribute")
    merge_id.data_type = "INT"
    merge_id.inputs["Name"].default_value = "merge_id"

    # Weld only true segment endpoints (valence 1) and standalone point entities
    # (valence 0) -- both have fewer than two neighbours. Tessellated interior
    # vertices (valence 2) are excluded, so their interpolated id is harmless.
    # Welding valence-0 points lets a point entity collapse onto the coincident
    # segment corner.
    neighbors = nodes.new("GeometryNodeInputMeshVertexNeighbors")
    is_end, end_a = _int_compare(nodes, links, "LESS_THAN", 2)
    links.new(neighbors.outputs["Vertex Count"], end_a)

    nonzero, nz_a = _int_compare(nodes, links, "NOT_EQUAL", 0)
    links.new(merge_id.outputs["Attribute"], nz_a)
    weld = nodes.new("FunctionNodeBooleanMath")
    weld.operation = "AND"
    links.new(is_end.outputs["Result"], weld.inputs[0])
    links.new(nonzero.outputs["Result"], weld.inputs[1])

    if _identity_weld_available():
        merge = nodes.new("GeometryNodeMergePoints")
        links.new(wire_mesh, merge.inputs["Geometry"])
        links.new(merge_id.outputs["Attribute"], merge.inputs["Merge ID"])
        links.new(weld.outputs["Boolean"], merge.inputs["Selection"])
    else:
        # Blender < 5.2 has no identity weld (Merge Points). Merge the same
        # selected endpoints by a tiny distance instead: it only collapses points
        # that already share a position, so it matches the identity weld for the
        # coincident sketch endpoints in practice. Both nodes output "Geometry",
        # so the downstream fill/non-fill wiring below is identical.
        merge = nodes.new("GeometryNodeMergeByDistance")
        links.new(wire_mesh, merge.inputs["Geometry"])
        links.new(weld.outputs["Boolean"], merge.inputs["Selection"])
        merge.inputs["Distance"].default_value = 1e-6

    # The welded wire mesh carries POINT values on its vertices and per-segment
    # values on its edges; it feeds the non-fill path directly and is the source
    # for re-establishing POINT values on the filled mesh below.
    pre_fill = merge.outputs["Geometry"]

    to_curve = nodes.new("GeometryNodeMeshToCurve")
    links.new(pre_fill, to_curve.inputs["Mesh"])

    fill_curve = nodes.new("GeometryNodeFillCurve")
    # Fill as a single n-gon per loop; the default 'Triangles' mode fans a quad
    # into two triangles, leaving a spurious diagonal edge (a rectangle would
    # convert to 5 edges instead of 4). The mode is a 5.x menu socket, not a
    # node property -- guard so an older/renamed build simply falls back.
    try:
        fill_curve.inputs["Mode"].default_value = "N-gons"
    except Exception:
        pass
    normalized = _normalize_winding(nodes, links, to_curve.outputs["Curve"])
    links.new(normalized, fill_curve.inputs["Curve"])
    # Fill Curve drops named attributes; re-establish them on the filled mesh from
    # the pre-fill welded mesh by nearest element (POINT and per-segment EDGE).
    filled = _transfer_attributes_after_fill(
        nodes, links, fill_curve.outputs["Mesh"], pre_fill, specs
    )

    switch = nodes.new("GeometryNodeSwitch")
    switch.input_type = "GEOMETRY"
    links.new(gi.outputs["Fill"], switch.inputs["Switch"])
    # Keep the non-fill path as the welded edge mesh. Sending these segment
    # values through Mesh to Curve would collapse a multi-segment loop to one
    # spline and adapt adjacent EDGE values onto shared curve points, recreating
    # the meaningless 15/25/35 corner averages the EDGE capture is meant to avoid.
    links.new(pre_fill, switch.inputs["False"])
    links.new(filled, switch.inputs["True"])

    geometry = add_generated_id_nodes(nodes, links, switch.outputs["Output"])
    links.new(geometry, go.inputs["Geometry"])

    ng["cad_convert_version"] = CONVERT_VERSION
    ng["cad_generated_id_version"] = GENERATED_ID_VERSION
    ng["cad_convert_attribute_signature"] = signature
    _restore_modifier_inputs(ng, saved)
    return ng
