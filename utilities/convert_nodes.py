"""Conversion-node helpers shared by the asset and programmatic paths.

The shipped node group (``resources/assets.blend``) closes sketch loops for
filling with Merge by Distance, which is a distance threshold and therefore
fragile: too tight and loose junctions never weld (fill vanishes), too loose and
distinct points on small models merge. Blender 5.2 adds the ``Merge Points`` node
with a ``Merge ID`` input, letting us weld by *identity* instead.

This builds an equivalent group that welds mesh vertices sharing a ``merge_id``
(see ``utilities.curve_data.compute_merge_ids``), gated to true segment endpoints
via vertex valence so tessellated interior vertices are never merged. The result
is tolerance-free and independent of sketch scale. Older Blender keeps loading
the merge-by-distance asset; both paths share the stable generated-id tail below.
"""

import bpy

CONVERT_NODE_GROUP = "CAD Sketcher Convert"
VERTEX_ID_ATTR = "cad_sketcher_vertex_id"
FACE_ID_ATTR = "cad_sketcher_face_id"
SOURCE_CURVE_ID_ATTR = ".cad_sketcher_source_curve_id"
SOURCE_ENDPOINT_ID_ATTR = ".cad_sketcher_source_endpoint_id"

GENERATED_ID_VERSION = 1

# Bump whenever the built node tree changes, so groups baked into existing files
# (or a stale merge-by-distance asset of the same name) are rebuilt on load.
CONVERT_VERSION = 4

_CHILD_ID_MULTIPLIER = 1_000_003
_VERTEX_ROLE = 0x13579
_FACE_ROLE = 0x2468B


def _int_compare(nodes, links, operation, value):
    """A Compare node on integers: returns (node, a_socket) with B set to value."""
    cmp = nodes.new("FunctionNodeCompare")
    cmp.data_type = "INT"
    cmp.operation = operation
    # data_type='INT' exposes just the two integer sockets; pick them by type so
    # this doesn't depend on socket ordering across Blender versions.
    a, b = (s for s in cmp.inputs if s.enabled and s.type == "INT")
    b.default_value = value
    return cmp, a


def _is_identity_group(ng) -> bool:
    return any(n.bl_idname == "GeometryNodeMergePoints" for n in ng.nodes)


def _named_int(nodes, name):
    node = nodes.new("GeometryNodeInputNamedAttribute")
    node.data_type = "INT"
    node.inputs["Name"].default_value = name
    return node.outputs["Attribute"]


def _local_child_index(nodes, links, source, domain):
    """Return a zero-based index accumulated independently per stable source."""
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


def add_generated_id_nodes(nodes, links, geometry):
    """Append stable generated vertex/face ids and return the new geometry.

    Source ids are hashes of the native Curves UUID attributes. Accumulate Field
    supplies an index local to each source rather than the topology-global Index,
    so inserting another curve cannot renumber unaffected children.
    """
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

    # Adapt the stable boundary ids to each fill child, then distinguish any
    # siblings with an index accumulated only within that stable source group.
    face_source = _named_int(nodes, VERTEX_ID_ATTR)
    face_local = _local_child_index(nodes, links, face_source, "FACE")
    face_id = _child_id(nodes, links, face_source, face_local, _FACE_ROLE)
    return _store_int_attribute(
        nodes, links, geometry, face_id, FACE_ID_ATTR, "FACE"
    )


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


def build_convert_node_group(name: str = CONVERT_NODE_GROUP):
    """Build the identity-weld convert node group (idempotent).

    Reuses an existing group of the same name, rebuilding it in place if it's a
    stale (merge-by-distance) version — so modifiers already bound to that name
    upgrade without rebinding.
    """
    ng = bpy.data.node_groups.get(name)
    if ng is not None:
        if ng.get("cad_convert_version") == CONVERT_VERSION:
            return ng
        ng.nodes.clear()
        ng.links.clear()
        ng.interface.clear()
    else:
        ng = bpy.data.node_groups.new(name, "GeometryNodeTree")

    iface = ng.interface
    iface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    iface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    fill = iface.new_socket("Fill", in_out="INPUT", socket_type="NodeSocketBool")
    fill.default_value = True

    nodes, links = ng.nodes, ng.links
    gi = nodes.new("NodeGroupInput")
    go = nodes.new("NodeGroupOutput")

    # 1. Drop construction curves and degenerate (< 2 point) splines before the
    #    fill so they never become geometry.
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
    links.new(gi.outputs["Geometry"], delete.inputs["Geometry"])
    links.new(drop.outputs["Boolean"], delete.inputs["Selection"])

    # 2. Tessellate to a wire mesh.
    to_mesh = nodes.new("GeometryNodeCurveToMesh")
    links.new(delete.outputs["Geometry"], to_mesh.inputs["Curve"])

    # 3. Weld by identity: merge vertices sharing merge_id, but only true segment
    #    endpoints (valence 1 on the disconnected chains) -- tessellated interior
    #    vertices (valence 2) are excluded, so their interpolated id is harmless.
    merge_id = nodes.new("GeometryNodeInputNamedAttribute")
    merge_id.data_type = "INT"
    merge_id.inputs["Name"].default_value = "merge_id"

    neighbors = nodes.new("GeometryNodeInputMeshVertexNeighbors")
    is_end, end_a = _int_compare(nodes, links, "EQUAL", 1)
    links.new(neighbors.outputs["Vertex Count"], end_a)

    # id 0 means "no weld". Exclude it so a not-yet-computed merge_id (e.g. a
    # transient frame mid-draw) can't collapse every endpoint into one point.
    nonzero, nz_a = _int_compare(nodes, links, "NOT_EQUAL", 0)
    links.new(merge_id.outputs["Attribute"], nz_a)
    weld = nodes.new("FunctionNodeBooleanMath")
    weld.operation = "AND"
    links.new(is_end.outputs["Result"], weld.inputs[0])
    links.new(nonzero.outputs["Result"], weld.inputs[1])

    merge = nodes.new("GeometryNodeMergePoints")
    links.new(to_mesh.outputs["Mesh"], merge.inputs["Geometry"])
    links.new(merge_id.outputs["Attribute"], merge.inputs["Merge ID"])
    links.new(weld.outputs["Boolean"], merge.inputs["Selection"])

    # 4. Back to curves; fill closed loops, or output the wire when Fill is off.
    to_curve = nodes.new("GeometryNodeMeshToCurve")
    links.new(merge.outputs["Geometry"], to_curve.inputs["Mesh"])

    fill_curve = nodes.new("GeometryNodeFillCurve")
    links.new(to_curve.outputs["Curve"], fill_curve.inputs["Curve"])

    switch = nodes.new("GeometryNodeSwitch")
    switch.input_type = "GEOMETRY"
    links.new(gi.outputs["Fill"], switch.inputs["Switch"])
    links.new(to_curve.outputs["Curve"], switch.inputs["False"])
    links.new(fill_curve.outputs["Mesh"], switch.inputs["True"])

    # 5. Derive generated-element identity from persistent source UUIDs and
    #    source-local child indices (never from topology-global Index).
    geometry = add_generated_id_nodes(nodes, links, switch.outputs["Output"])
    links.new(geometry, go.inputs["Geometry"])

    ng["cad_convert_version"] = CONVERT_VERSION
    ng["cad_generated_id_version"] = GENERATED_ID_VERSION
    return ng
