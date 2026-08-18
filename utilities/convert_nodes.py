"""Conversion-node helpers shared by the asset and programmatic paths.

The standard converter remains shared by sketches without user attributes.
Attribute-bearing sketches share a schema-specific variant. Instead of trying to
carry arbitrary fields through every topology-changing node, the variant samples
live values from a Curve-to-Points lookup built from the filtered native source
and writes them onto the final generated geometry. Attribute values therefore
remain native source data and value edits never rebuild the node tree.
"""

import bpy

CONVERT_NODE_GROUP = "CAD Sketcher Convert"
VERTEX_ID_ATTR = "id"
FACE_ID_ATTR = "cad_sketcher_face_id"
SOURCE_CURVE_ID_ATTR = ".cad_sketcher_source_curve_id"
SOURCE_ENDPOINT_ID_ATTR = ".cad_sketcher_source_endpoint_id"

GENERATED_ID_VERSION = 2
CONVERT_VERSION = 12

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


def normalize_attribute_definitions(attribute_definitions):
    """Return stable non-object specs used by the conversion group."""
    specs = []
    for entry in attribute_definitions or ():
        name = str(entry.get("name", "")).strip()
        data_type = str(entry.get("type", "")).upper()
        domain = str(entry.get("domain", "")).upper()
        if not name or domain == "OBJECT":
            continue
        if data_type not in {"BOOLEAN", "INT", "FLOAT"}:
            continue
        if domain not in {"POINT", "CURVE"}:
            continue
        specs.append({"name": name, "type": data_type, "domain": domain})
    specs.sort(key=lambda item: (item["name"], item["domain"], item["type"]))
    return specs


def attribute_signature(specs):
    return repr(tuple((x["name"], x["type"], x["domain"]) for x in specs))


def _transfer_custom_attributes(nodes, links, source_curves, geometry, specs):
    """Sample live source values onto final generated points.

    Curve to Points preserves both native POINT attributes and adapts CURVE-domain
    attributes to its point cloud. Sample Nearest maps every generated point to a
    lookup point, and Sample Index reads the requested value in that lookup's
    POINT domain. This makes the transfer independent of attribute propagation in
    Curve to Mesh, Merge Points, Mesh to Curve, and Fill Curve.
    """
    if not specs:
        return geometry

    lookup = nodes.new("GeometryNodeCurveToPoints")
    lookup.mode = "EVALUATED"
    links.new(source_curves, lookup.inputs["Curve"])
    lookup_points = lookup.outputs["Points"]

    current = geometry
    for entry in specs:
        nearest = nodes.new("GeometryNodeSampleNearest")
        nearest.domain = "POINT"
        links.new(lookup_points, nearest.inputs["Geometry"])

        named = nodes.new("GeometryNodeInputNamedAttribute")
        named.data_type = entry["type"]
        named.inputs["Name"].default_value = entry["name"]

        sample = nodes.new("GeometryNodeSampleIndex")
        sample.data_type = entry["type"]
        sample.domain = "POINT"
        sample.clamp = True
        links.new(lookup_points, sample.inputs["Geometry"])
        links.new(named.outputs["Attribute"], sample.inputs["Value"])
        links.new(nearest.outputs["Index"], sample.inputs["Index"])

        store = nodes.new("GeometryNodeStoreNamedAttribute")
        store.data_type = entry["type"]
        store.domain = "POINT"
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


def build_convert_node_group(
    name: str = CONVERT_NODE_GROUP, attribute_definitions=None
):
    """Build the identity-weld converter, sharing attribute variants by schema."""
    specs = normalize_attribute_definitions(attribute_definitions)
    signature = attribute_signature(specs)

    ng = bpy.data.node_groups.get(name)
    if ng is not None:
        if (
            ng.get("cad_convert_version") == CONVERT_VERSION
            and ng.get("cad_convert_attribute_signature", "") == signature
        ):
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
    filtered_source = delete.outputs["Geometry"]

    to_mesh = nodes.new("GeometryNodeCurveToMesh")
    links.new(filtered_source, to_mesh.inputs["Curve"])

    merge_id = nodes.new("GeometryNodeInputNamedAttribute")
    merge_id.data_type = "INT"
    merge_id.inputs["Name"].default_value = "merge_id"

    neighbors = nodes.new("GeometryNodeInputMeshVertexNeighbors")
    is_end, end_a = _int_compare(nodes, links, "EQUAL", 1)
    links.new(neighbors.outputs["Vertex Count"], end_a)

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

    to_curve = nodes.new("GeometryNodeMeshToCurve")
    links.new(merge.outputs["Geometry"], to_curve.inputs["Mesh"])

    fill_curve = nodes.new("GeometryNodeFillCurve")
    links.new(to_curve.outputs["Curve"], fill_curve.inputs["Curve"])

    switch = nodes.new("GeometryNodeSwitch")
    switch.input_type = "GEOMETRY"
    links.new(gi.outputs["Fill"], switch.inputs["Switch"])
    links.new(to_curve.outputs["Curve"], switch.inputs["False"])
    links.new(fill_curve.outputs["Mesh"], switch.inputs["True"])

    geometry = add_generated_id_nodes(nodes, links, switch.outputs["Output"])
    geometry = _transfer_custom_attributes(
        nodes, links, filtered_source, geometry, specs
    )
    links.new(geometry, go.inputs["Geometry"])

    ng["cad_convert_version"] = CONVERT_VERSION
    ng["cad_generated_id_version"] = GENERATED_ID_VERSION
    ng["cad_convert_attribute_signature"] = signature
    return ng
